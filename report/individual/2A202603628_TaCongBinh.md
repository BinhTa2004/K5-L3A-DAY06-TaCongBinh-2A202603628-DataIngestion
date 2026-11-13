# Báo cáo cá nhân — Day 06: Data Ingestion Engineering

- **Họ và tên:** Tạ Công Bình
- **MSSV:** 2A202603628
- **Lớp:** L3A
- **Chủ đề:** Xây dựng và đánh giá pipeline truy xuất tri thức về 3D Gaussian Splatting.
- **Repo:** https://github.com/BinhTa2004/K5-L3A-DAY06-TaCongBinh-2A202603628-DataIngestion
- **Ngày tổng hợp:** 13/11/2026, múi giờ Asia/Barnaul.

## 1. Dữ liệu và pipeline

### 1.1. Corpus và quyền sử dụng

Corpus gồm hai bài báo PDF tiếng Anh có nội dung liên quan đến biểu diễn,
rendering và ứng dụng 3D Gaussian Splatting (3D GS).

| ID tài liệu | Tài liệu và tác giả | Phiên bản | Trang vật lý chọn | Số trang |
|---|---|---|---|---:|
| `gs_driving_review` | *Scene reconstruction techniques for autonomous driving: a review of 3D Gaussian splatting*, Huixin Zhu và cộng sự | Bản nhà xuất bản, Artificial Intelligence Review 58:30 (2025); xuất bản online 30/11/2024 | 2–26 | 25 |
| `gs_general_survey` | *A Survey on 3D Gaussian Splatting*, Guikun Chen và Wenguan Wang | **arXiv:2401.03890v9**, ngày 09/04/2026 | 2–22 | 21 |
| **Tổng** | | | | **46** |

Nguồn: [bài báo nhà xuất bản](https://doi.org/10.1007/s10462-024-10955-4)
và [bản arXiv v9](https://arxiv.org/abs/2401.03890v9).
Các file gốc nằm tại `data/raw/`; thông tin tác giả, nguồn, phiên bản, hash và
số ký tự từng trang được lưu trong [manifest](../../data/manifest.json).

Đơn vị đếm là trang vật lý PDF, bắt đầu từ 1 và giữ nguyên sau khi lọc.
Mỗi trang được chọn có nội dung chuyên môn như văn bản, công thức, hình hoặc
bảng. Không dùng ngưỡng ký tự của tài liệu text để thay quy tắc đếm trang PDF.
Paper đầu loại trang 1, trang 27 và phần tham khảo 28–33; paper sau loại trang 1,
trang 23 chứa kết luận/tham khảo, phần tham khảo 24–36 và phụ lục 37–41.
Đây là phạm vi corpus được chủ động cố định, không phải toàn bộ nội dung hai bài.
Không nhân bản trang để đạt số lượng.

Giấy phép được ghi nhận là CC BY-NC-ND 4.0 cho paper đầu, theo thông báo trên
trang 27 và nhà xuất bản; CC BY 4.0 cho paper sau theo bản ghi arXiv và metadata
PDF. Paper sau còn có permission notice của template ACM trên trang đầu;
manifest giữ lại ghi chú này. Việc chuẩn bị artifact local không được xem là
xác nhận mọi bản chuyển đổi, trích đoạn hay ảnh bên thứ ba đều được phép công khai.
Khi không được phép chia sẻ một artifact, dùng manifest và hướng dẫn lấy/tái tạo
nguồn để người chấm xác minh. Ngày truy cập ghi trong manifest là ngày kiểm tra
file local; ngày tải gốc không được biết và không được tự suy đoán.

### 1.2. Trích xuất, chuẩn hóa và truy vết

Pipeline dùng Python 3.12.9, pypdf 6.21.4 và fonttools 4.56.0:

```text
PDF → đọc từng trang → chuẩn hóa NFC/khoảng trắng → gắn ranh giới mục
    → chia chunk → embedding local → PostgreSQL + pgvector
    → truy xuất top-3 → đối chiếu evidence → đánh giá chất lượng
```

Kết quả có **46 bản ghi trang**, **165.772 ký tự** và **96 đoạn giới hạn theo mục**.
Toàn bộ 46 bản ghi được kiểm tra nguồn, số trang, số ký tự và text khớp kết quả
trích xuất từ trang PDF tương ứng; không có trang được chọn bị rỗng hoặc lỗi.
Tám trang đại diện đã được đối chiếu trực quan trong bước kiểm tra text.
Khi chấm rubric, tiếp tục đối chiếu các đoạn được chọn và xem thêm các trang
đại diện; không khẳng định toàn bộ trang đã được chấm trực quan độc lập.

Chuẩn hóa giữ xuống dòng/ngắt đoạn, không tự sửa công thức, xóa header/footer
hoặc nối từ bị gạch nối ở cuối dòng. Các giới hạn đã thấy gồm bảng bị tuyến tính
hóa, hình mất quan hệ không gian, công thức mất bố cục hai chiều và text lẫn
caption/header/footer. Không cần OCR cho các trang chọn vì đã có text trích xuất.
Benchmark ban đầu dùng bằng chứng văn bản rõ nghĩa, không yêu cầu chép công thức
hoặc suy quan hệ ô bảng từ text phẳng.

### 1.3. Metadata

Mỗi chunk lưu `chunk_id`, `document_id`, `source`, `page`, `text` và metadata.
Các trường bổ sung gồm:

| Trường | Kiểu | Nguồn giá trị và mục đích |
|---|---|---|
| `section`, `section_id` | Chuỗi | Heading thật trong PDF; xác định phạm vi và lọc truy xuất |
| `heading_page` | Số nguyên | Trang xuất hiện heading, hỗ trợ xác minh mục kế thừa |
| `page_char_start`, `page_char_end` | Số nguyên | Khoảng ký tự `[start,end)` trong text trang gốc |
| `language` | Chuỗi | `en`, theo ngôn ngữ tài liệu |
| `char_count` | Số nguyên | Số ký tự thực tế của chunk |

Trang có nhiều mục được gắn các khoảng `section_spans`; chunk không vượt
ranh giới mục hoặc trang. Heading được đối chiếu bằng text thật; không dùng
các nhãn số mục xuất hiện trong hình để tự đoán heading mới.
`source`/`page`/offset giúp truy vết, còn `section` là trường lọc có các giá trị
phân biệt được. Metadata đúng không bảo đảm chunk liên quan hoặc đủ bằng chứng.

### 1.4. Embedding và vector store

| Thành phần | Cấu hình đã chạy |
|---|---|
| Model | `intfloat/multilingual-e5-small` |
| Revision | `614241f622f53c4eeff9890bdc4f31cfecc418b3` |
| Provider | Local qua Sentence Transformers, CPU, 4 thread, batch 16 |
| Vector | 384 chiều, float32, mean pooling, chuẩn hóa L2 |
| Document/query | Tiền tố `passage: ` / `query: `, cùng một encoder |
| Giới hạn | 512 token kể cả prefix và special tokens; từ chối input quá dài |
| Thư viện ML | sentence-transformers 5.6.0; transformers 4.52.3; torch 2.6.0+cu124; numpy 2.0.2; safetensors 0.5.3 |
| Database | PostgreSQL 16.16 + pgvector 0.8.7, Docker volume local |
| Lưu trữ | Database `day6_lab`, schema `day06`, bảng `chunks` và `snapshots` |
| Truy xuất | Exact cosine search, top-3, không tạo ANN/HNSW index |
| Chi phí API | **0 USD**; không ước tính điện/phần cứng/network local |

Bản PyTorch có hậu tố CUDA nhưng cấu hình chạy là **CPU**. Model được tải một
lần và kiểm tra hash; embedding không gọi dịch vụ API và không gửi tài liệu
ra ngoài. Mọi chunk thực tế đều dưới giới hạn token, không bị truncate ngầm.

Database dùng khóa `(strategy, chunk_id)` và transaction để đồng bộ snapshot
đầy đủ của một cấu hình: cập nhật ID hiện tại, xóa chunk cũ không còn, giữ cấu
hình khác. Nạp lại không tăng số bản ghi; tổng A/B/C là **677 dòng**.
Đã kiểm tra reconnect và restart container: các dòng cùng manifest snapshot
model/chunk/vector vẫn còn và khớp. Filter được parameterize trong SQL, không
nối trực tiếp giá trị người dùng vào câu lệnh.

## 2. Cấu hình và benchmark

### 2.1. Ba chiến lược

| Strategy | Cách chia | Giới hạn | Overlap | Filter |
|---|---|---:|---:|---|
| A | Cửa sổ kích thước cố định | 1.000 ký tự | 0 | Không |
| B | Gom đoạn; fallback theo câu rồi cắt cứng khi cần | 1.000 ký tự | 0 | Không |
| C | Giống B, cùng ID/chunk/vector | 1.000 ký tự | 0 | `section` nếu câu hỏi cung cấp |

A–B giữ cùng giới hạn, overlap, corpus, model và store, chỉ đổi thuật toán chia.
B–C giữ nguyên chunk/vector, chỉ đổi filter lúc truy xuất. Vì text PDF chỉ còn
15 ngắt đoạn trống, B không phải chia đoạn hoàn hảo: nhiều đoạn quá dài phải
dùng heuristic biên câu. Chunk đầu/cuối mục rất ngắn được giữ để tránh mất
nội dung hoặc ghép nhầm mục.

### 2.2. Bộ câu hỏi và cách chia

Bộ benchmark gồm **20 câu** tiếng Việt dựa trên corpus tiếng Anh:
[15 dev](../../benchmark/dev.json), [5 test](../../benchmark/test.json).
Mỗi câu có đáp án, nguồn/trang, quote evidence và các bằng chứng thay thế đã
xác minh. Tổng cộng **25 passage**; năm câu có nhiều lựa chọn gold, trong đó
bốn câu có bằng chứng ở cả hai tài liệu.

Có **5 câu filter**: `dev11`, `dev12`, `dev13`, `test02`, `test03`;
trong đó hai câu thuộc test. Giá trị lọc lấy từ tên mục nêu trong chính câu hỏi,
không suy từ trang/nguồn chứa đáp án. Khi câu không có filter, C chạy không lọc.
Encoder câu hỏi chỉ nhận `question`; các trường đáp án/gold/quote/filter không
được đưa vào vector câu hỏi.

Split được gán xác định theo nhóm nội dung, không lấy mẫu ngẫu nhiên nên không
cần seed. Cặp document/page chứa gold của dev và test không trùng nhau, nhưng
hai tập vẫn dùng cùng tài liệu và các khái niệm liên quan; không coi đây là
kiểm tra độc lập theo tài liệu hoặc chủ đề mới. Corpus, câu hỏi, split và protocol
đã được khóa hash trước lần retrieval đầu tiên.

### 2.3. Tiêu chí lựa chọn và metric

Tiêu chí chốt trước test: ưu tiên dev Evidence Hit@3, sau đó dev Hit@1,
thời gian nạp theo cùng quy trình, số chunk và cuối cùng tên strategy để phá hòa.
**C được chọn trên dev trước khi chạy test**: Hit@3 bằng A nhưng Hit@1 cao hơn.
Không đổi lựa chọn hoặc tham số theo kết quả test và đánh giá rubric sau đó.
Chạy lại cùng cấu hình được ghi là replay, không trình bày như một holdout mới.

Hit@1 là số câu mà chunk đầu đủ evidence chia tổng câu. Evidence Hit@3 là số
câu có ít nhất một chunk đủ evidence trong top-3 chia tổng câu. Không chỉ cần
đúng nguồn/trang; phải có bằng chứng đủ trả lời. Chấp nhận một nguồn gold hợp lệ
trong danh sách thay thế, không bắt tìm đủ mọi nguồn.

Code tự động dùng tiêu chuẩn bảo thủ **chứa trọn gold quote sau chuẩn hóa
NFC/whitespace, đúng nguồn và trang**. Cách này có thể báo miss khi quote chứa
phần dư so với nội dung thực sự cần trả lời. Vì vậy báo cả kết quả tự động gốc
và các quyết định kiểm tra ngữ nghĩa bổ sung, không âm thầm sửa log hoặc gold.

## 3. Kết quả

Năm khía cạnh benchmark được trình bày như sau:

| Khía cạnh | Chỉ số/minh chứng | Vị trí trong báo cáo |
|---|---|---|
| 1. Độ chính xác truy xuất | Hit@1, Evidence Hit@3 dev/test và kiểm tra evidence bổ sung | Mục 3.1, 3.3 |
| 2. Tính mạch lạc của chunk | Chấm 10 vị trí nguồn/cấu hình, thang 0–2, có lý do | Mục 3.2, 4.2 |
| 3. Tính hữu dụng của metadata | Đúng/đủ nguồn–trang–mục và tỷ lệ tuân thủ filter | Mục 1.3, 3.2, 4.3 |
| 4. Grounding | Top-3 có đủ bằng chứng trả lời, chấm 5 câu test/cấu hình | Mục 3.2, 4.1 |
| 5. Tác động chiến lược dữ liệu | So sánh A–B/B–C, số chunk, thời gian, chi phí và đánh đổi | Mục 3.4, 4.3 |

### 3.1. Retrieval tự động

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Số chunk |
|---|---|---:|---:|---:|
| A | Dev | 7/15 | 12/15 | 219 |
| B | Dev | 8/15 | 11/15 | 229 |
| C | Dev | 8/15 | 12/15 | 229 |
| A | Test | 1/5 | 2/5 | 219 |
| B | Test | 3/5 | 3/5 | 229 |
| C | Test | 3/5 | 3/5 | 229 |

Đã chạy **60 trường hợp truy xuất**, lưu **180 bản ghi top-3**.
Nguồn số liệu: [metrics.csv](../../results/metrics.csv),
[trace A](../../results/traces_A.jsonl), [trace B](../../results/traces_B.jsonl),
[trace C](../../results/traces_C.jsonl).

### 3.2. Coherence, metadata và grounding theo rubric

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng | Filter tuân thủ trên test | Grounding: số mức 0 / 1 / 2 | Grounding trung bình /2 |
|---|---:|---:|---:|---:|---:|
| A | 1,10 (10) | 15/15 | 1/2 | 2 / 0 / 3 | 1,20 |
| B | 1,80 (10) | 15/15 | 1/2 | 1 / 1 / 3 | 1,40 |
| C | 1,80 (10) | 15/15 | 2/2 | 1 / 1 / 3 | 1,40 |

Coherence dùng cùng 10 vị trí nguồn cho mỗi strategy: năm trang đầu đã chọn
của mỗi tài liệu, ký tự giữa trang, được xác định trước khi xem điểm.
Chấm 0 nếu không hiểu được ý chính, 1 nếu chỉ hiểu một phần/thiếu ngữ cảnh,
2 nếu các ý chính tự hiểu và giữ trọn. B/C có cùng chunk nên cùng nhãn,
không coi đó là hai bộ quan sát thống kê độc lập.

Metadata được kiểm tra trên 5 câu test × top-3 × 3 strategy, tổng 45 dòng.
Nguồn/trang/section/offset đều đúng với PDF, nhưng metadata đúng không chứng
minh kết quả đúng phạm vi query. Ở `test03`, A/B trả thêm chunk ngoài mục yêu cầu;
đó là lỗi tuân thủ phạm vi, không phải ghi sai section của nguồn.

Grounding được chấm trên toàn top-3 của mỗi câu test: 0 không có bằng chứng
trả lời, 1 có phần liên quan nhưng thiếu điều kiện/ngữ cảnh, 2 đủ để trả lời và
truy nguồn. Đây không phải độ chính xác câu trả lời do LLM sinh ra.

Nhãn/lý do nằm ở [coherence.csv](../../results/audit/coherence.csv),
[metadata.csv](../../results/audit/metadata.csv),
[grounding.csv](../../results/audit/grounding.csv).
[quality_metrics.json](../../results/quality_metrics.json) tổng hợp 90 hàng nhãn.
Phương pháp và nguồn gốc nhãn được nêu tại mục 5.2.

### 3.3. Kiểm tra evidence bổ sung

| Strategy | Test Hit@1 tự động | Test Hit@3 tự động | Kiểm tra đủ evidence trong một chunk: Hit@1 | Kiểm tra đủ evidence trong một chunk: Hit@3 |
|---|---:|---:|---:|---:|
| A | 1/5 | 2/5 | 2/5 | 3/5 |
| B | 3/5 | 3/5 | 3/5 | 3/5 |
| C | 3/5 | 3/5 | 3/5 | 3/5 |

Chỉ có `A/test02` khác kết quả máy: rank 1 đã chứa đủ ba giai đoạn GaussNav,
nhưng phần lợi ích ở cuối gold quote bị cắt. Không cần phần lợi ích đó để trả lời
câu hỏi chỉ hỏi tên các giai đoạn. Vì vậy đủ evidence theo nghĩa, dù không chứa
trọn quote máy yêu cầu. Quyết định, quote và reviewer được lưu riêng tại
[evidence_review.csv](../../results/audit/evidence_review.csv).
Các cột kiểm tra bổ sung không được trình bày như kết quả chạy tự động mới.

### 3.4. Tài nguyên và thời gian

| Strategy | Số chunk | Độ dài min / trung bình / max, ký tự | Chia chunk, giây | Encode document, giây | Nạp snapshot PostgreSQL, giây | Chi phí API |
|---|---:|---:|---:|---:|---:|---:|
| A | 219 | 9 / 756,950 / 1.000 | 0,012381 | 15,993517 | 0,178795 | 0 USD |
| B | 229 | 13 / 723,895 / 1.000 | 0,019177 | 21,010261 | 0,171545 | 0 USD |
| C | 229 | 13 / 723,895 / 1.000 | Dùng lại B | Dùng lại B | 0,173604 | 0 USD |

Thời gian encode bao gồm kiểm tra token/vector, không gồm load model và ghi
output. Load/kiểm tra model dùng chung mất 16,117203 giây; encode 20 query mất
0,541188 giây. Thời gian nạp database đo từ cache vector, không gồm embedding.
C có encode tăng thêm bằng 0 do reuse; không coi đó là đo ingest độc lập từ đầu.
Các số là phép đo thực trên máy hiện tại, có ảnh hưởng cache/tải hệ thống;
không kết luận tốc độ tổng quát từ một lần đo.

Nguồn: [thống kê chunk](../../results/chunking_stats.json),
[embedding run](../../results/embedding_run.json),
[store run](../../results/store_run.json) và
[nhật ký](../../artifacts/experiment_log.csv).

## 4. Phân tích lỗi, đánh đổi và kết luận

### 4.1. Hai trường hợp truy xuất chưa đủ bằng chứng

**`test01` — vì sao cần chiều thời gian cho cảnh động.** Gold ở
`gs_general_survey` trang 14 và `gs_driving_review` trang 24.
A lấy top-1 từ general survey trang 12, mục Hybrid Representation, chủ yếu nói
style transfer; các hit còn lại nói chất lượng rendering và ứng dụng chung.
Không có luận điểm trả lời nên grounding 0. B/C lấy được câu nói temporal
smoothness ở trang 12, liên quan một phần nhưng vẫn thiếu giải thích biểu diễn
cảnh thay đổi theo thời gian, nên grounding 1. Câu không có filter nên C giống B.

**`test04` — PhysGaussian gắn mô phỏng cơ học vào biểu diễn nào.** Gold ở
general survey trang 18, mục Physics và driving review trang 26, mục Vehicle navigation.
Cả ba strategy đều lấy top-1 từ driving review trang 18 nói Deformable 3D Gaussians;
các hit tiếp nói biểu diễn cảnh động hoặc DrivingGaussian/PVG. Không có bằng chứng
về phương pháp PhysGaussian, nên grounding 0 ở cả ba. Không suy đáp án của một
phương pháp cụ thể chỉ từ việc các đoạn đều nhắc Gaussian.

### 4.2. Lỗi biên chunk và đo lường

Ở A, nhiều mẫu bị cắt giữa từ/câu; ví dụ anchor 2, driving review trang 3,
bắt đầu bằng mảnh “e of each point” và kết thúc giữa từ. B/C giữ nhiều câu
đầy đủ hơn, nhưng anchor 8, general survey trang 4, vẫn lẫn caption hình và
phần tiếp “one is directly storing”; anchor 10 trang 6 còn mảnh caption và
đoạn non-Lambertian tiếp từ trang trước. Các mẫu này chỉ được coherence 1.

`A/test02` cho thấy cần phân biệt thiếu evidence thật với proxy quá nghiêm:
danh sách trả lời đã có nhưng máy đòi cả phần quote dư. Báo cáo giữ nguyên
raw metric và công bố kiểm tra bổ sung để người đọc đánh giá được giới hạn phép đo.

### 4.3. So sánh và lựa chọn

- **A–B:** B tăng coherence từ 1,10 lên 1,80 trên mẫu đã chọn; số chunk tăng
  219 lên 229. B không luôn thắng retrieval: dev Hit@3 của B là 11/15 so với
  12/15 của A. Biên câu tốt hơn chưa đảm bảo giữ đủ mọi passage gold hoặc xếp hạng tốt hơn.
- **B–C:** chunk/vector không đổi. Filter tăng tỷ lệ đúng phạm vi trên các câu
  test có filter từ 1/2 lên 2/2, dev Hit@3 từ 11/15 lên 12/15. Trên năm câu test,
  metric tự động B/C bằng nhau; filter không cứu được câu thiếu evidence mà không có filter.
- **Lựa chọn:** giữ C, đúng lựa chọn đã lưu trên dev trước test. Phù hợp khi
  corpus có heading/metadata đáng tin và người dùng cung cấp phạm vi hợp lệ.
  Với câu không có filter, C hoạt động như B; không tự suy nguồn gold để lọc.

Giới hạn gồm hai tài liệu gần chủ đề, câu hỏi ít, test chỉ năm câu, source text
mất bố cục và nhãn chất lượng chưa có reviewer độc lập. Không khẳng định C tốt
nhất cho mọi corpus. Nếu mở rộng, ưu tiên nhận diện đoạn/caption tốt hơn, thêm
corpus và câu hỏi, chuẩn hóa gold passage tối thiểu trước thí nghiệm mới,
và có người chấm độc lập. Thử nghiệm mới cần chọn trên dev và dùng test chưa
dùng để điều chỉnh, không sửa bộ hiện tại theo kết quả đã thấy.

## 5. Tái lập và phương pháp đánh giá

### 5.1. Chạy lại

Hướng dẫn setup máy mới và từng pha: [README.md](../../README.md).
Trên máy đã chuẩn bị, từ `starter/`:

```powershell
docker compose -p day6_student_starter up -d --wait
.\.venv\Scripts\python.exe -X utf8 -m src.run all
.\.venv\Scripts\python.exe -X utf8 -m src.run audit-summary
```

`all --rebuild` tạo lại text/chunk/embedding từ PDF; không tạo lại gold.
Truy vấn mới dùng `python -X utf8 -m src.run query --strategy C --question ... --section ...`.
Schema và model/vector snapshot được kiểm tra để tránh query vào index cũ.
`benchmark/lock.json` kiểm tra corpus/gold/protocol, `selection.json` giữ lựa
chọn trước test, `test_exposure.json` ghi holdout/replay.

Đã qua **29 test**, gồm giữ nội dung/offset/mục, embedding weights thật,
alternative evidence, thứ tự dev/test, cosine/filter, đồng bộ không trùng,
xóa chunk lỗi thời, rollback transaction và reconnect. Kiểm tra restart Docker
xác nhận 677 dòng cùng manifest vẫn còn.
Minh chứng: [code_tests.json](../../results/code_tests.json),
[persistence_check.json](../../results/persistence_check.json).

### 5.2. Phương pháp và nguồn gốc nhãn

Trợ lý AI được dùng để hỗ trợ viết mã, chuẩn bị câu hỏi, phân tích và chấm
theo rubric. Nhãn coherence/grounding dựa trên việc đọc nội dung mẫu và top-3,
đối chiếu câu hỏi/evidence, không được suy trực tiếp từ Hit@3. Metadata được
đối chiếu với PDF, số trang vật lý, offset và heading, có kiểm tra máy hỗ trợ.
Các nhận xét đều lưu lý do và reviewer; số liệu hiệu năng lấy từ lần chạy thật.

Đánh giá không mù, do cùng trợ lý thực hiện phần triển khai và soạn benchmark,
chưa có xác nhận của người chấm độc lập. Bảng CSV lưu điểm, lý do và reviewer
cho từng mẫu; không suy nhãn chất lượng trực tiếp từ metric tự động.

Mẫu và thang điểm: [hướng dẫn audit](../../results/audit/README.md).
Các quyết định bổ sung về evidence nằm tại
[evidence_review.csv](../../results/audit/evidence_review.csv).

## 6. Trạng thái hoàn thiện

Đã có code, corpus/manifest, benchmark, ba cấu hình, vector store, trace,
metric, nhãn rubric, nhật ký và hướng dẫn chạy. Báo cáo này tổng hợp trạng thái
đã đo trong working tree; trước khi nộp cần kiểm tra quyền chia sẻ artifact,
commit/push đầy đủ, ghi SHA commit chứa bài hoàn chỉnh trong `STUDENT.md`
và kiểm tra quyền truy cập repo cho người chấm theo hướng dẫn lớp.
