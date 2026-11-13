# Corpus đã kiểm tra — bước 4

Hai PDF gốc nằm trong `raw/`. `manifest.json` ghi tác giả, phiên bản, URL,
giấy phép quan sát được, SHA-256 file gốc, trang được chọn và số ký tự từng trang.
Ngày truy cập là ngày kiểm tra file local; ngày tải gốc chưa biết được ghi `null`.

| ID | Phiên bản | Trang PDF được chọn | Số trang |
|---|---|---|---:|
| `gs_driving_review` | Bản nhà xuất bản, Artif Intell Rev 58:30 (2025) | 2–26 | 25 |
| `gs_general_survey` | `arXiv:2401.03890v9` | 2–22 | 21 |

Tổng **46 trang**, **165.772 ký tự** đã chuẩn hóa. Số trang là số trang vật lý
PDF bắt đầu từ 1, không đánh lại sau khi lọc. Các trang đều có nội dung chủ đề;
không đếm trang tham khảo, trang trống hay nhân bản để đạt yêu cầu.
Một số trang đầu/cuối phạm vi là nội dung tiếp nối; manifest ghi rõ phần loại.

- `processed/pages.jsonl`: 46 bản ghi trang, giữ nguyên text đã chuẩn hóa.
- `section_boundaries.json`: heading lấy từ PDF và vị trí trang tương ứng.
- `processed/sections.jsonl`: 96 đoạn giới hạn theo mục, chuẩn bị cho chunking.
  Đây chưa phải các chunk/vector của ba cấu hình.
- `results/corpus_checks.json`: kiểm tra máy tất cả 46 trang, nguồn, số trang,
  text khớp trích xuất PDF, số ký tự và ranh giới mục.
- `results/text_audit.csv`: ghi nhận đối chiếu 8 trang đại diện, gồm nguồn PDF,
  số trang vật lý, nhận xét và người/công cụ đánh giá. Mở trực tiếp PDF gốc
  tại trang được ghi để kiểm tra; không cần lưu bản ảnh trùng lặp.

Trên trang có nhiều mục, `metadata.section_spans` lưu các khoảng `[start, end)`
theo ký tự Unicode của text trang. Chỉ trang có một mục mới có scalar `section`.
Mỗi bản ghi trong `sections.jsonl` luôn có scalar `metadata.section`,
`section_id`, `heading_page`, `page_char_start`, `page_char_end`.
Header/footer còn trong text và được kế thừa mục xung quanh; đó không phải
nội dung chuyên môn hay heading mới. Chunking cần giữ ranh giới mục.

Giới hạn đã thấy: bảng bị tuyến tính hóa, đồ thị/hình mất quan hệ không gian,
công thức mất bố cục 2D; header/footer và gạch nối cuối dòng còn nguyên.
Không sửa đoán công thức hay khẳng định bảng giữ nguyên cấu trúc. Benchmark
ban đầu dùng evidence văn bản rõ nghĩa, không dùng câu hỏi đọc ô bảng hoặc
chép lại công thức. Chưa thực hiện OCR vì các trang chọn có text trích xuất được.

Thông tin nguồn được đối chiếu với [nhà xuất bản](https://link.springer.com/article/10.1007/s10462-024-10955-4)
và [bản arXiv v9](https://arxiv.org/abs/2401.03890v9).
Manifest giữ thông tin CC BY-NC-ND 4.0 của paper đầu, CC BY 4.0 theo arXiv/PDF
metadata của paper sau và cả ghi chú permission template ACM trên trang đầu.
Việc chuẩn bị artifact local không phải tuyên bố mọi bản chỉnh sửa, ảnh bên thứ ba
hay trích đoạn đều được phép công khai. Khi nộp có thể dùng manifest/hướng dẫn
lấy lại nguồn cho các nội dung không được phép chia sẻ.

Từ `starter/`, tạo lại rồi kiểm tra:

```powershell
.\.venv\Scripts\python.exe -m src.ingestion
.\.venv\Scripts\python.exe scripts\audit_corpus.py
.\.venv\Scripts\python.exe scripts\prepare_benchmark.py
```

Kiểm tra cuối phát hiện corpus/benchmark khác snapshot đã chốt; không tự sửa
gold để thích nghi với corpus khác sau khi đã xem test.
