from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pandas.testing as pdt

from core.config import load_settings
from core.utils import read_json
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import (
    CorruptionConfig,
    corrupt_clean_dataframe,
    repair_from_raw_records,
    validate_corrupted_dataframe,
    validate_repaired_dataframe,
)
from ingestion.crossref import PaperRecord
from observability.quality import run_data_quality_checks


RUN_DATE = datetime(2026, 8, 6, tzinfo=UTC)


def make_raw_records(count: int = 40) -> list[PaperRecord]:
    records: list[PaperRecord] = []
    for index in range(count):
        published = (RUN_DATE - timedelta(days=index + 1)).date().isoformat()
        records.append(
            PaperRecord(
                paper_id=f"10.1234/rag-paper-{index:03d}",
                title=(
                    "Retrieval augmented generation and data observability "
                    f"study number {index}"
                ),
                summary=(
                    "This paper evaluates retrieval quality, data corruption, "
                    f"repair, and observability for experiment {index}."
                ),
                authors=[f"Author {index}", "Research Partner"],
                categories=["Artificial Intelligence", "Information Retrieval"],
                primary_category="Artificial Intelligence",
                published=published,
                updated=published,
                abs_url=f"https://doi.org/10.1234/rag-paper-{index:03d}",
                pdf_url="",
                comment="journal-article | Demo Journal",
            )
        )
    return records


def make_clean_dataframe(count: int = 40) -> tuple[list[PaperRecord], pd.DataFrame]:
    records = make_raw_records(count)
    return records, build_clean_dataframe(records, run_date=RUN_DATE)


def corruption_config() -> CorruptionConfig:
    return CorruptionConfig(
        drop_latest_fraction=0.10,
        blank_summary_fraction=0.10,
        noise_fraction=0.10,
        truncate_title_fraction=0.10,
        stale_date_fraction=0.10,
        duplicate_fraction=0.10,
        stale_years=5,
    )


def test_corruption_creates_all_scenarios_without_mutating_input(tmp_path: Path) -> None:
    _, baseline = make_clean_dataframe()
    baseline_before = baseline.copy(deep=True)
    log_path = tmp_path / "corruption_log.json"

    corrupted = corrupt_clean_dataframe(
        baseline,
        log_path,
        config=corruption_config(),
        random_seed=42,
        run_date=RUN_DATE,
    )

    pdt.assert_frame_equal(baseline, baseline_before)
    assert log_path.exists()

    log = read_json(log_path)
    expected_scenarios = {
        "drop_latest_records",
        "blank_summary",
        "inject_noise",
        "truncate_title",
        "stale_published_date",
        "duplicate_rows",
    }
    assert set(log["scenarios"]) == expected_scenarios
    assert all(log["scenarios"][name]["count"] > 0 for name in expected_scenarios)

    validation = validate_corrupted_dataframe(baseline, corrupted, log)
    assert validation["corruption_valid"] is True
    assert validation["derived_column_checks"]["summary_chars_consistent"] is True
    assert validation["derived_column_checks"]["age_days_consistent"] is True
    assert validation["derived_column_checks"]["text_for_embedding_consistent"] is True


def test_same_seed_produces_same_corrupted_data_and_scenario_selection(tmp_path: Path) -> None:
    _, baseline = make_clean_dataframe()

    first = corrupt_clean_dataframe(
        baseline,
        tmp_path / "first.json",
        config=corruption_config(),
        random_seed=7,
        run_date=RUN_DATE,
    )
    second = corrupt_clean_dataframe(
        baseline,
        tmp_path / "second.json",
        config=corruption_config(),
        random_seed=7,
        run_date=RUN_DATE,
    )

    pdt.assert_frame_equal(first.reset_index(drop=True), second.reset_index(drop=True))
    first_log = read_json(tmp_path / "first.json")
    second_log = read_json(tmp_path / "second.json")
    assert first_log["scenarios"] == second_log["scenarios"]


def test_repair_rebuilds_from_raw_and_matches_baseline(tmp_path: Path) -> None:
    raw_records, baseline = make_clean_dataframe()
    corrupted = corrupt_clean_dataframe(
        baseline,
        tmp_path / "corruption_log.json",
        config=corruption_config(),
        random_seed=11,
        run_date=RUN_DATE,
    )

    repaired = repair_from_raw_records(
        raw_records,
        reference_clean_df=baseline,
        run_date=RUN_DATE,
    )
    validation = validate_repaired_dataframe(repaired, baseline)

    assert corrupted["paper_id"].nunique() < baseline["paper_id"].nunique()
    assert validation["repair_valid"] is True
    assert validation["checks"]["content_digest_match"] is True
    assert validation["duplicate_rows"] == 0


def test_quality_checks_fail_for_corrupted_and_pass_for_repaired(tmp_path: Path) -> None:
    raw_records, baseline = make_clean_dataframe()
    settings = load_settings(project_dir=tmp_path)

    corrupted = corrupt_clean_dataframe(
        baseline,
        tmp_path / "corruption_log.json",
        config=corruption_config(),
        random_seed=19,
        run_date=RUN_DATE,
    )
    repaired = repair_from_raw_records(
        raw_records,
        reference_clean_df=baseline,
        run_date=RUN_DATE,
    )

    baseline_quality = run_data_quality_checks(baseline, settings, "baseline-test")
    corrupted_quality = run_data_quality_checks(corrupted, settings, "corrupted-test")
    repaired_quality = run_data_quality_checks(repaired, settings, "repaired-test")

    assert baseline_quality["overall"] == "pass"
    assert corrupted_quality["overall"] == "fail"
    assert "paper_id_unique" in corrupted_quality["failed_checks"]
    assert "summary_length" in corrupted_quality["failed_checks"]
    assert "noise_free" in corrupted_quality["failed_checks"]
    assert "title_not_truncated" in corrupted_quality["failed_checks"]
    assert repaired_quality["overall"] == "pass"
