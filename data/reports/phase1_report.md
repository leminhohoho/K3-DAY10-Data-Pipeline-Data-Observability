# Phase 1 - Baseline Pipeline Report

## 1. Source

- **Source Api:** Crossref REST API
- **Source Query:** agentic retrieval augmented generation large language model
- **Source Filter:** from-pub-date:2026-02-07,until-pub-date:2026-08-06,has-abstract:true
- **Source Mode:** cached_raw_snapshot
- **Raw Records:** 24
- **Clean Rows:** 24
- **Embedding Model:** sentence-transformers/all-MiniLM-L6-v2
- **Collection Name:** papers-baseline
- **Top K:** 4
- **Llm Provider:** gemini
- **Llm Model:** gemini-flash-lite-latest
- **Agent Demo Status:** ok
- **Agent Demo Artifact:** data/results/agent_demo_answers.json
- **Run Started At:** 2026-08-06T05:55:08.969931+00:00

## 2. Evaluation Metrics

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

## 3. Data Quality

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

## 4. Freshness

- **Is fresh:** **PASS**
- **Latest published:** 2026-08-06T00:00:00+00:00
- **Oldest published:** 2026-08-06T00:00:00+00:00
- **Stale rows:** 0 / 24
- **Threshold (days):** 180

---
_Generated pipeline report for the baseline (clean) dataset._
