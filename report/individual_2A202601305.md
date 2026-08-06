# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Đặng Tiến Thành |
| MSSV | 2A202601305 |
| Khóa/Lớp | K3 |
| Tên nhóm | Nhóm K3 Day 10 — 5 thành viên, chưa đặt tên riêng |
| Vai trò chính | Cleaning & evaluation-set owner |
| Repository | https://github.com/leminhohoho/K3-DAY10-Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Cleaning và data modeling | `src/ingestion/cleaning.py` — `build_clean_dataframe()` và các helper | `list[PaperRecord]`, `run_date` | Clean DataFrame; `data/clean/papers_clean.csv`, `papers_clean.json` | Hoàn thành, đã chạy end-to-end |
| Evaluation set | `src/evaluation/testset.py` — `build_test_set()` và các helper | Clean DataFrame | `data/eval/test_set.json` | Hoàn thành, đã dùng chung cho cả ba trạng thái |

Tôi chỉ nhận ownership cho cleaning và evaluation-set builder. Phần ingestion do thành viên 1 phụ trách; observability do thành viên 3; corruption/repair do thành viên 4; pipeline orchestration và chạy metrics do thành viên 5.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Đối chiếu clean schema với retrieval contract | `src/retrieval/index.py`, pipeline integration owner | Clean artifact có đủ 16 cột; 24/24 `text_for_embedding` không rỗng và `paper_id` unique |
| Đối chiếu format câu hỏi với QA contract | `src/retrieval/qa.py`, evaluation pipeline | 16 câu hỏi dùng đúng exact lookup và answer type; baseline đạt 16/16 retrieval hit |
| Phối hợp chẩn đoán clean DataFrame rỗng ở lần chạy đầu | Source và integration owner | Xác định raw snapshot chỉ chứa ngày tương lai; source filter được bổ sung `until-pub-date` và fetch lại thành công |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Chuẩn hóa text và danh sách | `cleaning.py` — `_clean_text()`, `_clean_string_list()` | Xóa XML/JATS tags, decode HTML entities, chuẩn hóa whitespace, dedupe authors/categories | Kiểm tra clean JSON và quality report baseline |
| Parse và chuẩn hóa ngày | `cleaning.py` — `_as_utc_timestamp()` | Parse UTC, xuất ISO date và tính `age_days` | `published_valid` và `age_days_consistency` đều PASS 24/24 |
| Lọc và deduplicate records | `build_clean_dataframe()` | Loại record thiếu trường bắt buộc/ngày tương lai; giữ duplicate có `updated` mới nhất | 24 raw records tạo 24 clean rows, 24 unique IDs |
| Tạo schema embedding | `build_clean_dataframe()` | Tạo `authors_joined`, `categories_joined`, `summary_chars`, `age_days`, `text_for_embedding` | Clean artifact có 16 cột; ba derived-column checks đều PASS |
| Tạo evaluation samples | `build_test_set()` | 16 câu hỏi cân bằng bốn loại, ground truth lấy từ clean data | `test_set.json`: 4 summary, 4 authors, 4 date, 4 categories |
| Giữ document lineage | `_question_payload()` | Mỗi sample có ID unique và `ground_truth_doc_ids` trỏ về DOI sạch | 4 ground-truth document IDs đều tồn tại trong baseline index |
| Ghi evaluation artifact | `build_test_set()` | JSON tái sử dụng nguyên vẹn cho baseline/corrupted/repaired | Ba evaluation run đều đọc cùng `data/eval/test_set.json` |

### Output thực tế

```text
Raw records:                 24
Clean rows:                  24
Clean columns:               16
Unique paper_id:             24
Empty text_for_embedding:     0
Evaluation samples:          16
Question types:               4 (mỗi loại 4 câu)
```

Artifact chính:

- `data/clean/papers_clean.csv`
- `data/clean/papers_clean.json`
- `data/eval/test_set.json`
- `data/results/baseline_answers.json`
- `data/results/corrupted_answers.json`
- `data/results/repaired_answers.json`

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Metadata từ Crossref có thể chứa whitespace thừa, JATS/XML markup, HTML entities, trường thiếu, ngày không hợp lệ và DOI trùng. Dữ liệu này cần được đưa về một schema ổn định trước khi embedding. Evaluation set cũng phải lấy ground truth từ clean data, giữ document identity xuyên suốt và dùng format câu hỏi tương thích với QA code của starter.

### Cách triển khai cleaning

`build_clean_dataframe()` thực hiện:

1. Chuẩn hóa `paper_id`, `title`, `summary`, authors và categories.
2. Xóa markup, decode HTML entities và gom whitespace.
3. Parse `published`/`updated` theo UTC.
4. Loại record thiếu `paper_id`, title, summary hoặc publication date hợp lệ.
5. Loại publication date lớn hơn ngày chạy.
6. Dedupe theo DOI viết thường, giữ record có `updated` mới nhất.
7. Tính `summary_chars` và `age_days`.
8. Tạo `text_for_embedding` với thứ tự nhãn cố định: Title, Summary, Authors, Categories, Published.
9. Sắp xếp paper mới nhất trước và trả về đúng 16 cột.

Việc giữ `published` và `updated` dưới dạng `YYYY-MM-DD` giúp CSV, JSON và Chroma metadata có giá trị ổn định. Authors/categories vẫn được giữ cả dạng list và dạng joined string: list phục vụ lineage/data model, còn joined string phù hợp với Chroma metadata và answer extraction.

### Cách triển khai evaluation set

`build_test_set()` kiểm tra clean schema và yêu cầu ít nhất bốn paper hợp lệ, unique. Hàm chọn deterministic bốn paper mới nhất rồi tạo bốn loại câu hỏi:

- `summary`: ground truth là câu đầu tiên của summary;
- `authors`: ground truth là `authors_joined`;
- `date`: ground truth là `published`;
- `categories`: ground truth là `categories_joined`.

Nếu bốn paper chính thiếu một loại metadata, hàm backfill từ paper khác trong clean corpus thay vì tự tạo ground truth. Nếu toàn corpus không có ground truth cho một question type, hàm dừng với `ValueError`.

QA starter dùng regex để lấy exact title trong dấu nháy đơn. Vì vậy câu hỏi đặt lookup value trong `'...'`. Nếu title có dấu nháy đơn, hàm dùng DOI làm lookup value để regex không cắt sai title. Mỗi sample chứa `ground_truth_doc_ids=[paper_id]`, nhờ vậy evaluator đo được paper đúng có nằm trong top-k hay không.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Cleaning input | `list[PaperRecord]`, `datetime run_date` |
| Cleaning output | DataFrame 16 cột, sẵn sàng cho CSV/JSON/Chroma |
| Evaluation input | Clean DataFrame có `paper_id`, `title`, `summary`, `authors_joined`, `categories_joined`, `published` |
| Evaluation output | List/JSON gồm `id`, `question_type`, `question`, `ground_truth`, `ground_truth_doc_ids` |
| Module phụ thuộc | `core.utils`, `ingestion.crossref.PaperRecord`, Pandas |
| Module sử dụng output | `retrieval.index`, `retrieval.qa`, `evaluation.metrics`, baseline/corruption pipelines |
| Điều kiện lỗi | Record thiếu dữ liệu, ngày invalid/tương lai, DOI trùng, thiếu clean columns, dưới 4 paper hoặc thiếu toàn bộ ground truth của một question type |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
python -m pytest tests/ -q
```

- **Kết quả mong đợi:** clean/index/test set/metrics/quality reports được sinh; cùng test set được dùng cho cả ba trạng thái; corrupted giảm chất lượng và repaired phục hồi.
- **Kết quả thực tế:** baseline và corruption flow thành công; test suite hiện có báo `4 passed`; 24 clean rows, 16 evaluation samples; corrupted validation và repaired validation đều PASS.
- **Artifact/log:** `data/results/phase1_run_summary.json`, `data/results/corruption_run_summary.json`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Evaluation set phải tái lập được, có ground truth chính xác và tương thích với `answer_question()` của starter.
- **Các phương án đã cân nhắc:** sinh câu hỏi bằng LLM; chọn paper ngẫu nhiên; hoặc dùng template và chọn paper deterministic.
- **Phương án đã chọn:** dùng template cho bốn question types và chọn deterministic bốn paper mới nhất; dùng DOI làm fallback lookup khi title chứa dấu nháy đơn.
- **Lý do:** không phát sinh ground truth giả, không phụ thuộc API khi build test set, cùng clean input luôn sinh cùng evaluation set và phù hợp với exact lookup hiện có.
- **Trade-off:** chọn paper mới nhất giúp corruption `drop_latest_records` tạo impact đo được, nhưng corpus hiện có cùng publication date nên nhóm câu hỏi `date` thiếu khả năng phân biệt tài liệu.
- **Bằng chứng:** test set có 16 ID unique và 4 document IDs hợp lệ; baseline đạt hit 16/16. Sau corruption, hai trong bốn document của test set bị drop nên hit còn 8/16; repaired trở lại 16/16.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** `python script/run_phase1.py` dừng với `ValueError: Cleaning produced an empty dataframe.` dù raw snapshot có 22 records.
- **Cách tái hiện:** chạy baseline với raw snapshot ban đầu rồi kiểm tra các giá trị `published`.
- **Nguyên nhân gốc:** source filter chỉ có `from-pub-date` nhưng không có upper bound. Crossref trả các publication đã lên lịch trong tương lai; cả 22 records có ngày từ `2026-12-31` đến `2028-06-15`, trong khi ngày chạy là `2026-08-06`. Cleaning loại đúng các record có ngày tương lai nên DataFrame trở thành rỗng.
- **Cách xử lý:** phối hợp với source/integration owner thêm `until-pub-date:2026-08-06` vào filter và refresh raw snapshot; không bỏ validation ngày tương lai trong cleaning.
- **Cách xác minh sau khi sửa:** raw snapshot mới có 24 records, cleaning tạo 24 rows; baseline đạt 12/12 quality checks PASS và freshness `is_fresh=true`.
- **Điều học được:** source query và cleaning là một contract liên module. Cleaning fail-fast giúp phát hiện filter nguồn sai thay vì âm thầm build một index rỗng.

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?** Crossref response được lưu raw để truy vết, parse thành `PaperRecord`, cleaning tạo schema cùng `text_for_embedding`, MiniLM biến text thành vector và ChromaDB lưu vector với metadata.
2. **Evaluation set và ground-truth document IDs đo chất lượng ra sao?** Mỗi câu hỏi chứa answer chuẩn và DOI chuẩn. Retrieval hit khi DOI chuẩn xuất hiện trong top-k. Answer được so với ground truth bằng token F1 và Gemini judge.
3. **Quality checks khác freshness monitoring thế nào?** Quality kiểm tra completeness, uniqueness, validity và consistency; freshness đo dữ liệu có quá cũ so với threshold 180 ngày hay không.
4. **Vì sao dùng cùng test set cho ba trạng thái?** Giữ question, ground truth, top-k và evaluator cố định giúp thay đổi metric phản ánh thay đổi của dữ liệu/index, không phải do đổi bài kiểm tra.
5. **Repair thành công dựa trên gì?** Repaired dataset được dựng lại từ raw snapshot; digest nội dung và paper-ID set phải khớp baseline, quality/freshness phải phục hồi và agent metrics phải trở lại baseline trên cùng test set.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.5000 | 1.0000 | Corruption làm mất 8/16 retrieval hits; repair phục hồi hoàn toàn |
| `mean_token_f1` | 1.0000 | 0.6244 | 1.0000 | Giảm 0.3756; không giảm sâu bằng hit rate do câu hỏi date trùng answer |
| `judge_accuracy` | 1.0000 | 0.5625 | 1.0000 | Giảm 0.4375 rồi phục hồi 100% |
| `mean_judge_score` | 5.0000 | 3.3750 | 5.0000 | Giảm 1.625 điểm rồi trở lại baseline |
| Quality checks | PASS, 0/12 fail | FAIL, 5/12 fail | PASS, 0/12 fail | Corrupted fail uniqueness, summary length, noise, title truncation và freshness |
| Freshness status | Fresh, 0/24 stale | Not fresh, 3/24 stale | Fresh, 0/24 stale | Ba publication date bị lùi 5 năm rồi được repair |

Ragas không chạy; cả ba metrics JSON ghi `Set RUN_RAGAS=1 to enable the slower Ragas pass.` Gemini judge được sử dụng cho toàn bộ 48 answers, không answer nào dùng fallback heuristic.

### Hai chuỗi nguyên nhân–bằng chứng

1. `drop_latest_records` xóa ba papers, trong đó hai papers thuộc bốn documents của test set → tám câu hỏi mất ground-truth document khỏi corrupted index → `retrieval_hit_rate` giảm từ 1.0000 xuống 0.5000, `judge_accuracy` xuống 0.5625 và `mean_judge_score` xuống 3.3750. Đồng thời các corruption blank summary/noise/truncated title/duplicate/stale date làm quality chuyển từ PASS sang FAIL ở 5/12 checks và freshness có 3/24 stale rows.
2. `repair_from_raw_records()` dựng lại clean data từ `data/raw/crossref_records.json` → validation xác nhận `paper_id_set_match=true`, `content_digest_match=true`, không còn noise/title truncation và `repair_valid=true` → quality về 12/12 PASS, freshness về fresh và cả bốn agent metrics trở lại đúng baseline.

### Corruption ảnh hưởng rõ nhất

`drop_latest_records` ảnh hưởng rõ nhất đến evaluation vì test set được build từ bốn paper mới nhất. Hai trong bốn target documents bị xóa, và mỗi document có bốn question types, tạo đúng tám retrieval misses trên tổng 16 câu.

### Kết quả khác kỳ vọng

`mean_token_f1` corrupted là 0.6244, cao hơn dự đoán gần 0.5. Phân tích `corrupted_answers.json` theo question type cho thấy:

| Question type | Retrieval hit | Mean token F1 | Mean judge score |
| --- | ---: | ---: | ---: |
| Summary | 2/4 | 0.3368 | 2.0 |
| Authors | 2/4 | 0.5000 | 3.0 |
| Date | 2/4 | 1.0000 | 5.0 |
| Categories | 2/4 | 0.6607 | 3.5 |

Cả 24 papers có cùng `published=2026-08-06`, nên câu hỏi date vẫn nhận answer đúng khi retrieval nhầm paper. Đây là giới hạn của test set/corpus hiện tại: với date questions, token F1 và judge score không phản ánh được document identity. Vì vậy cần đọc `retrieved_doc_ids` cùng answer metrics, không chỉ nhìn token F1.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Clean schema là contract chung giữa ingestion, embedding, retrieval, evaluation và observability; thay đổi tên/kiểu cột có thể làm hỏng toàn pipeline.
2. Evaluation set phải deterministic, lấy ground truth từ dữ liệu thật và giữ cố định giữa baseline/corrupted/repaired để phép so sánh công bằng.
3. Answer đúng không luôn đồng nghĩa retrieval đúng. Trường hợp tất cả paper cùng publication date cho thấy phải phân tích đồng thời retrieval hit, answer metric và từng question type.

### Nếu có thêm thời gian

Tôi sẽ mở rộng nguồn theo khoảng ngày đa dạng hơn để câu hỏi `date` phân biệt được documents, đồng thời thêm unit tests chính thức cho `build_clean_dataframe()` và `build_test_set()`. Cải thiện sẽ được đo bằng coverage test và việc token F1 của nhóm date giảm khi target document thực sự bị xóa.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Kết luận quality/freshness khớp với `data/quality/`.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đặng Tiến Thành  
**MSSV:** 2A202601305  
**Ngày xác nhận:** 2026-08-06
