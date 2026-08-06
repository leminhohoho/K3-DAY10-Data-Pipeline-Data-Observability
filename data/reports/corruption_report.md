# Corruption Flow - Comparison Report

## Overview

This report uses the same evaluation set for all three states. The corrupted
state is created deliberately and deterministically; the repaired state is rebuilt
from the raw Crossref artifact rather than patched from corrupted rows.

## 1. Corruption Scenarios

- **Run ID:** ca74d883-0c08-4bd6-8667-c81241345282
- **Random seed:** 42
- **Input rows:** 23
- **Output rows:** 22

| Scenario | Count | Affected paper IDs |
| --- | ---: | --- |
| Drop Latest Records | 3 | 10.1007/s10278-026-02086-9, 10.2196/preprints.106157, 10.3390/buildings16132637 |
| Blank Summary | 2 | 10.47576/2949-1894.2026.7.7.023, 10.21079/11681/50309 |
| Inject Noise | 2 | 10.1051/e3sconf/202668908004, 10.20944/preprints202602.0996.v1 |
| Truncate Title | 2 | 10.2139/ssrn.6386988, 10.7717/peerj-cs.3882 |
| Stale Published Date | 2 | 10.36085/jsai.v9i1.9632, 10.21203/rs.3.rs-10012178/v1 |
| Duplicate Rows | 2 | 10.36085/jsai.v9i1.9632, 10.21203/rs.3.rs-10012178/v1 |

## 2. Three-State Comparison

| State | Retrieval hit rate | Mean token F1 | Judge accuracy | Mean judge score | Quality | Freshness |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Baseline | 1.0000 | 0.1296 | 0.9375 | 4.8750 | **PASS** | **PASS** |
| Corrupted | 0.2500 | 0.0686 | 0.1875 | 1.7500 | **FAIL** | **FAIL** |
| Repaired | 1.0000 | 0.0907 | 0.9375 | 4.8125 | **PASS** | **PASS** |

## 3. Metric Changes

- **Retrieval Hit Rate:** corrupted vs baseline -0.7500; repaired vs corrupted +0.7500; repaired vs baseline +0.0000.
- **Mean Token F1:** corrupted vs baseline -0.0609; repaired vs corrupted +0.0221; repaired vs baseline -0.0389.
- **Judge Accuracy:** corrupted vs baseline -0.7500; repaired vs corrupted +0.7500; repaired vs baseline +0.0000.
- **Mean Judge Score:** corrupted vs baseline -3.1250; repaired vs corrupted +3.0625; repaired vs baseline -0.0625.

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
| Answer Mode | agent |
| Retrieval Hit Rate | 1.0000 |
| Mean Token F1 | 0.1296 |
| Judge Accuracy | 0.9375 |
| Mean Judge Score | 4.8750 |

### Ragas (optional)
| Metric | Value |
| --- | --- |
| Skipped | Set RUN_RAGAS=1 to enable the slower Ragas pass. |

## 7. Corrupted Metrics

| Metric | Value |
| --- | --- |
| Samples | 16 |
| Answer Mode | agent |
| Retrieval Hit Rate | 0.2500 |
| Mean Token F1 | 0.0686 |
| Judge Accuracy | 0.1875 |
| Mean Judge Score | 1.7500 |

### Ragas (optional)
| Metric | Value |
| --- | --- |
| Skipped | Set RUN_RAGAS=1 to enable the slower Ragas pass. |

## 8. Repaired Metrics

| Metric | Value |
| --- | --- |
| Samples | 16 |
| Answer Mode | agent |
| Retrieval Hit Rate | 1.0000 |
| Mean Token F1 | 0.0907 |
| Judge Accuracy | 0.9375 |
| Mean Judge Score | 4.8125 |

### Ragas (optional)
| Metric | Value |
| --- | --- |
| Skipped | Set RUN_RAGAS=1 to enable the slower Ragas pass. |

## 9. Baseline Data Quality

- **Overall:** **PASS**
- **Total rows:** 23
- **Failed checks:** none

| Check | Status | Value | Detail |
| --- | --- | --- | --- |
| Row Count | **PASS** | 23 | 23 rows total |
| Record Coverage | **PASS** | 23 | 0/23 expected paper_ids missing from corpus |
| Paper Id Not Null | **PASS** | 23 | 0/23 rows missing or empty paper_id |
| Paper Id Unique | **PASS** | 23 | 0 rows belong to duplicated paper_id groups |
| Title Not Null | **PASS** | 23 | 0/23 rows missing or empty title |
| Summary Length | **PASS** | 23 | 0/23 rows with summary shorter than 20 chars |
| Summary Chars Consistency | **PASS** | 23 | 0/23 rows have inconsistent summary_chars |
| Published Valid | **PASS** | 23 | 0/23 rows have an invalid published date |
| Age Days Consistency | **PASS** | 23 | 0/23 rows have age_days inconsistent with published |
| Embedding Text Consistency | **PASS** | 23 | 0/23 rows have stale text_for_embedding |
| Noise Free | **PASS** | 23 | 0/23 rows contain known corruption noise |
| Title Not Truncated | **PASS** | 23 | 0/23 titles end with the corruption truncation marker |
| Freshness | **PASS** | 23 | 0/23 rows stale (> 365 days old) |

## 10. Corrupted Data Quality

- **Overall:** **FAIL**
- **Total rows:** 22
- **Failed checks:** record_coverage, paper_id_unique, summary_length, noise_free, title_not_truncated, freshness

| Check | Status | Value | Detail |
| --- | --- | --- | --- |
| Row Count | **PASS** | 22 | 22 rows total |
| Record Coverage | **FAIL** | 20 | 3/23 expected paper_ids missing from corpus: 10.1007/s10278-026-02086-9, 10.2196/preprints.106157, 10.3390/buildings16132637 |
| Paper Id Not Null | **PASS** | 22 | 0/22 rows missing or empty paper_id |
| Paper Id Unique | **FAIL** | 20 | 4 rows belong to duplicated paper_id groups |
| Title Not Null | **PASS** | 22 | 0/22 rows missing or empty title |
| Summary Length | **FAIL** | 20 | 2/22 rows with summary shorter than 20 chars |
| Summary Chars Consistency | **PASS** | 22 | 0/22 rows have inconsistent summary_chars |
| Published Valid | **PASS** | 22 | 0/22 rows have an invalid published date |
| Age Days Consistency | **PASS** | 22 | 0/22 rows have age_days inconsistent with published |
| Embedding Text Consistency | **PASS** | 22 | 0/22 rows have stale text_for_embedding |
| Noise Free | **FAIL** | 20 | 2/22 rows contain known corruption noise |
| Title Not Truncated | **FAIL** | 20 | 2/22 titles end with the corruption truncation marker |
| Freshness | **FAIL** | 18 | 4/22 rows stale (> 365 days old) |

## 11. Repaired Data Quality

- **Overall:** **PASS**
- **Total rows:** 23
- **Failed checks:** none

| Check | Status | Value | Detail |
| --- | --- | --- | --- |
| Row Count | **PASS** | 23 | 23 rows total |
| Record Coverage | **PASS** | 23 | 0/23 expected paper_ids missing from corpus |
| Paper Id Not Null | **PASS** | 23 | 0/23 rows missing or empty paper_id |
| Paper Id Unique | **PASS** | 23 | 0 rows belong to duplicated paper_id groups |
| Title Not Null | **PASS** | 23 | 0/23 rows missing or empty title |
| Summary Length | **PASS** | 23 | 0/23 rows with summary shorter than 20 chars |
| Summary Chars Consistency | **PASS** | 23 | 0/23 rows have inconsistent summary_chars |
| Published Valid | **PASS** | 23 | 0/23 rows have an invalid published date |
| Age Days Consistency | **PASS** | 23 | 0/23 rows have age_days inconsistent with published |
| Embedding Text Consistency | **PASS** | 23 | 0/23 rows have stale text_for_embedding |
| Noise Free | **PASS** | 23 | 0/23 rows contain known corruption noise |
| Title Not Truncated | **PASS** | 23 | 0/23 titles end with the corruption truncation marker |
| Freshness | **PASS** | 23 | 0/23 rows stale (> 365 days old) |

## 12. Freshness

### Baseline

- **Is fresh:** **PASS**
- **Latest published:** 2026-07-13T00:00:00+00:00
- **Oldest published:** 2025-08-27T00:00:00+00:00
- **Stale rows:** 0 / 23
- **Threshold (days):** 365

### Corrupted

- **Is fresh:** **FAIL**
- **Latest published:** 2026-07-01T00:00:00+00:00
- **Oldest published:** 2020-12-30T00:00:00+00:00
- **Stale rows:** 4 / 22
- **Threshold (days):** 365

### Repaired

- **Is fresh:** **PASS**
- **Latest published:** 2026-07-13T00:00:00+00:00
- **Oldest published:** 2025-08-27T00:00:00+00:00
- **Stale rows:** 0 / 23
- **Threshold (days):** 365

---
_Generated comparison report for baseline / corrupted / repaired data states._
