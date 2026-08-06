from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, safe_slug, write_json


_REQUIRED_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "published",
}
_QUESTION_TYPES = ("summary", "authors", "date", "categories")


def _clean_scalar(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return normalize_whitespace(str(value))


def _lookup_value(row: pd.Series) -> str:
    """Return a value that the existing QA regex can safely exact-match."""
    title = _clean_scalar(row["title"])
    return title if "'" not in title else _clean_scalar(row["paper_id"])


def _question_payload(row: pd.Series, question_type: str, sequence: int) -> dict[str, Any] | None:
    paper_id = _clean_scalar(row["paper_id"])
    lookup_value = _lookup_value(row)

    if question_type == "summary":
        ground_truth = first_sentence(_clean_scalar(row["summary"]))
        question = f"What is the main idea of '{lookup_value}'?"
    elif question_type == "authors":
        ground_truth = _clean_scalar(row["authors_joined"])
        question = f"Who authored '{lookup_value}'?"
    elif question_type == "date":
        ground_truth = _clean_scalar(row["published"])
        question = f"When was '{lookup_value}' published?"
    elif question_type == "categories":
        ground_truth = _clean_scalar(row["categories_joined"])
        question = f"What categories does '{lookup_value}' belong to?"
    else:
        raise ValueError(f"Unsupported question type: {question_type}")

    if not paper_id or not lookup_value or not ground_truth:
        return None
    return {
        "id": f"{question_type}-{sequence:03d}-{safe_slug(paper_id)}",
        "question_type": question_type,
        "question": question,
        "ground_truth": ground_truth,
        "ground_truth_doc_ids": [paper_id],
    }


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build a deterministic, reusable evaluation set from cleaned papers.

    The four newest usable papers form the primary sample. Missing question
    types (for example, when a selected paper has no categories) are backfilled
    from the rest of the corpus. This preserves the four evaluation dimensions
    expected by the lab without inventing ground truth.
    """
    missing_columns = sorted(_REQUIRED_COLUMNS - set(df.columns))
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing required columns: {missing_columns}")

    candidates = df.copy()
    candidates["_paper_id"] = candidates["paper_id"].map(_clean_scalar)
    candidates["_title"] = candidates["title"].map(_clean_scalar)
    candidates["_published"] = pd.to_datetime(candidates["published"], errors="coerce", utc=True)
    candidates = candidates[
        candidates["_paper_id"].ne("")
        & candidates["_title"].ne("")
        & candidates["_published"].notna()
    ]
    candidates = (
        candidates.sort_values(
            by=["_published", "_paper_id"],
            ascending=[False, True],
            kind="stable",
        )
        .drop_duplicates(subset=["_paper_id"], keep="first")
        .reset_index(drop=True)
    )

    minimum_documents = 4
    if len(candidates) < minimum_documents:
        raise ValueError(
            f"At least {minimum_documents} valid, unique papers are required to build the test set; "
            f"received {len(candidates)}."
        )

    primary_candidates = candidates.head(minimum_documents)
    test_set: list[dict[str, Any]] = []
    covered_types: set[str] = set()

    for _, row in primary_candidates.iterrows():
        for question_type in _QUESTION_TYPES:
            payload = _question_payload(row, question_type, len(test_set) + 1)
            if payload is not None:
                test_set.append(payload)
                covered_types.add(question_type)

    # Backfill a type only when none of the four primary papers can answer it.
    for question_type in _QUESTION_TYPES:
        if question_type in covered_types:
            continue
        for _, row in candidates.iloc[minimum_documents:].iterrows():
            payload = _question_payload(row, question_type, len(test_set) + 1)
            if payload is not None:
                test_set.append(payload)
                covered_types.add(question_type)
                break

    missing_types = sorted(set(_QUESTION_TYPES) - covered_types)
    if missing_types:
        raise ValueError(
            "The cleaned corpus cannot provide ground truth for question types: "
            f"{missing_types}. Check summary/authors/categories fields."
        )

    write_json(Path(output_path), test_set)
    return test_set
