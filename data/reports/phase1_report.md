# Phase 1 - Baseline Pipeline Report

## 1. Source

- **Source Api:** Crossref REST API
- **Source Query:** agentic retrieval augmented generation large language model
- **Source Filter:** from-pub-date:2025-08-06,until-pub-date:2026-08-06,has-abstract:true
- **Source Mode:** fetched
- **Raw Records:** 23
- **Clean Rows:** 23
- **Embedding Model:** sentence-transformers/all-MiniLM-L6-v2
- **Collection Name:** papers-baseline
- **Top K:** 4
- **Llm Provider:** gemini
- **Llm Model:** gemini-flash-lite-latest
- **Agent Demo Status:** ok
- **Agent Demo Artifact:** data/results/agent_demo_answers.json
- **Run Started At:** 2026-08-06T09:53:14.365205+00:00

## 2. Evaluation Metrics

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

## 3. Data Quality

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

## 4. Freshness

- **Is fresh:** **PASS**
- **Latest published:** 2026-07-13T00:00:00+00:00
- **Oldest published:** 2025-08-27T00:00:00+00:00
- **Stale rows:** 0 / 23
- **Threshold (days):** 365

---
_Generated pipeline report for the baseline (clean) dataset._
