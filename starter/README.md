# Starter · PostgreSQL + pgvector

Pipeline đã triển khai và chạy trên PostgreSQL + pgvector local: đọc PDF, chia
chunk theo mục, embedding thật, lưu vector, filter và benchmark dev/test.
Xem [hướng dẫn từ đầu tới cuối](../RUNBOOK.md). Các bảng đánh giá thủ công và
báo cáo cá nhân vẫn cần người học hoàn thiện.

## Cấu trúc

```text
starter/
├── docker-compose.yml     # PostgreSQL 16 + pgvector, chỉ mở cổng local
├── init.sql               # bật extension khi tạo database mới
├── requirements.txt       # psycopg, pypdf và python-dotenv
├── .env.example           # cấu hình mẫu; copy thành .env
├── scripts/check_setup.py # kiểm tra kết nối và extension (đã chạy được)
├── src/
│   ├── models.py          # cấu trúc dữ liệu mẫu
│   ├── ingestion.py       # đọc / chuẩn hóa tài liệu
│   ├── chunking.py        # chia chunk, giữ mục và offset
│   ├── embeddings.py      # multilingual-e5-small local, vector 384D
│   ├── store.py           # snapshot pgvector và cosine search có filter
│   ├── evaluation.py      # đối chiếu evidence, tổng hợp dev/test
│   ├── artifacts.py       # kiểm tra hash và alignment vector/ID
│   ├── audits.py          # tạo mẫu chấm, tổng hợp nhãn đã nhập
│   └── run.py             # nối pipeline và CLI
└── ../data/, ../results/   # dữ liệu và kết quả ở root repo
```

## 1. Cài và kiểm tra database

Cần Docker Desktop hoặc Docker Engine + Compose, Python **3.11–3.14**, và mạng để tải image/dependencies lần đầu. Các lệnh sau chạy từ thư mục `starter/`:

```bash
cd starter
python3 -m venv .venv
```

Kích hoạt `.venv`: macOS/Linux dùng `source .venv/bin/activate`; Windows PowerShell dùng `.venv\Scripts\Activate.ps1`. Sau đó:

```bash
python -m pip install -r requirements.txt
# macOS/Linux: cp .env.example .env
# Windows PowerShell: Copy-Item .env.example .env
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
```

Kỳ vọng: hiện tên database, phiên bản PostgreSQL và pgvector, sau đó `Setup OK`. Đây **chỉ là kiểm tra hạ tầng**, không phải kết quả benchmark. Docker dùng cổng `127.0.0.1:55433` và mật khẩu cố định **chỉ dùng local cho lab**; nếu cổng bận, sửa đồng thời port trong `docker-compose.yml` và `DATABASE_URL` trong `.env`. `init.sql` chỉ chạy khi volume mới được tạo; nếu database sẵn có chưa bật extension, xem log Docker và kiểm tra cấu hình thay vì xóa volume chứa dữ liệu.

Dừng container nhưng giữ dữ liệu:

```bash
docker compose -p day6_student_starter stop
```

## 2. Embedding model đã chọn

Đã chọn `intfloat/multilingual-e5-small`, revision cố định, 384 chiều, local,
không cần API key. Cấu hình ở `../configs/embedding.json`; dependencies ML ở
`requirements-embeddings.txt`. Xem [chi tiết chunking/embedding](CHUNKING_EMBEDDINGS.md).

## 3. Chạy pipeline

Corpus 46 trang và benchmark 15 dev/5 test đã chốt. Khi database đang chạy:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m src.run all
```

Lệnh kiểm tra cache, nạp A/B/C, kiểm tra nạp lại, chạy dev/chọn cấu hình trước
test và xuất trace, metric, mẫu chấm thủ công. Cache hợp lệ được dùng lại;
`--rebuild` tạo lại text/chunk/embedding từ PDF, không tái tạo gold.
Chạy riêng từng pha và cách đọc kết quả có trong [RUNBOOK.md](../RUNBOOK.md).

Lưu code, cấu hình, kết quả và lệnh chạy để người chấm tái lập; không commit key, dữ liệu mật hoặc dữ liệu không có quyền chia sẻ.

## 4. Chạy riêng bước đọc PDF đã hoàn thiện

Đặt hai PDF trong `data/raw/` ở **root repo**, rồi chạy từ `starter/`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.ingestion
```

Lệnh này đọc `s10462-024-10955-4.pdf` (ID `gs_driving_review`, chọn trang
vật lý 2–26) và `2401.03890v9.pdf` (ID `gs_general_survey`, chọn trang
vật lý 2–22), xuất 46 bản ghi UTF-8 vào `data/processed/pages.jsonl`.
Đường dẫn dữ liệu được xác định từ vị trí code, không từ thư mục hiện hành;
có thể đổi bằng `--data-dir <đường-dẫn-data>`.

Mỗi dòng gồm `document_id`, `source`, `page`, `text`, `metadata`.
Metadata có tên tài liệu, ngôn ngữ, trạng thái trích xuất, số ký tự và
`section_spans` từ heading thật trong `data/section_boundaries.json`.
Trang chỉ có một mục có thêm `section`; trang nhiều mục giữ từng khoảng ký tự.
`data/processed/sections.jsonl` có 96 đoạn giới hạn theo mục để chuẩn bị chunking,
mỗi đoạn có scalar `section` và offset trong trang gốc.
Số trang luôn là số trang PDF gốc, không đánh lại sau lọc.
Chuẩn hóa NFC và khoảng trắng, giữ xuống dòng/ngắt đoạn có trong text trích xuất.
Chưa loại header/footer hay tái tạo bố cục bảng/công thức; cần đối chiếu PDF.

Log lần chạy và trang lỗi/rỗng nằm ở `data/processed/ingestion.log`.
Nếu trang được chọn bị rỗng, lỗi hoặc thiếu, lệnh báo lỗi và không thay thế
`pages.jsonl` hiện có. Chạy lại thành công sẽ thay file JSONL, không nối trùng.
Đã kiểm tra máy 46 trang và đối chiếu trực quan 8 trang đại diện; chi tiết tại
`data/manifest.json`, `results/corpus_checks.json`, `results/text_audit.csv`.
Benchmark đã tạo 15 dev/5 test và chốt snapshot trước retrieval; xem
`benchmark/README.md`. Kiểm tra lại từ `starter/`:

```powershell
.\.venv\Scripts\python.exe scripts\audit_corpus.py
.\.venv\Scripts\python.exe scripts\prepare_benchmark.py
```

Chunking và embedding thật đã triển khai; xem [hướng dẫn và kết quả](CHUNKING_EMBEDDINGS.md).
Vector store và retrieval benchmark đã chạy; xem `../results/metrics.csv`,
`../results/store_run.json`, `../results/selection.json` và `../results/run_summary.md`.
Nhãn coherence/metadata/grounding cần nhập ở `../results/audit/` rồi tổng hợp
bằng `python -m src.run audit-summary`; không tự điền điểm khi chưa chấm.
