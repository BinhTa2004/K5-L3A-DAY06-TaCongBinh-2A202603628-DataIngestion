# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.

## Tiến độ bài làm hiện tại

Đã hoàn tất bước đọc PDF, kiểm tra corpus và chuẩn bị bộ câu hỏi trước retrieval:

- [Manifest và hướng dẫn corpus](data/README.md): 2 tài liệu, 46 trang,
  96 đoạn theo heading; bản arXiv được ghi rõ `v9`.
- [Kiểm tra máy](results/corpus_checks.json) và [đối chiếu 8 trang PDF](results/text_audit.csv).
- [Benchmark](benchmark/README.md): 15 dev, 5 test, 5 câu filter, 25 passage gold.
- [Quy trình đánh giá đã định trước](benchmark/protocol.json) và
  [mã kiểm tra snapshot](benchmark/lock.json).

Đã triển khai [chunking và embedding local](starter/CHUNKING_EMBEDDINGS.md):
A có 219 chunk; B/C có 229 chunk và dùng chung vector cho B/C.
Đã tạo vector thật 384 chiều cho chunk và 20 câu hỏi, không dùng vector mock.
Thống kê tại [chunking_stats.json](results/chunking_stats.json), model/version,
thời gian và chi phí tại [embedding_run.json](results/embedding_run.json).

Đã triển khai vector store, evaluation và CLI nối pipeline; đã chạy trên
PostgreSQL 16.16 + pgvector 0.8.7. [RUNBOOK.md](RUNBOOK.md) hướng dẫn hoạt động
và cách chạy từ đầu tới cuối; [kết quả](results/run_summary.md) có metric dev/test.
Dev chọn C trước khi chạy test. [Đánh giá theo rubric](results/audit/review_summary.md)
đã có 30 nhãn coherence, 45 metadata và 15 grounding, kèm lý do/reviewer.
Đã có thông tin học viên và báo cáo cá nhân; còn chốt commit, ghi SHA thực tế,
push repo và kiểm tra quyền truy cập/quyền chia sẻ trước khi nộp.
Phương pháp và nguồn gốc nhãn được ghi trong
[báo cáo cá nhân](report/individual/2A202603628_TaCongBinh.md).
Thông tin về việc AI tham gia được giữ trong phương pháp; không ghi nhận
người học đã duyệt thủ công khi chưa có xác nhận thực tế.
