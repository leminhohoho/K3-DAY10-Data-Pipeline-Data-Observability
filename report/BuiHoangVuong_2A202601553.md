# Member Role Report — Day 10: Data Pipeline & Data Observability

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Bùi Hoàng Vương |
| MSSV | 2A202601553 |
| Khóa/Lớp | K3 |
| Tên nhóm | Not specified (bảng thông tin nhóm trong `report/group_report.md` để trống) |
| Vai trò chính | Source owner — raw ingestion từ Crossref |
| Module sở hữu | `src/ingestion/crossref.py`; artifacts trong `data/raw/` |
| Repository | https://github.com/leminhohoho/K3-DAY10-Data-Pipeline-Data-Observability |
| Commit của cá nhân | `185d260` — "Vuong_Task1" (2026-08-06) |
| Ngày hoàn thành | 2026-08-06 |

---

## 1. Mục tiêu bài lab

Bài lab xây dựng và vận hành một data pipeline hai pha cho hệ thống RAG dùng metadata bài báo học thuật từ Crossref, đồng thời chứng minh bằng artifact và metrics rằng **chất lượng dữ liệu ảnh hưởng trực tiếp tới chất lượng của agent**.

```text
Crossref API -> raw data -> cleaned data -> embedding + ChromaDB -> RAG evaluation
    -> quality/freshness reports -> corrupt data -> evaluate impact
    -> repair from raw data -> compare baseline/corrupted/repaired
```

- **Pha 1:** lấy dữ liệu, lưu raw artifacts để truy vết, làm sạch về schema chuẩn, tạo embedding và index, xây evaluation set, đo metrics baseline, chạy data quality/freshness checks và sinh báo cáo.
- **Pha 2:** tạo lỗi dữ liệu có chủ đích, đo lại trên cùng evaluation set, repair từ nguồn raw và so sánh ba trạng thái.

Trong luồng này, vai trò của tôi nằm ở mắt xích đầu tiên: bảo đảm dữ liệu nguồn được lấy về ổn định, được parse thành schema nhất quán và được **lưu bất biến trong `data/raw/`** — vì đây cũng chính là source of truth mà bước repair ở Pha 2 phải dựa vào.

## 2. Yêu cầu và các tính năng đã được cài đặt

### Yêu cầu đối với phần ingestion (Guide — Bước 3)

| Yêu cầu | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Gọi external source để lấy danh sách paper | Đã cài đặt | `fetch_source_records()` gọi `https://api.crossref.org/works` |
| Parse response thành record schema nhất quán | Đã cài đặt | `parse_crossref_payload()` trả về `list[PaperRecord]` 11 trường |
| Lưu raw response vào `data/raw/` | Đã cài đặt | `data/raw/crossref_response.json` |
| Lưu raw records đã parse vào `data/raw/` | Đã cài đặt | `data/raw/crossref_records.json` (23 records) |
| Xử lý rate limit `429`/`503` bằng retry/backoff | Đã cài đặt | `_request_payload()`: 4 attempts, backoff, đọc `Retry-After` |
| Đọc lại raw snapshot để tái sử dụng/repair | Đã cài đặt | `load_raw_records()` map JSON về `PaperRecord` |

### Trạng thái chung của repository

Starter ban đầu chứa `TODO(student)` và `NotImplementedError`. Trên phiên bản hiện tại, lệnh kiểm tra trong README không còn tìm thấy phần chưa hoàn thành nào trong `src/`:

```bash
grep -RInE 'TODO\(student\)|NotImplementedError' src   # không còn kết quả
```

Toàn bộ các module bắt buộc (`crossref.py`, `cleaning.py`, `testset.py`, `quality.py`, `reporting.py`, `phase1.py`, `corruption.py`, `corruption_flow.py`) đều đã được cài đặt và cả hai pipeline đã sinh đủ artifacts trong `data/`.

### Record schema do tôi bàn giao

`PaperRecord` gồm 11 trường, là contract giữa ingestion và cleaning:

```text
paper_id, title, summary, authors, categories, primary_category,
published, updated, abs_url, pdf_url, comment
```

## 3. Phần đóng góp cá nhân

### Phạm vi sở hữu

| Deliverable | File/hàm | Input | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Gọi source API có retry | `crossref.py` — `_request_payload()`, `fetch_source_records()` | `settings.source_query`, `source_filter`, `max_results` | `data/raw/crossref_response.json` | Hoàn thành |
| Parse payload thành record schema | `crossref.py` — `parse_crossref_payload()` và các helper (`_clean_abstract`, `_authors`, `_categories`, `_date_from_parts`, `_published_date`, `_updated_date`, `_pdf_url`, `_comment`) | Crossref JSON payload | `list[PaperRecord]`, `data/raw/crossref_records.json` | Hoàn thành |
| Đọc lại raw snapshot | `crossref.py` — `load_raw_records()` | `data/raw/crossref_records.json` | `list[PaperRecord]` cho baseline và repair | Hoàn thành |

Bằng chứng ownership: commit `185d260` ("Vuong_Task1") thay thế ba `NotImplementedError` trong `src/ingestion/crossref.py` bằng phần cài đặt hoàn chỉnh (+250/−20 dòng) và bổ sung hai raw artifacts.

### Ranh giới rõ ràng — phần **không** thuộc đóng góp của tôi

Để tránh nhận ownership sai, tôi ghi rõ:

- `cleaning.py`, `testset.py` — Thành viên 2; `quality.py`, `reporting.py` — Thành viên 3; `corruption.py`, `tests/test_corruption.py` — Thành viên 4; `phase1.py`, `corruption_flow.py` — Thành viên 5.
- Tham số `sort` trong `fetch_source_records()`: bản của tôi dùng `sort=published, order=desc`. Việc đổi sang `sort=relevance` (kèm comment giải thích) và refresh lại raw snapshot được thực hiện sau đó bởi integration owner trong commit `2d3317c`. Tôi không nhận phần thay đổi này.
- `source_filter` (bao gồm `until-pub-date`) nằm trong `src/core/config.py`, không thuộc file tôi sở hữu; tôi tham gia ở mức phối hợp chẩn đoán và fetch lại dữ liệu.
- Mức độ tham gia của tôi vào việc chạy hai pipeline end-to-end và sinh metrics: **Not specified** trong lịch sử repository — các run summary hiện tại được sinh trên máy của thành viên khác.

## 4. Giải thích kỹ thuật

### 4.1 Gọi API có kiểm soát lỗi

`_request_payload()` gửi request kèm `User-Agent` định danh (Crossref khuyến nghị) và `timeout = 30s`, sau đó lặp tối đa `MAX_ATTEMPTS = 4`:

- Status thuộc `{429, 500, 502, 503, 504}` → coi là lỗi tạm thời, đọc header `Retry-After` nếu là số, ngược lại dùng backoff tuyến tính `2.0 × attempt`.
- `requests.RequestException` (timeout, lỗi mạng) → cũng backoff và thử lại.
- Hết số lần thử → `RuntimeError` kèm lỗi cuối cùng, để pipeline fail-fast thay vì ghi ra một raw artifact rỗng.

`fetch_source_records()` ghi **raw response nguyên vẹn trước khi parse**. Đây là quyết định quan trọng nhất của phần việc này: nếu logic parse thay đổi hoặc có bug, payload gốc vẫn còn để parse lại; và bước repair ở Pha 2 có một nguồn dữ liệu không bị corrupt để dựng lại dataset.

### 4.2 Parse payload thành schema nhất quán

`parse_crossref_payload()` duyệt `payload["message"]["items"]` và áp dụng các quy tắc:

| Vấn đề của dữ liệu Crossref | Cách xử lý |
| --- | --- |
| Abstract trả về dưới dạng JATS XML | `_clean_abstract()` bỏ tag `<...>`, unescape HTML entity, gom whitespace và cắt prefix `Abstract` |
| `title`, `container-title` là list | `_first_text()` lấy phần tử non-empty đầu tiên |
| Ngày ở dạng `{"date-parts": [[2025, 3, 7]]}`, có thể thiếu tháng/ngày | `_date_from_parts()` fill mặc định `01` và xuất `YYYY-MM-DD` |
| Nhiều loại trường ngày khác nhau | `_published_date()` ưu tiên `published` → `published-online` → `published-print` → `issued` → `created`; `_updated_date()` dùng `indexed` → `deposited` → `created`, fallback về `published` |
| Tác giả có khi ở `name`, có khi tách `given`/`family` | `_authors()` ghép và dedupe giữ thứ tự |
| Rất nhiều record không có `subject` | `_categories()` fallback sang `container-title` rồi `type` |
| DOI viết hoa/thường không đồng nhất | Chuẩn hóa `paper_id` về lowercase, dedupe theo DOI, giữ bản đầu tiên |
| Thiếu `URL` | `abs_url` fallback về `https://doi.org/{paper_id}` |

Record bị loại ngay tại tầng ingestion nếu thiếu một trong bốn trường tối thiểu: `paper_id`, `title`, `summary`, `published`.

### 4.3 Bằng chứng cụ thể trên snapshot hiện tại

Đối chiếu `data/raw/crossref_response.json` với `data/raw/crossref_records.json`:

```text
total-results của query:        216,618
items nhận về (rows=24):             24
raw records sau parse:               23
record bị loại:                       1
DOI bị loại:      10.6028/nist.ir.8579a
lý do:            abstract chỉ là <jats:p/> -> rỗng sau khi bỏ tag
```

Hai con số đáng chú ý khác trên snapshot này:

- **0/24 items có trường `subject`.** Nếu không có fallback `container-title`/`type` trong `_categories()`, toàn bộ 23 records sẽ có `categories = []`; khi đó `build_test_set()` không tạo được nhóm câu hỏi `categories` và sẽ dừng với `ValueError`. Fallback này là điều kiện cần để evaluation set 16 câu (4 loại × 4 paper) tồn tại.
- **19/23 records không có `pdf_url`** vì Crossref không cung cấp link `application/pdf` cho phần lớn record. Đây là giới hạn của nguồn, không phải lỗi parse; `abs_url` vẫn có đủ cho 23/23 record.

### 4.4 Contract với các module phía sau

| Thành phần | Mô tả |
| --- | --- |
| Input | `Settings` (`source_query`, `source_filter`, `max_results`, `paths`) |
| Output | `list[PaperRecord]`; `crossref_response.json`; `crossref_records.json` |
| Module phụ thuộc | `core.config`, `core.utils`, `requests` |
| Module sử dụng output | `ingestion.cleaning.build_clean_dataframe()`, `pipelines.phase1` (`_load_or_fetch_records`), `pipelines.corruption_flow` (repair qua `load_raw_records()`) |
| Điều kiện lỗi | Hết retry → `RuntimeError`; payload không có record dùng được → `RuntimeError`; snapshot không phải JSON list → `ValueError` |

`load_raw_records()` là điểm nối trực tiếp tới Pha 2: `corruption_flow.py` gọi hàm này rồi truyền vào `repair_from_raw_records()`. Nói cách khác, tính đúng đắn của repair phụ thuộc vào việc raw snapshot được ghi đầy đủ và đọc lại không mất trường nào.

## 5. Kiểm thử và kết quả

### 5.1 Cách xác minh phần việc của tôi

| Cách xác minh | Kết quả |
| --- | --- |
| Kiểm tra hai raw artifacts tồn tại và đúng định dạng | `crossref_response.json` (payload gốc), `crossref_records.json` (23 records, đủ 11 trường) |
| Đối chiếu số item trong response với số record sau parse | 24 → 23, chênh lệch 1 record được giải thích bằng abstract rỗng (mục 4.3) |
| Kiểm tra tính hợp lệ của dữ liệu đã parse | 23/23 record có `paper_id`, `title`, `summary`, `published`; 23 DOI duy nhất; `published` từ `2025-08-27` đến `2026-07-13` trên 16 ngày khác nhau |
| Kiểm tra ingestion không chặn pipeline | `phase1_report.md` ghi `Raw Records: 23`, `Clean Rows: 23` — cleaning không loại thêm record nào |
| Kiểm tra vai trò của raw trong repair | `repaired_dataset_validation.json`: `content_digest_match = true`, `repair_valid = true` |

### 5.2 Kết quả pipeline (số liệu của nhóm, đọc từ artifacts)

| Metric/signal | Baseline | Corrupted | Repaired |
| --- | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.0000 | 0.2500 | 1.0000 |
| `mean_token_f1` | 0.1296 | 0.0686 | 0.0907 |
| `judge_accuracy` | 0.9375 | 0.1875 | 0.9375 |
| `mean_judge_score` | 4.8750 | 1.7500 | 4.8125 |
| Data quality | PASS (13/13) | FAIL (6/13 fail) | PASS (13/13) |
| Freshness | Fresh, 0/23 stale | Not fresh, 4/22 stale | Fresh, 0/23 stale |

Nguồn: `data/results/baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json`, `data/quality/data_quality_*.json`, `freshness_*.json`.

Liên hệ trực tiếp tới phần việc của tôi: repaired corpus quay lại **23 rows / 23 unique `paper_id`**, `content_digest_match = true` so với baseline. Điều này chỉ đạt được vì `crossref_records.json` giữ đúng và đủ dữ liệu gốc — repair dựng lại từ raw chứ không vá dòng bị hỏng.

### 5.3 Giới hạn của việc kiểm thử

- Repository **không có unit test cho `crossref.py`**. Test suite hiện tại chỉ gồm `tests/test_corruption.py` (4 test cases, thuộc Thành viên 4). Kết quả `4 passed` được ghi trong `group_report.md` và trong commit `2d3317c`.
- Trên môi trường làm việc hiện tại của tôi, dependencies chưa được cài (`pandas` chưa có trong `.venv`), nên tôi **không chạy lại** `pytest` hay hai pipeline ở lần rà soát này. Toàn bộ số liệu trong báo cáo được đọc trực tiếp từ artifacts đã commit, và phần đối chiếu 24 → 23 record được thực hiện lại trên `crossref_response.json` đã lưu.

## 6. Vấn đề và cách xử lý

| Vấn đề | Nguyên nhân | Cách xử lý | Kết quả |
| --- | --- | --- | --- |
| Abstract từ Crossref không dùng được trực tiếp | Trả về dưới dạng JATS XML, kèm prefix `Abstract` và HTML entity | `_clean_abstract()` bỏ tag, unescape, gom whitespace, cắt prefix | 23/23 record có `summary` dùng được cho embedding |
| `has-abstract:true` vẫn lọt record không có nội dung abstract | Record `10.6028/nist.ir.8579a` có `<jats:p/>` rỗng — filter của Crossref chỉ kiểm tra sự tồn tại của trường | Kiểm tra lại **sau khi làm sạch**: summary rỗng thì loại record tại tầng parse | 1 record bị loại đúng lúc, không tạo document rỗng trong index |
| Toàn bộ record thiếu trường `subject` | Nguồn Crossref không cung cấp subject cho các record trong query này (0/24) | `_categories()` fallback sang `container-title` rồi `type` | 23/23 record có `categories`; nhóm câu hỏi `categories` trong test set xây được |
| Rủi ro `429`/`503` khi gọi API | Rate limit và lỗi tạm thời của Crossref | Retry 4 lần, đọc `Retry-After`, backoff tuyến tính, timeout 30s, `User-Agent` định danh | Snapshot được fetch thành công; README cũng ghi đây là cách xử lý chuẩn cho lỗi này |
| Clean dataframe rỗng ở lần chạy đầu | `source_filter` chỉ có `from-pub-date`; Crossref trả về các số báo đã lên lịch xuất bản trong tương lai, cleaning loại đúng mọi record có `published > run_date` | Nhóm bổ sung `until-pub-date` vào filter trong `src/core/config.py`; phần của tôi là fetch lại và xác minh raw snapshot mới | Raw snapshot mới hợp lệ về thời gian; cleaning giữ lại toàn bộ record |
| DOI không đồng nhất hoa/thường, có khả năng trùng | Dữ liệu nguồn không chuẩn hóa | Lowercase `paper_id` và dedupe theo DOI ngay tại parse | 23 `paper_id` duy nhất, `paper_id_unique` PASS ở baseline |

## 7. Giới hạn

Giới hạn thuộc phạm vi module của tôi:

1. **Không có regression test cho ingestion.** `parse_crossref_payload()` và `_request_payload()` chưa có test với payload mẫu (thiếu trường, `date-parts` khuyết, list rỗng, status 429). Hiện chỉ được xác minh gián tiếp qua artifacts.
2. **Retry không phủ hết loại lỗi.** Nếu Crossref trả về `200` với body không phải JSON hợp lệ, `response.json()` ném `ValueError` — không thuộc `requests.RequestException` nên không được retry và sẽ thoát khỏi vòng lặp.
3. **`Retry-After` chỉ được đọc khi là số nguyên.** Dạng HTTP-date sẽ bị bỏ qua và rơi về backoff mặc định.
4. **Số lượng record phụ thuộc nguồn sống.** `max_results = 24` nhưng chỉ 23 record dùng được; mỗi lần `REFRESH_SOURCE=1` có thể cho corpus khác, nên chỉ so sánh ba trạng thái trong cùng một lần chạy.
5. **`pdf_url` rỗng ở 19/23 record**, do Crossref không cung cấp link PDF — trường này gần như không mang thông tin trong corpus hiện tại.
6. **Không phân trang.** Chỉ lấy một trang `rows=24`; muốn mở rộng corpus phải bổ sung cursor paging.

Giới hạn ở mức toàn bài mà tôi quan sát được từ artifacts:

7. **`data/results/phase1_run_summary.json` chưa đồng bộ với các quality artifact hiện tại**: file ghi `quality_overall = "fail"` và `freshness_is_fresh = false`, trong khi `data_quality_baseline.json` và `phase1_report.md` đều PASS/fresh. Ngoài ra hai run summary còn chứa absolute path của một máy khác (`/Users/...`). `group_report.md` §12 cũng đã ghi nhận điểm này; cần chạy lại pipeline trước khi nộp để artifact khớp nhau.
8. **Ragas chưa chạy** (`RUN_RAGAS` chưa bật) nên `baseline_metrics.json` chỉ ghi trạng thái `skipped`, dù Guide — Bước 10 có liệt kê `ragas` trong nhóm chỉ số cần quan tâm.
9. **`data/quality/data_quality_smoke-test.json`** là artifact thử nghiệm còn sót lại (report name `smoke_test`, `paper_id_not_null` FAIL), không do pipeline nào sinh ra trong lần chạy cuối.

## 8. Kết luận

Tôi phụ trách mắt xích đầu tiên của pipeline: `src/ingestion/crossref.py` và hai raw artifacts trong `data/raw/`. Phần việc này đã hoàn thành: API được gọi có retry/backoff cho lỗi tạm thời, payload gốc được lưu trước khi parse, và 24 items được chuyển thành 23 `PaperRecord` theo một schema 11 trường nhất quán, với các record không đủ dữ liệu bị loại ngay tại nguồn.

Giá trị của phần việc này thể hiện rõ nhất ở Pha 2. Vì raw snapshot được giữ bất biến và `load_raw_records()` đọc lại đầy đủ, `repair_from_raw_records()` dựng lại được dataset sạch với `content_digest_match = true` và `repair_valid = true`, kéo `retrieval_hit_rate` từ `0.2500` trở lại `1.0000` và `judge_accuracy` từ `0.1875` về `0.9375`. Đây là bằng chứng cho luận điểm trung tâm của bài lab: pipeline chỉ có khả năng phục hồi khi tồn tại một source of truth không bị corrupt.

Điều tôi rút ra là các quyết định nhỏ ở tầng ingestion có ảnh hưởng lan xuống toàn pipeline: fallback cho `categories` quyết định evaluation set có đủ bốn loại câu hỏi hay không; việc loại record có abstract rỗng ngăn một document vô nghĩa lọt vào vector index; và việc ghi raw trước khi parse là điều kiện tiên quyết cho toàn bộ bước repair. Nếu có thêm thời gian, tôi sẽ ưu tiên viết unit test cho `parse_crossref_payload()` với các payload lỗi và bổ sung phân trang để mở rộng corpus.

---

### Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi chỉ nhận ownership cho `src/ingestion/crossref.py` và các raw artifacts; phần do thành viên khác thực hiện đã được ghi rõ.
- [x] Mọi số liệu trong báo cáo được đọc từ artifacts trong `data/` hoặc từ lịch sử commit.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng trên môi trường của mình (xem mục 5.3).
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Bùi Hoàng Vương
**MSSV:** 2A202601553
**Ngày xác nhận:** 2026-08-06
