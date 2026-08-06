from __future__ import annotations

from datetime import datetime
from html import unescape
import re
from typing import Any, Iterable

import pandas as pd

from core.utils import normalize_whitespace
from ingestion.crossref import PaperRecord


_CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "age_days",
    "text_for_embedding",
]


def _clean_text(value: Any) -> str:
    """Convert a possibly missing scalar to normalized text."""
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return ""
    without_markup = re.sub(r"<[^>]+>", " ", str(value))
    return normalize_whitespace(unescape(without_markup))


def _clean_string_list(values: Iterable[Any] | Any) -> list[str]:
    """Normalize a list-like field and remove duplicates in source order."""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _clean_text(value)
        key = item.casefold()
        if item and key not in seen:
            cleaned.append(item)
            seen.add(key)
    return cleaned


def _as_utc_timestamp(value: Any) -> pd.Timestamp | None:
    """Parse a date-like value and return an UTC timestamp when valid."""
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed)


def _embedding_text(
    *,
    title: str,
    summary: str,
    authors_joined: str,
    categories_joined: str,
    published: str,
) -> str:
    parts = [f"Title: {title}", f"Summary: {summary}"]
    if authors_joined:
        parts.append(f"Authors: {authors_joined}")
    if categories_joined:
        parts.append(f"Categories: {categories_joined}")
    parts.append(f"Published: {published}")
    return "\n".join(parts)


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records into the schema used by retrieval and evaluation.

    Records missing an ID, title, summary, or valid publication date are
    removed. Duplicate paper IDs retain the record with the newest ``updated``
    timestamp. Dates are serialized as ISO dates for stable CSV/JSON output and
    valid Chroma metadata.
    """
    run_timestamp = pd.Timestamp(run_date)
    if run_timestamp.tzinfo is None:
        run_timestamp = run_timestamp.tz_localize("UTC")
    else:
        run_timestamp = run_timestamp.tz_convert("UTC")
    run_timestamp = run_timestamp.normalize()

    cleaned_rows: list[dict[str, Any]] = []
    for record in records:
        paper_id = _clean_text(record.paper_id).lower()
        title = _clean_text(record.title)
        summary = _clean_text(record.summary)
        published_timestamp = _as_utc_timestamp(record.published)

        # These fields form the minimum usable indexing/evaluation contract.
        if not paper_id or not title or not summary or published_timestamp is None:
            continue

        published_day = published_timestamp.normalize()
        if published_day > run_timestamp:
            continue

        updated_timestamp = _as_utc_timestamp(record.updated)
        if updated_timestamp is None:
            updated_timestamp = published_timestamp
        authors = _clean_string_list(record.authors)
        categories = _clean_string_list(record.categories)
        primary_category = _clean_text(record.primary_category)
        if not primary_category and categories:
            primary_category = categories[0]

        authors_joined = ", ".join(authors)
        categories_joined = ", ".join(categories)
        published = published_day.date().isoformat()
        updated = updated_timestamp.date().isoformat()

        cleaned_rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "categories": categories,
                "primary_category": primary_category,
                "published": published,
                "updated": updated,
                "abs_url": _clean_text(record.abs_url),
                "pdf_url": _clean_text(record.pdf_url),
                "comment": _clean_text(record.comment),
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "summary_chars": len(summary),
                "age_days": int((run_timestamp - published_day).days),
                "text_for_embedding": _embedding_text(
                    title=title,
                    summary=summary,
                    authors_joined=authors_joined,
                    categories_joined=categories_joined,
                    published=published,
                ),
                "_updated_timestamp": updated_timestamp,
            }
        )

    if not cleaned_rows:
        return pd.DataFrame(columns=_CLEAN_COLUMNS)

    dataframe = pd.DataFrame(cleaned_rows)
    dataframe = (
        dataframe.sort_values(
            by=["_updated_timestamp", "paper_id"],
            ascending=[False, True],
            kind="stable",
        )
        .drop_duplicates(subset=["paper_id"], keep="first")
        .sort_values(by=["published", "paper_id"], ascending=[False, True], kind="stable")
        .drop(columns=["_updated_timestamp"])
        .reset_index(drop=True)
    )
    return dataframe[_CLEAN_COLUMNS]
