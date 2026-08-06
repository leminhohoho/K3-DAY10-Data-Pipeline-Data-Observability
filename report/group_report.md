# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | K3 |
| Tên nhóm | |
| Repository | https://github.com/leminhohoho/K3-DAY10-Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| ---: | --- | --- | --- | --- |
| 1 | Bùi Hoàng Vương | 2A202601553 | Source owner | `src/ingestion/crossref.py`; raw response và raw records trong `data/raw/` |
| 2 | Đặng Tiến Thành | 2A202601305 | Cleaning & test-set owner | `src/ingestion/cleaning.py`, `src/evaluation/testset.py`; cleaned dataset và `data/eval/test_set.json` |
| 3 | Nguyễn Lê Minh | 2A202601045 | Observability owner | `src/observability/quality.py`, `src/observability/reporting.py`; quality/freshness artifacts và Markdown reports |
| 4 | Nguyễn Chí Quang | 2A202601932 | Corruption & repair owner | `src/ingestion/corruption.py`, `tests/test_corruption.py`; corruption log và corrupted/repaired validation |
| 5 | Ngô Thành Đạt | 2A202601323 | Pipeline integration & evidence owner | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`; orchestration, metrics và run summaries |

> Phạm vi có giao nhau: Thành viên 4 phối hợp với Thành viên 3 để bổ sung các quality checks cho derived columns, corruption markers và record coverage. Thành viên 5 tích hợp các API này vào hai pipeline nhưng không cài đặt lại logic corruption/repair.

## 2. Tóm tắt kết quả

Nhóm đã hoàn thành pipeline hai pha và tạo đủ ba trạng thái dữ liệu **baseline**, **corrupted** và **repaired**. Pipeline baseline lấy dữ liệu bài báo từ Crossref, lưu raw artifacts, làm sạch về schema 16 cột, tạo embedding bằng MiniLM, nạp vào ChromaDB, xây evaluation set 16 câu, chạy LangChain agent, tính metrics, kiểm tra data quality/freshness và sinh báo cáo.

Snapshot hiện tại có **23 raw records và 23 clean records**, tương ứng **23 `paper_id` duy nhất**. Corpus có **16 ngày xuất bản khác nhau**, từ `2025-08-27` đến `2026-07-13`, nên freshness và câu hỏi về ngày có độ đa dạng tốt hơn phiên bản đầu. Baseline đạt `retrieval_hit_rate = 1.0000`, `judge_accuracy = 0.9375` và `mean_judge_score = 4.8750`. Toàn bộ 16 câu evaluation được trả lời bởi agent, không có `agent_error`.

Corruption flow tạo sáu loại lỗi có chủ đích với seed 42. Ba bài mới nhất bị xóa; năm scenario còn lại tác động hai record cho mỗi loại. Sau khi xóa 3 dòng và thêm 2 duplicate, corrupted corpus còn **22 dòng nhưng chỉ có 20 `paper_id` duy nhất**. Data quality chuyển từ PASS sang FAIL ở 6/13 checks. Retrieval hit rate giảm từ `1.0000` xuống `0.2500`, judge accuracy giảm từ `0.9375` xuống `0.1875`, cho thấy chất lượng dữ liệu ảnh hưởng trực tiếp đến retrieval và câu trả lời của agent.

Repair không vá từng dòng corrupted mà dựng lại dataset từ `data/raw/crossref_records.json` qua cùng cleaning pipeline ban đầu. Repaired corpus trở về **23 dòng, 23 `paper_id` duy nhất**, content digest khớp baseline, 13/13 quality checks PASS và freshness PASS. Retrieval hit rate và judge accuracy được khôi phục hoàn toàn về baseline. `mean_token_f1` và `mean_judge_score` không trùng tuyệt đối do câu trả lời và LLM judge có tính biến thiên, nhưng validation ở tầng dữ liệu xác nhận repair hợp lệ.

## 3. Kiến trúc và luồng dữ liệu

```text
Crossref REST API
    -> data/raw/crossref_response.json
    -> data/raw/crossref_records.json
    -> cleaning + normalization + deduplication
    -> data/clean/papers_clean.{csv,json}
    -> MiniLM embeddings
    -> ChromaDB collection: papers-baseline
    -> data/eval/test_set.json
    -> LangChain agent + retrieval/answer evaluation
    -> data/results/baseline_{metrics,answers}.json
    -> data quality + freshness
    -> data/reports/phase1_report.md

Baseline clean dataframe
    -> six deterministic corruption scenarios
    -> data/clean/papers_clean_corrupted.{csv,json}
    -> ChromaDB collection: papers-corrupted
    -> evaluation trên cùng test set
    -> corrupted quality/freshness/metrics

Raw Crossref artifact
    -> build_clean_dataframe() lại từ đầu
    -> data/clean/papers_clean_repaired.{csv,json}
    -> ChromaDB collection: papers-repaired
    -> evaluation trên cùng test set
    -> repaired validation + comparison report
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output/artifact | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Crossref REST API | Query, retry/backoff, parse JATS abstract, chuẩn hóa ngày và metadata, lưu raw | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | Thành viên 1 |
| Cleaning | `list[PaperRecord]` | Validate required fields, loại ngày tương lai, dedupe theo `paper_id`, tạo derived columns | `data/clean/papers_clean.csv`, `.json` | Thành viên 2 |
| Embedding/index | `text_for_embedding` | `all-MiniLM-L6-v2`, ChromaDB persistent, ba collection tách biệt | `data/embeddings/*.json`, `data/chroma/` | Starter + Thành viên 5 |
| Evaluation | Clean dataframe, index, test set | 16 câu/4 loại; vector retrieval; agent answer; token F1 và LLM judge | `data/eval/test_set.json`, `data/results/*_metrics.json`, `*_answers.json` | Thành viên 2 + Thành viên 5 |
| Observability | Dataframe từng trạng thái | 13 quality checks, record coverage và freshness 365 ngày | `data/quality/*.json`, `data/reports/*.md` | Thành viên 3 |
| Corruption/repair | Baseline clean dataframe và raw records | Sáu corruption scenarios, log, rebuild derived columns, repair từ raw, validation | `corruption_log.json`, corrupted/repaired datasets và validation | Thành viên 4 |
| Orchestration | Toàn bộ module | Giữ cùng test set, build ba index, chạy evaluation và sinh evidence | Run summaries và comparison report | Thành viên 5 |

## 4. Cấu hình và cách tái hiện

### Cấu hình thực tế của lần chạy

| Biến/cấu hình | Giá trị |
| --- | --- |
| `LLM_PROVIDER` | `gemini` |
| `LLM_MODEL` | `gemini-flash-lite-latest` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Source query | `agentic retrieval augmented generation large language model` |
| Source filter | `from-pub-date:2025-08-06,until-pub-date:2026-08-06,has-abstract:true` |
| Crossref sort | `relevance`, descending |
| `max_results` | 24; thực nhận 23 usable records |
| Retrieval `top_k` | 4 |
| Freshness threshold | 365 ngày |
| Corruption random seed | 42 |
| Evaluation samples | 16 câu, gồm 4 `summary`, 4 `authors`, 4 `date`, 4 `categories` |

### Cài đặt

```bash
python -m pip install -e ".[dev]"
```

### Chạy baseline

```bash
python script/run_phase1.py
```

Để lấy lại dữ liệu Crossref thay vì dùng snapshot:

```bash
REFRESH_SOURCE=1 python script/run_phase1.py
```

### Chạy corruption/repair flow

```bash
python script/run_corruption_flow.py
```

### Chạy test

```bash
python -m pytest tests/ -q
```

Kết quả test hiện tại:

```text
4 passed
```

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

Crossref được gọi qua `https://api.crossref.org/works` với `query.bibliographic`, cửa sổ ngày một năm, `has-abstract:true` và `sort=relevance`. Cách sắp xếp theo relevance giúp corpus bám sát chủ đề RAG tốt hơn so với sắp xếp thuần theo ngày xuất bản. Request có timeout, retry tối đa bốn lần cho 429/5xx, đọc `Retry-After` khi có và dùng backoff nếu cần.

Snapshot hiện tại gồm 23 raw records. Sau cleaning vẫn còn 23 records vì tất cả record trong snapshot đều đáp ứng contract và không còn duplicate `paper_id`.

### Clean schema

| Trường | Kiểu | Vai trò |
| --- | --- | --- |
| `paper_id` | string | DOI viết thường, document identity xuyên suốt pipeline |
| `title` | string | Tiêu đề đã normalize whitespace và unescape HTML |
| `summary` | string | Abstract sau khi loại JATS tags và prefix thừa |
| `authors`, `authors_joined` | list/string | Tác giả dạng cấu trúc và dạng ghép |
| `categories`, `categories_joined`, `primary_category` | list/string | Chủ đề hoặc fallback từ container/type |
| `published`, `updated` | ISO date | Ngày xuất bản và cập nhật |
| `abs_url`, `pdf_url`, `comment` | string | Metadata bổ sung |
| `summary_chars` | integer | Độ dài thực tế của summary |
| `age_days` | integer | Số ngày từ `published` tới run date |
| `text_for_embedding` | string | Nội dung có nhãn dùng để embedding |

`text_for_embedding` được tạo theo format ổn định:

```text
Title: ...
Summary: ...
Authors: ...        # chỉ thêm khi có
Categories: ...     # chỉ thêm khi có
Published: ...
```

Các derived columns được tính lại sau corruption và sau repair. Vì vậy quality checks có thể phân biệt lỗi nội dung có chủ đích với lỗi pipeline do metadata dẫn xuất bị stale.

## 6. Embedding, retrieval và agent

Pipeline dùng `sentence-transformers/all-MiniLM-L6-v2` và ChromaDB persistent với ba collection:

```text
papers-baseline
papers-corrupted
papers-repaired
```

Retrieval metric được tính bằng `index.search(question, top_k=4)` trực tiếp trên vector index. Câu trả lời được sinh bởi LangChain agent có hai tool chính: semantic search và lookup paper. Trong artifacts hiện tại, cả baseline, corrupted và repaired đều có `answer_source = agent` cho 16/16 câu và không có `agent_error`.

Embedding manifests đã lưu `persist_path` tương đối (`data/chroma`), giúp index dễ di chuyển giữa các máy hơn. Tuy nhiên hai run summary hiện vẫn chứa absolute artifact paths và cần được tái sinh hoặc chuẩn hóa trước khi nộp.

## 7. Evaluation setup và baseline

Test set được xây dựng deterministically từ bốn paper mới nhất đủ dữ liệu. Mỗi paper tạo bốn câu hỏi:

```text
summary
authors
date
categories
```

Mỗi sample chứa `question`, `ground_truth`, `ground_truth_doc_ids` và `question_type`. Cùng file `data/eval/test_set.json` được tái sử dụng cho baseline, corrupted và repaired để bảo đảm so sánh công bằng.

### Baseline metrics

| Metric | Giá trị | Diễn giải |
| --- | ---: | --- |
| Samples | 16 | 4 paper × 4 loại câu hỏi |
| Answer mode | `agent` | 16/16 answers do LangChain agent tạo |
| `retrieval_hit_rate` | 1.0000 | 16/16 câu có ground-truth document trong top-4 |
| `mean_token_f1` | 0.1296 | Lexical overlap thấp vì agent trả lời dài hơn ground truth ngắn |
| `judge_accuracy` | 0.9375 | 15/16 câu được LLM judge đánh giá đúng |
| `mean_judge_score` | 4.8750 | Gần mức tối đa 5 |
| Ragas | Chưa chạy | Bật `RUN_RAGAS=1` để chạy pass bổ sung |

Baseline data quality hiện **PASS 13/13 checks** và freshness **PASS**, với 0/23 stale rows.

## 8. Data quality và freshness

### Các quality checks

| Check | Dimension | Kỳ vọng baseline |
| --- | --- | --- |
| `row_count` | Completeness | Dataframe không rỗng |
| `record_coverage` | Completeness | Không thiếu `paper_id` so với baseline |
| `paper_id_not_null` | Completeness | Không có ID rỗng |
| `paper_id_unique` | Uniqueness | Không có duplicate groups |
| `title_not_null` | Completeness | Không có title rỗng |
| `summary_length` | Validity | Summary có ít nhất 20 ký tự |
| `summary_chars_consistency` | Accuracy | `summary_chars == len(summary)` |
| `published_valid` | Validity | Parse được ngày |
| `age_days_consistency` | Accuracy | `age_days` khớp `published` và run date |
| `embedding_text_consistency` | Accuracy | `text_for_embedding` khớp các trường nguồn |
| `noise_free` | Validity | Không chứa corruption noise markers |
| `title_not_truncated` | Validity | Title không kết thúc bằng corruption marker |
| `freshness` | Timeliness | Không có record quá 365 ngày |

### Freshness hiện tại

| Trạng thái | Latest published | Oldest published | Stale rows | Kết quả |
| --- | --- | --- | ---: | --- |
| Baseline | 2026-07-13 | 2025-08-27 | 0/23 | PASS |
| Corrupted | 2026-07-01 | 2020-12-30 | 4/22 | FAIL |
| Repaired | 2026-07-13 | 2025-08-27 | 0/23 | PASS |

Corrupted có bốn stale rows dù scenario stale chỉ chọn hai source rows, vì hai rows đó cũng được duplicate. Đây là ví dụ cho thấy các corruption scenarios có thể tương tác và khuếch đại quality signals.

## 9. Corruption scenarios

Cấu hình chung: `random_seed = 42`, mỗi scenario dùng tỷ lệ 10%, tối thiểu một record và `stale_years = 5`.

| Scenario | Cách tạo | Số source records | Tín hiệu phát hiện |
| --- | --- | ---: | --- |
| Drop latest records | Xóa các record có `published` mới nhất | 3 | `record_coverage` FAIL; ground-truth documents biến mất |
| Blank summary | Đặt `summary = ""` | 2 | `summary_length` FAIL |
| Inject noise | Chèn marker rác vào summary | 2 | `noise_free` FAIL |
| Truncate title | Giữ khoảng 35% title và thêm `...` | 2 | `title_not_truncated` FAIL |
| Stale published date | Lùi `published` năm năm | 2 | `freshness` FAIL |
| Duplicate rows | Nhân bản nguyên row | 2 | `paper_id_unique` FAIL |

Từ 23 baseline rows:

```text
23 - 3 dropped + 2 duplicates = 22 corrupted rows
```

Corrupted dataframe có 22 rows nhưng chỉ 20 unique paper IDs. Điều này chứng minh `row_count` đơn lẻ không đủ để phát hiện mất dữ liệu; cần đồng thời kiểm tra record coverage và uniqueness.

`data/results/corruption_log.json` lưu run ID, seed, cấu hình, input/output row count, danh sách paper IDs của từng scenario và event-level before/after values. Corrupted dataset validation xác nhận cả sáu scenario đã xuất hiện và các derived columns vẫn nhất quán sau khi được rebuild.

## 10. Repair strategy và validation

Repair được thực hiện theo luồng:

```text
data/raw/crossref_records.json
    -> load_raw_records()
    -> build_clean_dataframe(run_date giống baseline)
    -> rebuild text_for_embedding và derived columns
    -> repaired dataframe
```

Hàm repair không sử dụng corrupted dataframe làm nguồn nội dung. Nhờ đó pipeline phục hồi được cả record đã bị xóa và các trường đã bị ghi đè hoàn toàn.

`data/quality/repaired_dataset_validation.json` xác nhận:

- row count khớp baseline;
- tập `paper_id` khớp baseline;
- không còn duplicate IDs;
- content digest khớp baseline;
- không còn corruption noise hoặc truncated title;
- `summary_chars`, `age_days` và `text_for_embedding` nhất quán.

Kết quả cuối:

```text
Baseline:  23 rows, 23 unique IDs
Corrupted: 22 rows, 20 unique IDs
Repaired:  23 rows, 23 unique IDs
Repair valid: True
```

## 11. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Corruption impact | Repair result |
| --- | ---: | ---: | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.0000 | 0.2500 | 1.0000 | −0.7500 | Khôi phục hoàn toàn |
| `mean_token_f1` | 0.1296 | 0.0686 | 0.0907 | −0.0609 | Tăng +0.0221; còn −0.0389 so với baseline |
| `judge_accuracy` | 0.9375 | 0.1875 | 0.9375 | −0.7500 | Khôi phục hoàn toàn |
| `mean_judge_score` | 4.8750 | 1.7500 | 4.8125 | −3.1250 | Còn −0.0625 so với baseline |
| Unique paper IDs | 23 | 20 | 23 | Mất coverage | Khôi phục hoàn toàn |
| Quality | PASS, 0/13 fail | FAIL, 6/13 fail | PASS, 0/13 fail | Sáu signals chuyển FAIL | Khôi phục hoàn toàn |
| Freshness | PASS, 0/23 stale | FAIL, 4/22 stale | PASS, 0/23 stale | Corpus chứa dữ liệu cũ giả lập | Khôi phục hoàn toàn |

### Phân tích quan hệ giữa corruption và metrics

Ba record bị drop chính là ba trong bốn documents được dùng để tạo evaluation set. Mỗi document tương ứng bốn câu hỏi, nên 12/16 câu không còn ground-truth document trong corrupted collection. Retrieval hit rate vì vậy giảm từ 16/16 xuống 4/16, tương ứng `1.0000 -> 0.2500`.

Khi ground-truth documents không còn trong corpus, agent thường trả lời rằng không tìm thấy paper hoặc dựa trên tài liệu gần nghĩa nhưng không đúng. Judge accuracy giảm xuống 3/16 (`0.1875`) và mean judge score còn `1.7500`. Đây là bằng chứng trực tiếp rằng lỗi dữ liệu upstream đã lan truyền tới retrieval và answer quality.

Sau repair, vector corpus được build lại từ dữ liệu đã phục hồi. Retrieval hit rate trở về 16/16 và judge accuracy trở về 15/16. Repaired data giống baseline ở tầng dữ liệu nhưng token F1 và mean judge score không trùng tuyệt đối. Nguyên nhân hợp lý là câu trả lời tự nhiên và LLM judge có tính biến thiên giữa các lần chạy; vì vậy kết luận repair dựa chủ yếu vào dataset validation, retrieval recovery và quality/freshness recovery, không dựa riêng vào lexical F1.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện |
| --- | --- | --- |
| Câu hỏi evaluation chứa nguyên title hoặc `paper_id` | Retrieval vẫn là bài toán tương đối dễ; chưa phản ánh đầy đủ semantic information need | Bổ sung nhóm câu hỏi semantic không chứa exact title, giữ separate metrics theo retrieval mode |
| Ground truth thường ngắn, agent trả lời dài | Token F1 thấp ngay cả khi judge đánh giá câu trả lời đúng | Báo cáo metrics theo question type; thêm semantic similarity/Ragas; hoặc yêu cầu agent trả lời ngắn |
| Retrieval evidence được lấy bằng direct index search, trong khi agent có thể gọi tool theo đường riêng | `retrieved_contexts` artifact chưa chắc là toàn bộ contexts agent thực sự dùng | Ghi agent tool-call trace hoặc sinh answer trực tiếp từ cùng retrieved contexts |
| Ragas chưa chạy | Chưa có faithfulness/context precision/context recall | Chạy với `RUN_RAGAS=1` khi đủ quota |
| Test tự động hiện chủ yếu phủ corruption/repair | Ingestion, cleaning và orchestration chưa có regression tests đầy đủ | Thêm tests cho parse Crossref, clean schema, test-set contract và quality checks |
| LLM API có quota và tính biến thiên | Answer/judge metrics có thể dao động nhẹ giữa các lần chạy | Lưu seed/config, retry có kiểm soát; cân nhắc provider/local model ổn định hơn |
| `phase1_run_summary.json` chưa đồng bộ với quality artifacts mới và còn absolute paths | Có thể gây mâu thuẫn khi người chấm đối chiếu artifact | Chạy lại baseline/corruption flow sau khi sửa path serialization, rồi kiểm tra summary khớp report |

## 13. Vấn đề tích hợp và bài học

### Chặn publication date trong tương lai

Crossref có thể trả về các issue đã lên lịch xuất bản trong tương lai. Nếu chỉ dùng `from-pub-date` và sắp xếp theo ngày mới nhất, cleaning đúng quy tắc sẽ loại toàn bộ record có `published > run_date`, tạo dataframe rỗng. Nhóm đã bổ sung `until-pub-date` bằng ngày chạy và chuyển sort sang `relevance`. Kết quả là corpus vừa hợp lệ về thời gian vừa liên quan hơn tới chủ đề RAG.

### Record coverage quan trọng hơn row count

Xóa record và thêm duplicate có thể giữ row count gần như không đổi. Check `record_coverage` đối chiếu tập `paper_id` hiện tại với baseline đã phát hiện chính xác 3 IDs bị mất, trong khi `row_count` vẫn PASS với 22 rows. Đây là bài học chính về data observability: cần kiểm tra identity/coverage, không chỉ số dòng.

### Repair phải có source of truth

Vá trực tiếp corrupted dataframe không thể phục hồi record đã bị xóa hoặc nội dung đã bị ghi đè. Việc giữ raw artifacts giúp pipeline dựng lại cleaned dataset và chứng minh khả năng phục hồi bằng content digest, thay vì chỉ làm cho metrics đẹp trở lại.

## 14. Artifacts chính

| Nhóm artifact | Đường dẫn |
| --- | --- |
| Raw source | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` |
| Clean datasets | `data/clean/papers_clean*.csv`, `data/clean/papers_clean*.json` |
| Embedding manifests | `data/embeddings/papers_embeddings*.json` |
| Evaluation set | `data/eval/test_set.json` |
| Answers/metrics | `data/results/*_answers.json`, `data/results/*_metrics.json` |
| Corruption log | `data/results/corruption_log.json` |
| Quality/freshness | `data/quality/*.json` |
| Reports | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` |
| Tests | `tests/test_corruption.py` |

## 15. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [x] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
