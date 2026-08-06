from __future__ import annotations

from typing import Any

from core.utils import write_text


def _fmt_key(key: str) -> str:
    return key.replace("_", " ").replace("-", " ").strip().title()


def _status_badge(status: Any) -> str:
    if status is None:
        return "n/a"
    if isinstance(status, bool):
        return "**PASS**" if status else "**FAIL**"
    return f"**{str(status).upper()}**"


def _fmt_number(value: Any) -> Any:
    if isinstance(value, float):
        return f"{value:.4f}"
    return value


def _metrics_table(metrics: dict[str, Any]) -> str:
    if not metrics:
        return "_No metrics available._"
    rows = []
    for key, value in metrics.items():
        if key == "ragas" or isinstance(value, (dict, list)):
            continue
        rows.append(f"| {_fmt_key(key)} | {_fmt_number(value)} |")
    lines = ["| Metric | Value |", "| --- | --- |", *rows]
    ragas = metrics.get("ragas")
    if isinstance(ragas, dict) and ragas:
        lines.extend(["", "### Ragas (optional)", "| Metric | Value |", "| --- | --- |"])
        for key, value in ragas.items():
            lines.append(f"| {_fmt_key(key)} | {_fmt_number(value)} |")
    return "\n".join(lines)


def _quality_section(quality: dict[str, Any]) -> str:
    if not quality:
        return "_No quality data available._"
    lines = [
        f"- **Overall:** {_status_badge(quality.get('overall'))}",
        f"- **Total rows:** {quality.get('total_rows', 'n/a')}",
        f"- **Failed checks:** {', '.join(quality.get('failed_checks', [])) or 'none'}",
        "",
        "| Check | Status | Value | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for name, check in quality.get("checks", {}).items():
        lines.append(
            f"| {_fmt_key(name)} | {_status_badge(check.get('status'))} | "
            f"{check.get('value', '')} | {check.get('detail', '')} |"
        )
    return "\n".join(lines)


def _freshness_section(freshness: dict[str, Any]) -> str:
    if not freshness:
        return "_No freshness data available._"
    return (
        f"- **Is fresh:** {_status_badge(freshness.get('is_fresh'))}\n"
        f"- **Latest published:** {freshness.get('latest_published', 'n/a')}\n"
        f"- **Oldest published:** {freshness.get('oldest_published', 'n/a')}\n"
        f"- **Stale rows:** {freshness.get('stale_rows', 'n/a')} / "
        f"{freshness.get('total_rows', 'n/a')}\n"
        f"- **Threshold (days):** {freshness.get('threshold_days', 'n/a')}"
    )


def _source_section(source_summary: dict[str, Any]) -> str:
    if not source_summary:
        return "_No source summary available._"
    lines = []
    for key, value in source_summary.items():
        if value in (None, "", [], {}):
            continue
        if key in {"authors", "categories"} and isinstance(value, list):
            value = ", ".join(str(item) for item in value[:10])
        lines.append(f"- **{_fmt_key(key)}:** {value}")
    return "\n".join(lines) or "_No source summary available._"


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    report = f"""# Phase 1 - Baseline Pipeline Report

## 1. Source

{_source_section(source_summary)}

## 2. Evaluation Metrics

{_metrics_table(metrics)}

## 3. Data Quality

{_quality_section(quality)}

## 4. Freshness

{_freshness_section(freshness)}

---
_Generated pipeline report for the baseline (clean) dataset._
"""
    write_text(report_path, report)


def _metric_value(metrics: dict[str, Any] | None, key: str) -> Any:
    if not metrics:
        return "n/a"
    return _fmt_number(metrics.get(key, "n/a"))


def _comparison_table(
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    baseline_quality: dict[str, Any] | None,
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    baseline_freshness: dict[str, Any] | None,
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> str:
    rows = [
        (
            "Baseline",
            baseline_metrics,
            baseline_quality,
            baseline_freshness,
        ),
        (
            "Corrupted",
            corrupted_metrics,
            corrupted_quality,
            corrupted_freshness,
        ),
        (
            "Repaired",
            repaired_metrics,
            repaired_quality,
            repaired_freshness,
        ),
    ]
    lines = [
        "| State | Retrieval hit rate | Mean token F1 | Judge accuracy | Mean judge score | Quality | Freshness |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for label, metrics, quality, freshness in rows:
        lines.append(
            f"| {label} | {_metric_value(metrics, 'retrieval_hit_rate')} | "
            f"{_metric_value(metrics, 'mean_token_f1')} | "
            f"{_metric_value(metrics, 'judge_accuracy')} | "
            f"{_metric_value(metrics, 'mean_judge_score')} | "
            f"{_status_badge((quality or {}).get('overall'))} | "
            f"{_status_badge((freshness or {}).get('is_fresh'))} |"
        )
    return "\n".join(lines)


def _corruption_scenarios_section(corruption_log: dict[str, Any] | None) -> str:
    if not corruption_log:
        return "_No corruption log available._"
    lines = [
        f"- **Run ID:** {corruption_log.get('run_id', 'n/a')}",
        f"- **Random seed:** {corruption_log.get('random_seed', 'n/a')}",
        f"- **Input rows:** {corruption_log.get('input_row_count', 'n/a')}",
        f"- **Output rows:** {corruption_log.get('output_row_count', 'n/a')}",
        "",
        "| Scenario | Count | Affected paper IDs |",
        "| --- | ---: | --- |",
    ]
    for scenario, payload in corruption_log.get("scenarios", {}).items():
        paper_ids = payload.get("paper_ids", [])
        preview = ", ".join(str(item) for item in paper_ids[:8])
        if len(paper_ids) > 8:
            preview += f", ... (+{len(paper_ids) - 8})"
        lines.append(
            f"| {_fmt_key(scenario)} | {payload.get('count', 0)} | {preview or 'none'} |"
        )
    return "\n".join(lines)


def _validation_section(validation: dict[str, Any] | None) -> str:
    if not validation:
        return "_No validation artifact available._"
    valid = validation.get("corruption_valid")
    if valid is None:
        valid = validation.get("repair_valid")
    lines = [f"- **Overall validation:** {_status_badge(valid)}", ""]

    checks = validation.get("scenario_checks") or validation.get("checks") or {}
    lines.extend(["| Check | Result |", "| --- | --- |"])
    for name, value in checks.items():
        lines.append(f"| {_fmt_key(name)} | {_status_badge(value)} |")

    derived = validation.get("derived_column_checks", {})
    for name, value in derived.items():
        if name.endswith("_consistent"):
            lines.append(f"| {_fmt_key(name)} | {_status_badge(value)} |")
    return "\n".join(lines)


def _metric_delta_summary(
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
) -> str:
    lines = []
    for key in (
        "retrieval_hit_rate",
        "mean_token_f1",
        "judge_accuracy",
        "mean_judge_score",
    ):
        baseline = baseline_metrics.get(key)
        corrupted = corrupted_metrics.get(key)
        repaired = repaired_metrics.get(key)
        if not all(isinstance(value, (int, float)) for value in (baseline, corrupted, repaired)):
            continue
        corruption_delta = corrupted - baseline
        repair_delta = repaired - corrupted
        recovery_gap = repaired - baseline
        lines.append(
            f"- **{_fmt_key(key)}:** corrupted vs baseline {corruption_delta:+.4f}; "
            f"repaired vs corrupted {repair_delta:+.4f}; repaired vs baseline {recovery_gap:+.4f}."
        )
    return "\n".join(lines) or "_Metric deltas are unavailable._"


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    *,
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
    corruption_log: dict[str, Any] | None = None,
    corrupted_validation: dict[str, Any] | None = None,
    repaired_validation: dict[str, Any] | None = None,
) -> None:
    """Write the before/corrupted/repaired comparison report."""
    report = f"""# Corruption Flow - Comparison Report

## Overview

This report uses the same evaluation set for all three states. The corrupted
state is created deliberately and deterministically; the repaired state is rebuilt
from the raw Crossref artifact rather than patched from corrupted rows.

## 1. Corruption Scenarios

{_corruption_scenarios_section(corruption_log)}

## 2. Three-State Comparison

{_comparison_table(
    baseline_metrics,
    corrupted_metrics,
    repaired_metrics,
    baseline_quality,
    corrupted_quality,
    repaired_quality,
    baseline_freshness,
    corrupted_freshness,
    repaired_freshness,
)}

## 3. Metric Changes

{_metric_delta_summary(baseline_metrics, corrupted_metrics, repaired_metrics)}

## 4. Corrupted Dataset Validation

{_validation_section(corrupted_validation)}

## 5. Repaired Dataset Validation

{_validation_section(repaired_validation)}

## 6. Baseline Metrics

{_metrics_table(baseline_metrics or {})}

## 7. Corrupted Metrics

{_metrics_table(corrupted_metrics or {})}

## 8. Repaired Metrics

{_metrics_table(repaired_metrics or {})}

## 9. Baseline Data Quality

{_quality_section(baseline_quality or {})}

## 10. Corrupted Data Quality

{_quality_section(corrupted_quality or {})}

## 11. Repaired Data Quality

{_quality_section(repaired_quality or {})}

## 12. Freshness

### Baseline

{_freshness_section(baseline_freshness or {})}

### Corrupted

{_freshness_section(corrupted_freshness or {})}

### Repaired

{_freshness_section(repaired_freshness or {})}

---
_Generated comparison report for baseline / corrupted / repaired data states._
"""
    write_text(report_path, report)
