# Chấm thủ công sau retrieval

Các file CSV đã có điểm và lý do do **Codex (AI-assisted review)** nhập theo
yêu cầu của người học. Xem [bảng điểm và phân tích](review_summary.md),
`codex_review_decisions.json` và `codex_review_provenance.json`.
Không ghi nhận người học hay reviewer độc lập đã xác nhận. Bản trước chấm nằm
ở `before_codex_review/`. Mở bằng Excel hỗ trợ CSV UTF-8 hoặc VS Code;
giữ nguyên hàng/ID, chỉ sửa nhãn, `reason`, `reviewer` khi thực sự đánh giá lại.
Không thay bằng điểm tự suy từ Hit@3. Nếu dùng AI hỗ trợ chấm, ghi rõ reviewer
và phương pháp, xem lại nhãn trước khi báo cáo.

Metric máy và gold giữ nguyên. Riêng `A/test02` đã có đủ danh sách ba giai đoạn
trong chunk nhưng auto miss vì quote chứa thêm câu lợi ích; quyết định review
bổ sung nằm ở `evidence_review.csv`, không âm thầm sửa kết quả tự động.

| File | Số hàng | Cột cần điền | Thang điểm |
|---|---:|---|---|
| `coherence.csv` | 30 | `score_0_1_2` | 0: cắt ý/không hiểu; 1: thiếu ngữ cảnh; 2: tự hiểu và giữ trọn ý |
| `metadata.csv` | 45 | `metadata_complete_and_correct_0_1` | 0: có trường thiếu/sai; 1: các trường cần thiết đủ và đúng khi đối chiếu nguồn |
| `grounding.csv` | 15 | `score_0_1_2` | 0: không bằng chứng; 1: thiếu điều kiện/ngữ cảnh; 2: top-3 đủ để trả lời và truy nguồn |

Mỗi nhãn cần có `reason` và tên/công cụ trong `reviewer`.

Coherence dùng cùng 10 vị trí nguồn cho A/B/C: 5 trang đầu đã chọn của mỗi
tài liệu, ký tự ở giữa trang. Quy tắc/anchor được lưu **trước khi xem điểm**
ở `anchors.json`. Không đổi sang các chunk đẹp hơn sau khi đã xem kết quả.

Metadata: đối chiếu `source`, `page`, `section`, offset và nội dung với PDF /
`data/processed/pages.jsonl`; có đủ trường không có nghĩa giá trị đúng.
Tỷ lệ top-3 tuân thủ filter được đo riêng trong `results/metrics.csv`.

Grounding dùng cả top-3 cho từng câu test, không đòi một chunk duy nhất như
metric Evidence Hit@3 bắt buộc. Không gọi điểm này là độ chính xác câu trả lời LLM.
Đáp án/evidence gốc để đối chiếu nằm ở `benchmark/test.json` và trace đầy đủ.

Sau khi điền, chạy từ `starter/`:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m src.run audit-summary
```

Kết quả ở `results/quality_metrics.json`: khi chưa nhập đủ, `complete` là false
và điểm trung bình là null; không mặc định 0 hoặc 100%. Nhãn có điểm nhưng
thiếu lý do/reviewer sẽ báo lỗi. Chạy `all` lại không ghi đè nhãn đã nhập.
