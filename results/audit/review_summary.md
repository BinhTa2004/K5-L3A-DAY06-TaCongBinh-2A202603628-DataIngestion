# Kết quả đánh giá theo rubric

Đã đọc và ghi lý do theo rubric cho 30 hàng
coherence, 45 hàng metadata và 15 hàng grounding. Đây là một lượt chấm AI,
không mù, do cùng trợ lý đã hỗ trợ code/benchmark; không ghi nhận người học
hay người chấm độc lập đã xác nhận. Nguy cơ thiên lệch tác giả cần nêu trong báo cáo.

| Strategy | Coherence /2 (10 vị trí) | Metadata đủ và đúng | Filter đúng toàn top-3 / câu test có filter | Grounding /2 (5 câu) |
|---|---:|---:|---:|---:|
| A | 1,10 | 15/15 | 1/2 | 1,20 |
| B | 1,80 | 15/15 | 1/2 | 1,40 |
| C | 1,80 | 15/15 | 2/2 | 1,40 |

## Coherence

- A: 9 mẫu mức 1, 1 mẫu mức 2. Nhiều chunk bắt đầu/kết thúc giữa từ hoặc câu,
  nhưng vẫn còn một phần thông tin hiểu được nên không tự động chấm 0.
- B/C: 2 mẫu mức 1, 8 mẫu mức 2. Biên câu tốt hơn trong mẫu này, nhưng chưa
  xử lý hết mảnh caption và phần tiếp từ trang trước.
- Ví dụ `anchor_id=8`, general survey trang 4: B/C vẫn mở bằng caption
  “Structure of the overall review” rồi “one is directly storing…”, nên chỉ 1/2.
- `anchor_id=10`, general survey trang 6: caption hình lẫn với phần tiếp về SH/
  non-Lambertian; frustum culling/splatting đọc được nhưng đầu chưa tự hiểu, 1/2.
- B/C có cùng ID/text tại 10 vị trí nên dùng cùng nhãn; không coi đây là hai
  bộ chứng cứ thống kê độc lập. Mẫu đã chọn trước khi xem kết quả, không thay vị trí.

## Metadata

Đã đối chiếu 45 dòng với file PDF gốc, trang vật lý, text đã chuẩn hóa, offset
và heading nguồn. Các giá trị cần thiết đều đủ/đúng. Chi tiết từng dòng ở
`metadata.csv` và `review_provenance.json`.

Điểm này đánh giá **sự chính xác của metadata**, không chứng minh chunk liên
quan câu hỏi. Ở `test03`, A/B có chunk mang section khác mục được yêu cầu;
section đó vẫn đúng với tài liệu gốc, nhưng là lỗi tuân thủ phạm vi query.
Vì vậy báo filter compliance riêng: A/B 1/2, C 2/2.
`source`/`page`/offset giúp kiểm tra lại bằng chứng; `section` giúp C giới hạn phạm vi.
Giới hạn: section đúng không đảm bảo evidence đủ hoặc nội dung được xếp hạng đúng.

## Grounding

| Câu test | A | B | C | Nhận xét |
|---|---:|---:|---:|---|
| test01 — chiều thời gian | 0 | 1 | 1 | A không có luận điểm trả lời; B/C chỉ có temporal smoothness, thiếu lý do biểu diễn cảnh thay đổi |
| test02 — ba giai đoạn GaussNav | 2 | 2 | 2 | Đủ ba tên giai đoạn, có nguồn trang 26 |
| test03 — đơn giản hóa SplaTAM | 2 | 2 | 2 | Có view-independent colors và isotropic Gaussian ở trang 20 |
| test04 — biểu diễn PhysGaussian | 0 | 0 | 0 | Truy xuất các phương pháp khác, không có evidence về PhysGaussian |
| test05 — metric cảnh phẫu thuật | 2 | 2 | 2 | Có heading Surgical Scenes và PSNR/SSIM/LPIPS ở trang 21 |

Grounding xét **toàn top-3 có đủ bằng chứng để trả lời không**, không phạt mất
điểm chỉ vì các hit khác không liên quan khi một hit đã đủ. Không gọi điểm này
là độ chính xác câu trả lời LLM. A có 2 mức 0, 0 mức 1, 3 mức 2; B/C mỗi cấu hình
có 1 mức 0, 1 mức 1 và 3 mức 2.

## Khác biệt với metric tự động cần ghi trong báo cáo

`A/test02` là một false negative của proxy **full gold quote containment**:
rank 1 ở trang 26 đã chứa đủ danh sách:

> sub-Gaussian segmentation, semantic Gaussian construction, and Gaussian navigation

Gold quote còn có phần mô tả lợi ích sau danh sách; phần đó bị cắt khỏi chunk
nhưng không cần để trả lời câu hỏi chỉ hỏi ba giai đoạn. Do vậy review ngữ nghĩa
chấm grounding 2 và xác nhận rank 1 đủ evidence, trong khi log máy báo miss.

| Strategy | Auto Hit@1 test | Auto Evidence Hit@3 test | Review đủ evidence trong một chunk: Hit@1 | Review đủ evidence trong một chunk: Hit@3 |
|---|---:|---:|---:|---:|
| A | 1/5 | 2/5 | 2/5 | 3/5 |
| B | 3/5 | 3/5 | 3/5 | 3/5 |
| C | 3/5 | 3/5 | 3/5 | 3/5 |

Các cột review là **đánh giá bổ sung có lý do**, không phải kết quả chạy máy mới.
Không sửa `benchmark/`, `metrics.csv`, trace, tham số hoặc selection dev để làm
đẹp số liệu. `evidence_review.csv` lưu từng quyết định và quote hỗ trợ.
Khi báo cáo phải nêu cách chấm và khác biệt, tránh trình bày hai cách đo như
cùng một số liệu tự động. Các ngữ cảnh tương đương khác chưa được xác nhận
không được tự coi là hit.

## Tác động chiến lược và giới hạn

Trên 10 vị trí cố định, chia đoạn/câu của B/C giữ biên ý tốt hơn cửa sổ A.
Đổi lại B/C có 229 chunk, nhiều hơn A 219 chunk; thời gian/tài nguyên thực đo
ở `results/chunking_stats.json` và `results/embedding_run.json`.
Filter C cải thiện phạm vi của các hit trong câu yêu cầu mục, nhưng không cứu
được `test01`/`test04` vì hai câu không có filter và thiếu evidence đúng.
C vẫn là cấu hình đã chọn trên dev trước test; không chọn lại theo review này.

Chỉ có 10 vị trí và 5 câu test/cấu hình, hai tài liệu gần chủ đề, một reviewer AI
không độc lập. Không suy rộng kết quả ra corpus khác. Các file trước khi chấm
được giữ ở `before_review/`; provenance lưu hash các artifact được bảo vệ.

## File nhãn và kiểm tra lại

- `coherence.csv`: 30 điểm và lý do.
- `metadata.csv`: 45 điểm và đối chiếu nguồn.
- `grounding.csv`: 15 điểm và lý do.
- `review_decisions.json`: rubric và quyết định ngữ nghĩa.
- `review_provenance.json`: nguồn gốc nhãn, kiểm tra PDF và hash.
- `../quality_metrics.json`: kết quả tổng hợp bởi chương trình.

Từ `starter/`: `python -X utf8 -m src.run audit-summary`.
Trước khi dùng trong báo cáo, ghi đúng đây là AI-assisted review và xem lại các
ca biên; không tự ghi người học/coach đã chấm nếu chưa thực hiện.
