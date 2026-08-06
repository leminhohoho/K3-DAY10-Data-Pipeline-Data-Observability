# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| Họ và tên       | Ngô Thành Đạt                                                                                                         |
| MSSV               | 2A202601323                                                                                                               |
| Khóa/Lớp         | K3                                                                                                                        |
| Tên nhóm         |                                                                                                                           |
| Vai trò chính    | Thành viên 5 — Pipeline integration & evidence owner                                                                   |
| Repository         | https://github.com/leminhohoho/K3-DAY10-Data-Pipeline-Data-Observability (branch`feature/member5-pipeline-integration`) |
| Ngày hoàn thành | 2026-08-06                                                                                                                |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable                       | File/hàm phụ trách                                                                                                                                                             | Input nhận vào                                                                                                                                                     | Output bàn giao                                                                                                                                                                                      | Trạng thái |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| Baseline orchestration                   | `src/pipelines/phase1.py` — `main()`, `_load_or_fetch_records`, `_validate_clean_dataframe`, `_load_or_build_test_set`, `_validate_test_set`, `_write_run_summary` | Raw records (TV1),`build_clean_dataframe` (TV2), `build_test_set` (TV2), `run_data_quality_checks`/`build_freshness_report`/`generate_phase1_report` (TV3) | `data/clean/`, `data/embeddings/`, `data/eval/test_set.json`, `data/results/baseline_metrics.json`, `baseline_answers.json`, `phase1_run_summary.json`, `data/reports/phase1_report.md` | Hoàn thành |
| Agent demo & bằng chứng multi-provider | `src/pipelines/phase1.py` — `_build_demo_answers`, `_agent_credentials_status`, `_normalize_agent_text`, `_run_agent_question`, `_retry_delay_seconds`               | `build_agent`/`run_agent_question` (starter), baseline index                                                                                                     | `data/results/agent_demo_answers.json` (`agent_status: ok`, 4/4 câu)                                                                                                                             | Hoàn thành |
| Corruption flow integration              | `src/pipelines/corruption_flow.py` — resolve merge, `run_corruption_flow()` wiring, persist run summary                                                                      | `corrupt_clean_dataframe`, `repair_from_raw_records`, `validate_corrupted_dataframe`, `validate_repaired_dataframe` (TV4)                                    | `data/results/corruption_run_summary.json`, `corrupted_*`/`repaired_*` metrics + answers, `data/reports/corruption_report.md`                                                                 | Hoàn thành |
| Reproducibility & consistency check      | Chạy lại end-to-end, đối chiếu report với artifact                                                                                                                          | Toàn bộ artifact trong`data/`                                                                                                                                    | Xác nhận`baseline_metrics.json` khớp `corruption_run_summary.json`                                                                                                                             | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                           | Thành viên/module được hỗ trợ                                              | Kết quả                                                                                          |
| -------------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Phát hiện và sửa blocker ingestion | TV1 (`crossref.py`) / TV2 (`cleaning.py`) — sửa tại `src/core/config.py` | Thêm`until-pub-date` vào `source_filter`; clean dataframe từ 0 → 24 dòng                  |
| Sửa cấu hình LLM provider           | Cả nhóm —`.env`, `.env.example`                                            | Đổi`LLM_MODEL` sang `gemini-flash-lite-latest`; LLM judge từ 0/48 → 48/48 lần chấm thật |
| Resolve merge conflict                 | TV4 (`corruption_flow.py`)                                                      | Giữ bản tích hợp dùng API mới của TV4, thêm lại`corruption_run_summary.json`            |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện                       | File/hàm/artifact liên quan                                | Kết quả bàn giao                                                                                                              | Cách xác minh                                                        |
| ------------------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Ghép baseline pipeline 8 bước                  | `phase1.py::main`                                          | 24 clean rows, 16 test samples, collection`papers-baseline`                                                                    | `python script/run_phase1.py`                                        |
| Validate contract trước khi build index         | `_validate_clean_dataframe`, `_validate_test_set`        | Fail-fast khi thiếu cột,`paper_id` rỗng/trùng, `text_for_embedding` rỗng, hoặc test set trỏ tới doc không tồn tại | Blocker mục 6 được phát hiện bằng đúng cơ chế này          |
| Chạy agent LangChain trên corpus                | `_build_demo_answers`                                      | `agent_demo_answers.json`: `agent_status: ok`, 4/4 câu có grounding                                                        | `jq .agent_status data/results/agent_demo_answers.json`              |
| Ghép corruption → evaluate → repair → compare | `corruption_flow.py::run_corruption_flow`                  | `corruption_valid: True`, `repair_valid: True`                                                                               | `python script/run_corruption_flow.py`                               |
| Đối chiếu report với artifact                 | `phase1_run_summary.json`, `corruption_run_summary.json` | Số trong báo cáo khớp file metrics                                                                                           | So sánh`baseline_metrics.json` với `corruption_run_summary.json` |

Nêu một output cụ thể mà phần việc của tôi tạo ra hoặc giúp xác minh:

`data/results/corruption_run_summary.json` là artifact máy đọc được duy nhất nối cả ba trạng thái vào một chỗ: row counts, metrics baseline/corrupted/repaired, `corruption_valid`, `repair_valid` và đường dẫn tới mọi artifact liên quan. Nhờ nó, mọi số trong `group_report.md` đều diff được với file thật mà không phải chạy lại pipeline.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Năm module do bốn thành viên khác viết đều đúng khi chạy riêng, nhưng chỉ có ý nghĩa khi ghép đúng thứ tự và đúng contract. Phần của tôi phải bảo đảm: (1) pipeline chạy được end-to-end từ máy sạch, (2) ba trạng thái baseline/corrupted/repaired được đo trên **cùng một** evaluation set nên số liệu mới so sánh được, (3) mọi kết luận trong báo cáo đều truy ngược được về một artifact cụ thể.

### Cách triển khai

**Baseline (`phase1.py`)** đi theo 8 bước: load/fetch raw → clean → validate → ghi CSV/JSON → build Chroma index → load/build test set → evaluate → quality + freshness → report → agent demo → run summary.

Điểm tôi chủ động thêm là **hai lớp validate chặn giữa các bước**:

- `_validate_clean_dataframe` chặn trước khi build index: thiếu cột bắt buộc, `paper_id` rỗng hoặc trùng, `text_for_embedding` rỗng, dataframe rỗng.
- `_validate_test_set` chặn trước khi evaluate: mọi `ground_truth_doc_ids` phải tồn tại trong corpus sạch, kèm gợi ý `REFRESH_TEST_SET=1`.

Lý do: nếu để lỗi trôi xuống, Chroma vẫn build được và evaluation vẫn ra số — nhưng là số vô nghĩa. Fail sớm với thông báo chỉ đúng module cần sửa rẻ hơn nhiều so với debug ngược từ metric sai.

**Agent demo** trả lời cùng một câu hỏi bằng hai đường: `answer_question` (rule-based, deterministic) và agent LangChain gọi tool `semantic_search_papers`/`lookup_paper`. Agent chạy sau khi mọi artifact baseline đã ghi xong và mọi lỗi được nuốt vào `agent_status` + `agent_error`, nên thiếu API key hay hết quota cũng không làm hỏng pipeline. `_normalize_agent_text` xử lý việc Gemini trả `content` dạng list of blocks thay vì chuỗi; `_run_agent_question` retry 429/5xx theo hint `retryDelay` trong response.

**Corruption flow** tái dùng chính xác `data/eval/test_set.json` của baseline cho cả hai lần đánh giá, và repair bằng cách dựng lại từ `data/raw/crossref_records.json` qua `repair_from_raw_records` — không vá từng dòng hỏng. Run date được suy ngược từ `published + age_days` của baseline nên repaired khớp baseline tuyệt đối.

### Input, output và contract

| Thành phần                   | Mô tả                                                                                                                                                                                                                                               |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Input                          | `list[PaperRecord]` từ `data/raw/crossref_records.json`; clean schema 16 cột; test set schema `id`/`question_type`/`question`/`ground_truth`/`ground_truth_doc_ids`                                                                   |
| Output                         | Clean CSV+JSON, embedding manifest, test set, metrics + answers cho 3 trạng thái, quality/freshness JSON, 2 report Markdown, 2 run summary JSON                                                                                                     |
| Module phụ thuộc             | `ingestion/crossref.py`, `ingestion/cleaning.py`, `ingestion/corruption.py`, `evaluation/testset.py`, `evaluation/metrics.py`, `observability/quality.py`, `observability/reporting.py`, `retrieval/index.py`, `retrieval/agent.py` |
| Module sử dụng output        | `script/run_phase1.py`, `script/run_corruption_flow.py`; báo cáo nhóm đọc `data/results/` và `data/reports/`                                                                                                                            |
| Điều kiện lỗi cần xử lý | Raw snapshot thiếu; cleaning trả dataframe rỗng; test set trỏ tới doc đã biến mất; chạy corruption flow khi chưa có baseline; thiếu credential LLM; provider trả 404/429                                                                |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** baseline mọi metric = 1.000 và quality/freshness PASS; corrupted tụt rõ và quality/freshness FAIL; repaired quay về đúng baseline với `repair_valid: True`.
- **Kết quả thực tế:** đúng như trên — baseline 1.000/1.000/1.000/5.00; corrupted 0.500/0.6244/0.5625/3.375; repaired 1.000/1.000/1.000/5.00; `corruption_valid: True`, `repair_valid: True`.
- **Artifact/log:** `data/results/phase1_run_summary.json`, `data/results/corruption_run_summary.json`, `data/reports/phase1_report.md`, `data/reports/corruption_report.md`. Không artifact nào chứa secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Khi pull bản tích hợp của TV4 về, `src/pipelines/corruption_flow.py` rơi vào trạng thái conflict `UU` từ một lần `git stash pop`. Hai phía: bản upstream của nhóm (~250 dòng, dùng API mới `repair_from_raw_records`/`validate_corrupted_dataframe`/`validate_repaired_dataframe`) và bản tôi đang stash (~418 dòng, tự cài `_repair_validation` và `_synchronize_derived_columns`).
- **Các phương án đã cân nhắc:**
  1. Giữ bản của tôi — đã chạy được và tôi hiểu rõ từng dòng.
  2. Lấy bản upstream — dùng API chính thức của owner module corruption.
  3. Merge tay hai phía.
- **Phương án đã chọn:** Phương án 2, sau đó thêm lại đúng một thứ mà upstream đánh rơi.
- **Lý do:** Bản của tôi tự viết lại logic vốn thuộc `corruption.py`, khiến bốn hàm của TV4 thành dead code và tạo hai nguồn sự thật cho cùng một quy tắc repair. Upstream còn kéo theo hai cải thiện mà bản tôi không có: `validate_corrupted_dataframe` chứng minh corruption đã lan tới derived columns, và `generate_corruption_report` được TV3 mở rộng nên hàng Baseline trong bảng so sánh không còn hiển thị `n/a`. Đổi lại, upstream tạo dict `result` đầy đủ nhưng không ghi ra file, nên tôi thêm 5 dòng persist `corruption_run_summary.json` để giữ tính đối xứng với `phase1_run_summary.json`.
- **Bằng chứng quyết định phù hợp:** Sau resolve, `python script/run_corruption_flow.py` chạy sạch với `corruption_valid: True` và `repair_valid: True`; `data/quality/corrupted_dataset_validation.json` xác nhận cả 6 scenario đều được phát hiện và cả ba derived column đều nhất quán. Stash cũ vẫn giữ ở `stash@{0}` nên quyết định này rollback được.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:**

  ```
  File "src/pipelines/phase1.py", line 72, in _validate_clean_dataframe
      raise ValueError("Cleaning produced an empty dataframe.")
  ValueError: Cleaning produced an empty dataframe.
  ```
- **Lệnh hoặc bước tái hiện:** `python script/run_phase1.py` với `data/raw/crossref_records.json` là snapshot lấy trước đó.
- **Nguyên nhân gốc:** `source_filter` trong `src/core/config.py` chỉ đặt chặn dưới `from-pub-date`, trong khi Crossref trả về cả các số báo **đã lên lịch xuất bản trong tương lai**. Toàn bộ 22/22 record trong snapshot có `published` từ `2026-12-31` đến `2028-06-15`, còn ngày chạy là `2026-08-06`. `build_clean_dataframe` loại đúng mọi record `published > run_date` (đây là hành vi đúng), nên kết quả là dataframe rỗng. Lỗi nằm ở tầng ingestion chứ không ở cleaning hay pipeline.
- **Cách xử lý:** Thêm chặn trên vào filter:

  ```python
  source_until_date = today.isoformat()
  source_filter = f"from-pub-date:{source_from_date},until-pub-date:{source_until_date},has-abstract:true"
  ```
- **Cách xác minh sau khi sửa:** Gọi thử Crossref với filter mới trả về 24 item đều có `issued = 2026-08-06`. Chạy lại `REFRESH_SOURCE=1 python script/run_phase1.py` cho 24 clean rows, 16 test samples, quality PASS toàn bộ 12 check và freshness `is_fresh: true` với 0/24 dòng stale.
- **Điều học được:** Một pipeline "chạy không lỗi" vẫn có thể sai hoàn toàn ở tầng dữ liệu. Thứ cứu tình huống này không phải try/except mà là assertion đặt đúng chỗ — `_validate_clean_dataframe` biến một corpus rỗng âm thầm thành một lỗi dừng hẳn, kèm thông báo chỉ thẳng tới bước cần sửa. Ngoài ra, filter dữ liệu nên chặn cả hai đầu: nguồn "sống" như Crossref chứa cả dữ liệu tương lai lẫn quá khứ.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

**1. Dữ liệu đi từ Crossref đến vector index như thế nào?**
`fetch_source_records` gọi `https://api.crossref.org/works` với `query.bibliographic` cùng filter `from-pub-date`/`until-pub-date`/`has-abstract`, có retry cho 429 và 5xx. Response thô lưu nguyên vào `data/raw/crossref_response.json`; `parse_crossref_payload` bóc JATS XML trong abstract, chuẩn hoá `date-parts` thành ISO date, dedupe theo DOI rồi ghi `data/raw/crossref_records.json`. `build_clean_dataframe` chuẩn hoá text, loại record thiếu trường bắt buộc hoặc có ngày tương lai, giữ bản `updated` mới nhất khi trùng `paper_id`, rồi sinh `text_for_embedding` (Title/Summary/Authors/Categories/Published) và `age_days`. `LocalEmbeddingIndex.build` encode cột đó bằng `all-MiniLM-L6-v2` và nạp vào collection Chroma với khoảng cách cosine, kèm manifest trong `data/embeddings/`.

**2. Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**
`build_test_set` sinh 16 câu từ 4 paper mới nhất, mỗi paper 4 loại câu hỏi (summary/authors/date/categories), mỗi mẫu mang `ground_truth` lấy trực tiếp từ dữ liệu sạch và `ground_truth_doc_ids` là `paper_id` nguồn. Khi evaluate, `retrieval_hit` đúng khi top-k trả về có chứa ít nhất một `ground_truth_doc_ids` — đây là thước đo tầng retrieval, độc lập với chất lượng sinh chữ. `mean_token_f1` so trùng token giữa câu trả lời và ground truth, còn `judge_accuracy`/`mean_judge_score` do LLM chấm theo cặp reference–prediction. Tách hai tầng như vậy mới biết lỗi nằm ở "tìm sai tài liệu" hay "tìm đúng nhưng trả lời sai".

**3. Quality checks khác freshness monitoring ở điểm nào?**
Quality checks trả lời "dữ liệu có đúng và toàn vẹn không" tại thời điểm hiện tại: `paper_id` unique, title/summary không rỗng, `summary_chars`/`age_days`/`text_for_embedding` có nhất quán với nguồn không, có noise hay title bị cắt không. Freshness trả lời một câu khác hẳn: "dữ liệu có còn mới không" — so `age_days` với ngưỡng 180 ngày và báo `latest_published`/`oldest_published`/`stale_rows`. Một corpus có thể sạch tuyệt đối mà vẫn cũ mèm; ngược lại có thể rất mới nhưng đầy duplicate. Trong bài này corruption đánh vào cả hai mặt nên cả hai tín hiệu đều đổi trạng thái.

**4. Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**
Vì chỉ khi giữ nguyên câu hỏi và ground truth thì chênh lệch metric mới quy được về **một** biến duy nhất là chất lượng dữ liệu. Nếu sinh lại test set cho mỗi trạng thái, độ khó câu hỏi thay đổi theo và ta không phân biệt được "agent tệ đi vì dữ liệu bẩn" với "bộ câu hỏi lần này khó hơn". `corruption_flow` đọc đúng file `data/eval/test_set.json` mà baseline đã dùng, và `corruption_run_summary.json` ghi lại đường dẫn đó làm bằng chứng.

**5. Repair được xem là thành công dựa trên artifact và metric nào?**
Ba tầng bằng chứng độc lập. Tầng dữ liệu: `data/quality/repaired_dataset_validation.json` với `repair_valid: True` — khớp row count, khớp tập `paper_id`, và digest nội dung trùng baseline. Tầng observability: `data_quality_repaired.json` PASS toàn bộ 12 check và `freshness_repaired.json` có `is_fresh: true`, `stale_rows: 0`. Tầng agent: `repaired_metrics.json` quay về đúng 1.000/1.000/1.000/5.00 trên cùng test set. Nếu repair chỉ "che" lỗi thay vì dựng lại từ nguồn, tầng dữ liệu sẽ lộ ngay dù hai tầng kia có đẹp.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          |          Baseline |                          Corrupted |          Repaired | Nhận xét của cá nhân                                                            |
| ---------------------- | ----------------: | ---------------------------------: | ----------------: | ------------------------------------------------------------------------------------ |
| `retrieval_hit_rate` |            1.0000 |                             0.5000 |            1.0000 | Mất đúng một nửa; nguyên nhân truy được về scenario cụ thể (xem dưới) |
| `mean_token_f1`      |            1.0000 |                             0.6244 |            1.0000 | Giảm ít hơn hit rate vì một số câu vẫn "đoán trúng" từ tài liệu sai    |
| `judge_accuracy`     |            1.0000 |                             0.5625 |            1.0000 | Bám sát hit rate — LLM judge phạt đúng phần nội dung sai                     |
| `mean_judge_score`   |              5.00 |                             3.3750 |              5.00 | Giảm 1.625 điểm trên thang 5                                                     |
| Quality checks         |  PASS (0/12 fail) |                   FAIL (5/12 fail) |  PASS (0/12 fail) | 5 check fail ứng 1-1 với 5 scenario corruption                                     |
| Freshness status       | fresh, 0/24 stale | **không fresh**, 3/24 stale | fresh, 0/24 stale | `oldest_published` lùi từ 2026-08-06 về 2021-08-06                              |

### Kết luận từ số liệu

1. **Xoá 3 record mới nhất** → 2 trong 4 paper của test set biến mất khỏi corpus, `duplicate_key_rows` tăng và `paper_id_unique` FAIL → `retrieval_hit_rate` rơi từ 1.000 xuống đúng 0.500 (8/16 câu mất ground-truth document).
2. **Dựng lại từ `data/raw/crossref_records.json`** → `repaired_dataset_validation.json` báo `repair_valid: True`, 12/12 quality check PASS trở lại và `is_fresh: true` → cả bốn metric agent phục hồi trọn vẹn về mức baseline, chênh lệch so với baseline đúng bằng 0.0000.

Corruption nào ảnh hưởng rõ nhất và vì sao?

**`drop_latest_records`.** Hai document mà retrieval trượt ở trạng thái corrupted là `10.1007/s00262-026-04505-w` và `10.1007/s44020-026-00124-1` — cả hai đều nằm trong danh sách `drop_latest_records` của `corruption_log.json`. Đây là loại lỗi nặng nhất vì nó không làm dữ liệu *xấu đi* mà làm dữ liệu *biến mất*: không kỹ thuật retrieval nào cứu được tài liệu không còn trong index. Các scenario còn lại (blank summary, noise, truncate title) chỉ làm giảm chất lượng embedding nên document vẫn có cơ hội lọt top-k. Đối chiếu theo loại câu hỏi cho thấy cả bốn loại đều tụt đúng 2/4 hit — nhất quán với giả thuyết "mất document" chứ không phải "mất chất lượng text".

Kết quả nào khác với kỳ vọng ban đầu?

Tôi kỳ vọng `mean_token_f1` tụt tương đương `retrieval_hit_rate`, nhưng nó chỉ còn 0.6244 thay vì khoảng 0.5. Tách theo `question_type` thì thấy nhóm `date` giữ nguyên `token_f1 = 1.000` và `judge_score = 5.00` **dù chỉ hit 2/4**. Nguyên nhân: cả 24 paper trong corpus đều có `published = 2026-08-06`, nên khi retrieval trả về nhầm tài liệu, câu trả lời về ngày vẫn tình cờ đúng. Đây là một điểm yếu thật của evaluation set hiện tại — `token_f1` cho câu hỏi ngày gần như không phân biệt được đúng/sai document, và nó khiến corruption trông nhẹ hơn thực tế. Tôi kiểm chứng bằng cách đối chiếu `retrieved_doc_ids` với `ground_truth_doc_ids` trong `corrupted_answers.json` thay vì chỉ nhìn metric tổng.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** validate giữa các bước quan trọng ngang với bản thân các bước xử lý. Blocker lớn nhất của nhóm không phải một exception mà là một corpus rỗng — nó chỉ trở nên nhìn thấy được vì có assertion chặn trước khi build index.
2. **Về data quality/observability:** phải tách "dữ liệu đúng không" khỏi "dữ liệu mới không", và phải kiểm tra cả **derived columns**. `validate_corrupted_dataframe` xác nhận `text_for_embedding` nhất quán với `title`/`summary` đã bị bẩn — đó mới là bằng chứng corruption thực sự chạm tới corpus embedding, chứ không dừng ở cột hiển thị.
3. **Về ảnh hưởng của data đến RAG agent:** metric tổng có thể che giấu vấn đề. `mean_token_f1 = 0.6244` trông như "vẫn ổn", nhưng tách theo loại câu hỏi mới lộ ra nhóm `date` đạt điểm tuyệt đối trên những câu retrieval đã trượt. Luôn phải đọc xuống tầng `retrieved_doc_ids`.

### Nếu có thêm thời gian

Tôi sẽ đa dạng hoá `published` trong evaluation set thay vì để cả 24 paper cùng một ngày. Cách đo: sau khi mở rộng khoảng ngày, `token_f1` của nhóm `date` ở trạng thái corrupted phải tụt xuống xấp xỉ `retrieval_hit_rate` (~0.5) thay vì giữ 1.000. Nếu điều đó xảy ra thì evaluation set đã thực sự phân biệt được document đúng và document sai, và mức độ thiệt hại do corruption sẽ được phản ánh trung thực hơn.

## 10. Cam kết của thành viên

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** [Điền họ tên đầy đủ]
**Ngày xác nhận:** 2026-08-06
