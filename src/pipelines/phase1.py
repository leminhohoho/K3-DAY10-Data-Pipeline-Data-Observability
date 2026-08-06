from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import time
from typing import Any

import pandas as pd

from core.config import Settings, load_settings, normalized_provider, require_llm_credentials
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import EvaluationBundle, evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import PaperRecord, fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


_REQUIRED_CLEAN_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "published",
    "age_days",
    "text_for_embedding",
    "abs_url",
    "pdf_url",
}
_REQUIRED_TESTSET_KEYS = {
    "id",
    "question_type",
    "question",
    "ground_truth",
    "ground_truth_doc_ids",
}
# Free-tier LLM endpoints throttle aggressively; the agent demo retries the
# transient statuses instead of losing the evidence artifact to one 429.
_AGENT_RETRY_ATTEMPTS = 3
_AGENT_RETRY_BACKOFF_SECONDS = 15.0
_AGENT_RETRY_MAX_DELAY_SECONDS = 60.0
_RETRYABLE_ERROR_MARKERS = (
    "429",
    "RESOURCE_EXHAUSTED",
    "500",
    "INTERNAL",
    "503",
    "UNAVAILABLE",
    "504",
    "DEADLINE_EXCEEDED",
)


def _dataframe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Return JSON-safe records without leaking pandas/numpy scalar types."""
    return json.loads(df.to_json(orient="records", force_ascii=False, date_format="iso"))


def _load_or_fetch_records(settings: Settings) -> tuple[list[PaperRecord], str]:
    paths = settings.paths
    must_fetch = (
        settings.refresh_source
        or not paths.raw_api_response.exists()
        or not paths.raw_records_json.exists()
    )
    if must_fetch:
        records = fetch_source_records(settings)
        source_mode = "fetched"
    else:
        records = load_raw_records(paths.raw_records_json)
        source_mode = "cached_raw_snapshot"

    if not records:
        raise RuntimeError("No usable raw records are available for the baseline pipeline.")
    return records, source_mode


def _validate_clean_dataframe(df: pd.DataFrame) -> None:
    missing_columns = sorted(_REQUIRED_CLEAN_COLUMNS - set(df.columns))
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing required columns: {missing_columns}")
    if df.empty:
        raise ValueError("Cleaning produced an empty dataframe.")

    paper_ids = df["paper_id"].fillna("").astype(str).str.strip()
    if paper_ids.eq("").any():
        raise ValueError("Clean dataframe contains empty paper_id values.")
    if paper_ids.duplicated().any():
        duplicated = sorted(paper_ids[paper_ids.duplicated(keep=False)].unique().tolist())
        raise ValueError(f"Clean dataframe contains duplicated paper_id values: {duplicated}")

    embedding_text = df["text_for_embedding"].fillna("").astype(str).str.strip()
    if embedding_text.eq("").any():
        raise ValueError("Clean dataframe contains empty text_for_embedding values.")


def _validate_test_set(test_set: Any, corpus_ids: set[str]) -> list[dict[str, Any]]:
    if not isinstance(test_set, list) or not test_set:
        raise ValueError("Evaluation test set must be a non-empty JSON list.")

    missing_ground_truth_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for position, item in enumerate(test_set, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Test-set item {position} is not an object.")
        missing_keys = sorted(_REQUIRED_TESTSET_KEYS - set(item))
        if missing_keys:
            raise ValueError(f"Test-set item {position} is missing keys: {missing_keys}")
        ground_truth_ids = item.get("ground_truth_doc_ids")
        if not isinstance(ground_truth_ids, list) or not ground_truth_ids:
            raise ValueError(
                f"Test-set item {position} must contain non-empty ground_truth_doc_ids."
            )
        missing_ground_truth_ids.update(
            str(doc_id) for doc_id in ground_truth_ids if str(doc_id) not in corpus_ids
        )
        validated.append(item)

    if missing_ground_truth_ids:
        raise ValueError(
            "Evaluation set references document IDs missing from the clean corpus: "
            f"{sorted(missing_ground_truth_ids)}. Set REFRESH_TEST_SET=1 after refreshing the source."
        )
    return validated


def _load_or_build_test_set(
    settings: Settings,
    clean_df: pd.DataFrame,
) -> tuple[list[dict[str, Any]], str]:
    path = settings.paths.eval_testset
    should_build = (
        settings.refresh_test_set
        or settings.refresh_source
        or not path.exists()
    )
    if should_build:
        test_set = build_test_set(clean_df, path)
        mode = "built"
    else:
        test_set = read_json(path)
        mode = "cached"

    corpus_ids = set(clean_df["paper_id"].astype(str))
    return _validate_test_set(test_set, corpus_ids), mode


def _agent_credentials_status(settings: Settings) -> tuple[bool, str | None]:
    """Report whether the configured provider can back the LangChain agent."""
    try:
        require_llm_credentials(settings)
    except RuntimeError as error:
        return False, str(error)
    return True, None


def _normalize_agent_text(value: Any) -> str:
    """Flatten a LangChain message payload, which may be text or content blocks."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for block in value:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(part for part in parts if part).strip()
    return str(value).strip()


def _retry_delay_seconds(error: Exception, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None when the failure is permanent."""
    message = str(error)
    if not any(marker in message for marker in _RETRYABLE_ERROR_MARKERS):
        return None
    hinted = re.search(r"'retryDelay': '(\d+(?:\.\d+)?)s'", message)
    delay = float(hinted.group(1)) + 1.0 if hinted else _AGENT_RETRY_BACKOFF_SECONDS * attempt
    return min(delay, _AGENT_RETRY_MAX_DELAY_SECONDS)


def _run_agent_question(agent: Any, question: str) -> tuple[str | None, str | None]:
    """Return (answer, error) for one agent question, retrying transient failures."""
    last_error: Exception | None = None
    for attempt in range(1, _AGENT_RETRY_ATTEMPTS + 1):
        try:
            return _normalize_agent_text(run_agent_question(agent, question)), None
        except Exception as error:
            last_error = error
            delay = _retry_delay_seconds(error, attempt)
            if delay is None or attempt == _AGENT_RETRY_ATTEMPTS:
                break
            time.sleep(delay)
    return None, f"{type(last_error).__name__}: {last_error}"


def _build_demo_answers(
    settings: Settings,
    index: LocalEmbeddingIndex,
    test_set: list[dict[str, Any]],
    limit: int = 4,
) -> dict[str, Any]:
    """Answer sample questions twice: deterministic retrieval, then the LLM agent.

    The deterministic pass always runs so the artifact exists even without
    credentials. The agent pass is the evidence that the multi-provider
    LangChain agent can reach the same corpus through its tools; it degrades to
    a recorded status instead of failing the pipeline, because every baseline
    artifact has already been written by the time it runs.
    """
    samples: list[dict[str, Any]] = []
    for item in test_set[:limit]:
        result = answer_question(item["question"], settings=settings, index=index)
        samples.append(
            {
                "id": item["id"],
                "question_type": item["question_type"],
                "question": item["question"],
                "retrieval_answer": result.answer,
                "retrieved_doc_ids": result.retrieved_doc_ids,
                "retrieved_titles": result.retrieved_titles,
                "agent_answer": None,
                "agent_error": None,
            }
        )

    has_credentials, note = _agent_credentials_status(settings)
    if not has_credentials:
        status = "skipped"
    else:
        try:
            agent = build_agent(settings=settings, index=index)
        except Exception as error:  # provider/SDK misconfiguration
            status = "skipped"
            note = f"Agent construction failed: {type(error).__name__}: {error}"
        else:
            failures = 0
            for sample in samples:
                answer, error = _run_agent_question(agent, sample["question"])
                sample["agent_answer"] = answer
                sample["agent_error"] = error
                if error is not None:
                    failures += 1
            if failures == 0:
                status = "ok"
            elif failures < len(samples):
                status = "partial"
            else:
                status = "failed"
            if failures:
                note = f"{failures}/{len(samples)} agent questions failed."

    return {
        "generated_at": now_utc().isoformat(),
        "collection_name": index.collection_name,
        "llm_provider": normalized_provider(settings),
        "llm_model": settings.model_name,
        "agent_tools": ["semantic_search_papers", "lookup_paper"],
        "agent_status": status,
        "agent_note": note,
        "samples": samples,
    }


def _write_run_summary(
    settings: Settings,
    *,
    run_started_at: datetime,
    source_mode: str,
    test_set_mode: str,
    raw_record_count: int,
    clean_row_count: int,
    evaluation: EvaluationBundle,
    quality: dict[str, Any],
    freshness: dict[str, Any],
    demo: dict[str, Any],
) -> Path:
    output_path = settings.paths.baseline_metrics.parent / "phase1_run_summary.json"
    payload = {
        "pipeline": "phase1_baseline",
        "started_at": run_started_at.isoformat(),
        "completed_at": now_utc().isoformat(),
        "source_mode": source_mode,
        "test_set_mode": test_set_mode,
        "raw_record_count": raw_record_count,
        "clean_row_count": clean_row_count,
        "collection_name": settings.baseline_collection_name,
        "embedding_model": settings.embedding_model,
        "llm_provider": demo.get("llm_provider"),
        "llm_model": demo.get("llm_model"),
        "agent_status": demo.get("agent_status"),
        "agent_note": demo.get("agent_note"),
        "top_k": settings.top_k,
        "metrics": evaluation.summary,
        "quality_overall": quality.get("overall"),
        "freshness_is_fresh": freshness.get("is_fresh"),
        "artifacts": {
            "raw_api_response": str(settings.paths.raw_api_response),
            "raw_records": str(settings.paths.raw_records_json),
            "clean_csv": str(settings.paths.clean_csv),
            "clean_json": str(settings.paths.clean_json),
            "embedding_manifest": str(settings.paths.embeddings_json),
            "test_set": str(settings.paths.eval_testset),
            "metrics": str(settings.paths.baseline_metrics),
            "answers": str(settings.paths.baseline_answers),
            "demo_answers": str(settings.paths.demo_answers),
            "freshness": str(settings.paths.freshness_report),
            "report": str(settings.paths.baseline_report),
        },
    }
    write_json(output_path, payload)
    return output_path


def main() -> None:
    """Run the clean baseline pipeline end to end and persist its evidence."""
    run_started_at = now_utc()
    settings = load_settings()
    paths = settings.paths

    records, source_mode = _load_or_fetch_records(settings)
    clean_df = build_clean_dataframe(records, run_date=run_started_at)
    _validate_clean_dataframe(clean_df)

    write_csv(clean_df, paths.clean_csv)
    write_json(paths.clean_json, _dataframe_records(clean_df))

    index = LocalEmbeddingIndex.build(
        clean_df,
        settings=settings,
        embeddings_output_path=paths.embeddings_json,
    )

    test_set, test_set_mode = _load_or_build_test_set(settings, clean_df)
    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=paths.eval_testset,
        metrics_output_path=paths.baseline_metrics,
        answers_output_path=paths.baseline_answers,
    )

    quality = run_data_quality_checks(clean_df, settings, report_name="baseline")
    freshness = build_freshness_report(clean_df, settings, paths.freshness_report)

    demo = _build_demo_answers(settings, index, test_set)
    write_json(paths.demo_answers, demo)

    source_summary = {
        "source_api": settings.source_api,
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "source_mode": source_mode,
        "raw_records": len(records),
        "clean_rows": len(clean_df),
        "embedding_model": settings.embedding_model,
        "collection_name": index.collection_name,
        "top_k": settings.top_k,
        "llm_provider": demo["llm_provider"],
        "llm_model": demo["llm_model"],
        "agent_demo_status": demo["agent_status"],
        # Relative so the committed report stays machine-independent.
        "agent_demo_artifact": paths.demo_answers.relative_to(paths.project_dir).as_posix(),
        "run_started_at": run_started_at.isoformat(),
    }
    generate_phase1_report(
        paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )

    summary_path = _write_run_summary(
        settings,
        run_started_at=run_started_at,
        source_mode=source_mode,
        test_set_mode=test_set_mode,
        raw_record_count=len(records),
        clean_row_count=len(clean_df),
        evaluation=evaluation,
        quality=quality,
        freshness=freshness,
        demo=demo,
    )

    print("Phase 1 baseline pipeline completed.")
    print(f"- Clean rows: {len(clean_df)}")
    print(f"- Test samples: {len(test_set)}")
    print(f"- Collection: {index.collection_name}")
    print(f"- Agent demo: {demo['agent_status']} ({demo['llm_provider']}/{demo['llm_model']})")
    if demo["agent_note"]:
        print(f"  note: {demo['agent_note']}")
    print(f"- Metrics: {paths.baseline_metrics}")
    print(f"- Report: {paths.baseline_report}")
    print(f"- Run summary: {summary_path}")


if __name__ == "__main__":
    main()
