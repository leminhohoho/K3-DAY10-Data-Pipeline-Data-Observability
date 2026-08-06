from __future__ import annotations

from typing import Any

from core.utils import write_text


def _fmt_key(key: str) -> str:
    return key.replace("_", " ").replace("-", " ").strip().title()


def _status_badge(status: Any) -> str:
    return f"**{str(status).upper()}**" if status else status


def _metrics_table(metrics: dict[str, Any]) -> str:
    if not metrics:
        return "_No metrics available._"
    rows = []
    for key, value in metrics.items():
        if key == "ragas":
            continue
        rows.append(f"| {_fmt_key(key)} | {value} |")
    lines = ["| Metric | Value |", "| --- | --- |", *rows]
    ragas = metrics.get("ragas")
    if isinstance(ragas, dict) and ragas:
        lines.append("")
        lines.append("### Ragas (optional)")
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
        for key, value in ragas.items():
            lines.append(f"| {_fmt_key(key)} | {value} |")
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
    checks = quality.get("checks", {})
    for name, check in checks.items():
        lines.append(
            f"| {_fmt_key(name)} | {_status_badge(check.get('status'))} | {check.get('value', '')} | {check.get('detail', '')} |"
        )
    return "\n".join(lines)


def _freshness_section(freshness: dict[str, Any]) -> str:
    if not freshness:
        return "_No freshness data available._"
    return (
        f"- **Is fresh:** {_status_badge(freshness.get('is_fresh'))}\n"
        f"- **Latest published:** {freshness.get('latest_published', 'n/a')}\n"
        f"- **Oldest published:** {freshness.get('oldest_published', 'n/a')}\n"
        f"- **Stale rows:** {freshness.get('stale_rows', 'n/a')} / {freshness.get('total_rows', 'n/a')}\n"
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
    """TODO(student): viet markdown report cho baseline phase.

    Pseudo-code:
    1. Gom source summary.
    2. In metrics retrieval/evaluation.
    3. In data quality va freshness.
    4. Ghi markdown vao report_path.
    """
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


def _state_comparison(
    state_label: str,
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> str:
    metrics_value = metrics.get("retrieval_hit_rate", "n/a") if metrics else "n/a"
    quality_status = quality.get("overall", "n/a") if quality else "n/a"
    fresh_status = freshness.get("is_fresh", "n/a") if freshness else "n/a"
    return (
        f"| {state_label} | {metrics_value} | {quality_status} | {fresh_status} |"
    )


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """TODO(student): viet markdown report so sanh baseline/corrupted/repaired."""
    report = f"""# Corruption Flow - Comparison Report

## Overview

This report compares the baseline (clean), corrupted (deliberately degraded) and
repaired datasets to demonstrate that data quality directly affects the RAG agent.

## 1. Comparison Table

| State | Retrieval hit rate | Quality | Freshness |
| --- | --- | --- | --- |
{_state_comparison("Baseline", baseline_metrics, None, None)}
{_state_comparison("Corrupted", corrupted_metrics, corrupted_quality, corrupted_freshness)}
{_state_comparison("Repaired", repaired_metrics, repaired_quality, repaired_freshness)}

## 2. Baseline Metrics

{_metrics_table(baseline_metrics or {})}

## 3. Corrupted Metrics

{_metrics_table(corrupted_metrics or {})}

## 4. Repaired Metrics

{_metrics_table(repaired_metrics or {})}

## 5. Corrupted Data Quality

{_quality_section(corrupted_quality or {})}

## 6. Repaired Data Quality

{_quality_section(repaired_quality or {})}

## 7. Freshness: Corrupted vs Repaired

### Corrupted

{_freshness_section(corrupted_freshness or {})}

### Repaired

{_freshness_section(repaired_freshness or {})}

---
_Generated comparison report for the corruption flow (baseline / corrupted / repaired)._
"""
    write_text(report_path, report)
