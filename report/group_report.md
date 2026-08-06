# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                                                                |
| ------------------ | ------------------------------------------------------------------------ |
| Khóa/Lớp         | K3                                                                       |
| Tên nhóm         |                                                                          |
| Repository         | https://github.com/leminhohoho/K3-DAY10-Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06                                                               |

### Thành viên và phân công

| STT | Họ và tên        | MSSV        | Vai trò chính                       | Module/deliverable sở hữu                                                                                                   |
| --: | ------------------- | :---------- | ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
|   1 | Bùi Hoàng Vương | 2A202601553 | Source owner                          | `src/ingestion/crossref.py`; raw response và raw records trong `data/raw/`                                               |
|   2 | Đặng Tiến Thành | 2A202601305 | Cleaning & test-set owner             | `src/ingestion/cleaning.py`, `src/evaluation/testset.py`; cleaned dataset và `data/eval/test_set.json`                 |
|   3 | Lê Minh Nguyên    | 2A202601045 | Observability owner                   | `src/observability/quality.py`, `src/observability/reporting.py`; artifacts trong `data/quality/` và `data/reports/` |
|   4 | Nguyễn Chí Quang  | 2A202601932 | Corruption & repair owner             | `src/ingestion/corruption.py`, `tests/test_corruption.py`; `data/results/corruption_log.json` và hai file validation   |
|   5 | Ngô Thành Đạt   | 2A202601323 | Pipeline integration & evidence owner | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`; run summaries và toàn bộ metrics ba trạng thái        |

> Ghi chú phạm vi: trong commit `3164b36`, thành viên 4 có mở rộng thêm `quality.py` và `reporting.py` (vốn thuộc thành viên 3) để bổ sung các check về derived columns và các mục mới trong comparison report. Hai bên đã thống nhất trước khi merge.

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm hoàn thành toàn bộ hai pha của bài lab. Baseline pipeline chạy end-to-end từ Crossref API tới báo cáo, sinh đầy đủ raw response/records, cleaned dataset 24 dòng với schema 16 cột, embedding manifest 24 document trong ChromaDB, evaluation set 16 câu cân bằng 4 loại câu hỏi, metrics baseline, 12 data quality checks, freshness report và `phase1_report.md`. Agent LangChain chạy thật trên corpus với hai tool và đạt `agent_status: ok` 4/4 câu.

Corruption flow tạo 6 loại lỗi có chủ đích (seed 42, mỗi loại 3 dòng): xoá record mới nhất, làm rỗng summary, chèn noise, cắt title, làm cũ ngày xuất bản và thêm duplicate. Corruption ảnh hưởng rõ nhất là **xoá record mới nhất** — hai trong bốn paper của test set biến mất khỏi corpus, kéo `retrieval_hit_rate` từ 1.0000 xuống đúng 0.5000 và `judge_accuracy` từ 1.0000 xuống 0.5625. Data quality chuyển từ PASS sang FAIL ở 5/12 check và freshness mất trạng thái fresh với 3/24 dòng stale.

Repair dựng lại corpus từ `data/raw/crossref_records.json` thay vì vá từng dòng hỏng, và phục hồi **toàn bộ** chỉ số: cả bốn metric agent quay về đúng mức baseline (chênh lệch 0.0000), 12/12 quality check PASS, freshness trở lại `is_fresh: true`, và `repaired_dataset_validation.json` xác nhận `repair_valid: True` bằng digest nội dung khớp baseline.

Giới hạn quan trọng nhất còn lại: cả 24 paper trong corpus đều có cùng `published = 2026-08-06`, khiến `token_f1` của nhóm câu hỏi về ngày vẫn đạt 1.000 ngay cả khi retrieval trả sai tài liệu. Điều này làm mức thiệt hại do corruption bị phản ánh nhẹ hơn thực tế ở metric tổng.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (query.bibliographic + from/until-pub-date + has-abstract)
    -> data/raw/crossref_response.json, data/raw/crossref_records.json
    -> cleaning: chuẩn hoá, loại record không hợp lệ, dedupe theo paper_id,
       sinh text_for_embedding và age_days -> data/clean/
    -> MiniLM embeddings -> ChromaDB collection papers-baseline -> data/embeddings/
    -> evaluation trên data/eval/test_set.json -> data/results/baseline_metrics.json
    -> quality (12 checks) + freshness -> data/quality/ -> data/reports/phase1_report.md
    -> corruption (6 scenarios, seed 42) -> data/clean/papers_clean_corrupted.*
    -> re-index (papers-corrupted) + re-evaluate trên CÙNG test set
    -> repair_from_raw_records() từ data/raw/ -> re-index (papers-repaired) + re-evaluate
    -> data/reports/corruption_report.md + data/results/corruption_run_summary.json
```

### Trách nhiệm của từng khối

| Khối             | Input                                  | Xử lý chính                                                                                                                                                                                         | Output/artifact                                                                  | Owner                           |
| ----------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------- | ------------------------------- |
| Ingestion         | Crossref REST API                      | Fetch có retry/backoff cho 429 và 5xx, honor`Retry-After`; parse JATS abstract; chuẩn hoá `date-parts`; dedupe theo DOI                                                                        | `data/raw/crossref_response.json`, `data/raw/crossref_records.json`          | Thành viên 1                  |
| Cleaning          | `list[PaperRecord]`                  | Loại record thiếu id/title/summary/ngày hợp lệ hoặc có ngày tương lai; giữ bản`updated` mới nhất khi trùng `paper_id`; sinh `text_for_embedding`, `summary_chars`, `age_days` | `data/clean/papers_clean.csv`, `.json` (24 dòng, 16 cột)                   | Thành viên 2                  |
| Embedding/index   | `text_for_embedding`                 | `all-MiniLM-L6-v2`, ChromaDB persistent, HNSW cosine, 3 collection tách biệt                                                                                                                       | `data/embeddings/papers_embeddings*.json`, `data/chroma/`                    | Starter + Thành viên 5        |
| Evaluation        | Cleaned dataset + index                | Sinh 16 câu hỏi 4 loại; đo`retrieval_hit_rate`, `mean_token_f1`; LLM judge cho `judge_accuracy`, `mean_judge_score`                                                                        | `data/eval/test_set.json`, `data/results/*_metrics.json`, `*_answers.json` | Thành viên 2 + Thành viên 5 |
| Observability     | Dataframe từng trạng thái           | 12 data quality checks gồm cả nhất quán derived columns; freshness theo ngưỡng 180 ngày; sinh Markdown report                                                                                   | `data/quality/*.json`, `data/reports/*.md`                                   | Thành viên 3                  |
| Corruption/repair | Baseline clean dataframe + raw records | 6 scenario theo seed; log JSON có metadata,`scenarios` và `events`; repair dựng lại từ raw; validate corrupted và repaired                                                                   | `data/results/corruption_log.json`, `data/quality/*_dataset_validation.json` | Thành viên 4                  |
| Orchestration     | Toàn bộ module trên                 | Thứ tự chạy, validate contract giữa các bước, giữ nguyên test set cho 3 trạng thái, agent demo, run summary                                                                                 | `phase1_run_summary.json`, `corruption_run_summary.json`                     | Thành viên 5                  |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng                                  |
| ---------------------------- | ---------------------------------------------------- |
| `LLM_PROVIDER`             | `gemini`                                           |
| `LLM_MODEL`                | `gemini-flash-lite-latest`                         |
| Embedding model              | `sentence-transformers/all-MiniLM-L6-v2`           |
| Số lượng Crossref records | `max_results = 24`; thực nhận 24 record hợp lệ |
| Retrieval`top_k`           | `4`                                                |
| Freshness threshold          | `180` ngày                                        |
| Random seed                  | `42` (corruption)                                  |

Không dán nội dung API key hoặc file `.env` vào báo cáo. `.env` đã nằm trong `.gitignore`.

> Lưu ý về model: `gemini-2.5-flash` trong `.env.example` gốc trả `404 NOT_FOUND` với tài khoản mới ("no longer available to new users"). `gemini-flash-latest` gọi được nhưng free tier chỉ 20 request/ngày, không đủ cho ~60 lần gọi LLM của cả hai flow. Nhóm dùng `gemini-flash-lite-latest`.

### Lệnh cài đặt

```bash
python -m pip install -e .
```

### Lệnh chạy

Baseline:

```bash
python script/run_phase1.py
```

Corruption flow:

```bash
python script/run_corruption_flow.py
```

Test:

```bash
python -m pytest tests/ -q
```

### Kết quả tái hiện

| Lệnh             | Trạng thái             | Thời điểm chạy gần nhất | Bằng chứng                                                                        |
| ----------------- | ------------------------ | ----------------------------- | ----------------------------------------------------------------------------------- |
| Baseline pipeline | Thành công             | 2026-08-06                    | `data/results/phase1_run_summary.json`, `data/reports/phase1_report.md`         |
| Corruption flow   | Thành công             | 2026-08-06                    | `data/results/corruption_run_summary.json`, `data/reports/corruption_report.md` |
| `pytest tests/` | Thành công — 4 passed | 2026-08-06                    | `tests/test_corruption.py`                                                        |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                                                                                                                                                                                                                   |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source                      | Crossref REST API —`https://api.crossref.org/works`                                                                                                                                                                      |
| Query/filter                | `query.bibliographic = "agentic retrieval augmented generation large language model"`; `filter = from-pub-date:2026-02-07,until-pub-date:2026-08-06,has-abstract:true`; `sort=published`, `order=desc`, `rows=24` |
| Thời điểm lấy dữ liệu | 2026-08-06                                                                                                                                                                                                                  |
| Số record nhận được    | 24 item trả về, 24 record hợp lệ sau parse                                                                                                                                                                              |
| Cơ chế retry/backoff      | Tối đa 4 lần cho status 429/500/502/503/504; ưu tiên header`Retry-After`, mặc định backoff tuyến tính 2s × lần thử; `User-Agent` định danh rõ                                                           |

### Raw và clean schema

| Trường                                                    | Kiểu dữ liệu | Bắt buộc? | Ý nghĩa                                                                                         | Xử lý khi thiếu/sai                                        |
| ----------------------------------------------------------- | --------------- | ----------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `paper_id`                                                | str             | Có         | DOI viết thường, dùng làm document ID xuyên suốt                                           | Loại record; trùng thì giữ bản có`updated` mới nhất |
| `title`                                                   | str             | Có         | Tiêu đề đã unescape HTML và gộp khoảng trắng                                             | Loại record nếu rỗng                                       |
| `summary`                                                 | str             | Có         | Abstract đã bóc JATS XML và bỏ tiền tố "Abstract"                                          | Loại record nếu rỗng                                       |
| `published`                                               | str (ISO date)  | Có         | Ngày xuất bản từ`published`/`published-online`/`published-print`/`issued`/`created` | Loại nếu không parse được hoặc lớn hơn ngày chạy   |
| `updated`                                                 | str (ISO date)  | Không      | Lấy từ`indexed`/`deposited`/`created`                                                     | Fallback về`published`                                     |
| `authors`, `authors_joined`                             | list[str], str  | Không      | Tác giả, dedupe giữ thứ tự nguồn                                                            | Để rỗng, bỏ khỏi`text_for_embedding`                   |
| `categories`, `categories_joined`                       | list[str], str  | Không      | `subject`; fallback `container-title` rồi `type`                                           | Để rỗng                                                    |
| `summary_chars`                                           | int             | Có         | Độ dài summary, dùng cho quality check                                                        | Tính lại từ`summary`                                     |
| `age_days`                                                | int             | Có         | Số ngày từ`published` tới ngày chạy, dùng cho freshness                                  | Tính lại từ`published`                                   |
| `text_for_embedding`                                      | str             | Có         | Nội dung đưa vào embedding                                                                    | Loại record nếu rỗng (chặn ở`phase1.py`)               |
| `abs_url`, `pdf_url`, `comment`, `primary_category` | str             | Không      | Metadata bổ sung                                                                                 | Để rỗng                                                    |

### Quy tắc cleaning

| Quy tắc                                                                                  | Quality dimension |                                           Số record bị tác động | Cách xác minh                                                                                    |
| ----------------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------------: | -------------------------------------------------------------------------------------------------- |
| Loại record thiếu`paper_id`/`title`/`summary`/ngày hợp lệ                      | Completeness      |                            0 (nguồn đã lọc`has-abstract:true`) | `data_quality_baseline.json`: `paper_id_not_null`, `title_not_null` đều PASS               |
| Loại record có`published` lớn hơn ngày chạy                                       | Validity          | 0 sau khi thêm`until-pub-date` (trước đó là **22/22**) | Xem mục 11                                                                                        |
| Dedupe theo`paper_id`, giữ bản `updated` mới nhất                                 | Uniqueness        |                                             0 dòng trùng còn lại | `paper_id_unique` PASS, `unique_key_count = 24`                                                |
| Chuẩn hoá whitespace, unescape HTML, bóc thẻ markup                                   | Consistency       |                                                   Toàn bộ 24 dòng | `noise_free` PASS ở baseline                                                                    |
| Sinh lại`summary_chars`, `age_days`, `text_for_embedding` từ dữ liệu đã sạch | Accuracy          |                                                   Toàn bộ 24 dòng | `summary_chars_consistency`, `age_days_consistency`, `embedding_text_consistency` đều PASS |

Giải thích cách nhóm tạo `text_for_embedding`, document ID và `age_days`:

`text_for_embedding` ghép các trường có nhãn theo thứ tự cố định: `Title:`, `Summary:`, rồi `Authors:` và `Categories:` chỉ khi không rỗng, cuối cùng là `Published:`. Giữ nhãn giúp embedding phân biệt được ngữ cảnh từng trường thay vì trộn thành một khối text phẳng, và bỏ qua trường rỗng để tránh dạy model rằng "Authors:" thường theo sau bởi khoảng trắng.

Document ID là DOI viết thường. DOI được chọn vì nó ổn định theo thời gian và duy nhất trên toàn Crossref, nên `ground_truth_doc_ids` trong test set vẫn trỏ đúng sau khi corrupt rồi repair. Chroma dùng `record_id = f"{paper_id}::{index}"` để duplicate row vẫn nạp được mà không đụng khoá.

`age_days` là hiệu giữa ngày chạy (đã normalize về 00:00 UTC) và `published`. Nó là cột trung gian cho freshness check: so `age_days` với ngưỡng 180 rẻ hơn và ổn định hơn so với parse lại ngày ở mỗi lần kiểm tra. Ở corruption flow, ngày chạy được suy ngược từ `published + age_days` của baseline để repaired khớp baseline tuyệt đối.

## 6. Evaluation setup

| Thành phần                             | Cấu hình thực tế                                                                                                                               |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Số câu hỏi                            | 16                                                                                                                                                 |
| Các`question_type`                    | `summary` (4), `authors` (4), `date` (4), `categories` (4)                                                                                 |
| Ground-truth document ID                 | `ground_truth_doc_ids = [paper_id]`, lấy trực tiếp từ dòng sinh ra câu hỏi; `phase1.py` chặn nếu có ID không tồn tại trong corpus |
| Embedding model                          | `sentence-transformers/all-MiniLM-L6-v2`                                                                                                         |
| Vector store/collection                  | ChromaDB persistent tại`data/chroma/`, HNSW cosine; `papers-baseline` / `papers-corrupted` / `papers-repaired`                            |
| Retrieval`top_k`                       | 4                                                                                                                                                  |
| LLM provider/model                       | `gemini` / `gemini-flash-lite-latest`; LLM judge chấm thật 48/48 lượt trên cả ba trạng thái                                            |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` — đường dẫn được ghi lại trong `corruption_run_summary.json`                                                |

Giải thích vì sao test set được giữ nguyên khi đánh giá baseline, corrupted và repaired:

Vì mục tiêu là đo tác động của **một** biến duy nhất là chất lượng dữ liệu. Nếu sinh lại test set cho mỗi trạng thái, độ khó của bộ câu hỏi sẽ thay đổi theo dữ liệu và ta không tách được "agent tệ đi vì corpus bẩn" khỏi "bộ câu hỏi lần này khó hơn". Đặc biệt với corruption có xoá record: test set sinh lại từ corpus đã bị xoá sẽ không bao giờ hỏi về tài liệu đã mất, và corruption sẽ trông như vô hại. Giữ nguyên test set chính là thứ làm cho `retrieval_hit_rate` rơi xuống 0.5000 — con số đó có nghĩa vì nó nói rằng 8/16 câu hỏi đã mất tài liệu nguồn.

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                | Trạng thái | Ghi chú                                                          |
| ------------------------ | -------------------------------------- | ------------ | ----------------------------------------------------------------- |
| Raw response/records     | `data/raw/`                          | Có          | `crossref_response.json`, `crossref_records.json` (24 record) |
| Cleaned dataset          | `data/clean/`                        | Có          | CSV + JSON, 24 dòng × 16 cột                                   |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/` | Có          | Manifest 24 document, collection`papers-baseline`               |
| Evaluation set           | `data/eval/test_set.json`            | Có          | 16 mẫu, 4 loại câu hỏi                                        |
| Baseline metrics         | `data/results/baseline_metrics.json` | Có          | Kèm`baseline_answers.json` và `agent_demo_answers.json`     |
| Quality/freshness        | `data/quality/`                      | Có          | `data_quality_baseline.json`, `freshness_report.json`         |
| Baseline report          | `data/reports/phase1_report.md`      | Có          | Kèm`phase1_run_summary.json`                                   |

### Baseline metrics

| Metric                 | Giá trị | Diễn giải                                                                                 |
| ---------------------- | --------: | ------------------------------------------------------------------------------------------- |
| `retrieval_hit_rate` |    1.0000 | Cả 16/16 câu đều có ground-truth document trong top-4                                  |
| `mean_token_f1`      |    1.0000 | Câu trả lời trích trực tiếp từ metadata nên trùng khớp ground truth               |
| `judge_accuracy`     |    1.0000 | LLM judge xác nhận 16/16 câu đúng về mặt nội dung                                   |
| `mean_judge_score`   |      5.00 | Điểm tuyệt đối trên thang 1–5                                                        |
| Ragas                  |       N/A | Chưa chạy — cần bật`RUN_RAGAS=1`; nhóm bỏ qua để tiết kiệm quota LLM free tier |

Baseline đạt điểm tuyệt đối là hợp lý chứ không phải dấu hiệu đo sai: `answer_question` trả lời bằng cách trích thẳng trường metadata tương ứng với loại câu hỏi, còn ground truth cũng lấy từ chính trường đó. Điều này là **cố ý** — nó tạo một mốc trần sạch để mọi sụt giảm ở trạng thái corrupted đều quy được về chất lượng dữ liệu chứ không lẫn với nhiễu của tầng sinh chữ.

Ngoài ra agent LangChain chạy độc lập trên cùng index với hai tool `semantic_search_papers` và `lookup_paper`, đạt `agent_status: ok` với 4/4 câu trả lời có dẫn chứng từ corpus — xem `data/results/agent_demo_answers.json`.

## 8. Data quality và freshness

### Quality checks

| Check                          | Quality dimension | Ngưỡng/kỳ vọng                                | Kết quả baseline    | Bằng chứng                   |
| ------------------------------ | ----------------- | ------------------------------------------------- | --------------------- | ------------------------------ |
| `row_count`                  | Completeness      | > 0                                               | PASS — 24 dòng      | `data_quality_baseline.json` |
| `paper_id_not_null`          | Completeness      | 0 dòng rỗng                                     | PASS — 0/24          | như trên                     |
| `paper_id_unique`            | Uniqueness        | 0 dòng thuộc nhóm trùng                       | PASS — 0             | như trên                     |
| `title_not_null`             | Completeness      | 0 dòng rỗng                                     | PASS — 0/24          | như trên                     |
| `summary_length`             | Validity          | ≥ 20 ký tự                                     | PASS — 0/24 vi phạm | như trên                     |
| `summary_chars_consistency`  | Accuracy          | Khớp`len(summary)`                             | PASS — 0/24 lệch    | như trên                     |
| `published_valid`            | Validity          | Parse được thành ngày                        | PASS — 0/24 lỗi     | như trên                     |
| `age_days_consistency`       | Accuracy          | Khớp`published` và run date                   | PASS — 0/24 lệch    | như trên                     |
| `embedding_text_consistency` | Accuracy          | `text_for_embedding` khớp các trường nguồn | PASS — 0/24 lệch    | như trên                     |
| `noise_free`                 | Validity          | Không chứa mẫu noise đã biết                | PASS — 0/24          | như trên                     |
| `title_not_truncated`        | Validity          | Không kết thúc bằng dấu cắt                 | PASS — 0/24          | như trên                     |
| `freshness`                  | Timeliness        | `age_days` ≤ 180                               | PASS — 0/24 stale    | `freshness_report.json`      |

### Freshness

| Thuộc tính               | Giá trị                                                                                                                                                                                                        |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Freshness được đo tại | Cleaned dataset của từng trạng thái, qua cột`age_days`                                                                                                                                                    |
| Timestamp mới nhất       | `latest_published = 2026-08-06`                                                                                                                                                                                |
| Ngưỡng freshness         | 180 ngày                                                                                                                                                                                                        |
| Trạng thái baseline      | Fresh —`is_fresh: true`, `stale_rows: 0/24`                                                                                                                                                                 |
| Lý do                     | Filter nguồn giới hạn trong khoảng`from-pub-date:2026-02-07` đến `until-pub-date:2026-08-06`, đúng bằng cửa sổ 180 ngày của ngưỡng freshness, nên mọi record hợp lệ đều nằm trong hạn |

## 9. Corruption scenarios và repair

Tham số chung: `random_seed = 42`, mỗi scenario 10% số dòng (tối thiểu 1), `stale_years = 5`. Input 24 dòng, output 24 dòng — bằng nhau vì 3 dòng bị xoá được bù bằng 3 dòng duplicate, nên `row_count` **không** phát hiện được corruption; đó là lý do cần các check khác.

| Corruption           | Cách tạo                                | Record bị tác động | Quality signal kỳ vọng     | Tác động thực tế                                                                                   | Cách repair       |
| -------------------- | ----------------------------------------- | ---------------------: | ---------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------ |
| Drop latest records  | Xoá 3 record có`published` mới nhất |                      3 | Mất document khỏi corpus   | `retrieval_hit_rate` 1.0000 → 0.5000; 2 trong 3 ID bị xoá chính là document mà test set trượt | Dựng lại từ raw |
| Blank summary        | Đặt`summary = ""`                     |                      3 | `summary_length` FAIL      | FAIL — 3/24 dòng dưới 20 ký tự                                                                    | Dựng lại từ raw |
| Inject noise         | Chèn chuỗi rác vào giữa summary      |                      3 | `noise_free` FAIL          | FAIL — 4/24 dòng (3 gốc + 1 bị nhân bản)                                                          | Dựng lại từ raw |
| Truncate title       | Cắt còn 35% độ dài, thêm`...`     |                      3 | `title_not_truncated` FAIL | FAIL — 3/24 title                                                                                      | Dựng lại từ raw |
| Stale published date | Lùi ngày 5 năm                         |                      3 | `freshness` FAIL           | FAIL — 3/24 stale;`oldest_published` lùi về 2021-08-06                                             | Dựng lại từ raw |
| Duplicate rows       | Nhân bản nguyên dòng                  |                      3 | `paper_id_unique` FAIL     | FAIL — 6 dòng thuộc nhóm trùng                                                                     | Dựng lại từ raw |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi `run_id`, `random_seed`, `run_date_utc`, `input_row_count`/`output_row_count`, toàn bộ `config`, mục `scenarios` liệt kê số dòng và danh sách `paper_ids` cho từng loại, cùng mục `events` ghi before/after ở mức từng dòng. Đủ để tái hiện chính xác và để truy ngược mỗi metric sụt về nguyên nhân cụ thể.

Giải thích cách repair đảm bảo dữ liệu được phục hồi từ nguồn đáng tin cậy thay vì chỉ che kết quả lỗi:

`repair_from_raw_records` **không đọc dataframe corrupted** để sửa. Nó nạp lại `data/raw/crossref_records.json` — artifact đã lưu ở bước ingestion, chưa từng bị corruption chạm vào — rồi chạy lại đúng pipeline cleaning ban đầu. Cách này khôi phục được cả những lỗi mà vá tại chỗ không xử lý nổi: record bị **xoá** không có gì để vá, và summary bị **ghi đè bằng chuỗi rỗng** thì thông tin gốc đã mất hẳn.

Bằng chứng repair là thật chứ không phải che số: `data/quality/repaired_dataset_validation.json` báo `repair_valid: True` dựa trên ba điều kiện độc lập — khớp row count, khớp tập `paper_id`, và **digest nội dung** của các cột so sánh trùng khớp baseline. Nếu repair chỉ làm metric đẹp lên mà dữ liệu khác baseline, digest sẽ lệch ngay. Ngoài ra `corruption_flow` sẽ `raise RuntimeError` nếu validation fail, nên không thể có chuyện flow báo thành công với dữ liệu chưa phục hồi.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            |           Baseline |                 Corrupted |           Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét                                                  |
| ------------------------ | -----------------: | ------------------------: | -----------------: | -----------------------: | --------------: | ----------------------------------------------------------- |
| `retrieval_hit_rate`   |             1.0000 |                    0.5000 |             1.0000 |                 −0.5000 |  +0.5000 (100%) | 8/16 câu mất ground-truth document                        |
| `mean_token_f1`        |             1.0000 |                    0.6244 |             1.0000 |                 −0.3756 |  +0.3756 (100%) | Giảm ít hơn hit rate — xem phân tích dưới           |
| `judge_accuracy`       |             1.0000 |                    0.5625 |             1.0000 |                 −0.4375 |  +0.4375 (100%) | Bám sát hit rate                                          |
| `mean_judge_score`     |               5.00 |                    3.3750 |               5.00 |                 −1.6250 |  +1.6250 (100%) | Giảm gần 1/3 thang điểm                                 |
| Quality checks pass/fail |   PASS (0/12 fail) |          FAIL (5/12 fail) |   PASS (0/12 fail) |     5 check chuyển FAIL |      Về 0 fail | 5 check fail ứng 1-1 với 5 scenario                       |
| Freshness status         | fresh (0/24 stale) | không fresh (3/24 stale) | fresh (0/24 stale) |  Mất trạng thái fresh |     Khôi phục | `oldest_published` 2026-08-06 → 2021-08-06 → 2026-08-06 |

Hai kết luận có quan hệ nhân quả được hỗ trợ bởi artifacts:

1. **Xoá 3 record mới nhất** (`corruption_log.json` → `drop_latest_records`) → hai trong bốn paper của test set biến mất khỏi collection `papers-corrupted`, đồng thời `paper_id_unique` và `freshness` chuyển FAIL trong `data_quality_corrupted.json` → `retrieval_hit_rate` rơi từ 1.0000 xuống 0.5000 và `judge_accuracy` xuống 0.5625. Đối chiếu `retrieved_doc_ids` với `ground_truth_doc_ids` trong `corrupted_answers.json` cho thấy đúng hai document bị trượt là `10.1007/s00262-026-04505-w` và `10.1007/s44020-026-00124-1` — cả hai đều nằm trong danh sách bị xoá.
2. **Repair bằng `repair_from_raw_records`** từ `data/raw/crossref_records.json` → `repaired_dataset_validation.json` báo `repair_valid: True` với digest khớp baseline, `data_quality_repaired.json` về 12/12 PASS và `freshness_repaired.json` về `is_fresh: true` → cả bốn metric agent phục hồi 100%, chênh lệch so với baseline đúng bằng 0.0000 trên cùng test set.

Kết quả khác kỳ vọng và cách nhóm đã kiểm tra:

Nhóm kỳ vọng `mean_token_f1` tụt xấp xỉ `retrieval_hit_rate` (~0.5), nhưng thực tế là 0.6244. Giả thuyết ban đầu là metric tính sai. Nhóm tách kết quả theo `question_type` trong `corrupted_answers.json`:

| `question_type` | hit | `mean_token_f1` | `mean_judge_score` |
| ----------------- | --: | ----------------: | -------------------: |
| `summary`       | 2/4 |             0.337 |                 2.00 |
| `authors`       | 2/4 |             0.500 |                 3.00 |
| `date`          | 2/4 |   **1.000** |       **5.00** |
| `categories`    | 2/4 |             0.661 |                 3.50 |

Nhóm `date` giữ điểm tuyệt đối dù chỉ hit 2/4. Nguyên nhân không phải lỗi metric mà là đặc điểm của corpus: cả 24 paper đều có `published = 2026-08-06`, nên khi retrieval trả nhầm tài liệu, câu trả lời về ngày vẫn tình cờ đúng. Đây là giới hạn thật của evaluation set — với loại câu hỏi này, `token_f1` gần như không phân biệt được document đúng và sai, và nó khiến corruption trông nhẹ hơn thực tế ở metric tổng. Cách kiểm tra đáng tin duy nhất là đọc xuống tầng `retrieved_doc_ids`.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** `python script/run_phase1.py` dừng ở `ValueError: Cleaning produced an empty dataframe.` dù `data/raw/crossref_records.json` có đủ 22 record và cả `crossref.py` lẫn `cleaning.py` đều chạy đúng khi test riêng.
- **Nguyên nhân:** `source_filter` trong `src/core/config.py` chỉ đặt chặn dưới `from-pub-date`. Crossref trả về cả các số báo **đã lên lịch xuất bản trong tương lai**, và vì query dùng `sort=published&order=desc` nên những record đó đứng đầu kết quả. Toàn bộ 22/22 record trong snapshot có `published` từ `2026-12-31` đến `2028-06-15`, trong khi ngày chạy là `2026-08-06`. `build_clean_dataframe` loại đúng mọi record có `published` lớn hơn ngày chạy — đây là hành vi **đúng** — nên kết quả là dataframe rỗng. Không module nào sai; lỗi nằm ở contract của filter nguồn.
- **Cách xử lý:** Thêm chặn trên vào filter trong `src/core/config.py`:

  ```python
  source_until_date = today.isoformat()
  source_filter = f"from-pub-date:{source_from_date},until-pub-date:{source_until_date},has-abstract:true"
  ```
- **Cách xác minh:** Gọi thử Crossref với filter mới trả về 24 item đều có `issued = 2026-08-06`. Chạy `REFRESH_SOURCE=1 python script/run_phase1.py` cho 24 clean rows, 16 test samples, 12/12 quality check PASS và `is_fresh: true`. Bài học rút ra: filter trên nguồn dữ liệu sống phải chặn cả hai đầu, và assertion đặt giữa các bước pipeline (`_validate_clean_dataframe`) chính là thứ biến một corpus rỗng âm thầm thành một lỗi dừng hẳn có thể lần ra nguyên nhân.

Một vấn đề tích hợp thứ hai đáng ghi nhận: khi merge nhánh của thành viên 4 vào nhánh của thành viên 5, `src/pipelines/corruption_flow.py` rơi vào trạng thái conflict `UU`. Nhóm chọn giữ bản tích hợp dùng API chính thức của `corruption.py` (`repair_from_raw_records`, `validate_corrupted_dataframe`, `validate_repaired_dataframe`) thay vì bản tự cài lại logic repair, để tránh hai nguồn sự thật cho cùng một quy tắc; sau đó bổ sung lại việc ghi `corruption_run_summary.json` mà bản tích hợp đánh rơi.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại                                                                             | Ảnh hưởng                                                                                              | Hướng cải thiện có thể kiểm chứng                                                                                              |
| ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Cả 24 paper có cùng`published = 2026-08-06`                                                  | `token_f1` nhóm `date` đạt 1.000 ngay cả khi retrieval sai, làm nhẹ hoá tác động corruption | Mở rộng khoảng ngày nguồn; đo lại:`token_f1` nhóm `date` ở trạng thái corrupted phải tụt về xấp xỉ 0.5             |
| `answer_question` trích thẳng metadata, không sinh chữ bằng LLM                            | Baseline đạt trần 1.0000 nên không đo được chất lượng generation                              | Thay bằng đường sinh chữ có LLM cho evaluation; đo bằng chênh lệch`mean_judge_score` giữa hai cách trả lời             |
| Ragas chưa chạy                                                                                 | Thiếu`faithfulness`, `context_precision`, `context_recall`                                         | Chạy`RUN_RAGAS=1` và ghi kết quả vào `baseline_metrics.json`                                                                  |
| `row_count` không phát hiện được corruption vì số dòng xoá bằng số dòng nhân bản | Một check trông PASS trong khi dữ liệu đã hỏng                                                     | Thêm check đối chiếu`unique_key_count` với số record trong raw snapshot                                                        |
| Test tự động mới phủ module corruption (4 test)                                              | Ingestion, cleaning, orchestration chưa có test                                                         | Thêm test cho`build_clean_dataframe` và các hàm validate của `phase1.py`; đo bằng số test và số nhánh lỗi được phủ |
| LLM free tier giới hạn quota                                                                    | Phải chọn model theo quota thay vì theo chất lượng; một số lần chạy phải retry                 | Dùng tài khoản có quota cao hơn hoặc`ollama` chạy local; đo bằng tỉ lệ lần gọi LLM thành công ngay lần đầu         |

## 13. Checklist trước khi nộp

- [ ] Thông tin nhóm và repository chính xác.
- [ ] Phân công khớp với module, artifact và kết quả thực tế.
- [ ] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [ ] Baseline, corrupted và repaired dùng cùng evaluation set.
- [ ] Bảng metrics khớp với các file trong `data/results/`.
- [ ] Quality/freshness conclusions khớp với `data/quality/`.
- [ ] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [ ] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
