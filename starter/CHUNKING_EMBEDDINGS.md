# Chunking và embedding đã chạy

Hai bước này dùng corpus/benchmark đã chốt, không sửa gold hoặc tính chỉ số retrieval.

| Cấu hình | Chunking | Giới hạn ký tự | Overlap | Số chunk | Vector document |
|---|---|---:|---:|---:|---|
| A | Cửa sổ cố định | 1000 | 0 | 219 | `documents_A.npy` |
| B | Gom đoạn; fallback theo câu khi đoạn quá dài | 1000 | 0 | 229 | `documents_B.npy` |
| C | Giống B; dự kiến thêm filter ở bước search | 1000 | 0 | 229 | Dùng lại chính `documents_B.npy` |

Tham số nằm ở `configs/strategies.json`. A–B giữ cùng giới hạn và overlap,
chỉ đổi thuật toán chia. B–C giữ byte-identical chunk/ID và vector; khác biệt
filter chỉ được thực thi sau khi hoàn thiện `store.py`.

Mọi chunk giữ `document_id`, `source`, số trang vật lý và scalar
`metadata.section`. Offset `page_char_start`/`page_char_end` trỏ về text trang gốc.
ID là hash ổn định theo nguồn/trang/offset/nội dung/mục/tham số; tài liệu đổi
thì ID liên quan đổi. Chạy lại cùng đầu vào sinh cùng ID và nội dung.
Không chunk nào vượt ranh giới trang hoặc mục. Audit cả 46 trang cho thấy
không mất ký tự, không chunk rỗng, không ID trùng và không nhầm mục.

Chỉ 15 ngắt đoạn trống còn tồn tại trong text PDF toàn corpus. `by_paragraph`
ưu tiên ngắt đoạn đó; với đoạn quá dài dùng dấu kết thúc câu, rồi cắt cứng nếu
một câu vẫn quá dài. Không tự xem mọi dòng PDF là một đoạn, không nối/sửa text.
Fallback theo câu là heuristic, có thể nhầm dấu chấm trong viết tắt. Đây chưa
phải kết quả chấm coherence. Các chunk rất ngắn có thể là heading/mảnh đầu cuối
mục; chúng được giữ để tránh mất nội dung hoặc ghép nhầm mục.

## Model và cách encode

Dùng [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small)
revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, local qua Sentence Transformers.
Chọn model đa ngữ vì câu hỏi tiếng Việt và evidence tiếng Anh; chưa đo chất lượng
retrieval để khẳng định hiệu quả trên corpus này.

- Vector 384 chiều, float32, mean pooling và L2 normalization.
- Tài liệu thêm `passage: `, câu hỏi thêm `query: ` theo hướng dẫn model.
- Giới hạn 512 token gồm prefix và special tokens. Adapter đếm trước và báo lỗi
  nếu quá dài; không âm thầm truncate hay chuyển model/vector ngẫu nhiên.
- CPU, 4 thread, batch 16; cùng cấu hình cho A/B/C và câu hỏi.
- Chỉ `question` được đưa vào encoder truy vấn; không đưa gold answer/source,
  page, quote hoặc filter vào vector câu hỏi.
- Đã encode 219 + 229 document và 20 query; C tham chiếu vector B.
  Encode query test là phép biến đổi cố định, chưa search, xem điểm hay chọn tham số bằng test.
- Chi phí API trả phí **0 USD**. Không ước tính điện/phần cứng/network local.

`src/embeddings.py` giữ interface `MyEmbedder`, `embed_documents()` và
`embed_query()`, thêm `embed_queries()` để batch câu hỏi.
Model chỉ đọc từ snapshot local đã kiểm tra hash; tải lỗi hoặc thiếu weights
thì báo lỗi. Inference không upload text vào dịch vụ ngoài.

## Chạy lại

Trên máy hiện tại, `.venv` đã được cấu hình dùng lại các thư viện ML có sẵn
từ Python gốc `D:\py`, thay vì cài lại PyTorch. Phiên bản thực tế được lưu trong
`results/embedding_run.json`. Trên máy khác có thể tạo venv độc lập và cài:

```powershell
cd starter
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-embeddings.txt
```

Tải model một lần, rồi tạo chunk/vector từ thư mục `starter/`:

```powershell
.\.venv\Scripts\python.exe scripts\download_embedding_model.py
.\.venv\Scripts\python.exe scripts\build_chunks.py
.\.venv\Scripts\python.exe scripts\build_embeddings.py
```

Downloader tải 10 file từ revision cố định, kiểm tra size và SHA-256/LFS hoặc
Git blob SHA-1 từ metadata nguồn. Có thể dùng `--direct` nếu cần kết nối trực tiếp
thay proxy môi trường. Máy hiện tại đã tải xong model; không cần tải lại để encode.
`models/` được gitignore; nộp cấu hình, hash và script tải, không cần commit weights.

## Artifact để kiểm chứng

```text
configs/strategies.json
configs/embedding.json
data/processed/chunks_A.jsonl
data/processed/chunks_B.jsonl
data/processed/chunks_C.jsonl
data/processed/embeddings/documents_A.npy
data/processed/embeddings/documents_A_ids.json
data/processed/embeddings/documents_B.npy
data/processed/embeddings/documents_B_ids.json
data/processed/embeddings/queries.npy
data/processed/embeddings/queries_ids.json
results/chunking_stats.json
results/embedding_run.json
artifacts/embedding_log.csv
```

Mỗi dòng trong file ID tương ứng một hàng vector theo thứ tự lưu. Load `.npy`
bằng `numpy.load(path, allow_pickle=False)`; đây là artifact trung gian, chưa
thay thế vector store bắt buộc.

`chunking_stats.json` có số lượng, phân bố độ dài, fallback, thời gian chia và
audit coverage. `embedding_run.json` có model/revision, dependency versions,
token counts, shape/dtype/norm, hash input/output, thời gian và phạm vi tính chi phí.
CSV tách thời gian load chung, encode A/B, reuse C và query. Thời gian reuse C
bằng 0 là chi phí encode tăng thêm, không phải đo ingest độc lập từ đầu.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\prepare_benchmark.py
```

Test kiểm tra giữ nội dung/offset/mục, overlap, tham số lỗi, ID ổn định,
paragraph/sentence fallback; integration test dùng weights thật để kiểm tra
vector hai ngôn ngữ, batch order, prefix và từ chối input quá dài.
Benchmark/corpus đã khóa vẫn giữ nguyên. Vector store và retrieval benchmark
đã triển khai sau bước này; xem [RUNBOOK](../RUNBOOK.md) và `results/metrics.csv`.
Các nhãn coherence/metadata/grounding vẫn cần chấm riêng.
