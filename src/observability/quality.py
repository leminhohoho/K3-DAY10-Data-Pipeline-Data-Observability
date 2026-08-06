from __future__ import annotations

from datetime import UTC
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import now_utc, safe_slug, write_json
from ingestion.corruption import (
    NOISE_MARKERS,
    infer_run_date_from_clean_dataframe,
    rebuild_derived_columns,
)


def _present_count(df: pd.DataFrame, column: str) -> int:
    if column not in df.columns:
        return 0
    mask = df[column].notna()
    return int(df.loc[mask, column].astype(str).str.strip().ne("").sum(skipna=True))


def _record_coverage_check(
    df: pd.DataFrame,
    expected_paper_ids: set[str],
) -> dict[str, Any]:
    """Detect missing records directly: which expected paper_ids are absent.

    ``row_count`` only proves the corpus is non-empty; a dropped-records
    corruption still passes it. This check compares the corpus against the set
    of paper_ids it is supposed to contain (typically the clean baseline), so a
    ``drop_latest_records`` scenario surfaces as a quality failure instead of
    silently shrinking the corpus.
    """
    expected = {str(paper_id).strip().casefold() for paper_id in expected_paper_ids if str(paper_id).strip()}
    if "paper_id" in df.columns:
        present = {
            value
            for value in df["paper_id"].fillna("").astype(str).str.strip().str.casefold()
            if value
        }
    else:
        present = set()
    missing = sorted(expected - present)
    return {
        "status": "pass" if not missing else "fail",
        "value": len(expected & present),
        "detail": f"{len(missing)}/{len(expected)} expected paper_ids missing from corpus"
        + (f": {', '.join(missing[:8])}" if missing else ""),
    }


def _not_null_check(df: pd.DataFrame, column: str, total: int) -> dict[str, Any]:
    present = _present_count(df, column)
    missing = total - present
    return {
        "status": "pass" if missing == 0 else "fail",
        "value": present,
        "detail": f"{missing}/{total} rows missing or empty {column}",
    }


def _unique_check(df: pd.DataFrame, column: str, total: int) -> dict[str, Any]:
    if column not in df.columns:
        duplicate_rows = total
        unique_values = 0
    else:
        values = df[column].fillna("").astype(str).str.strip().str.casefold()
        duplicate_rows = int(values[values.ne("")].duplicated(keep=False).sum())
        unique_values = int(values[values.ne("")].nunique())
    return {
        "status": "pass" if duplicate_rows == 0 else "fail",
        "value": unique_values,
        "detail": f"{duplicate_rows} rows belong to duplicated {column} groups",
    }


def _summary_length_check(
    df: pd.DataFrame,
    total: int,
    min_chars: int = 20,
) -> dict[str, Any]:
    # Measure the actual summary, not summary_chars, so stale derived metadata
    # cannot hide a blank-summary corruption.
    if "summary" in df.columns:
        lengths = df["summary"].fillna("").astype(str).str.len()
    else:
        lengths = pd.Series([0] * total, index=df.index)
    short = int((lengths < min_chars).sum())
    return {
        "status": "pass" if short == 0 else "fail",
        "value": int((lengths >= min_chars).sum()),
        "detail": f"{short}/{total} rows with summary shorter than {min_chars} chars",
    }


def _summary_chars_consistency_check(df: pd.DataFrame, total: int) -> dict[str, Any]:
    if "summary" not in df.columns or "summary_chars" not in df.columns:
        mismatch = total
    else:
        expected = df["summary"].fillna("").astype(str).str.len().astype("Int64")
        actual = pd.to_numeric(df["summary_chars"], errors="coerce").astype("Int64")
        mismatch = int((expected != actual).fillna(True).sum())
    return {
        "status": "pass" if mismatch == 0 else "fail",
        "value": total - mismatch,
        "detail": f"{mismatch}/{total} rows have inconsistent summary_chars",
    }


def _published_validity_check(df: pd.DataFrame, total: int) -> dict[str, Any]:
    if "published" not in df.columns:
        invalid = total
    else:
        invalid = int(pd.to_datetime(df["published"], errors="coerce", utc=True).isna().sum())
    return {
        "status": "pass" if invalid == 0 else "fail",
        "value": total - invalid,
        "detail": f"{invalid}/{total} rows have an invalid published date",
    }


def _age_days_consistency_check(df: pd.DataFrame, total: int) -> dict[str, Any]:
    required = {"published", "age_days"}
    if not required.issubset(df.columns):
        mismatch = total
    else:
        run_date = infer_run_date_from_clean_dataframe(df)
        published = pd.to_datetime(df["published"], errors="coerce", utc=True)
        run_timestamp = pd.Timestamp(run_date)
        if run_timestamp.tzinfo is None:
            run_timestamp = run_timestamp.tz_localize("UTC")
        else:
            run_timestamp = run_timestamp.tz_convert("UTC")
        expected = (run_timestamp.normalize() - published.dt.normalize()).dt.days.astype("Int64")
        actual = pd.to_numeric(df["age_days"], errors="coerce").astype("Int64")
        mismatch = int((expected != actual).fillna(True).sum())
    return {
        "status": "pass" if mismatch == 0 else "fail",
        "value": total - mismatch,
        "detail": f"{mismatch}/{total} rows have age_days inconsistent with published",
    }


def _embedding_consistency_check(df: pd.DataFrame, total: int) -> dict[str, Any]:
    required = {
        "title",
        "summary",
        "published",
        "authors_joined",
        "categories_joined",
        "text_for_embedding",
    }
    if not required.issubset(df.columns):
        mismatch = total
    else:
        expected = rebuild_derived_columns(
            df,
            run_date=infer_run_date_from_clean_dataframe(df),
        )["text_for_embedding"].fillna("").astype(str)
        actual = df["text_for_embedding"].fillna("").astype(str)
        mismatch = int((expected != actual).sum())
    return {
        "status": "pass" if mismatch == 0 else "fail",
        "value": total - mismatch,
        "detail": f"{mismatch}/{total} rows have stale text_for_embedding",
    }


def _noise_check(df: pd.DataFrame, total: int) -> dict[str, Any]:
    if "summary" not in df.columns:
        noisy = total
    else:
        noisy = int(
            df["summary"]
            .fillna("")
            .astype(str)
            .map(lambda text: any(marker in text for marker in NOISE_MARKERS))
            .sum()
        )
    return {
        "status": "pass" if noisy == 0 else "fail",
        "value": total - noisy,
        "detail": f"{noisy}/{total} rows contain known corruption noise",
    }


def _truncated_title_check(df: pd.DataFrame, total: int) -> dict[str, Any]:
    if "title" not in df.columns:
        truncated = total
    else:
        truncated = int(df["title"].fillna("").astype(str).str.endswith("...").sum())
    return {
        "status": "pass" if truncated == 0 else "fail",
        "value": total - truncated,
        "detail": f"{truncated}/{total} titles end with the corruption truncation marker",
    }


def _stale_count(df: pd.DataFrame, settings: Settings) -> int:
    threshold = settings.freshness_threshold_days
    if "age_days" in df.columns:
        ages = pd.to_numeric(df["age_days"], errors="coerce")
        return int((ages.fillna(float("inf")) > threshold).sum())
    if "published" in df.columns:
        stale = 0
        for value in df["published"]:
            try:
                dt = pd.to_datetime(value, errors="coerce")
                if pd.isna(dt):
                    continue
                dt = dt.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                if (now_utc() - dt).days > threshold:
                    stale += 1
            except Exception:
                continue
        return stale
    return 0


def _freshness_check(df: pd.DataFrame, settings: Settings, total: int) -> dict[str, Any]:
    stale = _stale_count(df, settings)
    return {
        "status": "pass" if stale == 0 else "fail",
        "value": total - stale,
        "detail": f"{stale}/{total} rows stale (> {settings.freshness_threshold_days} days old)",
    }


def run_data_quality_checks(
    df: pd.DataFrame,
    settings: Settings,
    report_name: str,
    expected_paper_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Run reproducible quality checks and persist the JSON artifact.

    When ``expected_paper_ids`` is provided (typically the clean baseline's
    paper_ids), a ``record_coverage`` check flags any expected record missing
    from the corpus, so dropped-record corruption is detected directly by the
    quality report rather than only by the corruption validator.
    """
    total = int(len(df))
    checks: dict[str, dict[str, Any]] = {
        "row_count": {
            "status": "pass" if total > 0 else "fail",
            "value": total,
            "detail": f"{total} rows total",
        },
    }
    if expected_paper_ids is not None:
        checks["record_coverage"] = _record_coverage_check(df, expected_paper_ids)
    checks.update({
        "paper_id_not_null": _not_null_check(df, "paper_id", total),
        "paper_id_unique": _unique_check(df, "paper_id", total),
        "title_not_null": _not_null_check(df, "title", total),
        "summary_length": _summary_length_check(df, total),
        "summary_chars_consistency": _summary_chars_consistency_check(df, total),
        "published_valid": _published_validity_check(df, total),
        "age_days_consistency": _age_days_consistency_check(df, total),
        "embedding_text_consistency": _embedding_consistency_check(df, total),
        "noise_free": _noise_check(df, total),
        "title_not_truncated": _truncated_title_check(df, total),
        "freshness": _freshness_check(df, settings, total),
    })

    failed = [name for name, check in checks.items() if check["status"] == "fail"]
    result: dict[str, Any] = {
        "report_name": report_name,
        "checked_at": now_utc().isoformat(),
        "total_rows": total,
        "checks": checks,
        "failed_checks": failed,
        "overall": "fail" if failed else "pass",
    }

    output_path = settings.paths.quality_dir / f"data_quality_{safe_slug(report_name)}.json"
    write_json(output_path, result)
    return result


def _to_utc_datetime(value: Any) -> Any:
    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        return None
    dt = dt.to_pydatetime()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Build and optionally persist a freshness summary."""
    dates: list[Any] = []
    if "published" in df.columns:
        converted = [_to_utc_datetime(value) for value in df["published"]]
        dates = [item for item in converted if item is not None]

    total = int(len(df))
    stale = _stale_count(df, settings)
    payload: dict[str, Any] = {
        "latest_published": max(dates).isoformat() if dates else None,
        "oldest_published": min(dates).isoformat() if dates else None,
        "stale_rows": stale,
        "fresh_rows": max(0, total - stale),
        "total_rows": total,
        "is_fresh": stale == 0 and total > 0,
        "threshold_days": settings.freshness_threshold_days,
        "generated_at_utc": now_utc().isoformat(),
    }

    if report_path is not None:
        write_json(report_path, payload)
    return payload
