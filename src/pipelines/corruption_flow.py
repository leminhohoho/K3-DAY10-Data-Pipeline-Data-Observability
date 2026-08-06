from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import read_json, write_csv, write_json
from ingestion.corruption import (
    CorruptionConfig,
    corrupt_clean_dataframe,
    infer_run_date_from_clean_dataframe,
    repair_from_raw_records,
    validate_corrupted_dataframe,
    validate_repaired_dataframe,
)
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report


def _require_artifact(path: Path, description: str) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {description}: {path}. Run the Phase 1 baseline pipeline first."
        )


def _load_clean_dataframe(settings: Settings) -> pd.DataFrame:
    """Load baseline clean data, preferring JSON to preserve list columns."""
    if settings.paths.clean_json.exists():
        payload = read_json(settings.paths.clean_json)
        if not isinstance(payload, list):
            raise ValueError(f"Expected a list in {settings.paths.clean_json}.")
        dataframe = pd.DataFrame(payload)
    elif settings.paths.clean_csv.exists():
        dataframe = pd.read_csv(settings.paths.clean_csv)
    else:
        raise FileNotFoundError(
            "Missing clean baseline artifacts. Expected one of: "
            f"{settings.paths.clean_json} or {settings.paths.clean_csv}. "
            "Run Phase 1 first."
        )

    if dataframe.empty:
        raise ValueError(
            "The clean baseline dataframe is empty. Check raw publication dates and "
            "the cleaning run date before running the corruption flow."
        )
    return dataframe


def _records_payload(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert pandas/numpy values into JSON-safe Python values."""
    return json.loads(df.to_json(orient="records", force_ascii=False, date_format="iso"))


def _save_clean_state(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    write_csv(df, csv_path)
    write_json(json_path, _records_payload(df))


def run_corruption_flow(
    settings: Settings | None = None,
    *,
    config: CorruptionConfig | None = None,
    random_seed: int = 42,
) -> dict[str, Any]:
    """Run corruption -> evaluate -> repair -> evaluate -> compare.

    The same Phase 1 evaluation set is reused for both corrupted and repaired
    states. Repair is rebuilt from ``data/raw/crossref_records.json``.
    """
    effective_settings = settings or load_settings()

    # Heavy RAG dependencies are imported lazily so corruption/repair unit tests
    # can run without loading Chroma, sentence-transformers, datasets, or an LLM.
    from evaluation.metrics import evaluate_pipeline
    from retrieval.index import LocalEmbeddingIndex

    _require_artifact(effective_settings.paths.eval_testset, "evaluation test set")
    _require_artifact(effective_settings.paths.baseline_metrics, "baseline metrics")
    _require_artifact(effective_settings.paths.raw_records_json, "raw Crossref records")

    baseline_df = _load_clean_dataframe(effective_settings)
    baseline_metrics = read_json(effective_settings.paths.baseline_metrics)
    if not isinstance(baseline_metrics, dict):
        raise ValueError(
            f"Expected a metrics object in {effective_settings.paths.baseline_metrics}."
        )

    run_date = infer_run_date_from_clean_dataframe(baseline_df)

    # Baseline observability is recomputed with the same check implementation so
    # the comparison table is methodologically consistent.
    baseline_quality = run_data_quality_checks(
        baseline_df,
        effective_settings,
        report_name="baseline-for-corruption-comparison",
    )
    baseline_freshness = build_freshness_report(
        baseline_df,
        effective_settings,
        effective_settings.paths.quality_dir / "freshness_baseline_comparison.json",
    )

    # ------------------------------------------------------------------
    # Corrupted state
    # ------------------------------------------------------------------
    corrupted_df = corrupt_clean_dataframe(
        baseline_df,
        effective_settings.paths.corruption_log,
        config=config,
        random_seed=random_seed,
        run_date=run_date,
    )
    _save_clean_state(
        corrupted_df,
        effective_settings.paths.corrupted_clean_csv,
        effective_settings.paths.corrupted_clean_json,
    )

    corruption_log = read_json(effective_settings.paths.corruption_log)
    corrupted_validation = validate_corrupted_dataframe(
        baseline_df,
        corrupted_df,
        corruption_log,
    )
    corrupted_validation_path = (
        effective_settings.paths.quality_dir / "corrupted_dataset_validation.json"
    )
    write_json(corrupted_validation_path, corrupted_validation)

    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        effective_settings,
        effective_settings.paths.corrupted_embeddings_json,
    )
    corrupted_evaluation = evaluate_pipeline(
        settings=effective_settings,
        index=corrupted_index,
        test_set_path=effective_settings.paths.eval_testset,
        metrics_output_path=effective_settings.paths.corrupted_metrics,
        answers_output_path=effective_settings.paths.corrupted_answers,
    )
    corrupted_quality = run_data_quality_checks(
        corrupted_df,
        effective_settings,
        report_name="corrupted",
    )
    corrupted_freshness = build_freshness_report(
        corrupted_df,
        effective_settings,
        effective_settings.paths.quality_dir / "freshness_corrupted.json",
    )

    # ------------------------------------------------------------------
    # Repaired state: reconstruct from raw artifact, never patch bad rows.
    # ------------------------------------------------------------------
    raw_records = load_raw_records(effective_settings.paths.raw_records_json)
    repaired_df = repair_from_raw_records(
        raw_records,
        reference_clean_df=baseline_df,
        run_date=run_date,
    )
    _save_clean_state(
        repaired_df,
        effective_settings.paths.repaired_clean_csv,
        effective_settings.paths.repaired_clean_json,
    )

    repaired_validation = validate_repaired_dataframe(repaired_df, baseline_df)
    repaired_validation_path = (
        effective_settings.paths.quality_dir / "repaired_dataset_validation.json"
    )
    write_json(repaired_validation_path, repaired_validation)

    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        effective_settings,
        effective_settings.paths.repaired_embeddings_json,
    )
    repaired_evaluation = evaluate_pipeline(
        settings=effective_settings,
        index=repaired_index,
        test_set_path=effective_settings.paths.eval_testset,
        metrics_output_path=effective_settings.paths.repaired_metrics,
        answers_output_path=effective_settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(
        repaired_df,
        effective_settings,
        report_name="repaired",
    )
    repaired_freshness = build_freshness_report(
        repaired_df,
        effective_settings,
        effective_settings.paths.quality_dir / "freshness_repaired.json",
    )

    generate_corruption_report(
        report_path=effective_settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_evaluation.summary,
        repaired_metrics=repaired_evaluation.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
        baseline_quality=baseline_quality,
        baseline_freshness=baseline_freshness,
        corruption_log=corruption_log,
        corrupted_validation=corrupted_validation,
        repaired_validation=repaired_validation,
    )

    result = {
        "baseline_rows": int(len(baseline_df)),
        "corrupted_rows": int(len(corrupted_df)),
        "repaired_rows": int(len(repaired_df)),
        "corruption_valid": corrupted_validation["corruption_valid"],
        "repair_valid": repaired_validation["repair_valid"],
        "baseline_metrics": baseline_metrics,
        "corrupted_metrics": corrupted_evaluation.summary,
        "repaired_metrics": repaired_evaluation.summary,
        "artifacts": {
            "corruption_log": str(effective_settings.paths.corruption_log),
            "corrupted_clean_json": str(effective_settings.paths.corrupted_clean_json),
            "repaired_clean_json": str(effective_settings.paths.repaired_clean_json),
            "corrupted_validation": str(corrupted_validation_path),
            "repaired_validation": str(repaired_validation_path),
            "comparison_report": str(effective_settings.paths.comparison_report),
        },
    }

    # Persisted counterpart of `phase1_run_summary.json`: one machine-readable
    # file tying the three states, their metrics and their validations together,
    # so report claims can be diffed against artifacts without re-running.
    run_summary_path = (
        effective_settings.paths.baseline_metrics.parent / "corruption_run_summary.json"
    )
    write_json(run_summary_path, result)
    result["artifacts"]["run_summary"] = str(run_summary_path)

    if not corrupted_validation["corruption_valid"]:
        raise RuntimeError(
            f"Corrupted dataset validation failed. See {corrupted_validation_path}."
        )
    if not repaired_validation["repair_valid"]:
        raise RuntimeError(
            f"Repaired dataset validation failed. See {repaired_validation_path}."
        )
    return result


def main() -> None:
    result = run_corruption_flow()
    print("Corruption flow completed successfully.")
    print(f"Baseline rows: {result['baseline_rows']}")
    print(f"Corrupted rows: {result['corrupted_rows']}")
    print(f"Repaired rows: {result['repaired_rows']}")
    print(f"Corruption valid: {result['corruption_valid']}")
    print(f"Repair valid: {result['repair_valid']}")
    print(f"Comparison report: {result['artifacts']['comparison_report']}")
    print(f"Run summary: {result['artifacts']['run_summary']}")


if __name__ == "__main__":
    main()
