# Benchmark đã chuẩn bị — bước 5

`dev.json` có **15 câu**, `test.json` có **5 câu**. Có **5 câu filter**:
`dev11`, `dev12`, `dev13`, `test02`, `test03` (2 câu thuộc test).
Câu hỏi/đáp án bằng tiếng Việt, evidence giữ tiếng Anh nguyên văn từ text đã xử lý.

Mỗi câu có `id`, `split`, `question`, `expected_answer`, `gold_source_id`,
`gold_page`, `evidence_quote`, `filter` và `gold_evidence`.
`filter: {}` nghĩa là không lọc; cấu hình C cũng không lọc câu đó.

`gold_evidence` chứa **tất cả các passage đã xác minh cho câu đó**, bao gồm
passage chính và các lựa chọn thay thế; mỗi entry có source/page, quote,
offset ký tự `evidence_start`/`evidence_end` và section.
Offset tính trên `pages.jsonl`: bắt đầu từ 0, end không bao gồm ký tự cuối.
Các trường gold cấp cao là bản sao của entry đầu để tương thích schema đề bài.

Đã có 25 passage cho 20 câu. Năm câu có nhiều lựa chọn gold:
`dev03`, `dev04`, `dev05`, `test01`, `test04`; trong đó bốn câu có evidence
ở cả hai tài liệu, `dev05` có hai trang hợp lệ trong cùng tài liệu.
Đánh giá phải chấp nhận **một** passage hợp lệ, không bắt buộc tìm đủ mọi lựa chọn.
Nếu tìm thấy bằng chứng tương đương khác, xác minh và ghi quyết định chấm;
không đánh sai chỉ vì khác nguồn chính. Danh sách hiện tại không khẳng định
đã tìm hết mọi cách diễn đạt bằng chứng có thể có trong corpus.

Corpus đã chốt 46 trang. Chia câu theo nhóm nội dung; mọi cặp document/page
chứa gold của dev và test không trùng nhau. Không chia ngẫu nhiên nên không cần seed.
Đây không phải chia tách theo tài liệu: hai paper vẫn chung chủ đề/khái niệm,
do đó test nhỏ không chứng minh khái quát ra nguồn hoặc chủ đề mới.

Filter lấy từ **tên mục đã nêu ngay trong câu hỏi**, đối chiếu heading thật.
Ví dụ `dev12` dùng `{"section": "Memory-efficient 3D GS"}`, nằm ở trang 9
paper v9. Không đưa đáp án, gold source/page hay quote vào truy vấn/filter.
Các đoạn trong `data/processed/sections.jsonl` giữ section chính xác; chunking
sau này cần giữ các ranh giới đó để một chunk không bị gán nhầm mục.

`protocol.json` ghi định nghĩa metric, cách dùng alternative gold và tiêu chí
chọn cấu hình **trước khi chạy retrieval**. Dùng dev để chọn, ưu tiên
Evidence Hit@3, rồi Hit@1, rồi thời gian ingest, số chunk và tên cấu hình để phá hòa.
Chốt tham số và lựa chọn trước khi chạy test; không sửa theo điểm test rồi
báo đó là holdout độc lập. Đánh giá và báo riêng dev/test cho cả ba cấu hình.

`dev12` có quote 960 ký tự vì cần hai hướng giảm bộ nhớ và điều kiện kết hợp;
đây là ca khó về giữ đủ ngữ cảnh. Không rút bớt gold dựa trên kết quả test.
Exact string match chỉ là kiểm tra vị trí quote và có thể là proxy cho retrieval;
nó không tự thay thế đánh giá đủ nghĩa, coherence hoặc grounding thủ công.

Các câu và đáp án do **Codex hỗ trợ soạn và kiểm tra ngữ nghĩa**, kết hợp
kiểm tra máy từng quote/source/page/offset/section. Không ghi nhận người học
đã duyệt thủ công khi việc đó chưa xảy ra. Chưa có kết quả retrieval hay nhãn
coherence/grounding; `results/benchmark_checks.json` chỉ xác nhận dữ liệu benchmark.

Từ thư mục `starter/`, kiểm tra lại:

```powershell
.\.venv\Scripts\python.exe scripts\audit_corpus.py
.\.venv\Scripts\python.exe scripts\prepare_benchmark.py
```

`lock.json` ghi SHA-256 của corpus, manifest và benchmark để phát hiện sửa đổi.
`prepare_benchmark.py --write` chỉ tạo lần đầu hoặc giữ nguyên dữ liệu giống hệt;
không tự ghi đè bộ câu hỏi đã thay đổi. Muốn thay benchmark phải tạo phiên bản
mới có lý do, đặc biệt nếu đã xem kết quả test.
