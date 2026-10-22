# Nâng cấp tư vấn AI theo catalog (22/10/2026)

Nâng cấp AI Chatbot VieTech thành trợ lý tư vấn dựa trên catalog: hiểu ý định tiếng Việt, giữ ngữ cảnh nhiều lượt, không lặp sản phẩm đã giới thiệu, xếp hạng có giải thích và để Gemini viết câu trả lời tự nhiên nhưng chỉ hiển thị khi mọi số liệu có căn cứ. Giữ nguyên Google Gemini (`gemini-3.5-flash-lite`, Interactions API, `store=false`), API chat, giao diện và database. **Không có migration.**

## 1. Nguyên nhân chatbot tư vấn chưa đúng

Kiểm tra mã nguồn trước khi sửa cho thấy:

1. **Lịch sử cá nhân quyết định gợi ý.** Công thức bước 10.6 có H (0,15) lấy từ danh sách yêu thích và đơn đã giao; hãng/danh mục yêu thích còn được gửi cho Gemini mỗi lượt. Câu trả lời có dòng “cùng hãng/nhóm với sản phẩm bạn đã yêu thích hoặc đã mua”.
2. **Không chống lặp.** Xếp hạng là tất định, nên “đề xuất thêm” chạy lại cùng truy vấn và trả lại đúng các mẫu cũ. Backend không lưu mẫu nào đã hiển thị theo nhóm nhu cầu.
3. **Mất ngữ cảnh.** Điều kiện lượt trước chỉ được kế thừa khi câu hỏi khớp một regex hẹp (“máy thứ nhất”, “rẻ hơn”…). “Tôi muốn điện thoại pin trâu” sau “dưới 8 triệu” mất ngân sách; “Đề xuất thêm 3 mẫu khác” không có danh mục. “Máy thứ nhất/thứ hai” chỉ tra theo câu trả lời gần nhất có thẻ. Sau một câu hỏi thông số về một máy, “so sánh máy thứ nhất và thứ hai” không còn tìm được máy thứ hai.
4. **Câu trả lời là bản ghép dữ liệu.** Toàn bộ văn bản do backend dựng theo mẫu: “Thông tin sản phẩm từ catalog VieTech:”, rồi tên, phiên bản, giá. Gemini chỉ trả ID nên không thể giải thích ưu nhược điểm hay khác biệt.
5. **Chấm điểm sai với dữ liệu thật:**
   - Pin laptop ghi “56WHrs”, “54WHr”, “53,8 watt‑giờ” không được đọc (18/35 laptop bị coi là thiếu dữ liệu).
   - MacBook Air M4 bị đánh giá “dưới nhóm Core i5” vì chip chỉ nằm trong tên.
   - Tiêu chí đạt/không đạt khiến các máy cùng qua ngưỡng hòa điểm và máy rẻ hơn luôn thắng.
   - Khi khách chỉ nêu danh mục và ngân sách, chỉ có B nên máy rẻ nhất (cấu hình yếu nhất) đứng đầu.
   - Tiêu chí mà không ứng viên nào có dữ liệu (công suất sạc điện thoại, khối lượng laptop) vẫn kéo điểm mọi máy xuống.
6. **Nhóm con được dùng làm bộ lọc cứng.** Mỗi sản phẩm chỉ thuộc một nhóm con, nên “điện thoại tầm trung”, “laptop văn phòng”… bỏ sót máy phù hợp nằm ở nhóm anh em. Trong catalog thật, nhóm “Điện thoại pin trâu” có slug `samsung`, nên câu hỏi có chữ “Samsung” bị lọc nhầm vào nhóm này.
7. **Chỉ chấm 20 ứng viên đầu theo giá tăng dần.** Mẫu đắt hơn trong ngân sách không bao giờ được xét.

## 2. Luồng xử lý mới

```
Customer Chat UI ─POST /conversations/{id}/ai-messages─▶ AiChatService
  1. _prepare   : kiểm tra quyền/lease, lưu câu hỏi Pending, đọc ≤12 lượt đã hoàn tất → lịch sử + ConversationState
  2. _analyze   : AiTools.prepare (transaction ngắn, không giữ kết nối khi gọi model)
                  ├─ Vocabulary: danh mục/hãng đang hiển thị (CategoryService, BrandService)
                  ├─ analyze(): ý định, slot, kế thừa ngữ cảnh, tham chiếu, sản phẩm cần loại
                  ├─ sản phẩm được tham chiếu → ProductService.get_product_details
                  └─ gợi ý trong danh mục đã biết → search_products (lọc cứng + xếp hạng) chạy sẵn
     Tham chiếu không xác định được (“máy thứ ba” khi danh sách có 2 mẫu) → backend tự hỏi lại, không gọi model
  3. Gemini     : system = persona (prompts/vietech_ai.py) + quy ước backend (prompts/vietech_ai_protocol.py)
                  + dữ liệu lượt này; function calling search_products/get_product/list_offers/present_answer
  4. finish     : đọc lại giá/tồn kho, loại mẫu đã giới thiệu, sắp theo điểm, dựng ≤3 thẻ,
                  kiểm tra message của Gemini (ai_grounding) → hiển thị hoặc thay bằng văn bản backend
  5. Lưu tin AI + thẻ trong một transaction; metadata nội bộ phục vụ lượt sau
```

## 3. Nhận diện ý định (`services/ai_intent.py`)

Hàm thuần `analyze(question, vocabulary, state)`, không truy cập database hay model, chạy trên văn bản đã bỏ dấu (`fold`).

| Ý định | Ví dụ |
|---|---|
| `product_recommendation` | “Tư vấn điện thoại dưới 8 triệu”, “Có laptop ASUS nào không?”, “Có mẫu nào rẻ hơn?” |
| `recommend_more` | “Đề xuất thêm 3 mẫu khác”, “Còn mẫu nào khác không?”, “Cho tôi lựa chọn khác”, “Tôi không thích máy thứ hai”, “Có mẫu nào pin tốt hơn không?” |
| `product_comparison` | “So sánh máy thứ nhất và thứ hai”, “Máy nào pin tốt hơn?”, “iPhone 17 hay S26 tốt hơn” |
| `product_information` | “Máy thứ hai pin bao nhiêu?”, “Có iPhone 16 Plus không?” |
| `price_inquiry` | “iPhone 17 Pro Max giá bao nhiêu?” |
| `promotion_inquiry` | “Có mã giảm giá nào?”, “Mã VIETECH300K áp dụng cho đơn từ bao nhiêu?” |
| `follow_up_question` | “Vậy thì sao?”, “Máy thứ ba thì sao?” |
| `general_chat` | “Xin chào”, câu ngoài phạm vi mua sắm |

Thông tin trích xuất (lưu trong `ShoppingIntent`):

- **Category:** tên/slug danh mục, alias tiếng Anh (“phone”, “tablet”), dòng sản phẩm (iPhone → Điện thoại, MacBook → Laptop). Slug trùng tên hãng bị bỏ qua.
- **MinBudget/MaxBudget:** “dưới/không quá/tối đa/tầm/khoảng”, “từ … đến …”, “20tr500”, “20.000.000 đồng”.
- **Brand:** một hãng không kèm từ mềm là bắt buộc. “ưu tiên/hoặc/cũng được” là ưu tiên mềm. “không chọn/trừ” là loại trừ. Hãng nêu trong câu so sánh không thành điều kiện.
- **UsageNeeds:** nhu cầu (bảng mục 5.3). **Priorities:** nhãn tiêu chí tương ứng, ví dụ pin trâu → dung lượng pin, công suất sạc.
- **HardConstraints / SoftPreferences / ExcludedProductIds:** xem mục 5 và 6.

Các cụm như “pin trâu”, “chơi game mượt”, “học lập trình”, “mỏng nhẹ”, “ngon trong tầm giá” chỉ là tiêu chí chấm điểm, không bao giờ là từ khóa bắt buộc có trong tên sản phẩm. “nhẹ” được so khớp có dấu, vì khi bỏ dấu “nhé” cũng thành “nhe”.

## 4. Ngữ cảnh hội thoại

Quy tắc (đúng thứ tự áp dụng):

1. Điều câu hỏi hiện tại nêu được ưu tiên.
2. Câu nối tiếp cùng danh mục kế thừa danh mục, ngân sách, hãng và nhu cầu mà nó không nêu lại.
3. Ngân sách mới thay toàn bộ khoảng cũ; “bỏ giới hạn ngân sách” xóa ngân sách.
4. Nêu danh mục gốc khác (“Không, tôi muốn laptop”) mở nhóm nhu cầu mới: không kế thừa gì từ nhóm cũ.
5. Câu hỏi về sản phẩm cụ thể (thông số, giá, so sánh) chỉ áp điều kiện chính nó nêu, để ngân sách cũ không chặn sản phẩm khách đang hỏi.
6. Nhu cầu nêu lại thay nhu cầu cũ, trừ khi khách thêm vào (“… nữa”, “kèm …”).
7. Tham chiếu được backend giải quyết:
   - “Máy thứ nhất/hai/ba/cuối”, “mẫu số 2”, “2 máy đầu” theo danh sách gợi ý/so sánh gần nhất.
   - “Máy này/máy vừa nói” theo câu trả lời gần nhất có sản phẩm.
   - “Các mẫu trên” là cả danh sách.
   - Không xác định được thì hỏi lại kèm danh sách, không đoán.
8. “Có mẫu nào rẻ hơn?” đặt trần giá thấp hơn mẫu rẻ nhất vừa hiển thị (hoặc mẫu được nêu).

Trạng thái lưu trong cột `Messages.Metadata` sẵn có (không trả cho khách):

- Tin hỏi: `AiIntent` = `{Intent, FollowUp, CategoryChanged, Inherited, References, ExcludedProductIds, Slots{CategoryId, MinBudget, MaxBudget, BrandId, SoftBrandIds, ExcludedBrandIds, Needs, Rejected, RejectedKeys}}`, cùng `AiAnswerSource` (`model`/`backend`) và `AiGroundingIssues` khi văn bản của Gemini bị từ chối.
- Tin trả lời: `AnswerIntent` và `ProductReferences` (Rank, ProductId, ProductVariantId, ProductName, ModelKey, Price, Slug, SnapshotAt).

Dữ liệu cũ chỉ có `AiConstraints` vẫn đọc được. Cửa sổ ngữ cảnh: 12 lượt hoàn tất gần nhất (`AI_CONTEXT_MAX_TURNS`).

## 5. Recommendation Engine (`services/recommendation.py`)

### 5.1. Tầng 1 — Lọc cứng (trong `AiTools.search_products`)

1. Sản phẩm đang bán (`Active`, chưa xóa), biến thể đang bán và còn hàng.
2. Đúng danh mục gốc (gồm nhóm con). Nhóm con mang tên nhu cầu/phân khúc (pin trâu, chơi game, chụp ảnh, mỏng nhẹ, nhỏ gọn, phổ thông, tầm trung, cao cấp, học tập, văn phòng, đồ họa, lập trình…) lọc theo danh mục gốc và được chấm mềm. Nhóm là dạng sản phẩm (2 trong 1, màn hình gập, kèm bút, các loại tai nghe) vẫn là lọc cứng.
3. Giá thực bán của biến thể (giá sau khuyến mãi tự động từ PricingService, `match_variant_price`) nằm trong ngân sách; cùng một biến thể phải vừa giá vừa còn hàng.
4. Đúng hãng bắt buộc; loại hãng bị loại trừ.
5. Loại sản phẩm khách đã từ chối, và khi khách xin thêm thì loại sản phẩm đã giới thiệu trong nhóm nhu cầu hiện tại (mục 6).

Ứng viên đọc theo trang 30 sản phẩm, tối đa 60 ứng viên đạt lọc cứng (danh mục lớn nhất của VieTech có 35 sản phẩm), thông số tải theo lô một lần. Không giới hạn 3 sản phẩm ở bước tìm kiếm.

### 5.2. Tầng 2 — Xếp hạng mềm

```
Score_final = Σ(wᵢ × sᵢ) / Σ(wᵢ),  i ∈ tiêu chí đang áp dụng,  sᵢ ∈ [0, 1]
w: N = 0,40   B = 0,25   T = 0,20     (H = 0,15 của thiết kế Giai đoạn 10 không dùng)
```

| Tiêu chí áp dụng | Công thức |
|---|---|
| N, B, T | (0,40N + 0,25B + 0,20T) / 0,85 |
| N, B (không ưu tiên hãng) | (0,40N + 0,25B) / 0,65 |
| N, T (không ngân sách) | (0,40N + 0,20T) / 0,60 |
| Chỉ N | N |

Thiếu ngân sách hay thiếu ưu tiên hãng không làm giảm điểm của mọi sản phẩm vì tiêu chí đó bị loại khỏi cả tử và mẫu. Không có lịch sử mua hàng, wishlist hay giỏ hàng thì vẫn xếp hạng như nhau; hai khách khác nhau hỏi cùng một câu nhận cùng thứ tự (có test).

**B — ngân sách:** chỉ áp dụng khi có trần giá, sau khi lọc cứng. `B = 0,70 + 0,30 × (BudgetMax − Price) / BudgetMax`, chặn trong [0, 1]. Price là giá thực bán của biến thể được chọn.

**T — thương hiệu:** chỉ khi có hãng ưu tiên mềm: 1 nếu đúng hãng, 0 nếu khác. Hãng bắt buộc xử lý ở tầng 1. Không dùng hãng từng mua hay từng yêu thích.

### 5.3. N — mức độ đáp ứng nhu cầu

- N là trung bình có trọng số của các kiểm tra theo thông số thật.
- Đơn vị được chuẩn hóa trước: “5.000 mAh”, “6000mAh”, “56WHrs”, “53,8 watt‑giờ”, “1TB”, “6.1 inches”.
- Mỗi kiểm tra cho điểm liên tục giữa hai mốc (`_ramp`). Ngưỡng chỉ quyết định lời giải thích “đạt/chưa đạt”, nên máy 7.000 mAh hơn máy 5.000 mAh dù cả hai đều qua ngưỡng 5.000 mAh.

| Nhu cầu (cụm nhận diện) | Loại | Tiêu chí: trọng số (mốc 0 → 1; ngưỡng đạt) |
|---|---|---|
| Cấu hình cân bằng (khi không nêu nhu cầu) / “ngon trong tầm giá”, “đáng tiền” | Điện thoại | chip 0,30 (nhóm cao 1,0 / tầm trung 0,55 / phổ thông 0,15); RAM 0,15 (4→12 GB; 8); bộ nhớ 0,10 (64→256 GB; 128); pin 0,20 (4.000→6.000 mAh; 5.000); tần số quét 0,10 (60→120 Hz; 120); chống rung quang học 0,15 |
| | Laptop | CPU 0,30 (cao 1,0 / tầm trung 0,75 / phổ thông 0,2); RAM 0,25 (4→16 GB; 16); SSD 0,20 (128→512 GB; 512); GPU rời 0,10; pin 0,15 (40→70 Wh; 50) |
| | Máy tính bảng | chip 0,30; RAM 0,20 (4→8 GB; 6); bộ nhớ 0,20 (64→256 GB; 128); pin 0,15 (5.000→9.000 mAh; 7.000); tần số quét 0,15 (60→120 Hz; 90) |
| Lập trình (“lập trình”, “code”, “CNTT”) | Laptop | RAM 0,35 (8→16 GB; 16); SSD 0,25 (128→512 GB; 512); CPU 0,25 (đạt: nhóm cao/tầm trung); khe RAM nâng cấp 0,15 |
| Chơi game (“chơi game”, “gaming”, “Liên Quân”, “PUBG”) | Laptop | GPU rời 0,45 (RTX xx50 0,6 / xx60 0,8 / ≥xx70 1,0; Radeon RX 0,7; GTX 0,4); RAM 0,25 (8→16 GB); CPU 0,15; tần số quét 0,15 (60→144 Hz; 120) |
| | Điện thoại | chip 0,45 (chỉ nhóm cao là đạt); RAM 0,25 (6→12 GB; 8); tần số quét 0,30 (60→120 Hz; 120) |
| | Máy tính bảng | chip 0,45; RAM 0,25 (4→8 GB; 8); tần số quét 0,30 (60→120 Hz; 90) |
| Đồ họa/dựng video (“đồ họa”, “thiết kế”, “dựng video”, “render”) | Laptop | GPU rời 0,40; RAM 0,30 (8→32 GB; 16); CPU 0,30 (chỉ nhóm cao là đạt) |
| Học tập/văn phòng (“học tập”, “sinh viên”, “văn phòng”) | Laptop | RAM 0,30 (4→16 GB; 8); SSD 0,25 (128→512 GB; 256); pin 0,20 (40→70 Wh; 50); khối lượng 0,25 (≤1,6 kg đạt; 2,5 kg → 0) |
| | Máy tính bảng | RAM 0,5 (3→8 GB; 4); bộ nhớ 0,5 (64→256 GB; 128) |
| Pin trâu (“pin trâu”, “pin (phải) trâu/tốt/lâu”, “sạc nhanh”) | Điện thoại | dung lượng pin 0,75 (4.000→7.000 mAh; 5.000); công suất sạc 0,25 (18→67 W; 33) |
| | Máy tính bảng / Laptop | 5.000→10.000 mAh (7.000) / 40→80 Wh (50) |
| Chụp ảnh (“chụp ảnh”, “camera”, “quay video”, “selfie”) | Điện thoại | chống rung quang học 0,6; ống kính tele/zoom quang 0,4 — không dùng số MP |
| Mỏng nhẹ (“mỏng nhẹ”, “nhỏ gọn”, “nhẹ”) | Laptop | khối lượng 0,6 (≤1,5 kg); kích thước màn hình 0,4 (≤14 inch đạt; 16 inch → 0) |
| | Điện thoại | khối lượng 0,6 (≤190 g); kích thước màn hình 0,4 (≤6,3 inch; 6,9 inch → 0) |

Quy tắc dữ liệu:

- **Nhóm chip/CPU** đọc theo tên chip ghi trong catalog (có bảng mẫu và test):
  - Snapdragon 8, Dimensity 8xxx/9xxx, Apple A15+/M, Core i7/i9, Ultra 7/9, Ryzen 7/9: nhóm hiệu năng cao.
  - Snapdragon 7, Dimensity 7xxx, Exynos 13xx–19xx, Helio G9x, Core i5/5, Ryzen 5, Apple A18 Pro trên laptop: nhóm tầm trung.
  - Helio khác, Unisoc, Snapdragon 4–6, Dimensity 6xxx, Core i3, Celeron, Pentium: nhóm phổ thông.
  - Chip chỉ có trong tên (MacBook Air M4) vẫn được đọc. Dòng chip không có trong bảng thì ghi “chưa xếp nhóm”, không đoán.
- **Thiếu dữ liệu** được 0 điểm và hiện trong “Lưu ý” (“chưa có dữ liệu …”, “chưa xác nhận …”); không bao giờ được tính là đạt. Văn bản camera không ghi OIS không chứng minh có OIS.
- **Tiêu chí không ứng viên nào có dữ liệu** (ví dụ công suất sạc điện thoại, khối lượng laptop trong catalog hiện tại) bị loại khỏi N của lượt đó, vì không phân biệt được ứng viên. Tiêu chí nhóm con VieTech (0,2) cũng bị loại khi không ứng viên nào thuộc nhóm.
- **Khi có nhu cầu cụ thể**, tiêu chí nhu cầu giữ 75% N; hồ sơ cân bằng đóng góp 25%. Nhờ vậy hai máy cùng pin 6.000 mAh được phân biệt bằng phần cấu hình còn lại, không chỉ bằng giá.
- Pin chỉ là tín hiệu dung lượng; câu trả lời không suy ra số giờ sử dụng.

### 5.4. Top K và đồng điểm

1. Sắp xếp giảm dần theo Score_final, so ở 2 chữ số thập phân (đúng giá trị model nhìn thấy). Chênh lệch nhỏ hơn mức đó thường chỉ do B, nên không được để máy rẻ hơn vượt máy phù hợp nhu cầu hơn.
2. Đồng điểm: N cao hơn, rồi dữ liệu đầy đủ hơn, rồi giá thấp hơn, rồi ProductId (ổn định).
3. Đưa tối đa 5 ứng viên đã xếp hạng (kèm `Matched`/`Gaps`) cho Gemini; câu trả lời hiển thị tối đa 5 thẻ. Khi `intent=recommend`, backend đọc lại giá/tồn kho và sắp thẻ theo điểm, không theo thứ tự model liệt kê.
4. Khách yêu cầu thứ tự (“rẻ nhất”, “mới nhất”, “giá giảm dần”) thì giữ thứ tự đó và không xếp hạng lại.
5. Tìm kiếm rỗng vì ngân sách thì backend tìm mẫu rẻ nhất vượt ngân sách mà vẫn đạt mọi điều kiện khác (`NearestAboveBudget`) và nói rõ mẫu đó cùng giá.
6. `AI_RANKING_ENABLED=false` vẫn cho chế độ baseline (thứ tự catalog) để so sánh.

## 6. Chống đề xuất trùng

Khi `recommend_more` (“đề xuất thêm”, “còn mẫu nào khác”, “lựa chọn khác”, “mẫu tương tự”, “không thích máy này”):

1. Backend đọc các lượt liên tiếp gần nhất cùng danh mục gốc (nhóm nhu cầu hiện tại) từ metadata đã lưu.
2. Gom ProductId và **tên mẫu chuẩn** (`model_key`: bỏ dung lượng, màu, 5G, chữ “Điện thoại”/“Laptop”) của mọi sản phẩm đã hiển thị, cộng các sản phẩm khách từ chối. Hai biến thể màu hay dung lượng của cùng một mẫu không bị tính là mẫu mới.
3. `search_products` bỏ các sản phẩm đó trước khi xếp hạng và báo `AlreadyShownExcluded`.
4. Ở `finish`, nếu model vẫn chọn một mẫu cũ thì backend bỏ mẫu đó và lấy mẫu mới xếp hạng kế tiếp.
5. Hết mẫu mới thì trả lời rõ, ví dụ: “Mình đã giới thiệu hết 2 mẫu laptop đang có hàng phù hợp với … hãng ASUS. Bạn có muốn nới ngân sách, đổi hãng hoặc bớt tiêu chí…?” Còn ít hơn số mẫu khách xin thì báo “Hiện chỉ còn 2 mẫu mới phù hợp…”.

Sản phẩm bị từ chối giữ trong `Slots.Rejected` suốt nhóm nhu cầu. Đổi danh mục gốc thì nhóm mới bắt đầu.

## 7. Dữ liệu từ Supabase đưa vào Gemini

Không gửi toàn bộ database. Mỗi lượt Gemini nhận:

- **Persona** (`prompts/vietech_ai.py`) và **quy ước backend** (`prompts/vietech_ai_protocol.py`).
- **Phân tích lượt này** (JSON): ý định, tên danh mục, ngân sách, nhu cầu, tiêu chí ưu tiên, hãng bắt buộc/ưu tiên/loại trừ, điều kiện kế thừa, số mẫu đã loại, sản phẩm được tham chiếu (Rank, ProductId, tên). Không chứa văn bản của khách.
- **Kết quả `search_products` đã chạy sẵn** khi là câu gợi ý trong danh mục đã biết: tối đa 5 ứng viên (tên, hãng, danh mục, một biến thể với giá thực bán, Ranking gồm Rank/Score/Parts/Matched/Gaps), số ứng viên đạt, điều kiện đã áp.
- **Sản phẩm được tham chiếu** (“máy thứ hai”, “máy thứ năm”): tối đa 5 sản phẩm, 12 thông số công khai, 4 biến thể, số tháng bảo hành.
- **Lịch sử:** cặp hỏi–đáp đã hoàn tất (≤10.000 ký tự, đã ẩn email/số điện thoại), kèm tên sản phẩm đã hiển thị.
- **Kết quả công cụ** do model tự gọi thêm (schema Pydantic, chỉ đọc).

Không gửi họ tên, email, số điện thoại, địa chỉ, đơn hàng, wishlist hay giỏ hàng. Nhờ dữ liệu chạy sẵn, đa số lượt gợi ý hay hỏi “máy thứ hai” chỉ cần một lần gọi Gemini.

## 8. Câu trả lời tự nhiên có kiểm chứng (`services/ai_grounding.py`)

`present_answer` có thêm `message` (≤1.500 ký tự) và `intent=chat`. Backend chỉ hiển thị `message` khi:

- Mọi số có đơn vị (GB, mAh, Wh, W, Hz, inch, tháng…) có trong dữ liệu lượt này. Dòng nhắc đúng một sản phẩm được so với chính sản phẩm đó, nên không thể gán pin máy này cho máy khác.
- Mọi số tiền trùng giá hiện tại, ngân sách hay giá trị coupon đã đọc. Viết dạng “7,99 triệu” được sai lệch tối đa 50.000 đ; viết bằng đồng thì phải trùng khớp.
- Mã mẫu/mã coupon (“S25”, “i7-13620H”, “VIETECH300K”) và tên hãng có trong dữ liệu, câu hỏi, phân tích hoặc sản phẩm đã hiển thị trước đó.
- Không có khẳng định ngoài dữ liệu: trả góp, quà tặng, giao hàng miễn phí, “dùng cả ngày”, “tốt nhất phân khúc”. Không nhắc ưu đãi khi chưa đọc ưu đãi.
- Không có lý do cá nhân (“bạn đã mua/yêu thích”), không tên công cụ hay system prompt, không liên hệ/đường dẫn.
- Sản phẩm được nêu theo đúng thứ tự thẻ.

Không đạt thì dùng văn bản backend: câu mở đầu nối với nhu cầu, tên, phiên bản/giá, “Phù hợp: …”, “Lưu ý: …”. Lý do bị từ chối được lưu ở `AiGroundingIssues` để đánh giá. Thẻ, giá và tồn kho luôn do backend dựng.

## 9. Function calling Gemini (đã kiểm tra, không đổi adapter)

`integrations/gemini.py` dùng Interactions API (`google-genai` 2.31.0) với `store=false`. Lịch sử do backend giữ; trong một lượt nhiều vòng, adapter gửi lại nguyên `provider_steps` (thought, function_call kèm chữ ký) và `function_result` có `name` + `call_id`. Nó không tự retry và chuyển 429 thành `ai_quota_exceeded` kèm Retry-After.

Phía service:

- `tool_choice="any"`, nên vòng nào model cũng gọi một hàm; kết thúc chỉ bằng `present_answer`.
- Tên hàm được dispatch tường minh, hàm lạ trả `unknown_tool`.
- Tham số kiểm tra bằng Pydantic (`extra="forbid"`, không có tham số SQL).
- Tối đa 4 vòng và 6 lệnh gọi; vòng cuối chỉ còn `present_answer`; một lần sửa khi JSON sai.
- Chỉ nhận ProductId/biến thể đã được tra cứu trong lượt; giá và tồn kho được kiểm tra lại trước khi tạo thẻ.

Các test SDK hiện có (`test_ai_gemini.py`) vẫn đạt.

## 10. Tệp thay đổi

| Tệp | Nội dung |
|---|---|
| `backend/app/services/ai_intent.py` (mới) | Ý định, slot, ngân sách, ngữ cảnh, tham chiếu, sản phẩm loại trừ, nhóm con mềm/cứng |
| `backend/app/services/ai_grounding.py` (mới) | Kiểm tra số liệu/tên/khẳng định trong message của Gemini |
| `backend/app/services/recommendation.py` | Công thức N/B/T không H; điểm liên tục; hồ sơ cân bằng; nhu cầu đồ họa; chip/CPU theo tên; Wh; loại tiêu chí không có dữ liệu; đồng điểm; `model_key` |
| `backend/app/services/ai_tools.py` | Dùng phân tích của backend; chạy sẵn tìm kiếm/tham chiếu; loại mẫu đã giới thiệu; 30/trang, ≤60 ứng viên; NearestAboveBudget; finish với message đã kiểm tra và văn bản dự phòng tự nhiên |
| `backend/app/services/ai_chat.py` | Bỏ tín hiệu wishlist/đơn hàng khỏi lượt AI; pha `_analyze`; tự hỏi lại khi tham chiếu không rõ; dựng ConversationState; lưu AiIntent/AnswerIntent/AiAnswerSource |
| `backend/app/schemas/ai_chat.py` | `present_answer`: `message`, `intent=chat` |
| `backend/app/prompts/vietech_ai_protocol.py` (mới) | Quy ước backend nối sau persona `vietech_ai.py` |
| `backend/app/cli/ai_benchmark.py`, `ai_benchmark_cases.py` | Chấm được câu trả lời dạng văn xuôi; intent lấy từ metadata; ca an toàn chấp nhận `chat` |
| `frontend/src/customer/components/AiChatThread.jsx` | Hiển thị câu trả lời có định dạng; đã xóa đoạn thông báo Gemini và lưu ý giá/tồn kho dưới ô nhập |
| Tests | `test_ai_advisor.py` (mới), cập nhật `test_ai_recommendation.py`, `test_ai_grounded.py`, `test_ai_personalization.py`, `AiChat.test.jsx` |

`repositories/ai_personalization.py` được giữ nguyên (vẫn có test) nhưng không còn được lượt AI gọi.

## 11. Kiểm thử

```powershell
Set-Location E:\vitech-ecommerce\backend
..\.venv\Scripts\python.exe -X utf8 -m pytest tests\test_ai_advisor.py tests\test_ai_recommendation.py tests\test_ai_grounded.py tests\test_ai_personalization.py tests\test_ai_chat.py tests\test_ai_chat_http.py tests\test_ai_gemini.py tests\test_ai_benchmark.py tests\test_ai_migration.py tests\test_ai_connection_check.py -q
```

`test_ai_advisor.py` dùng model giả trả lời như Gemini từ dữ liệu backend đưa vào, nên không tốn quota. Nó kiểm tra:

- Hội thoại 8 lượt theo yêu cầu, với các khẳng định cho từng lượt:

  | Lượt | Câu hỏi | Khẳng định |
  |---|---|---|
  | 1 | Tư vấn điện thoại dưới 8 triệu | Ba điện thoại ≤ 8 triệu; máy mạnh nhất đứng đầu, không phải máy rẻ nhất |
  | 2 | Tôi muốn điện thoại pin trâu | Giữ ngân sách; máy pin lớn nhất đứng đầu |
  | 3 | Đề xuất thêm 3 mẫu khác | Ba mẫu mới, không trùng lượt 1–2 |
  | 4 | Máy thứ hai pin bao nhiêu? | Đúng máy thứ hai của lượt 3, một lần gọi model, đúng số mAh |
  | 5 | So sánh máy thứ nhất và thứ hai | Vẫn là hai máy của lượt 3 |
  | 6 | Giờ tôi muốn laptop dưới 20 triệu học lập trình | Danh mục mới, không mang ngân sách/nhu cầu cũ |
  | 7 | Có laptop ASUS nào không? | Chỉ ASUS, giữ ngân sách 20 triệu |
  | 8 | Còn mẫu khác không? | Báo đã giới thiệu hết |

- Model cố chọn lại mẫu cũ vẫn không lặp; mẫu bị từ chối không quay lại.
- Lọc cứng: sai danh mục, vượt ngân sách, hãng bắt buộc. Sản phẩm không có trong database bị từ chối. Không cần bảng giỏ hàng/wishlist/đơn hàng.
- Văn bản bịa số liệu bị thay và ghi lý do. Tìm kiếm rỗng nêu mẫu gần nhất.
- Điểm liên tục thắng máy rẻ hơn yếu hơn; tiêu chí không có dữ liệu bị loại; đồng điểm sát nút ưu tiên N.
- Đơn vị Wh; nhóm CPU (M4 trong tên, A18 Pro, i3, i7); “nhé” không thành “nhẹ”; `model_key`.
- 13 cách hỏi → đúng ý định; quy tắc kế thừa/thay/xóa ngữ cảnh; hỏi lại khi “máy thứ ba” không tồn tại; slug `samsung`; nhóm con mềm/cứng; kiểm tra message.

Kết quả ngày 22/10/2026:

- Backend: các tệp `tests/test_ai*.py`, `tests/test_chat*.py`, `tests/api/test_chat_api.py` **238 passed, 7 skipped** (các test chỉ chạy trên PostgreSQL thật).
- Frontend: `npx vitest run src/customer/components/AiChat.test.jsx` **27 passed**.
- Chưa chạy toàn bộ bộ test backend/frontend.

### Kiểm tra thật với Gemini

Script tạm chạy 8 lượt trên qua `AiChatService` + `GeminiChatModel` thật (`gemini-3.5-flash-lite`). Database là SQLite trong bộ nhớ nạp `backend/data/sample-catalog-2026-10-17.json` (200 sản phẩm) và nhóm con thật, không đụng database phát triển. Lần chạy cuối:

| Lượt | Kết quả |
|---|---|
| 1. Tư vấn điện thoại dưới 8 triệu | Redmi Note 14 Pro+, Meizu Lucky 08, Meizu Mblu Note 21 Pro; Gemini viết, đạt kiểm tra |
| 2. Tôi muốn điện thoại pin trâu | Giữ 8 triệu; HONOR X7d (6.500 mAh) đầu tiên |
| 3. Đề xuất thêm 3 mẫu khác | Loại 5 mẫu đã giới thiệu; chỉ còn 2 mẫu mới và câu trả lời nói rõ |
| 4. Máy thứ hai pin bao nhiêu? | Đúng Meizu Mblu 22 Pro, 5000 mAh |
| 5. So sánh máy thứ nhất và thứ hai | Đúng hai máy của lượt 3; nêu RAM/bộ nhớ/màn hình và gợi ý chọn |
| 6. Laptop dưới 20 triệu học lập trình | Danh mục mới; MacBook Air M2, Acer Aspire Lite 14, Lenovo IdeaPad Slim 3 |
| 7. Có laptop ASUS nào không? | Catalog mẫu không có ASUS ≤ 20 triệu; nêu mẫu gần nhất Vivobook 14 (22.990.000 đ) |
| 8. Còn mẫu khác không? | Giữ ASUS + 20 triệu; nói rõ không còn mẫu khác |

- 8/8 lượt hoàn tất; mọi câu trả lời do Gemini viết và đạt kiểm tra (0 lần bị thay).
- Thời gian mỗi lượt 7–19 giây; một lượt 56 giây vì chờ thử lại sau lỗi 503.
- Khoảng 4.600–11.100 token đầu vào mỗi lượt.
- Google trả HTTP 503 ba lần trong lần chạy này và hai lượt ở lần chạy đầu. Adapter không tự retry; script thử lại cùng mã yêu cầu như nút “Kiểm tra và thử lại”.
- Hai lần chạy trước phát hiện và đã sửa:
  - Đồng điểm sát nút do B (Meizu Lucky hơn HONOR X7d 0,0003 điểm).
  - Văn bản bị từ chối oan vì nhắc hãng ASUS kế thừa và sản phẩm đã hiển thị trước đó.

Đây là kiểm tra chức năng trên dữ liệu mẫu, không phải benchmark 40 câu của [bước 10.7](stage10-ai-evaluation.md).

## 12. Hạn chế

- Nhận diện ý định và nhu cầu bằng mẫu cụm từ tiếng Việt; cách nói mới cần bổ sung mẫu và test. Câu mơ hồ được xếp `general_chat` hoặc hỏi lại.
- Trọng số, mốc chuẩn hóa và bảng nhóm chip là giả thuyết thiết kế, chưa hiệu chỉnh bằng dữ liệu người dùng; bảng chip cần cập nhật khi có dòng chip mới.
- Catalog thiếu nhiều thông số (khối lượng, công suất sạc, tần số quét laptop), nên các tiêu chí này thường bị loại hoặc ghi “chưa có dữ liệu”.
- Chống lặp dựa trên 12 lượt gần nhất trong cùng hội thoại; quay lại danh mục cũ sau khi đã đổi danh mục được tính là nhóm mới.
- Kiểm tra message xác minh số, mã, tên hãng và các khẳng định đã liệt kê. Nó không hiểu ngữ nghĩa câu, ví dụ một nhận xét định tính sai nhưng không có số liệu. Dòng nhắc nhiều sản phẩm chỉ được so với dữ liệu của các sản phẩm đó gộp lại.
- Gemini Free có lúc trả 503/quá hạn mức; adapter cố ý không tự retry, khách dùng nút thử lại.
- Văn bản dự phòng của backend vẫn có cấu trúc liệt kê. Nó chỉ xuất hiện khi văn bản của Gemini không đạt kiểm tra.

## 13. Bổ sung: hỏi chính sách, hỏi vì sao đề xuất và mô tả chi tiết sản phẩm (22/10/2026, tối)

Kiểm tra trên giao diện khách phát hiện hai câu hỏi không có câu trả lời. Mã lỗi đọc từ `Messages.Metadata`:

| Câu hỏi | Lỗi | Nguyên nhân |
|---|---|---|
| “Thông tin khuyến mãi bảo hành như nào” | `ai_invalid_output` | Backend không có dữ liệu chính sách để đưa cho Gemini. Quy ước cũ còn bảo model chuyển câu hỏi bảo hành/đổi trả sang `handoff`. |
| “Tại sao bạn lại đề xuất cho tôi 3 máy này” | `ai_ungrounded_output` | Câu hỏi bị hiểu là gợi ý mới (`product_recommendation`). Tìm kiếm chạy sẵn ghi đè dữ liệu chi tiết của các máy đã giới thiệu, nên phiên bản/thông số Gemini chọn bị coi là chưa tra cứu. |
| “Tại sao bạn lại đề xuất cho tôi những máy này” | `ai_unavailable` | Gemini lỗi (503/quá thời gian); câu hỏi này không có câu trả lời dự phòng. |

Thay đổi (không có migration, API và giao diện giữ nguyên):

- **Hai ý định mới trong `ai_intent.py`:**
  - `policy_inquiry`: có từ bảo hành, đổi trả, đổi hàng, trả hàng, hoàn tiền hoặc chính sách, bao gồm câu hỏi về chính sách/thủ tục của sản phẩm đã tham chiếu. “Bảo hành của 2 sản phẩm trên như thế nào” và “Tôi muốn biết bảo hành của 2 sản phẩm trên” giữ đúng danh sách vừa so sánh; hỏi riêng “máy thứ hai” chỉ kèm thời hạn của máy đó. `Topics` gồm `promotion`, `warranty`, `returns`; hỏi kèm khuyến mãi thì có cả `promotion`. Câu chỉ hỏi thời hạn (“Máy thứ hai bảo hành bao lâu?”) hoặc hỏi thêm thông số khác vẫn là `product_information`. “đời mới” không bị nhầm với “đổi mới”.
  - `explain_recommendation`: có từ hỏi lý do (“tại sao”, “vì sao”, “sao lại”, “lý do”, “dựa vào đâu”) đi cùng động từ chọn (“đề xuất”, “gợi ý”, “chọn”…), khi hội thoại đã có danh sách. Câu hỏi giải thích cả danh sách vừa hiển thị, hoặc đúng máy được nêu (“máy thứ hai”). Điều kiện đang áp dụng (danh mục, ngân sách, nhu cầu) được giữ nguyên.
- **Dữ liệu chính sách (`services/ai_policy.py`):**
  - Bảo hành: quy tắc của `warranty_period.py` và trang “Chính sách bảo hành”. Kèm số tháng bảo hành đọc từ catalog của đúng sản phẩm được tham chiếu; nếu không chỉ rõ thì dùng danh sách vừa gợi ý hoặc sản phẩm vừa xem. Sản phẩm có thời hạn 0 tháng được ghi rõ không có bảo hành.
  - Đổi trả: thời hạn `RETURN_WINDOW_DAYS` (mặc định 7 ngày) và điều kiện đổi giống trang tạo yêu cầu đổi trả.
  - Khuyến mãi: giảm giá tự động theo danh mục (`PricingService.category_offers`) và mã giảm giá công khai (`list_offers`).
  - Dữ liệu được đưa cho Gemini trong khối “CHÍNH SÁCH VÀ ƯU ĐÃI VIETECH”, đồng thời là căn cứ để kiểm chứng câu trả lời. Mã giảm giá được đọc lại khi dựng câu trả lời.
- **Giải thích đề xuất:**
  - Backend áp lại công thức xếp hạng cho đúng các máy đã hiển thị, giữ nguyên thứ tự hiển thị. Mỗi máy nhận `Matched`/`Gaps`, cờ trong ngân sách và cờ đúng hãng ưu tiên.
  - Câu trả lời chỉ có văn bản, không lặp thẻ sản phẩm. `ProductReferences` giữ nguyên Rank, nên “máy thứ hai” vẫn trỏ đúng danh sách cũ.
- **Backend quyết định nội dung:**
  - Với hai ý định này, Gemini chỉ viết lời. Sản phẩm hay ý định model chọn sai không làm hỏng lượt.
  - Gemini lỗi (503, quá thời gian, JSON sai, vượt giới hạn tra cứu) thì hiển thị câu trả lời của backend; áp dụng cho cả `promotion_inquiry`. Lỗi hết hạn mức (`ai_quota_exceeded`) vẫn báo lỗi để giữ thời gian chờ.
  - Lời Gemini có số liệu hoặc khẳng định không có trong dữ liệu (ví dụ “30 ngày”, “1 đổi 1”) thì bị thay bằng văn bản backend, như mục 8.
  - Với câu hỏi chính sách, chỉ dùng lời Gemini khi model chọn `intent=policy` và nội dung được kiểm chứng; nếu model chuyển nhầm sang `handoff` hoặc ý định khác thì dùng câu trả lời chính sách của backend.
- **Giới thiệu/mô tả chi tiết sản phẩm đang đề xuất** (ý định `product_description`):
  - Ví dụ: “Mô tả cụ thể từng máy”, “Cho tôi biết thông tin cụ thể hơn 3 chiếc laptop”, “Giới thiệu chi tiết các máy này”, “Giới thiệu thêm về máy thứ hai”, “Đánh giá máy thứ nhất”. Trước đây các câu này bị xếp `general_chat`, nên Gemini không nhận dữ liệu sản phẩm.
  - Điều kiện: có từ mô tả (“mô tả”, “chi tiết”, “cụ thể”, “ưu nhược điểm”…), hoặc từ “giới thiệu/thông tin/cấu hình/đánh giá” kèm tham chiếu (“từng máy”, “3 chiếc”, “máy thứ hai”, “các máy này”). Câu không được nêu tiêu chí mới (ngân sách, nhu cầu, tên mẫu khác) và phải cùng nhóm danh mục.
  - Sản phẩm được mô tả:
    - “Từng máy”, “3 chiếc”: cả danh sách vừa gợi ý.
    - “Mô tả chi tiết hơn”: sản phẩm của câu trả lời gần nhất, ví dụ đúng máy vừa hỏi pin.
  - Backend đọc 20 thông số và 8 phiên bản mỗi máy. Câu trả lời chỉ có văn bản, theo đúng thứ tự đã hiển thị. Mỗi máy gồm phiên bản, giá, còn hàng, tối đa 8 thông số nổi bật (chip/CPU, RAM, bộ nhớ, card, màn hình, pin…) và bảo hành.
  - Gemini lỗi thì backend tự trả lời; lời có số liệu bịa thì bị thay.
- Câu trả lời giải thích và mô tả không tạo danh sách mới: “máy thứ hai” vẫn là máy thứ hai của lần gợi ý gần nhất.
- Ngân sách nói kiểu “Tôi chỉ có 20 triệu thôi”, “còn 15 triệu”, “20 triệu trở xuống/đổ lại” được hiểu là trần giá. Câu chỉ nêu ngân sách giữ danh mục và nhu cầu đang tư vấn, rồi tìm lại. Trước đây câu này bị xếp `general_chat`.
- **Hỏi lại khi khách chưa nêu tiêu chí:**
  - Ví dụ: “Tôi muốn mua 1 chiếc điện thoại”, “Tư vấn laptop cho tôi”, “Tôi cần mua máy”.
  - Điều kiện hỏi lại: là yêu cầu gợi ý nhưng chưa có ngân sách, nhu cầu, hãng, thứ tự (“rẻ nhất”, “mới nhất”) hay dòng sản phẩm (“iPhone”), kể cả điều kiện kế thừa trong cùng nhóm danh mục.
  - Backend tự hỏi ngân sách, nhu cầu sử dụng và hãng yêu thích, kèm ví dụ theo loại sản phẩm, không gọi Gemini. Chưa có danh mục thì hỏi thêm loại sản phẩm.
  - Câu trả lời của khách (“Tầm 8 triệu, chơi game”) được ghép với danh mục đã hỏi rồi gợi ý ngay.
  - Chỉ hỏi một lần cho mỗi yêu cầu. Khách trả lời “tùy bạn”, “gì cũng được” hoặc nhắc lại yêu cầu thì gợi ý theo hồ sơ cấu hình cân bằng.
  - Câu đã có tiêu chí rõ (“Tư vấn điện thoại dưới 8 triệu”, “Điện thoại pin trâu”, “Có laptop ASUS nào không?”) vẫn được gợi ý ngay.
- `present_answer` có thêm `intent=explain` và `intent=policy`. `handoff` chỉ dùng cho tình trạng một đơn hàng, thanh toán hay yêu cầu cụ thể.
- Câu trả lời ưu đãi (`intent=offers`) có thêm dòng giảm giá tự động theo danh mục. Hạn mã ghi dạng ngày/tháng/năm.

Kiểm thử: `tests/test_ai_policy_explain.py`:

- Nhận diện ý định và chủ đề.
- Câu “tại sao” khi Gemini lỗi, chọn sản phẩm lạ hoặc trả tham số sai.
- Câu khuyến mãi + bảo hành khi Gemini lỗi, trả văn bản không phải JSON hoặc chọn `handoff`.
- Hai cách hỏi bảo hành của “2 sản phẩm trên” sau khi so sánh: nêu đúng thời hạn của hai máy, không lấy thêm máy thứ ba; hoạt động khi Gemini lỗi/JSON sai/chuyển nhầm `handoff`, giữ lời model hợp lệ và không làm mất ngữ cảnh “máy thứ hai”.
- Thời hạn đổi trả theo cấu hình; lời bịa bị thay.
- Lỗi hết hạn mức vẫn báo lỗi.
- Mô tả từng máy khi Gemini lỗi, chọn sản phẩm lạ hoặc bịa thông số; “mô tả chi tiết hơn” chỉ mô tả máy vừa nói tới.
- Câu chung chung được hỏi lại trước, câu trả lời của khách dẫn tới gợi ý; không hỏi hai lần.
- Các test vòng đời lượt AI (`test_ai_chat.py`, `test_ai_chat_http.py`, hai test trong `test_ai_grounded.py`) dùng câu hỏi có tiêu chí, để vẫn kiểm tra luồng gọi model.

Toàn bộ `tests/test_ai*.py`, `tests/test_chat*.py`, `tests/api/test_chat_api.py`: **302 passed, 7 skipped**, cùng **45 subtests passed**. Ba test benchmark dùng thư mục tạm cần chạy lại với quyền tạo thư mục tương thích sandbox Windows; không thay đổi mã ứng dụng hoặc mã kiểm thử để xử lý quyền thư mục.

## 14. Khuyến mãi đúng sản phẩm, câu hỏi đổi trả và trình bày tin nhắn (23/10/2026)

- “Khuyến mãi sản phẩm như nào” sau một danh sách dùng đúng các mẫu vừa nhắc tới. “Khuyến mãi các sản phẩm trên như nào” giữ danh sách đang so sánh. “Khuyến mãi sản phẩm trên như nào” dùng mẫu vừa xem; nếu còn nhiều mẫu thì hỏi lại.
- Mỗi mẫu có một nhóm riêng: giá gốc/giá sau giảm tự động và mã công khai thực sự áp dụng cho mẫu đó. Không lấy mã của mẫu khác. Hỏi theo danh mục thì lọc coupon theo các sản phẩm trong danh mục; hỏi một mã cụ thể thì không đưa mã khác vào trả lời. Hỏi cách áp dụng mã thì hướng dẫn giỏ hàng.
- Ưu đãi được đọc lại khi dựng câu trả lời; dữ liệu dùng kiểm chứng cũng được thay mới để lời model không giữ mã vừa hết hạn.
- Nhận diện thêm “được đổi mới”, “muốn đổi máy”, “được trả không”, kể cả khi nhắc tới mẫu cụ thể. Câu trả lời tập trung vào thời hạn, cách gửi, chênh lệch, hoàn tiền hoặc cách xem tiến độ theo điều khách hỏi.
- Nội dung đổi trả tuân theo luồng hiện hành: chỉ tạo yêu cầu đổi sản phẩm, mỗi phiếu 1 sản phẩm; không cam kết trả hàng hoàn tiền mới. Thời hạn lấy từ RETURN_WINDOW_DAYS; nhân viên kiểm tra điều kiện thực tế. Lời model hứa hoàn tiền được thay bằng câu trả lời có căn cứ.
- Prompt yêu cầu trả lời trực tiếp, đoạn ngắn, chữ đậm ở tên/mã/số liệu chính, tiêu đề nhỏ khi cần, danh sách và các bước rõ ràng. Câu dự phòng từ backend cũng chia riêng từng sản phẩm. ai_grounding.py giữ định dạng khi hiển thị và bỏ ký hiệu định dạng khi kiểm tra số liệu, nên chữ đậm không che được việc gán sai thông số.
- AiChatText.jsx dựng đoạn, tiêu đề, chữ đậm/nghiêng, mã ngắn và danh sách bằng React; không render HTML thô hoặc liên kết. Ký hiệu Markdown chưa đóng không làm mất chữ. Không thêm thư viện frontend.
- Xóa toàn bộ thông báo “Nội dung chat được Google Gemini xử lý…” và “Giá và tồn kho có thể thay đổi…” dưới ô nhập.

Tham khảo cách tổ chức nội dung và hướng dẫn định dạng từ [ChatGPT](https://help.openai.com/en/articles/20001246-working-with-writing-blocks-and-code-blocks-in-chatgpt), [Claude](https://support.claude.com/en/articles/14546867-set-organization-instructions) và [Gemini](https://ai.google.dev/gemini-api/docs/prompting-strategies). Chọn tập định dạng gọn phù hợp khung chat của VieTech.

Xác minh: **364 kiểm thử backend đạt, 7 bỏ qua, 45 subtests đạt** (AI, chat và pricing); **32 kiểm thử frontend đạt**; production build và lint các thành phần liên quan đạt. Đã kiểm tra hai mẫu trả lời khuyến mãi/đổi trả trên viewport 1440, 390 và 320 px: không tràn ngang và ô nhập nằm trong khung. Ảnh mẫu nằm trong output/ai-offers-*.png và output/ai-returns-*.png.

Đã gọi Gemini thật với catalog giả và SQLite trong bộ nhớ cho câu hỏi khuyến mãi hai sản phẩm, cách gửi yêu cầu đổi trả và trả hàng hoàn tiền. Các câu đều hoàn tất; sau khi làm rõ prompt yêu cầu trả lời chính sách bằng văn bản với products rỗng, câu khuyến mãi dùng trực tiếp lời Gemini đã được kiểm chứng trong một lần gọi. Không kết nối database cửa hàng hoặc dùng dữ liệu tài khoản khách trong kiểm tra này.

## 15. Tư vấn tối đa 5 sản phẩm và hỏi nhu cầu tự nhiên hơn (23/10/2026)

- AI_MAX_PRODUCTS mặc định 5, nhận cấu hình từ 1 đến 5. Schema kết quả, công cụ đọc theo thứ tự/danh sách, prompt, lịch sử, chính sách và giao diện đều hỗ trợ 5 sản phẩm.
- Khách hỏi 2 mẫu thì chỉ tư vấn 2. Khách hỏi 5 mẫu nhưng model chọn ít hơn, backend bổ sung từ các ứng viên đã lọc và xếp hạng, không nới ngân sách hoặc hãng. Nếu chỉ có ít mẫu phù hợp thì nêu số lượng thực tế.
- Câu “hãy đề xuất tối đa 5 sản phẩm cho tôi” chưa nêu loại hàng/ngân sách vẫn được hỏi thêm. Số lượng 5 được giữ qua bước hỏi nhu cầu, thay vì mất khi khách trả lời “laptop dưới 20 triệu”.
- Hiểu “máy thứ tư”, “máy thứ năm”, “bốn máy đầu”, “năm sản phẩm trên”. Lượt “tư vấn thêm 5 mẫu” loại các mẫu đã tư vấn trong ngữ cảnh hiện tại. Bảo hành và khuyến mãi vẫn áp dụng đúng cả mẫu thứ 4 và thứ 5.
- Giữ cấu trúc câu hỏi và ba mục ngân sách, mục đích sử dụng, hãng yêu thích cùng các ví dụ. Chỉ chỉnh câu mở đầu thành “Để tư vấn laptop phù hợp với bạn, bạn cho mình biết thêm nhé:”; không rút gọn hoặc thêm cụm “vài mẫu”.
- Prompt yêu cầu dùng “tư vấn”, giữ đủ các thông tin cần hỏi và cho phép danh sách kèm ví dụ. Hãng là tùy chọn. Câu hỏi chung không cần gọi model và chỉ hỏi một lần cho yêu cầu hiện tại.

Kiểm thử bổ sung ở tests/test_ai_five_products.py: giới hạn schema/cấu hình, đủ 5 thẻ, giới hạn thấp hơn, bổ sung từ 3 lên 5, giữ số lượng qua lượt hỏi thêm, không lặp 5 mẫu trước, tham chiếu thứ 4/5, bảo hành đủ 5 máy và kích thước kết quả đọc nhóm. Test frontend xác nhận hiển thị 5 thẻ theo thứ tự, bỏ thẻ thứ 6.

Xác minh cho cập nhật này: **344 kiểm thử AI/chat backend đạt, 7 bỏ qua, 45 subtests đạt**; **32 kiểm thử frontend đạt**; production build và lint thành công. Gemini thật đã hoàn tất luồng hỏi nhu cầu laptop → tư vấn 5 mẫu dưới 20 triệu cho lập trình → hỏi pin máy thứ năm, trên catalog giả trong SQLite bộ nhớ. Bước hỏi thêm không gọi model; không truy cập database cửa hàng.
