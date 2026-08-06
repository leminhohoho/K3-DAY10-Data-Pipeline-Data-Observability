from __future__ import annotations

from datetime import UTC
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import now_utc, safe_slug, write_json


def _present_count(df: pd.DataFrame, column: str) -> int:
    """Number of rows where ``column`` has a non-empty string value."""
    if column not in df.columns:
        return 0
    mask = df[column].notna()
    return int(df.loc[mask, column].astype(str).str.strip().ne("").sum(skipna=True))


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
        duplicates = total
    else:
        duplicates = int(df[column].dropna().duplicated().sum())
    return {
        "status": "pass" if duplicates == 0 else "fail",
        "value": total - duplicates,
        "detail": f"{duplicates} duplicated {column} values",
    }


def _summary_length_check(df: pd.DataFrame, total: int, min_chars: int = 20) -> dict[str, Any]:
    if "summary_chars" in df.columns:
        lengths = pd.to_numeric(df["summary_chars"], errors="coerce").fillna(0).astype(int)
    elif "summary" in df.columns:
        lengths = df["summary"].fillna("").astype(str).str.len()
    else:
        lengths = pd.Series([0] * total, index=df.index)
    empty = int((lengths < min_chars).sum())
    return {
        "status": "pass" if empty == 0 else "fail",
        "value": int((lengths >= min_chars).sum()),
        "detail": f"{empty}/{total} rows with summary shorter than {min_chars} chars",
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


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """TODO(student): tao bo data quality checks.

    Pseudo-code:
    1. Check row count.
    2. Check `paper_id` not null va unique.
    3. Check `title` not null.
    4. Check do dai `summary`.
    5. Check freshness bang `age_days`.
    6. Ghi ket qua vao `data/quality/`.
    """
    total = int(len(df))

    checks: dict[str, dict[str, Any]] = {
        "row_count": {
            "status": "pass" if total > 0 else "fail",
            "value": total,
            "detail": f"{total} rows total",
        },
        "paper_id_not_null": _not_null_check(df, "paper_id", total),
        "paper_id_unique": _unique_check(df, "paper_id", total),
        "title_not_null": _not_null_check(df, "title", total),
        "summary_length": _summary_length_check(df, total),
        "freshness": _freshness_check(df, settings, total),
    }

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
    """TODO(student): tong hop freshness report.

    Pseudo-code:
    1. Tim latest va oldest published date.
    2. Dem so dong stale.
    3. Tao payload:
       - latest_published
       - oldest_published
       - stale_rows
       - total_rows
       - is_fresh
    4. Ghi JSON report.
    """
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
        "total_rows": total,
        "is_fresh": stale == 0 and total > 0,
        "threshold_days": settings.freshness_threshold_days,
    }

    if report_path is not None:
        write_json(report_path, payload)
    return payload
