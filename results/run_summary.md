# Kết quả pipeline

Cấu hình chọn trên dev: **C**.

| Strategy | Split | Hit@1 | Evidence Hit@3 |
|---|---|---|---|
| A | dev | 7/15 | 12/15 |
| A | test | 1/5 | 2/5 |
| B | dev | 8/15 | 11/15 |
| B | test | 3/5 | 3/5 |
| C | dev | 8/15 | 12/15 |
| C | test | 3/5 | 3/5 |

Đây là metric tự động theo full gold evidence containment, không phải nhãn coherence/grounding hay độ chính xác câu trả lời LLM.

Nhãn và lý do theo rubric nằm trong [audit/](audit/). Bảng điểm tổng hợp,
trường hợp auto-miss nhưng đủ evidence và phương pháp được trình bày trong
[báo cáo cá nhân](../report/individual/2A202603628_TaCongBinh.md).
Báo cáo cá nhân đã có tại report/individual/2A202603628_TaCongBinh.md. Còn chốt commit, ghi SHA và push repo trước khi nộp.
