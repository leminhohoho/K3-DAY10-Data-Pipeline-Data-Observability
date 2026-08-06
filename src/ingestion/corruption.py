from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CorruptionConfig:
    """Tỷ lệ và tham số cho từng kịch bản corruption."""

    drop_latest_fraction: float = 0.10
    blank_summary_fraction: float = 0.10
    noise_fraction: float = 0.10
    truncate_title_fraction: float = 0.10
    stale_date_fraction: float = 0.10
    duplicate_fraction: float = 0.10
    stale_years: int = 5
    minimum_rows_per_scenario: int = 1

    def validate(self) -> None:
        fraction_fields = (
            "drop_latest_fraction",
            "blank_summary_fraction",
            "noise_fraction",
            "truncate_title_fraction",
            "stale_date_fraction",
            "duplicate_fraction",
        )
        for field_name in fraction_fields:
            value = getattr(self, field_name)
            if not 0 <= value <= 1:
                raise ValueError(f"{field_name} phải nằm trong [0, 1], nhận được {value}.")
        if self.stale_years < 1:
            raise ValueError("stale_years phải >= 1.")
        if self.minimum_rows_per_scenario < 0:
            raise ValueError("minimum_rows_per_scenario phải >= 0.")


NOISE_TEMPLATES: tuple[str, ...] = (
    " ###@@@ corrupted_text !!! ",
    " [ADVERTISEMENT] click here click here ",
    " <html><body>navigation footer cookie-policy</body></html> ",
    " zxqv zxqv 0000 NULL UNKNOWN ",
    " References References References DOI DOI DOI ",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    """Chuyển giá trị pandas/numpy sang kiểu có thể ghi JSON."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if pd.isna(value):
        return None
    return value


def _preview(value: Any, limit: int = 160) -> str | None:
    safe = _json_safe(value)
    if safe is None:
        return None
    text = str(safe).replace("\n", "\\n")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _detect_key_column(df: pd.DataFrame, key_col: str | None = None) -> str:
    if key_col:
        if key_col not in df.columns:
            raise KeyError(f"Không tìm thấy key column '{key_col}'.")
        return key_col

    candidates = ("doi", "DOI", "id", "paper_id", "record_id", "crossref_id")
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    raise KeyError(
        "Không tìm thấy khóa ổn định. Hãy truyền key_col hoặc thêm một cột như "
        "'doi', 'id', 'paper_id'."
    )


def _require_columns(df: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise KeyError(f"DataFrame thiếu các cột bắt buộc: {missing}")


def _scenario_count(total_rows: int, fraction: float, minimum: int) -> int:
    if total_rows <= 0 or fraction <= 0:
        return 0
    return min(total_rows, max(minimum, math.ceil(total_rows * fraction)))


def _non_empty_mask(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("")


def _sample_indices(
    rng: np.random.Generator,
    candidates: Sequence[Any],
    count: int,
    *,
    excluded: set[Any] | None = None,
) -> list[Any]:
    excluded = excluded or set()
    available = [index for index in candidates if index not in excluded]
    if count <= 0 or not available:
        return []
    count = min(count, len(available))
    chosen = rng.choice(np.array(available, dtype=object), size=count, replace=False)
    return chosen.tolist()


def rebuild_text_for_embedding(
    df: pd.DataFrame,
    *,
    title_col: str = "title",
    summary_col: str = "summary",
    output_col: str = "text_for_embedding",
) -> pd.DataFrame:
    """
    Tạo lại text dùng cho embedding từ dữ liệu hiện tại.

    Không fallback sang dữ liệu khác khi summary bị rỗng, vì mục tiêu của bài lab
    là để corruption thực sự lan truyền tới corpus embedding.
    """
    _require_columns(df, (title_col, summary_col))
    result = df.copy(deep=True)

    title = result[title_col].fillna("").astype(str).str.strip()
    summary = result[summary_col].fillna("").astype(str).str.strip()

    result[output_col] = (
        "Title: "
        + title
        + "\nSummary: "
        + summary
    ).str.strip()

    return result


def corrupt_clean_dataframe(
    df: pd.DataFrame,
    output_log_path: str | Path,
    *,
    config: CorruptionConfig | None = None,
    random_state: int = 42,
    key_col: str | None = None,
    title_col: str = "title",
    summary_col: str = "summary",
    published_col: str = "published_date",
    embedding_col: str = "text_for_embedding",
) -> pd.DataFrame:
    """
    Mô phỏng nhiều dạng lỗi dữ liệu trên clean DataFrame.

    Các kịch bản:
    1. Xóa một số bản ghi mới nhất.
    2. Làm rỗng summary.
    3. Chèn text nhiễu.
    4. Cắt ngắn title.
    5. Làm published date cũ đi.
    6. Thêm duplicate rows.
    7. Tạo lại text_for_embedding.
    8. Ghi corruption log dạng JSONL.

    Hàm không sửa trực tiếp DataFrame đầu vào.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df phải là pandas.DataFrame.")
    if df.empty:
        raise ValueError("Không thể corrupt DataFrame rỗng.")

    config = config or CorruptionConfig()
    config.validate()
    _require_columns(df, (title_col, summary_col, published_col))
    resolved_key = _detect_key_column(df, key_col)

    rng = np.random.default_rng(random_state)
    run_id = str(uuid.uuid4())
    started_at = _utc_now_iso()
    original = df.copy(deep=True)
    corrupted = df.copy(deep=True)
    events: list[dict[str, Any]] = []

    def log_event(
        scenario: str,
        *,
        row_index: Any = None,
        row_key: Any = None,
        field: str | None = None,
        before: Any = None,
        after: Any = None,
        note: str | None = None,
    ) -> None:
        events.append(
            {
                "event_type": "mutation",
                "run_id": run_id,
                "timestamp_utc": _utc_now_iso(),
                "scenario": scenario,
                "row_index": _json_safe(row_index),
                "row_key": _json_safe(row_key),
                "field": field,
                "before_preview": _preview(before),
                "after_preview": _preview(after),
                "note": note,
            }
        )

    # 1) Drop latest records.
    parsed_dates = pd.to_datetime(corrupted[published_col], errors="coerce", utc=True)
    latest_order = parsed_dates.sort_values(ascending=False, na_position="last").index.tolist()
    drop_count = _scenario_count(
        len(corrupted),
        config.drop_latest_fraction,
        config.minimum_rows_per_scenario,
    )
    drop_indices = latest_order[:drop_count]

    for index in drop_indices:
        row = corrupted.loc[index]
        log_event(
            "drop_latest_record",
            row_index=index,
            row_key=row[resolved_key],
            field=None,
            before="row exists",
            after="row removed",
            note=f"{published_col}={_preview(row[published_col])}",
        )
    corrupted = corrupted.drop(index=drop_indices).copy()

    # Dùng tập chỉ mục để hạn chế nhiều corruption chồng lên cùng một dòng.
    used_indices: set[Any] = set()
    remaining_indices = corrupted.index.tolist()

    # 2) Blank summary.
    blank_candidates = corrupted.index[_non_empty_mask(corrupted[summary_col])].tolist()
    blank_count = _scenario_count(
        len(corrupted),
        config.blank_summary_fraction,
        config.minimum_rows_per_scenario,
    )
    blank_indices = _sample_indices(rng, blank_candidates, blank_count, excluded=used_indices)
    for index in blank_indices:
        before = corrupted.at[index, summary_col]
        corrupted.at[index, summary_col] = ""
        used_indices.add(index)
        log_event(
            "blank_summary",
            row_index=index,
            row_key=corrupted.at[index, resolved_key],
            field=summary_col,
            before=before,
            after="",
        )

    # 3) Inject noise vào summary.
    noise_candidates = corrupted.index[_non_empty_mask(corrupted[summary_col])].tolist()
    noise_count = _scenario_count(
        len(corrupted),
        config.noise_fraction,
        config.minimum_rows_per_scenario,
    )
    noise_indices = _sample_indices(rng, noise_candidates, noise_count, excluded=used_indices)
    for position, index in enumerate(noise_indices):
        before = str(corrupted.at[index, summary_col])
        noise = NOISE_TEMPLATES[position % len(NOISE_TEMPLATES)]
        insert_at = len(before) // 2
        after = before[:insert_at] + noise + before[insert_at:]
        corrupted.at[index, summary_col] = after
        used_indices.add(index)
        log_event(
            "inject_noise",
            row_index=index,
            row_key=corrupted.at[index, resolved_key],
            field=summary_col,
            before=before,
            after=after,
        )

    # 4) Truncate title.
    title_candidates = corrupted.index[
        corrupted[title_col].notna() & corrupted[title_col].astype(str).str.len().ge(12)
    ].tolist()
    truncate_count = _scenario_count(
        len(corrupted),
        config.truncate_title_fraction,
        config.minimum_rows_per_scenario,
    )
    truncate_indices = _sample_indices(
        rng, title_candidates, truncate_count, excluded=used_indices
    )
    for index in truncate_indices:
        before = str(corrupted.at[index, title_col])
        keep = max(8, int(len(before) * 0.35))
        after = before[:keep].rstrip() + "..."
        corrupted.at[index, title_col] = after
        used_indices.add(index)
        log_event(
            "truncate_title",
            row_index=index,
            row_key=corrupted.at[index, resolved_key],
            field=title_col,
            before=before,
            after=after,
        )

    # 5) Make published date stale.
    valid_date_indices = parsed_dates.loc[corrupted.index].dropna().index.tolist()
    stale_count = _scenario_count(
        len(corrupted),
        config.stale_date_fraction,
        config.minimum_rows_per_scenario,
    )
    stale_indices = _sample_indices(
        rng, valid_date_indices, stale_count, excluded=used_indices
    )
    for index in stale_indices:
        before = corrupted.at[index, published_col]
        parsed = pd.to_datetime(before, errors="coerce", utc=True)
        if pd.isna(parsed):
            continue
        stale_date = parsed - pd.DateOffset(years=config.stale_years)
        after = stale_date.date().isoformat()
        corrupted.at[index, published_col] = after
        used_indices.add(index)
        log_event(
            "stale_published_date",
            row_index=index,
            row_key=corrupted.at[index, resolved_key],
            field=published_col,
            before=before,
            after=after,
            note=f"shifted_back_years={config.stale_years}",
        )

    # 6) Add duplicate rows.
    duplicate_count = _scenario_count(
        len(corrupted),
        config.duplicate_fraction,
        config.minimum_rows_per_scenario,
    )
    duplicate_source_indices = _sample_indices(
        rng, remaining_indices, duplicate_count
    )
    duplicate_rows: list[pd.DataFrame] = []
    for index in duplicate_source_indices:
        if index not in corrupted.index:
            continue
        row_frame = corrupted.loc[[index]].copy(deep=True)
        duplicate_rows.append(row_frame)
        log_event(
            "duplicate_row",
            row_index=index,
            row_key=corrupted.at[index, resolved_key],
            field=None,
            before="1 row",
            after="2 rows with same key/content",
        )

    if duplicate_rows:
        corrupted = pd.concat([corrupted, *duplicate_rows], ignore_index=True)
    else:
        corrupted = corrupted.reset_index(drop=True)

    # 7) Rebuild text_for_embedding để corruption ảnh hưởng corpus embedding.
    before_embedding_exists = embedding_col in corrupted.columns
    corrupted = rebuild_text_for_embedding(
        corrupted,
        title_col=title_col,
        summary_col=summary_col,
        output_col=embedding_col,
    )
    log_event(
        "rebuild_text_for_embedding",
        field=embedding_col,
        before="column existed" if before_embedding_exists else "column missing",
        after=f"rebuilt for {len(corrupted)} rows",
    )

    scenario_counts: dict[str, int] = {}
    for event in events:
        scenario = event["scenario"]
        scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1

    completed_at = _utc_now_iso()
    metadata = {
        "event_type": "run_metadata",
        "run_id": run_id,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "random_state": random_state,
        "key_column": resolved_key,
        "input_rows": int(len(original)),
        "output_rows": int(len(corrupted)),
        "config": asdict(config),
        "scenario_counts": scenario_counts,
    }

    output_path = Path(output_log_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        file.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        for event in events:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    corrupted.attrs["corruption_run_id"] = run_id
    corrupted.attrs["corruption_log_path"] = str(output_path)
    corrupted.attrs["corruption_scenario_counts"] = scenario_counts
    return corrupted


def _normalize_key_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.lower()


def build_data_quality_report(
    df: pd.DataFrame,
    *,
    key_col: str | None = None,
    title_col: str = "title",
    summary_col: str = "summary",
    published_col: str = "published_date",
    embedding_col: str = "text_for_embedding",
    freshness_cutoff_days: int = 365 * 3,
) -> dict[str, Any]:
    """Tạo các chỉ số DQ đơn giản để so sánh baseline/corrupted/repaired."""
    _require_columns(df, (title_col, summary_col, published_col))
    resolved_key = _detect_key_column(df, key_col)

    keys = _normalize_key_series(df[resolved_key])
    duplicate_key_rows = int(keys.duplicated(keep=False).sum())
    duplicate_key_groups = int(keys[keys.duplicated(keep=False)].nunique())

    summary_blank = int((~_non_empty_mask(df[summary_col])).sum())
    title_blank = int((~_non_empty_mask(df[title_col])).sum())

    parsed_dates = pd.to_datetime(df[published_col], errors="coerce", utc=True)
    invalid_dates = int(parsed_dates.isna().sum())
    now = pd.Timestamp.now(tz="UTC")
    stale_dates = int((parsed_dates < now - pd.Timedelta(days=freshness_cutoff_days)).sum())

    if embedding_col in df.columns:
        embedding_blank = int((~_non_empty_mask(df[embedding_col])).sum())
    else:
        embedding_blank = len(df)

    noise_regex = r"###@@@|\[ADVERTISEMENT\]|<html>|zxqv|cookie-policy|References References"
    noisy_rows = int(
        df[summary_col]
        .fillna("")
        .astype(str)
        .str.contains(noise_regex, case=False, regex=True)
        .sum()
    )

    truncated_titles = int(
        df[title_col].fillna("").astype(str).str.endswith("...").sum()
    )

    return {
        "row_count": int(len(df)),
        "unique_key_count": int(keys.nunique()),
        "duplicate_key_rows": duplicate_key_rows,
        "duplicate_key_groups": duplicate_key_groups,
        "blank_summary_rows": summary_blank,
        "blank_title_rows": title_blank,
        "blank_embedding_rows": int(embedding_blank),
        "invalid_published_date_rows": invalid_dates,
        "stale_published_date_rows": stale_dates,
        "noisy_summary_rows": noisy_rows,
        "truncated_title_rows": truncated_titles,
        "freshness_cutoff_days": freshness_cutoff_days,
    }


def _dataframe_digest(
    df: pd.DataFrame,
    *,
    key_col: str,
    compare_columns: Sequence[str],
) -> str:
    normalized = df[[key_col, *compare_columns]].copy()
    normalized[key_col] = _normalize_key_series(normalized[key_col])
    normalized = normalized.sort_values(key_col).reset_index(drop=True)

    for column in compare_columns:
        normalized[column] = normalized[column].fillna("").astype(str).str.strip()

    payload = normalized.to_json(
        orient="records",
        force_ascii=False,
        date_format="iso",
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_repair(
    repaired_df: pd.DataFrame,
    reference_clean_df: pd.DataFrame,
    *,
    key_col: str | None = None,
    compare_columns: Sequence[str] = (
        "title",
        "summary",
        "published_date",
        "text_for_embedding",
    ),
) -> dict[str, Any]:
    """Kiểm tra repaired có khớp với clean reference hay không."""
    resolved_key = _detect_key_column(reference_clean_df, key_col)
    _require_columns(repaired_df, (resolved_key, *compare_columns))
    _require_columns(reference_clean_df, (resolved_key, *compare_columns))

    repaired_keys = set(_normalize_key_series(repaired_df[resolved_key]))
    reference_keys = set(_normalize_key_series(reference_clean_df[resolved_key]))

    repaired_digest = _dataframe_digest(
        repaired_df,
        key_col=resolved_key,
        compare_columns=compare_columns,
    )
    reference_digest = _dataframe_digest(
        reference_clean_df,
        key_col=resolved_key,
        compare_columns=compare_columns,
    )

    return {
        "row_count_match": len(repaired_df) == len(reference_clean_df),
        "missing_keys_after_repair": sorted(reference_keys - repaired_keys),
        "unexpected_keys_after_repair": sorted(repaired_keys - reference_keys),
        "content_digest_match": repaired_digest == reference_digest,
        "repaired_digest": repaired_digest,
        "reference_digest": reference_digest,
        "repair_valid": (
            len(repaired_df) == len(reference_clean_df)
            and repaired_keys == reference_keys
            and repaired_digest == reference_digest
        ),
    }


def repair_corrupted_dataframe(
    corrupted_df: pd.DataFrame,
    raw_source_df: pd.DataFrame,
    output_log_path: str | Path,
    *,
    clean_from_raw_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    key_col: str | None = None,
    title_col: str = "title",
    summary_col: str = "summary",
    published_col: str = "published_date",
    embedding_col: str = "text_for_embedding",
) -> pd.DataFrame:
    """
    Repair corpus bằng cách dựng lại từ source of truth, không vá theo dữ liệu lỗi.

    - Nếu raw_source_df đã là clean/normalized DataFrame: để clean_from_raw_fn=None.
    - Nếu raw_source_df còn là dữ liệu raw Crossref: truyền hàm cleaning hiện có của nhóm,
      ví dụ clean_from_raw_fn=transform_crossref_raw_to_clean.

    Cách này phục hồi được cả record bị drop, summary/title/date bị sửa và duplicate.
    """
    if not isinstance(corrupted_df, pd.DataFrame):
        raise TypeError("corrupted_df phải là pandas.DataFrame.")
    if not isinstance(raw_source_df, pd.DataFrame):
        raise TypeError("raw_source_df phải là pandas.DataFrame.")

    rebuilt = (
        clean_from_raw_fn(raw_source_df.copy(deep=True))
        if clean_from_raw_fn is not None
        else raw_source_df.copy(deep=True)
    )
    if not isinstance(rebuilt, pd.DataFrame):
        raise TypeError("clean_from_raw_fn phải trả về pandas.DataFrame.")

    _require_columns(rebuilt, (title_col, summary_col, published_col))
    resolved_key = _detect_key_column(rebuilt, key_col)
    _require_columns(corrupted_df, (resolved_key,))

    # Chuẩn hóa key và loại duplicate từ nguồn dựng lại.
    rebuilt = rebuilt.copy(deep=True)
    rebuilt["_normalized_repair_key"] = _normalize_key_series(rebuilt[resolved_key])
    rebuilt = rebuilt.loc[rebuilt["_normalized_repair_key"].ne("")].copy()
    rebuilt = rebuilt.drop_duplicates(
        subset=["_normalized_repair_key"],
        keep="first",
    ).drop(columns=["_normalized_repair_key"])

    repaired = rebuild_text_for_embedding(
        rebuilt,
        title_col=title_col,
        summary_col=summary_col,
        output_col=embedding_col,
    ).reset_index(drop=True)

    corrupted_keys = _normalize_key_series(corrupted_df[resolved_key])
    repaired_keys = _normalize_key_series(repaired[resolved_key])

    repair_report = {
        "event_type": "repair_report",
        "timestamp_utc": _utc_now_iso(),
        "strategy": "rebuild_from_raw_source_of_truth",
        "key_column": resolved_key,
        "corrupted_row_count": int(len(corrupted_df)),
        "repaired_row_count": int(len(repaired)),
        "corrupted_duplicate_key_rows": int(
            corrupted_keys.duplicated(keep=False).sum()
        ),
        "missing_keys_restored": sorted(set(repaired_keys) - set(corrupted_keys)),
        "unexpected_corrupted_keys_removed": sorted(
            set(corrupted_keys) - set(repaired_keys)
        ),
        "repaired_quality_report": build_data_quality_report(
            repaired,
            key_col=resolved_key,
            title_col=title_col,
            summary_col=summary_col,
            published_col=published_col,
            embedding_col=embedding_col,
        ),
    }

    output_path = Path(output_log_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(repair_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    repaired.attrs["repair_log_path"] = str(output_path)
    return repaired


def compare_pipeline_states(
    baseline_df: pd.DataFrame,
    corrupted_df: pd.DataFrame,
    repaired_df: pd.DataFrame,
    *,
    key_col: str | None = None,
) -> pd.DataFrame:
    """Tạo bảng so sánh data-quality metrics của ba trạng thái."""
    reports = {
        "baseline": build_data_quality_report(baseline_df, key_col=key_col),
        "corrupted": build_data_quality_report(corrupted_df, key_col=key_col),
        "repaired": build_data_quality_report(repaired_df, key_col=key_col),
    }
    return pd.DataFrame.from_dict(reports, orient="index").reset_index(
        names="pipeline_state"
    )
