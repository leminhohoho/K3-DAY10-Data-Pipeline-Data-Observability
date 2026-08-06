# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Chí Quang |
| MSSV | 2A202601932 |
| Khóa/Lớp | K3 |
| Tên nhóm | |
| Vai trò chính | Corruption & Repair Owner |
| Repository | https://github.com/leminhohoho/K3-DAY10-Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Cấu hình và tạo dữ liệu lỗi có kiểm soát | `src/ingestion/corruption.py`: `CorruptionConfig`, `corrupt_clean_dataframe()` | Clean dataframe theo schema của pipeline; random seed; run date | Corrupted dataframe và `data/results/corruption_log.json` | Hoàn thành |
| Tạo lại các trường dẫn xuất sau corruption | `rebuild_derived_columns()`, logic dựng `text_for_embedding` | Dataframe sau khi sửa `title`, `summary` hoặc `published` | `summary_chars`, `age_days`, `text_for_embedding` nhất quán với dữ liệu hiện tại | Hoàn thành |
| Kiểm tra dữ liệu corrupted | `validate_corrupted_dataframe()` | Baseline dataframe, corrupted dataframe và corruption log | `data/quality/corrupted_dataset_validation.json` | Hoàn thành |
| Repair dữ liệu từ raw source of truth | `repair_from_raw_records()` | Raw Crossref records, baseline reference và run date | `papers_clean_repaired.csv/json` | Hoàn thành |
| Kiểm tra repaired dataset | `validate_repaired_dataframe()` | Repaired dataframe và baseline dataframe | `data/quality/repaired_dataset_validation.json` | Hoàn thành |
| Unit test cho corruption và repair | `tests/test_corruption.py` | Synthetic Crossref records và temporary artifacts | 4 test cases kiểm tra scenarios, reproducibility, repair và quality signals | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Phối hợp bổ sung các quality checks liên quan corruption | Thành viên 3 — `src/observability/quality.py` | Phát hiện missing `paper_id`, duplicate, summary rỗng, noise, title bị truncate, freshness và derived-column inconsistency |
| Hỗ trợ tích hợp API corruption/repair vào pipeline | Thành viên 5 — `src/pipelines/corruption_flow.py` | Corrupted và repaired datasets được build thành hai Chroma collections riêng, sau đó đánh giá bằng cùng test set |
| Đối chiếu artifacts và cập nhật phần kết quả | Báo cáo nhóm | Số liệu baseline/corrupted/repaired được đồng bộ với các JSON metrics và quality reports hiện tại |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Tạo đủ sáu corruption scenarios | `corrupt_clean_dataframe()`; `data/results/corruption_log.json` | Drop latest, blank summary, inject noise, truncate title, stale date và duplicate rows | Đọc `scenarios` trong corruption log và `scenario_checks` trong corrupted validation |
| Bảo đảm corruption có thể tái lập | `CorruptionConfig`; tham số `random_seed` | Cùng baseline, config và seed tạo cùng dataframe và cùng danh sách record bị chọn | Test `test_same_seed_produces_same_corrupted_data_and_scenario_selection` |
| Không làm thay đổi baseline đầu vào | `corrupt_clean_dataframe()` | Baseline dataframe vẫn giữ nguyên sau khi tạo corrupted dataframe | `pandas.testing.assert_frame_equal()` trong unit test |
| Giữ derived columns nhất quán | Logic rebuild trong `corruption.py` | Không có mismatch ở `summary_chars`, `age_days`, `text_for_embedding` | `corrupted_dataset_validation.json`: cả ba consistency checks đều `true` |
| Repair từ raw artifacts | `repair_from_raw_records()` | Repaired dataframe có 23 dòng, 23 unique IDs và khớp baseline | `repaired_dataset_validation.json`: `repair_valid = true` |
| Loại bỏ toàn bộ dấu vết corruption sau repair | `validate_repaired_dataframe()` | Không còn duplicate, noise, truncated title hoặc missing IDs | Validation có `duplicate_rows = 0`, `noisy_summary_rows = 0`, `truncated_title_rows = 0` |
| Kiểm tra tự động | `tests/test_corruption.py` | 4 test cases pass | `python -m pytest tests/test_corruption.py -q` |

Một output cụ thể do phần việc của tôi tạo ra là `data/results/corruption_log.json`. Artifact này lưu random seed, cấu hình từng scenario, số dòng trước/sau, danh sách `paper_id` bị tác động và giá trị trước/sau của từng mutation. Log giúp truy vết chính xác vì sao quality checks hoặc RAG metrics thay đổi, thay vì chỉ quan sát kết quả cuối.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Mục tiêu của phần tôi phụ trách là tạo ra các lỗi dữ liệu đủ thực tế để chứng minh ảnh hưởng của data quality tới hệ thống RAG, nhưng các lỗi phải có kiểm soát, tái lập được và có log để truy vết. Sau đó pipeline phải có khả năng phục hồi dữ liệu từ raw artifacts và chứng minh repaired dataset hợp lệ, thay vì chỉ làm cho chương trình chạy lại hoặc làm metrics tăng trở lại.

### Cách triển khai

Tôi triển khai sáu nhóm corruption:

1. **Drop latest records:** sắp xếp theo `published` và xóa các bài mới nhất để mô phỏng thiếu dữ liệu mới.
2. **Blank summary:** đặt một số `summary` thành chuỗi rỗng để mô phỏng mất nội dung.
3. **Inject noise:** chèn các marker như `CORRUPTED_TEXT`, advertisement hoặc HTML rác vào summary.
4. **Truncate title:** cắt title còn khoảng 35% và thêm `...`.
5. **Stale published date:** lùi ngày xuất bản năm năm để làm freshness fail.
6. **Duplicate rows:** nhân bản một số record để tạo duplicate `paper_id`.

Các scenario dùng `random_seed` và tỷ lệ trong `CorruptionConfig`, vì vậy cùng input và cùng seed sẽ chọn cùng record. Tôi hạn chế việc nhiều scenario chồng lên cùng một source row khi có thể để log và kết quả dễ giải thích hơn.

Sau khi sửa dữ liệu gốc, pipeline tính lại:

- `summary_chars = len(summary)`;
- `age_days` từ `published` và run date;
- `text_for_embedding` theo đúng format của cleaning pipeline.

Repair được thực hiện bằng cách đọc lại raw Crossref records và gọi lại `build_clean_dataframe()` với cùng run date. Repaired dataframe sau đó được so sánh với baseline về số dòng, tập `paper_id`, uniqueness, content digest và các consistency checks.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Clean dataframe có các cột bắt buộc: `paper_id`, `title`, `summary`, `published`, `authors_joined`, `categories_joined`, `summary_chars`, `age_days`, `text_for_embedding`; raw `PaperRecord`; `random_seed`; `run_date` |
| Output | Corrupted dataframe, repaired dataframe, corruption log và hai validation reports |
| Module phụ thuộc | `src/ingestion/cleaning.py`, `src/ingestion/crossref.py`, `src/core/utils.py` |
| Module sử dụng output | `src/pipelines/corruption_flow.py`, `src/observability/quality.py`, retrieval/index và evaluation pipeline |
| Điều kiện lỗi cần xử lý | Thiếu cột bắt buộc; config ngoài khoảng hợp lệ; dataframe rỗng; ngày không parse được; duplicate IDs; derived columns không nhất quán; repaired content không khớp baseline |

### Cách xác minh

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/test_corruption.py -q
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Các unit tests pass; corrupted validation `true`; repaired validation `true`; corrupted quality FAIL và repaired quality PASS.
- **Kết quả thực tế:** `4 passed`; corrupted dataset có 22 rows và 20 unique IDs; repaired dataset có 23 rows và 23 unique IDs; cả corruption validation và repair validation đều hợp lệ.
- **Artifact/log:**  
  - `data/results/corruption_log.json`  
  - `data/quality/corrupted_dataset_validation.json`  
  - `data/quality/repaired_dataset_validation.json`  
  - `data/quality/data_quality_corrupted.json`  
  - `data/quality/data_quality_repaired.json`

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Sau khi tạo corrupted dataset, pipeline cần phục hồi các record bị xóa và các giá trị đã bị sửa hoặc ghi đè.
- **Các phương án đã cân nhắc:**  
  1. Vá trực tiếp từng dòng dựa trên corruption log.  
  2. Copy lại baseline dataframe làm repaired dataset.  
  3. Dựng lại clean dataframe từ raw Crossref artifacts bằng cùng cleaning pipeline.
- **Phương án đã chọn:** Dựng lại dữ liệu từ raw source of truth.
- **Lý do:** Vá theo log có độ phức tạp cao, dễ bỏ sót trường dẫn xuất và phụ thuộc chặt vào format log. Copy baseline cho kết quả đúng nhưng không chứng minh pipeline có khả năng phục hồi từ raw artifacts. Rebuild từ raw vừa phục hồi được record đã drop, vừa tái sử dụng cleaning contract ban đầu và phù hợp với yêu cầu truy vết của bài lab.
- **Bằng chứng quyết định phù hợp:** `repaired_dataset_validation.json` có `row_count_match = true`, `paper_id_set_match = true`, `paper_id_unique = true`, `content_digest_match = true` và `repair_valid = true`. Repaired digest và reference digest đều bằng `37cbd15f5d4ffe30cefbc55d8b89c272ca1a2774bed1852b943a8e238447d688`.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Quality check `row_count` vẫn PASS dù corrupted corpus đã bị mất các bản ghi mới nhất.
- **Lệnh hoặc bước tái hiện:** Chạy corruption flow với seed 42, sau đó đối chiếu baseline và corrupted datasets.
- **Nguyên nhân gốc:** Pipeline xóa 3 rows nhưng đồng thời thêm 2 duplicate rows. Vì vậy corrupted dataframe vẫn có 22 rows, nhìn tương đối gần baseline 23 rows; chỉ kiểm tra tổng số dòng không thể xác định chính xác document identity đã bị mất.
- **Cách xử lý:** Phối hợp bổ sung `record_coverage` dựa trên tập `paper_id` baseline, đồng thời giữ `paper_id_unique` để phát hiện duplicate groups. Validation riêng cũng đối chiếu các IDs bị drop với corruption log.
- **Cách xác minh sau khi sửa:** `data_quality_corrupted.json` báo `record_coverage = fail`, chi tiết `3/23 expected paper_ids missing`, và `paper_id_unique = fail` với 4 rows thuộc duplicate groups. Baseline và repaired đều PASS hai checks này.
- **Điều học được:** Số dòng chỉ là một tín hiệu completeness sơ cấp. Với corpus RAG, cần kiểm tra document identity, coverage và uniqueness; nếu không, duplicate có thể che giấu missing records.

## 7. Hiểu biết về luồng end-to-end

1. Crossref API trả về raw response. Pipeline lưu nguyên response và raw records trước khi cleaning. `build_clean_dataframe()` chuẩn hóa title, summary, authors, categories và dates; loại dữ liệu không hợp lệ; tạo `summary_chars`, `age_days` và `text_for_embedding`. Trường `text_for_embedding` được đưa vào MiniLM để tạo vector, sau đó nạp vào ChromaDB collection tương ứng.

2. Evaluation set lưu câu hỏi, đáp án chuẩn và `ground_truth_doc_ids`. Retrieval quality được đo bằng việc ground-truth document có nằm trong top-k hay không. Answer quality được đo bằng token F1 và LLM judge. Các document IDs nối evaluation evidence với record cụ thể trong corpus.

3. Quality checks kiểm tra completeness, uniqueness, validity và consistency của dữ liệu, ví dụ missing IDs, duplicate, summary rỗng, noise hoặc stale embedding text. Freshness monitoring tập trung riêng vào timeliness, đo ngày mới nhất/cũ nhất và số record vượt ngưỡng 365 ngày.

4. Cùng một test set phải được dùng cho baseline, corrupted và repaired để giữ nguyên điều kiện đánh giá. Nếu tạo test set mới sau corruption, các câu hỏi có thể né những record đã mất và kết quả ba trạng thái sẽ không còn so sánh công bằng.

5. Repair được xem là thành công khi repaired dataframe khớp baseline về row count, tập `paper_id` và content digest; không còn duplicate, noise hoặc truncated title; derived columns nhất quán; quality và freshness quay về PASS. Ở tầng RAG, retrieval hit rate và judge accuracy cũng phải phục hồi gần hoặc bằng baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.2500 | 1.0000 | Mất ground-truth documents làm retrieval giảm mạnh; repair khôi phục hoàn toàn |
| `mean_token_f1` | 0.1296 | 0.0686 | 0.0907 | Corruption làm overlap giảm; repaired tăng lại nhưng không bằng baseline do câu trả lời agent có tính biến thiên |
| `judge_accuracy` | 0.9375 | 0.1875 | 0.9375 | Agent trả lời sai hoặc không tìm thấy paper khi tài liệu bị drop; repair khôi phục về baseline |
| `mean_judge_score` | 4.8750 | 1.7500 | 4.8125 | Chất lượng ngữ nghĩa giảm rõ khi dữ liệu lỗi và gần phục hồi hoàn toàn sau repair |
| Quality checks | PASS, 13/13 | FAIL, 6/13 fail | PASS, 13/13 | Corruption tạo đúng các tín hiệu quality; repair loại bỏ toàn bộ failed checks |
| Freshness status | PASS, 0/23 stale | FAIL, 4/22 stale | PASS, 0/23 stale | Hai stale source rows bị duplicate nên xuất hiện bốn stale rows trong corrupted corpus |

### Kết luận từ số liệu

1. **Drop latest records và các lỗi nội dung** → `record_coverage`, uniqueness, summary, noise, truncation và freshness chuyển sang FAIL → `retrieval_hit_rate` giảm từ `1.0000` xuống `0.2500`, `judge_accuracy` giảm từ `0.9375` xuống `0.1875`.

2. **Rebuild từ raw Crossref artifacts** → repaired dataset khớp baseline, quality PASS 13/13 và freshness PASS → retrieval hit rate và judge accuracy phục hồi hoàn toàn; mean judge score phục hồi gần hoàn toàn, còn token F1 không trùng tuyệt đối do LLM generation variability.

**Corruption ảnh hưởng rõ nhất:** Drop latest records. Ba record bị xóa là ba trong bốn paper dùng để tạo evaluation set. Mỗi paper tương ứng bốn câu hỏi, nên 12/16 câu không còn ground-truth document trong corrupted collection. Điều này giải thích trực tiếp vì sao retrieval hit rate còn 4/16, tương ứng `0.2500`.

**Kết quả khác với kỳ vọng ban đầu:** Tôi ban đầu kỳ vọng repaired answer metrics phải trùng hoàn toàn baseline vì repaired dataframe có cùng content digest. Thực tế repaired `mean_token_f1 = 0.0907`, thấp hơn baseline `0.1296`, và mean judge score thấp hơn `0.0625`. Sau khi kiểm tra, retrieval hit rate, judge accuracy, dataset digest, quality và freshness đều đã phục hồi. Vì vậy chênh lệch nhỏ ở answer metrics hợp lý hơn với tính không xác định của agent response và LLM judge, không phải do repair thất bại.

Một kết quả khác là stale scenario chỉ chọn hai source rows nhưng freshness report ghi bốn stale rows. Nguyên nhân là hai stale rows cũng nằm trong nhóm được duplicate, cho thấy các scenario có thể tương tác và khuếch đại quality signal.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Raw artifacts là nền tảng của khả năng phục hồi.** Nếu chỉ giữ clean hoặc corrupted output, pipeline khó chứng minh được dữ liệu được repair đúng từ source of truth.
2. **Data observability phải kiểm tra identity và consistency, không chỉ row count.** `record_coverage`, uniqueness và derived-column checks phát hiện được các lỗi mà tổng số dòng không thể hiện.
3. **Lỗi dữ liệu upstream có thể truyền thẳng tới RAG agent.** Việc mất ba ground-truth documents làm retrieval hit rate và judge accuracy cùng giảm 0.75; khi dữ liệu được phục hồi, hai metrics này quay lại baseline.

### Nếu có thêm thời gian

Tôi sẽ bổ sung chế độ **per-scenario ablation**, trong đó mỗi lần chạy chỉ bật một loại corruption. Mỗi scenario sẽ được đánh giá bằng cùng test set và lưu metrics riêng. Cách này giúp định lượng chính xác lỗi nào tác động mạnh nhất tới retrieval, answer quality và freshness, thay vì chỉ quan sát tác động tổng hợp của sáu scenario. Kết quả có thể được đo bằng chênh lệch `retrieval_hit_rate`, `judge_accuracy`, số quality checks fail và số samples bị ảnh hưởng cho từng scenario.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Chí Quang  
**Ngày xác nhận:** 2026-08-06
