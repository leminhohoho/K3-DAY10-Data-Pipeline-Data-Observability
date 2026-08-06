from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import html
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import compact_join, normalize_whitespace, read_json, write_json

CROSSREF_API_URL = "https://api.crossref.org/works"
REQUEST_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 2.0
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
USER_AGENT = "day10-data-observability-lab/0.1 (https://github.com/VinUni-AI20k)"


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return normalize_whitespace(html.unescape(value))


def _clean_abstract(value: Any) -> str:
    """Crossref tra abstract duoi dang JATS XML, can bo tag va prefix `Abstract`."""
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = _clean_text(text)
    return re.sub(r"^abstract[:\s-]*", "", text, flags=re.IGNORECASE).strip()


def _first_text(values: Any) -> str:
    if isinstance(values, list):
        for value in values:
            cleaned = _clean_text(value)
            if cleaned:
                return cleaned
    return _clean_text(values)


def _date_from_parts(node: Any) -> str:
    """`{"date-parts": [[2025, 3, 7]]}` -> `2025-03-07`. Phan thieu duoc fill bang 01."""
    if not isinstance(node, dict):
        return ""
    parts = node.get("date-parts") or []
    if not parts or not isinstance(parts[0], list) or not parts[0]:
        return ""
    values = [int(part) for part in parts[0] if isinstance(part, int)]
    if not values:
        return ""
    year = values[0]
    month = values[1] if len(values) > 1 else 1
    day = values[2] if len(values) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _published_date(item: dict) -> str:
    for key in ("published", "published-online", "published-print", "issued", "created"):
        value = _date_from_parts(item.get(key))
        if value:
            return value
    return ""


def _updated_date(item: dict, fallback: str) -> str:
    for key in ("indexed", "deposited", "created"):
        value = _date_from_parts(item.get(key))
        if value:
            return value
    return fallback


def _authors(item: dict) -> list[str]:
    authors: list[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = _clean_text(author.get("name")) or compact_join(
            [_clean_text(author.get("given")), _clean_text(author.get("family"))], sep=" "
        )
        if name and name not in authors:
            authors.append(name)
    return authors


def _categories(item: dict) -> list[str]:
    categories: list[str] = []
    for subject in item.get("subject") or []:
        cleaned = _clean_text(subject)
        if cleaned and cleaned not in categories:
            categories.append(cleaned)
    if not categories:
        # Nhieu record Crossref khong co `subject`; dung container/type lam fallback.
        for fallback in (_first_text(item.get("container-title")), _clean_text(item.get("type"))):
            if fallback and fallback not in categories:
                categories.append(fallback)
    return categories


def _pdf_url(item: dict) -> str:
    for link in item.get("link") or []:
        if not isinstance(link, dict):
            continue
        if str(link.get("content-type", "")).lower() == "application/pdf":
            url = _clean_text(link.get("URL"))
            if url:
                return url
    return ""


def _comment(item: dict) -> str:
    return compact_join(
        [
            _clean_text(item.get("type")),
            _first_text(item.get("container-title")),
            _clean_text(item.get("publisher")),
        ],
        sep=" | ",
    )


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thanh list `PaperRecord` voi schema nhat quan.

    Record khong co DOI, title hoac abstract bi loai; DOI trung lap chi giu ban dau tien.
    """
    items = ((payload or {}).get("message") or {}).get("items") or []

    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue

        paper_id = _clean_text(item.get("DOI")).lower()
        title = _first_text(item.get("title"))
        summary = _clean_abstract(item.get("abstract"))
        published = _published_date(item)
        if not paper_id or not title or not summary or not published:
            continue
        if paper_id in seen_ids:
            continue
        seen_ids.add(paper_id)

        categories = _categories(item)
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_authors(item),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published,
                updated=_updated_date(item, published),
                abs_url=_clean_text(item.get("URL")) or f"https://doi.org/{paper_id}",
                pdf_url=_pdf_url(item),
                comment=_comment(item),
            )
        )
    return records


def _request_payload(params: dict[str, Any]) -> dict:
    """Goi Crossref voi retry/backoff cho cac status tam thoi (429/5xx)."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    last_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                CROSSREF_API_URL,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code in RETRY_STATUS_CODES:
                last_error = f"HTTP {response.status_code}"
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else RETRY_BACKOFF_SECONDS * attempt
            else:
                response.raise_for_status()
                return response.json()
        except requests.RequestException as error:
            last_error = str(error)
            delay = RETRY_BACKOFF_SECONDS * attempt

        if attempt < MAX_ATTEMPTS:
            time.sleep(delay)

    raise RuntimeError(f"Crossref request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Goi Crossref API, luu raw response va raw records vao `data/raw/`."""
    params = {
        "query.bibliographic": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        # Sort by relevance (not published date) so the corpus actually matches
        # the RAG query. `sort=published desc` returned the newest papers
        # regardless of topic, which both mismatched the query and clustered every
        # record on a single publication date.
        "sort": "relevance",
        "order": "desc",
    }

    payload = _request_payload(params)
    write_json(settings.paths.raw_api_response, payload)

    records = parse_crossref_payload(payload)
    if not records:
        raise RuntimeError("Crossref returned no usable record. Check source_query/source_filter.")

    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot trong `data/raw/` va map lai thanh `PaperRecord`."""
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected a list of raw records in {path}.")

    records: list[PaperRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        records.append(
            PaperRecord(
                paper_id=str(item.get("paper_id", "")),
                title=str(item.get("title", "")),
                summary=str(item.get("summary", "")),
                authors=[str(author) for author in item.get("authors") or []],
                categories=[str(category) for category in item.get("categories") or []],
                primary_category=str(item.get("primary_category", "")),
                published=str(item.get("published", "")),
                updated=str(item.get("updated", "")),
                abs_url=str(item.get("abs_url", "")),
                pdf_url=str(item.get("pdf_url", "")),
                comment=str(item.get("comment", "")),
            )
        )
    return records
