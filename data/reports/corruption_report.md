# Corruption Flow - Comparison Report

## Overview

This report uses the same evaluation set for all three states. The corrupted
state is created deliberately and deterministically; the repaired state is rebuilt
from the raw Crossref artifact rather than patched from corrupted rows.

## 1. Corruption Scenarios

- **Run ID:** 840fda4a-d1e3-4795-9e22-8275e167e3b7
- **Random seed:** 42
- **Input rows:** 24
- **Output rows:** 24

| Scenario | Count | Affected paper IDs |
| --- | ---: | --- |
| Drop Latest Records | 3 | 10.1007/s00262-026-04505-w, 10.1007/s44020-026-00124-1, 10.61798/wjpe.v5i3.1127 |
| Blank Summary | 3 | 10.64223/tvj.e2026.v2.i7.a109, 10.1093/9780197900413.003.0007, 10.1093/9780197900413.003.0003 |
| Inject Noise | 3 | 10.3389/fendo.2026.1809624, 10.21462/jeltl.v11i2.2181, 10.51878/academia.v6i3.11992 |
| Truncate Title | 3 | 10.1093/9780197900413.003.0009, 10.3389/fsufs.2026.1899973, 10.1093/9780197900413.003.0005 |
| Stale Published Date | 3 | 10.5130/ccs.v18.i3.9890, 10.3389/fsufs.2026.1881632, 10.1108/ijicc-01-2026-0054 |
| Duplicate Rows | 3 | 10.51878/academia.v6i3.11992, 10.3389/fpsyg.2026.1859726, 10.1093/9780197900413.003.0004 |

## 2. Three-State Comparison

| State | Retrieval hit rate | Mean token F1 | Judge accuracy | Mean judge score | Quality | Freshness |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Baseline | 1.0000 | 1.0000 | 1.0000 | 5 | **PASS** | **PASS** |
| Corrupted | 0.5000 | 0.6244 | 0.5625 | 3.3750 | **FAIL** | **FAIL** |
| Repaired | 1.0000 | 1.0000 | 1.0000 | 5 | **PASS** | **PASS** |

## 3. Metric Changes

- **Retrieval Hit Rate:** corrupted vs baseline -0.5000; repaired vs corrupted +0.5000; repaired vs baseline +0.0000.
- **Mean Token F1:** corrupted vs baseline -0.3756; repaired vs corrupted +0.3756; repaired vs baseline +0.0000.
- **Judge Accuracy:** corrupted vs baseline -0.4375; repaired vs corrupted +0.4375; repaired vs baseline +0.0000.
- **Mean Judge Score:** corrupted vs baseline -1.6250; repaired vs corrupted +1.6250; repaired vs baseline +0.0000.

## 4. Corrupted Dataset Validation

- **Overall validation:** **PASS**

| Check | Result |
| --- | --- |
| Drop Latest Records Detected | **PASS** |
| Blank Summary Detected | **PASS** |
| Noise Detected | **PASS** |
| Truncated Title Detected | **PASS** |
| Stale Date Detected | **PASS** |
| Duplicate Rows Detected | **PASS** |
| Row Count Matches Log | **PASS** |
| Summary Chars Consistent | **PASS** |
| Age Days Consistent | **PASS** |
| Text For Embedding Consistent | **PASS** |

## 5. Repaired Dataset Validation

- **Overall validation:** **PASS**

| Check | Result |
| --- | --- |
| Row Count Match | **PASS** |
| Paper Id Set Match | **PASS** |
| Paper Id Unique | **PASS** |
| Content Digest Match | **PASS** |
| No Corruption Noise | **PASS** |
| No Truncated Titles | **PASS** |
| Summary Chars Consistent | **PASS** |
| Age Days Consistent | **PASS** |
| Text For Embedding Consistent | **PASS** |

## 6. Baseline Metrics

| Metric | Value |
| --- | --- |
| Samples | 16 |
| Retrieval Hit Rate | 1.0000 |
| Mean Token F1 | 1.0000 |
| Judge Accuracy | 1.0000 |
| Mean Judge Score | 5 |

### Ragas (optional)
| Metric | Value |
| --- | --- |
| Skipped | Set RUN_RAGAS=1 to enable the slower Ragas pass. |

## 7. Corrupted Metrics

| Metric | Value |
| --- | --- |
| Samples | 16 |
| Retrieval Hit Rate | 0.5000 |
| Mean Token F1 | 0.6244 |
| Judge Accuracy | 0.5625 |
| Mean Judge Score | 3.3750 |

### Ragas (optional)
| Metric | Value |
| --- | --- |
| Skipped | Set RUN_RAGAS=1 to enable the slower Ragas pass. |

## 8. Repaired Metrics

| Metric | Value |
| --- | --- |
| Samples | 16 |
| Retrieval Hit Rate | 1.0000 |
| Mean Token F1 | 1.0000 |
| Judge Accuracy | 1.0000 |
| Mean Judge Score | 5 |

### Ragas (optional)
| Metric | Value |
| --- | --- |
| Skipped | Set RUN_RAGAS=1 to enable the slower Ragas pass. |

## 9. Baseline Data Quality

- **Overall:** **PASS**
- **Total rows:** 24
- **Failed checks:** none

| Check | Status | Value | Detail |
| --- | --- | --- | --- |
| Row Count | **PASS** | 24 | 24 rows total |
| Paper Id Not Null | **PASS** | 24 | 0/24 rows missing or empty paper_id |
| Paper Id Unique | **PASS** | 24 | 0 rows belong to duplicated paper_id groups |
| Title Not Null | **PASS** | 24 | 0/24 rows missing or empty title |
| Summary Length | **PASS** | 24 | 0/24 rows with summary shorter than 20 chars |
| Summary Chars Consistency | **PASS** | 24 | 0/24 rows have inconsistent summary_chars |
| Published Valid | **PASS** | 24 | 0/24 rows have an invalid published date |
| Age Days Consistency | **PASS** | 24 | 0/24 rows have age_days inconsistent with published |
| Embedding Text Consistency | **PASS** | 24 | 0/24 rows have stale text_for_embedding |
| Noise Free | **PASS** | 24 | 0/24 rows contain known corruption noise |
| Title Not Truncated | **PASS** | 24 | 0/24 titles end with the corruption truncation marker |
| Freshness | **PASS** | 24 | 0/24 rows stale (> 180 days old) |

## 10. Corrupted Data Quality

- **Overall:** **FAIL**
- **Total rows:** 24
- **Failed checks:** paper_id_unique, summary_length, noise_free, title_not_truncated, freshness

| Check | Status | Value | Detail |
| --- | --- | --- | --- |
| Row Count | **PASS** | 24 | 24 rows total |
| Paper Id Not Null | **PASS** | 24 | 0/24 rows missing or empty paper_id |
| Paper Id Unique | **FAIL** | 21 | 6 rows belong to duplicated paper_id groups |
| Title Not Null | **PASS** | 24 | 0/24 rows missing or empty title |
| Summary Length | **FAIL** | 21 | 3/24 rows with summary shorter than 20 chars |
| Summary Chars Consistency | **PASS** | 24 | 0/24 rows have inconsistent summary_chars |
| Published Valid | **PASS** | 24 | 0/24 rows have an invalid published date |
| Age Days Consistency | **PASS** | 24 | 0/24 rows have age_days inconsistent with published |
| Embedding Text Consistency | **PASS** | 24 | 0/24 rows have stale text_for_embedding |
| Noise Free | **FAIL** | 20 | 4/24 rows contain known corruption noise |
| Title Not Truncated | **FAIL** | 21 | 3/24 titles end with the corruption truncation marker |
| Freshness | **FAIL** | 21 | 3/24 rows stale (> 180 days old) |

## 11. Repaired Data Quality

- **Overall:** **PASS**
- **Total rows:** 24
- **Failed checks:** none

| Check | Status | Value | Detail |
| --- | --- | --- | --- |
| Row Count | **PASS** | 24 | 24 rows total |
| Paper Id Not Null | **PASS** | 24 | 0/24 rows missing or empty paper_id |
| Paper Id Unique | **PASS** | 24 | 0 rows belong to duplicated paper_id groups |
| Title Not Null | **PASS** | 24 | 0/24 rows missing or empty title |
| Summary Length | **PASS** | 24 | 0/24 rows with summary shorter than 20 chars |
| Summary Chars Consistency | **PASS** | 24 | 0/24 rows have inconsistent summary_chars |
| Published Valid | **PASS** | 24 | 0/24 rows have an invalid published date |
| Age Days Consistency | **PASS** | 24 | 0/24 rows have age_days inconsistent with published |
| Embedding Text Consistency | **PASS** | 24 | 0/24 rows have stale text_for_embedding |
| Noise Free | **PASS** | 24 | 0/24 rows contain known corruption noise |
| Title Not Truncated | **PASS** | 24 | 0/24 titles end with the corruption truncation marker |
| Freshness | **PASS** | 24 | 0/24 rows stale (> 180 days old) |

## 12. Freshness

### Baseline

- **Is fresh:** **PASS**
- **Latest published:** 2026-08-06T00:00:00+00:00
- **Oldest published:** 2026-08-06T00:00:00+00:00
- **Stale rows:** 0 / 24
- **Threshold (days):** 180

### Corrupted

- **Is fresh:** **FAIL**
- **Latest published:** 2026-08-06T00:00:00+00:00
- **Oldest published:** 2021-08-06T00:00:00+00:00
- **Stale rows:** 3 / 24
- **Threshold (days):** 180

### Repaired

- **Is fresh:** **PASS**
- **Latest published:** 2026-08-06T00:00:00+00:00
- **Oldest published:** 2026-08-06T00:00:00+00:00
- **Stale rows:** 0 / 24
- **Threshold (days):** 180

---
_Generated comparison report for baseline / corrupted / repaired data states._
