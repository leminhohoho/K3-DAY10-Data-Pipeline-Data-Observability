from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Iterable, Sequence
import uuid

import pandas as pd

from core.utils import now_utc, read_json, write_json
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import PaperRecord


REQUIRED_CLEAN_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "published",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "age_days",
    "text_for_embedding",
}

NOISE_TEMPLATES: tuple[str, ...] = (
    " ###@@@ CORRUPTED_TEXT !!! ",
    " [ADVERTISEMENT] click here click here ",
    " <html><body>navigation footer cookie-policy</body></html> ",
    " zxqv zxqv 0000 NULL UNKNOWN ",
    " References References References DOI DOI DOI ",
)

NOISE_MARKERS: tuple[str, ...] = (
    "###@@@",
    "CORRUPTED_TEXT",
    "[ADVERTISEMENT]",
    "<html>",
    "zxqv",
    "cookie-policy",
    "References References",
)

COMPARE_COLUMNS: tuple[str, ...] = (
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
    "summary_chars",
    "age_days",
    "text_for_embedding",
)


@dataclass(frozen=True)
class CorruptionConfig:
    """Configuration for deterministic data-corruption scenarios."""

    drop_latest_fraction: float = 0.10
    blank_summary_fraction: float = 0.10
    noise_fraction: float = 0.10
    truncate_title_fraction: float = 0.10
    stale_date_fraction: float = 0.10
    duplicate_fraction: float = 0.10
    stale_years: int = 5
    minimum_rows_per_scenario: int = 1

    def validate(self) -> None:
        for field_name in (
            "drop_latest_fraction",
            "blank_summary_fraction",
            "noise_fraction",
            "truncate_title_fraction",
            "stale_date_fraction",
            "duplicate_fraction",
        ):
            value = getattr(self, field_name)
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be in [0, 1], received {value}.")
        if self.stale_years < 1:
            raise ValueError("stale_years must be at least 1.")
        if self.minimum_rows_per_scenario < 0:
            raise ValueError("minimum_rows_per_scenario cannot be negative.")


def _require_columns(df: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f"Clean dataframe is missing required columns: {missing}")


def _scenario_count(total_rows: int, fraction: float, minimum: int) -> int:
    if total_rows <= 0 or fraction <= 0:
        return 0
    return min(total_rows, max(minimum, math.ceil(total_rows * fraction)))


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            pass
    return value


def _clean_scalar(value: Any) -> str:
    safe = _json_safe(value)
    return "" if safe is None else str(safe).strip()


def _embedding_text_from_row(row: pd.Series | dict[str, Any]) -> str:
    title = _clean_scalar(row.get("title"))
    summary = _clean_scalar(row.get("summary"))
    authors_joined = _clean_scalar(row.get("authors_joined"))
    categories_joined = _clean_scalar(row.get("categories_joined"))
    published = _clean_scalar(row.get("published"))

    parts = [f"Title: {title}", f"Summary: {summary}"]
    if authors_joined:
        parts.append(f"Authors: {authors_joined}")
    if categories_joined:
        parts.append(f"Categories: {categories_joined}")
    parts.append(f"Published: {published}")
    return "\n".join(parts)


def infer_run_date_from_clean_dataframe(
    df: pd.DataFrame,
    fallback: datetime | None = None,
) -> datetime:
    """Infer the cleaning run date from ``published + age_days``.

    This lets a repair run reproduce the original ``age_days`` values even when
    corruption is executed on a later calendar day.
    """
    if "published" in df.columns and "age_days" in df.columns:
        published = pd.to_datetime(df["published"], errors="coerce", utc=True)
        ages = pd.to_numeric(df["age_days"], errors="coerce")
        candidates = (published + pd.to_timedelta(ages, unit="D")).dropna()
        if not candidates.empty:
            normalized = candidates.dt.normalize()
            mode = normalized.mode()
            chosen = mode.iloc[0] if not mode.empty else normalized.median()
            return pd.Timestamp(chosen).to_pydatetime()

    chosen_fallback = fallback or now_utc()
    timestamp = pd.Timestamp(chosen_fallback)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.normalize().to_pydatetime()


def rebuild_derived_columns(
    df: pd.DataFrame,
    *,
    run_date: datetime | None = None,
) -> pd.DataFrame:
    """Rebuild fields derived from corrupted source columns.

    The embedding text format is intentionally identical to
    ``ingestion.cleaning._embedding_text`` so the three states differ only
    because of data quality, not because of a formatting change.
    """
    _require_columns(
        df,
        {
            "title",
            "summary",
            "published",
            "authors_joined",
            "categories_joined",
        },
    )
    result = df.copy(deep=True)
    effective_run_date = infer_run_date_from_clean_dataframe(result, fallback=run_date)
    run_timestamp = pd.Timestamp(effective_run_date)
    if run_timestamp.tzinfo is None:
        run_timestamp = run_timestamp.tz_localize("UTC")
    else:
        run_timestamp = run_timestamp.tz_convert("UTC")
    run_timestamp = run_timestamp.normalize()

    result["summary"] = result["summary"].fillna("").astype(str)
    result["summary_chars"] = result["summary"].str.len().astype(int)

    published = pd.to_datetime(result["published"], errors="coerce", utc=True)
    result["age_days"] = (run_timestamp - published.dt.normalize()).dt.days.astype("Int64")
    result["text_for_embedding"] = result.apply(_embedding_text_from_row, axis=1)
    return result


def _sample_indices(
    rng: random.Random,
    candidates: Sequence[Any],
    count: int,
    *,
    excluded: set[Any] | None = None,
) -> list[Any]:
    excluded = excluded or set()
    available = [index for index in candidates if index not in excluded]
    if count <= 0 or not available:
        return []
    return rng.sample(available, k=min(count, len(available)))


def _scenario_payload(events: list[dict[str, Any]], scenario: str) -> dict[str, Any]:
    selected = [event for event in events if event["scenario"] == scenario]
    return {
        "count": len(selected),
        "paper_ids": [event["paper_id"] for event in selected],
    }


def corrupt_clean_dataframe(
    df: pd.DataFrame,
    output_log_path: str | Path,
    *,
    config: CorruptionConfig | None = None,
    random_seed: int = 42,
    random_state: int | None = None,
    run_date: datetime | None = None,
) -> pd.DataFrame:
    """Create a deterministic corrupted copy of a clean Crossref dataframe.

    The function never mutates ``df``. It writes one valid JSON corruption log
    to ``output_log_path`` because the starter project config uses a ``.json``
    artifact, not JSONL.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas.DataFrame.")
    if df.empty:
        raise ValueError("Cannot corrupt an empty dataframe.")
    _require_columns(df, REQUIRED_CLEAN_COLUMNS)

    effective_config = config or CorruptionConfig()
    effective_config.validate()
    seed = random_seed if random_state is None else random_state
    rng = random.Random(seed)
    effective_run_date = infer_run_date_from_clean_dataframe(df, fallback=run_date)

    original = df.copy(deep=True)
    corrupted = df.copy(deep=True)
    events: list[dict[str, Any]] = []
    run_id = str(uuid.uuid4())

    def add_event(
        scenario: str,
        *,
        paper_id: Any,
        field: str | None,
        before: Any,
        after: Any,
        source_index: Any,
        note: str | None = None,
    ) -> None:
        events.append(
            {
                "scenario": scenario,
                "paper_id": _clean_scalar(paper_id),
                "field": field,
                "source_index": _json_safe(source_index),
                "before": _json_safe(before),
                "after": _json_safe(after),
                "note": note,
            }
        )

    # 1. Drop the newest records. The evaluation set is also built from newest
    # records, so this scenario is expected to have a measurable retrieval impact.
    published = pd.to_datetime(corrupted["published"], errors="coerce", utc=True)
    latest_indices = published.sort_values(ascending=False, na_position="last").index.tolist()
    drop_count = _scenario_count(
        len(corrupted),
        effective_config.drop_latest_fraction,
        effective_config.minimum_rows_per_scenario,
    )
    drop_indices = latest_indices[:drop_count]
    for index in drop_indices:
        row = corrupted.loc[index]
        add_event(
            "drop_latest_records",
            paper_id=row["paper_id"],
            field=None,
            before={"published": row["published"], "row_present": True},
            after={"row_present": False},
            source_index=index,
        )
    corrupted = corrupted.drop(index=drop_indices).copy()

    used_indices: set[Any] = set()

    # 2. Blank summary.
    summary_candidates = corrupted.index[
        corrupted["summary"].fillna("").astype(str).str.strip().ne("")
    ].tolist()
    blank_indices = _sample_indices(
        rng,
        summary_candidates,
        _scenario_count(
            len(corrupted),
            effective_config.blank_summary_fraction,
            effective_config.minimum_rows_per_scenario,
        ),
        excluded=used_indices,
    )
    for index in blank_indices:
        before = corrupted.at[index, "summary"]
        corrupted.at[index, "summary"] = ""
        used_indices.add(index)
        add_event(
            "blank_summary",
            paper_id=corrupted.at[index, "paper_id"],
            field="summary",
            before=before,
            after="",
            source_index=index,
        )

    # 3. Inject obvious text noise.
    noise_candidates = corrupted.index[
        corrupted["summary"].fillna("").astype(str).str.strip().ne("")
    ].tolist()
    noise_indices = _sample_indices(
        rng,
        noise_candidates,
        _scenario_count(
            len(corrupted),
            effective_config.noise_fraction,
            effective_config.minimum_rows_per_scenario,
        ),
        excluded=used_indices,
    )
    for position, index in enumerate(noise_indices):
        before = str(corrupted.at[index, "summary"])
        noise = NOISE_TEMPLATES[position % len(NOISE_TEMPLATES)]
        insert_at = len(before) // 2
        after = before[:insert_at] + noise + before[insert_at:]
        corrupted.at[index, "summary"] = after
        used_indices.add(index)
        add_event(
            "inject_noise",
            paper_id=corrupted.at[index, "paper_id"],
            field="summary",
            before=before,
            after=after,
            source_index=index,
            note=f"noise_template={noise.strip()}",
        )

    # 4. Truncate titles.
    title_candidates = corrupted.index[
        corrupted["title"].fillna("").astype(str).str.len().ge(12)
    ].tolist()
    truncate_indices = _sample_indices(
        rng,
        title_candidates,
        _scenario_count(
            len(corrupted),
            effective_config.truncate_title_fraction,
            effective_config.minimum_rows_per_scenario,
        ),
        excluded=used_indices,
    )
    for index in truncate_indices:
        before = str(corrupted.at[index, "title"])
        keep_chars = max(8, int(len(before) * 0.35))
        after = before[:keep_chars].rstrip() + "..."
        corrupted.at[index, "title"] = after
        used_indices.add(index)
        add_event(
            "truncate_title",
            paper_id=corrupted.at[index, "paper_id"],
            field="title",
            before=before,
            after=after,
            source_index=index,
        )

    # 5. Shift publication dates backwards.
    valid_date_indices = pd.to_datetime(
        corrupted["published"], errors="coerce", utc=True
    ).dropna().index.tolist()
    stale_indices = _sample_indices(
        rng,
        valid_date_indices,
        _scenario_count(
            len(corrupted),
            effective_config.stale_date_fraction,
            effective_config.minimum_rows_per_scenario,
        ),
        excluded=used_indices,
    )
    for index in stale_indices:
        before = corrupted.at[index, "published"]
        parsed = pd.to_datetime(before, errors="coerce", utc=True)
        if pd.isna(parsed):
            continue
        after = (parsed - pd.DateOffset(years=effective_config.stale_years)).date().isoformat()
        corrupted.at[index, "published"] = after
        used_indices.add(index)
        add_event(
            "stale_published_date",
            paper_id=corrupted.at[index, "paper_id"],
            field="published",
            before=before,
            after=after,
            source_index=index,
            note=f"shifted_back_years={effective_config.stale_years}",
        )

    # Rebuild derived columns before copying duplicate rows so duplicates are
    # internally consistent copies of their corrupted source rows.
    corrupted = rebuild_derived_columns(corrupted, run_date=effective_run_date)

    # 6. Duplicate rows. Index IDs remain unique because retrieval/index.py uses
    # paper_id plus row index as Chroma record_id.
    duplicate_indices = _sample_indices(
        rng,
        corrupted.index.tolist(),
        _scenario_count(
            len(corrupted),
            effective_config.duplicate_fraction,
            effective_config.minimum_rows_per_scenario,
        ),
    )
    duplicate_frames: list[pd.DataFrame] = []
    for index in duplicate_indices:
        row = corrupted.loc[index]
        duplicate_frames.append(corrupted.loc[[index]].copy(deep=True))
        add_event(
            "duplicate_rows",
            paper_id=row["paper_id"],
            field=None,
            before={"copies": 1},
            after={"copies": 2},
            source_index=index,
        )

    if duplicate_frames:
        corrupted = pd.concat([corrupted, *duplicate_frames], ignore_index=True)
    else:
        corrupted = corrupted.reset_index(drop=True)

    # A final rebuild guarantees every row has current derived values.
    corrupted = rebuild_derived_columns(corrupted, run_date=effective_run_date)

    scenario_names = (
        "drop_latest_records",
        "blank_summary",
        "inject_noise",
        "truncate_title",
        "stale_published_date",
        "duplicate_rows",
    )
    log_payload: dict[str, Any] = {
        "run_id": run_id,
        "created_at_utc": now_utc().isoformat(),
        "random_seed": seed,
        "run_date_utc": effective_run_date.isoformat(),
        "input_row_count": int(len(original)),
        "output_row_count": int(len(corrupted)),
        "config": asdict(effective_config),
        "scenarios": {
            scenario: _scenario_payload(events, scenario) for scenario in scenario_names
        },
        "events": events,
    }
    write_json(Path(output_log_path), log_payload)

    corrupted.attrs["corruption_log"] = log_payload
    corrupted.attrs["corruption_log_path"] = str(output_log_path)
    return corrupted


def _load_log(log_or_path: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(log_or_path, dict):
        return log_or_path
    payload = read_json(Path(log_or_path))
    if not isinstance(payload, dict):
        raise ValueError("Corruption log must be a JSON object.")
    return payload


def _rows_for_paper(df: pd.DataFrame, paper_id: str) -> pd.DataFrame:
    if "paper_id" not in df.columns:
        return df.iloc[0:0]
    return df[df["paper_id"].fillna("").astype(str).str.casefold() == paper_id.casefold()]


def _derived_column_validation(df: pd.DataFrame, run_date: datetime) -> dict[str, Any]:
    expected = rebuild_derived_columns(df, run_date=run_date)

    summary_actual = pd.to_numeric(df["summary_chars"], errors="coerce").astype("Int64")
    summary_expected = pd.to_numeric(expected["summary_chars"], errors="coerce").astype("Int64")
    summary_mismatch = int((summary_actual != summary_expected).fillna(True).sum())

    age_actual = pd.to_numeric(df["age_days"], errors="coerce").astype("Int64")
    age_expected = pd.to_numeric(expected["age_days"], errors="coerce").astype("Int64")
    age_mismatch = int((age_actual != age_expected).fillna(True).sum())

    embedding_actual = df["text_for_embedding"].fillna("").astype(str)
    embedding_expected = expected["text_for_embedding"].fillna("").astype(str)
    embedding_mismatch = int((embedding_actual != embedding_expected).sum())

    return {
        "summary_chars_consistent": summary_mismatch == 0,
        "summary_chars_mismatch_rows": summary_mismatch,
        "age_days_consistent": age_mismatch == 0,
        "age_days_mismatch_rows": age_mismatch,
        "text_for_embedding_consistent": embedding_mismatch == 0,
        "text_for_embedding_mismatch_rows": embedding_mismatch,
    }


def validate_corrupted_dataframe(
    baseline_df: pd.DataFrame,
    corrupted_df: pd.DataFrame,
    corruption_log: dict[str, Any] | str | Path,
) -> dict[str, Any]:
    """Verify that every logged corruption scenario is visible in the data."""
    _require_columns(baseline_df, REQUIRED_CLEAN_COLUMNS)
    _require_columns(corrupted_df, REQUIRED_CLEAN_COLUMNS)
    log = _load_log(corruption_log)
    scenarios = log.get("scenarios", {})

    dropped_ids = scenarios.get("drop_latest_records", {}).get("paper_ids", [])
    blank_ids = scenarios.get("blank_summary", {}).get("paper_ids", [])
    noisy_ids = scenarios.get("inject_noise", {}).get("paper_ids", [])
    truncated_ids = scenarios.get("truncate_title", {}).get("paper_ids", [])
    stale_ids = scenarios.get("stale_published_date", {}).get("paper_ids", [])
    duplicate_ids = scenarios.get("duplicate_rows", {}).get("paper_ids", [])

    dropped_ok = all(_rows_for_paper(corrupted_df, paper_id).empty for paper_id in dropped_ids)
    blank_ok = all(
        not _rows_for_paper(corrupted_df, paper_id).empty
        and _rows_for_paper(corrupted_df, paper_id)["summary"].fillna("").astype(str).eq("").all()
        and pd.to_numeric(
            _rows_for_paper(corrupted_df, paper_id)["summary_chars"], errors="coerce"
        ).fillna(-1).eq(0).all()
        for paper_id in blank_ids
    )
    noise_ok = all(
        not _rows_for_paper(corrupted_df, paper_id).empty
        and _rows_for_paper(corrupted_df, paper_id)["summary"]
        .fillna("")
        .astype(str)
        .map(lambda text: any(marker in text for marker in NOISE_MARKERS))
        .all()
        for paper_id in noisy_ids
    )
    truncated_ok = all(
        not _rows_for_paper(corrupted_df, paper_id).empty
        and _rows_for_paper(corrupted_df, paper_id)["title"]
        .fillna("")
        .astype(str)
        .str.endswith("...")
        .all()
        for paper_id in truncated_ids
    )

    stale_event_after = {
        event["paper_id"]: event.get("after")
        for event in log.get("events", [])
        if event.get("scenario") == "stale_published_date"
    }
    stale_ok = all(
        not _rows_for_paper(corrupted_df, paper_id).empty
        and _rows_for_paper(corrupted_df, paper_id)["published"]
        .fillna("")
        .astype(str)
        .eq(str(stale_event_after.get(paper_id, "")))
        .all()
        for paper_id in stale_ids
    )
    duplicate_ok = all(len(_rows_for_paper(corrupted_df, paper_id)) >= 2 for paper_id in duplicate_ids)

    expected_rows = (
        int(log.get("input_row_count", len(baseline_df)))
        - len(dropped_ids)
        + len(duplicate_ids)
    )
    row_count_ok = len(corrupted_df) == expected_rows

    run_date = pd.to_datetime(log.get("run_date_utc"), errors="coerce", utc=True)
    if pd.isna(run_date):
        run_date_value = infer_run_date_from_clean_dataframe(baseline_df)
    else:
        run_date_value = pd.Timestamp(run_date).to_pydatetime()
    derived = _derived_column_validation(corrupted_df, run_date_value)

    scenario_checks = {
        "drop_latest_records_detected": dropped_ok,
        "blank_summary_detected": blank_ok,
        "noise_detected": noise_ok,
        "truncated_title_detected": truncated_ok,
        "stale_date_detected": stale_ok,
        "duplicate_rows_detected": duplicate_ok,
        "row_count_matches_log": row_count_ok,
    }
    valid = all(scenario_checks.values()) and all(
        value for key, value in derived.items() if key.endswith("_consistent")
    )
    return {
        "validation_type": "corrupted_dataset",
        "validated_at_utc": now_utc().isoformat(),
        "scenario_checks": scenario_checks,
        "derived_column_checks": derived,
        "expected_row_count": expected_rows,
        "actual_row_count": int(len(corrupted_df)),
        "corruption_valid": valid,
    }


def repair_from_raw_records(
    raw_records: list[PaperRecord],
    reference_clean_df: pd.DataFrame,
    *,
    run_date: datetime | None = None,
) -> pd.DataFrame:
    """Repair by rebuilding from the immutable raw Crossref artifact."""
    if not isinstance(raw_records, list):
        raise TypeError("raw_records must be a list of PaperRecord objects.")
    _require_columns(reference_clean_df, REQUIRED_CLEAN_COLUMNS)
    effective_run_date = run_date or infer_run_date_from_clean_dataframe(reference_clean_df)
    return build_clean_dataframe(raw_records, run_date=effective_run_date)


def _canonical_cell(value: Any) -> str:
    safe = _json_safe(value)
    if isinstance(safe, (list, dict)):
        return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "" if safe is None else str(safe).strip()


def _dataframe_digest(df: pd.DataFrame, compare_columns: Sequence[str]) -> str:
    available = [column for column in compare_columns if column in df.columns]
    normalized = df[available].copy()
    if "paper_id" in normalized.columns:
        normalized["paper_id"] = normalized["paper_id"].map(_canonical_cell).str.casefold()
        normalized = normalized.sort_values("paper_id", kind="stable").reset_index(drop=True)
    for column in available:
        normalized[column] = normalized[column].map(_canonical_cell)
    payload = normalized.to_dict(orient="records")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_repaired_dataframe(
    repaired_df: pd.DataFrame,
    reference_clean_df: pd.DataFrame,
    *,
    compare_columns: Sequence[str] = COMPARE_COLUMNS,
) -> dict[str, Any]:
    """Validate that repair restored the clean baseline contract and content."""
    _require_columns(repaired_df, REQUIRED_CLEAN_COLUMNS)
    _require_columns(reference_clean_df, REQUIRED_CLEAN_COLUMNS)

    repaired_ids = repaired_df["paper_id"].fillna("").astype(str).str.casefold()
    reference_ids = reference_clean_df["paper_id"].fillna("").astype(str).str.casefold()
    repaired_id_set = set(repaired_ids)
    reference_id_set = set(reference_ids)

    repaired_digest = _dataframe_digest(repaired_df, compare_columns)
    reference_digest = _dataframe_digest(reference_clean_df, compare_columns)
    run_date = infer_run_date_from_clean_dataframe(reference_clean_df)
    derived = _derived_column_validation(repaired_df, run_date)

    noisy_rows = int(
        repaired_df["summary"]
        .fillna("")
        .astype(str)
        .map(lambda text: any(marker in text for marker in NOISE_MARKERS))
        .sum()
    )
    truncated_rows = int(
        repaired_df["title"].fillna("").astype(str).str.endswith("...").sum()
    )
    duplicate_rows = int(repaired_ids.duplicated(keep=False).sum())

    checks = {
        "row_count_match": len(repaired_df) == len(reference_clean_df),
        "paper_id_set_match": repaired_id_set == reference_id_set,
        "paper_id_unique": duplicate_rows == 0,
        "content_digest_match": repaired_digest == reference_digest,
        "no_corruption_noise": noisy_rows == 0,
        "no_truncated_titles": truncated_rows == 0,
        "summary_chars_consistent": derived["summary_chars_consistent"],
        "age_days_consistent": derived["age_days_consistent"],
        "text_for_embedding_consistent": derived["text_for_embedding_consistent"],
    }
    return {
        "validation_type": "repaired_dataset",
        "validated_at_utc": now_utc().isoformat(),
        "checks": checks,
        "missing_paper_ids": sorted(reference_id_set - repaired_id_set),
        "unexpected_paper_ids": sorted(repaired_id_set - reference_id_set),
        "duplicate_rows": duplicate_rows,
        "noisy_summary_rows": noisy_rows,
        "truncated_title_rows": truncated_rows,
        "repaired_digest": repaired_digest,
        "reference_digest": reference_digest,
        "repair_valid": all(checks.values()),
    }


# Backward-compatible name used in earlier drafts.
def validate_repair(
    repaired_df: pd.DataFrame,
    reference_clean_df: pd.DataFrame,
    *,
    compare_columns: Sequence[str] = COMPARE_COLUMNS,
) -> dict[str, Any]:
    return validate_repaired_dataframe(
        repaired_df,
        reference_clean_df,
        compare_columns=compare_columns,
    )
