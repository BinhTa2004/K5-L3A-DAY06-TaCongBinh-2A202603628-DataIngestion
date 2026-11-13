# Day 06 — Data Ingestion

Bài cá nhân của **Tạ Công Bình — 2A202603628 — L3A**. Pipeline đọc PDF,
chuẩn hóa, chia chunk, tạo embedding local, lưu vào PostgreSQL/pgvector
và so sánh ba cấu hình A/B/C trên cùng corpus và benchmark.

## Nội dung bài nộp

```text
STUDENT.md
README.md
starter/                     # Code, Docker Compose, dependencies, scripts và tests
configs/                     # Cấu hình model và ba chiến lược
data/                       # Manifest, PDF nguồn và dữ liệu đã xử lý
benchmark/                   # 15 dev, 5 test, gold evidence và protocol
artifacts/experiment_log.csv # Cấu hình, giả thuyết và kết quả thí nghiệm
results/                     # Thống kê, trace top-3, chỉ số, nhãn audit và log
report/individual/2A202603628_TaCongBinh.md
```

Yêu cầu gốc: [SUBMISSION.md](SUBMISSION.md). Thông tin học viên:
[STUDENT.md](STUDENT.md). Phân tích đầy đủ và phương pháp đánh giá:
[báo cáo cá nhân](report/individual/2A202603628_TaCongBinh.md).
Các tài liệu đề bài còn lại được giữ để đối chiếu yêu cầu.

## Dữ liệu và cấu hình

Hai PDF nằm trong `data/raw/`, tổng **46 trang nội dung**:

| ID | File | Trang vật lý | Số trang |
|---|---|---|---:|
| `gs_driving_review` | `s10462-024-10955-4.pdf` | 2–26 | 25 |
| `gs_general_survey` | `2401.03890v9.pdf` | 2–22 | 21 |

Nguồn, phiên bản, giấy phép, hash và cách lấy lại file:
[data/manifest.json](data/manifest.json). Quy tắc xử lý:
[data/README.md](data/README.md). Giữ số trang PDF gốc sau khi lọc.

| Cấu hình | Chia chunk | Metadata filter | Số chunk |
|---|---|---|---:|
| A | Cửa sổ cố định, tối đa 1000 ký tự, overlap 0 | Không | 219 |
| B | Theo đoạn, fallback theo câu, tối đa 1000 ký tự, overlap 0 | Không | 229 |
| C | Cùng chunk và vector của B | Theo `section` khi câu hỏi có filter | 229 |

A–B thay cách chia chunk; B–C chỉ thay việc lọc. Chunk giữ nguồn, trang, mục
và offset; không vượt ranh giới trang/mục. Tham số ở
[configs/strategies.json](configs/strategies.json).

Embedding: `intfloat/multilingual-e5-small`, revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`, chạy CPU local, 384 chiều float32,
mean pooling, chuẩn hóa L2. Document dùng prefix `passage: `; query dùng `query: `.
Giới hạn 512 token; đầu vào quá dài báo lỗi. Batch 16, CPU 4 thread.
Cấu hình: [configs/embedding.json](configs/embedding.json).
Chi phí API: **0 USD**, chưa tính điện và phần cứng.

Vector store: PostgreSQL **16.16**, pgvector **0.8.7**, exact cosine search
bằng `<=>`, JSONB metadata filter. Database `day6_lab`, schema `day06`,
bảng `chunks` và `snapshots`; dữ liệu lưu bền vững trên Docker volume.
Nạp lại cùng snapshot không nhân đôi dữ liệu.

## Cài đặt và chạy

Đã kiểm tra với **Python 3.12.9**, Docker Desktop và Docker Compose.
Các lệnh PowerShell sau chạy từ root repo. Cần mạng trong lần cài thư viện,
tải Docker image và model; inference xử lý text tại máy, không dùng API.

```powershell
Set-Location starter
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-embeddings.txt
.\.venv\Scripts\python.exe -m pip install pypdf==6.21.4 fonttools==4.56.0
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -p day6_student_starter up -d --wait
.\.venv\Scripts\python.exe -X utf8 scripts\check_setup.py
.\.venv\Scripts\python.exe -X utf8 scripts\download_embedding_model.py
.\.venv\Scripts\python.exe -X utf8 -m src.run all --rebuild
.\.venv\Scripts\python.exe -X utf8 -m src.run audit-summary
```

Máy hiện tại đã có venv và model; chỉ cần mở Docker Desktop, vào `starter/`
và chạy:

```powershell
docker compose -p day6_student_starter up -d --wait
.\.venv\Scripts\python.exe -X utf8 -m src.run all
.\.venv\Scripts\python.exe -X utf8 -m src.run audit-summary
```

Trên máy hiện tại, venv dùng lại thư viện ML từ Python gốc `D:\py`.
Máy khác dùng venv độc lập như lệnh cài ở trên. `models/` và `.venv/` không
đưa lên Git; script tải model kiểm tra revision/hash.

Luồng chạy: **PDF → trang và mục → chunk A/B/C → embedding → pgvector →
dev/chọn cấu hình → test → trace và metric → tổng hợp nhãn audit**.
`--rebuild` tạo lại text/chunk/vector, giữ nguyên gold. Không có `--rebuild`,
cache hợp lệ được dùng lại. Hash corpus/benchmark được kiểm tra trước khi chạy;
khác snapshot thì dừng, không tự sửa gold.

Có thể chạy riêng `python -X utf8 -m src.run` với các lệnh:
`prepare`, `ingest`, `dev`, `test`, `audit`, `audit-summary`.
Selection được chốt trên dev trước lần test đầu; chạy lại cùng cấu hình là replay,
lịch sử nằm trong `results/test_exposure.json`. Gold không đưa vào query/filter.

Truy vấn thử, từ `starter/`:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m src.run query --strategy C --question "Trong mục Memory-efficient 3D GS, hai hướng giảm bộ nhớ là gì?" --section "Memory-efficient 3D GS"
```

Database mở tại `127.0.0.1:55433`. Thông tin kết nối nằm trong `starter/.env`
được gitignore. Số dòng dự kiến: A=219, B=229, C=229, tổng **677**.
Dừng container và giữ dữ liệu: `docker compose -p day6_student_starter stop`.
Khởi động lại bằng lệnh `up -d --wait` ở trên.

## Kết quả và minh chứng

Benchmark có [15 dev](benchmark/dev.json), [5 test](benchmark/test.json),
25 passage gold và 5 câu có filter. Quy tắc chọn cấu hình:
[benchmark/protocol.json](benchmark/protocol.json).

| Cấu hình | Dev Hit@1 | Dev Hit@3 | Test Hit@1 | Test Hit@3 |
|---|---|---|---|---|
| A | 7/15 | 12/15 | 1/5 | 2/5 |
| B | 8/15 | 11/15 | 3/5 | 3/5 |
| C | 8/15 | 12/15 | 3/5 | 3/5 |

C được chọn trên dev trước test. Metric tự động yêu cầu một chunk đúng nguồn,
trang và chứa đủ một passage gold hợp lệ sau chuẩn hóa. Bằng chứng tương đương
được phân tích bổ sung trong báo cáo; không sửa metric máy theo nhãn review.

| Minh chứng | Đường dẫn |
|---|---|
| Corpus, trang lỗi/rỗng, kiểm tra text | [corpus_checks.json](results/corpus_checks.json), [text_audit.csv](results/text_audit.csv) |
| Số chunk và độ dài | [chunking_stats.json](results/chunking_stats.json) |
| Model/version, thời gian, chi phí | [embedding_run.json](results/embedding_run.json), [embedding_log.csv](artifacts/embedding_log.csv) |
| Backend, nạp lại và lưu bền vững | [store_run.json](results/store_run.json), [persistence_check.json](results/persistence_check.json) |
| Chỉ số dev/test | [metrics.csv](results/metrics.csv) |
| Trace top-3, đủ 60 lượt và 180 hit | [A](results/traces_A.jsonl), [B](results/traces_B.jsonl), [C](results/traces_C.jsonl) |
| Chọn cấu hình và lịch sử test | [selection.json](results/selection.json), [test_exposure.json](results/test_exposure.json) |
| Nhãn, lý do và mẫu đánh giá | [results/audit/](results/audit/), [quality_metrics.json](results/quality_metrics.json) |
| Cấu hình, giả thuyết và so sánh A/B/C | [experiment_log.csv](artifacts/experiment_log.csv) |
| Phân tích 5 khía cạnh, ví dụ lỗi và giới hạn | [Báo cáo cá nhân](report/individual/2A202603628_TaCongBinh.md) |

Năm khía cạnh gồm retrieval, coherence, metadata, grounding và ảnh hưởng
chiến lược dữ liệu. Bảng nhãn có 30 mẫu coherence, 45 metadata và 15 grounding;
phương pháp và nguồn gốc nhãn được trình bày trong mục 5.2 của báo cáo.
Test chỉ có 5 câu; kết quả không đại diện cho mọi corpus. Bảng/công thức/hình
mất bố cục khi trích text, header/footer còn trong corpus.

## Kiểm thử và nộp bài

Từ `starter/`, khi database và model local sẵn sàng:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

Đã chạy **29/29 test đạt**, gồm chunking, embedding thật, evaluation, thứ tự
dev/test và PostgreSQL integration trong schema tạm riêng.
Kết quả đã ghi tại [code_tests.json](results/code_tests.json).

Trước khi nộp: kiểm tra [SUBMISSION.md](SUBMISSION.md), điền SHA commit thực tế
vào `STUDENT.md`, commit/push bài làm và bảo đảm người chấm truy cập được repo.
Không commit `.env`, token, model weights hoặc venv. Với nội dung không được
phép chia sẻ, cung cấp manifest/hướng dẫn truy cập theo yêu cầu của đề.
