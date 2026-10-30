# AI Smart Compare trong chatbot VIETECH

Ngày bàn giao: 28/10/2026.

## Chức năng đã triển khai

- Bảng 2–3 sản phẩm/phiên bản ngay trong cửa sổ AI Chat hiện tại, gồm tên, ảnh, phiên bản, thương hiệu, danh mục, giá bán, tồn kho, thông số và liên kết chi tiết.
- Nhận diện tên sản phẩm trực tiếp, thứ tự trong danh sách và các câu tham chiếu như “So sánh 2 laptop vừa giới thiệu”, “Máy thứ nhất và máy thứ hai khác nhau thế nào?”, “So sánh 3 sản phẩm trên”, “Máy nào pin tốt hơn?”.
- So sánh theo nhu cầu lập trình, học tập, mang đi học, camera, pin… bằng tiêu chí của Recommendation Engine hiện có.
- Hỏi lại khi số lượng không hợp lệ, tên trùng, phiên bản chưa rõ, sản phẩm không tồn tại/bị ẩn/ngừng bán hoặc tham chiếu không xác định. Không tự cắt danh sách dài xuống ba mẫu. Phiên bản chỉ khác màu (cùng giá, cùng thông số) được tự chọn và ghi trong "Điều cần lưu ý"; tên khớp cả "iPhone 17 Pro" và "iPhone 17 Pro Max" chọn đúng mẫu đã gõ.
- Lưu các sản phẩm đang cần làm rõ phiên bản vào slots nội bộ. Câu trả lời tiếp theo, ví dụ “Chọn bản 16GB / 512GB”, tiếp tục so sánh được cả khi service được khởi tạo lại.
- Giữ đúng SKU đã giới thiệu kể cả khi hết hàng; không đổi sang SKU khác còn hàng hoặc đắt hơn.
- Chuẩn hóa thông số lồng nhau và các tên RAM, CPU, SSD/bộ nhớ, GPU, màn hình, pin, camera, khối lượng…; dữ liệu bộ nhớ của SKU được ưu tiên hơn thông số chung. Thiếu dữ liệu hiển thị “Chưa có dữ liệu”.
- Lưu snapshot trong metadata của tin nhắn Text hiện có; bảng xuất hiện lại khi tải lịch sử, refresh hoặc khôi phục request.
- Khi backend đã xác định đủ 2–3 SKU, lượt so sánh hoàn tất bằng bảng và nhận xét có căn cứ mà không gọi Gemini (giống câu hỏi làm rõ), nên không phụ thuộc timeout/429 của Gemini. Khi chỉ Gemini chọn được sản phẩm, lỗi Gemini làm lượt thất bại như các câu hỏi khác, không dựng bảng đoán. Giữ cooldown khi hết quota và kiểm tra cancellation/lease trước khi ghi kết quả.
- Bảng có vùng cuộn ngang riêng, truy cập được bằng bàn phím, chạy trong chat thường và phóng to. Nội dung được render bằng React text; ảnh chỉ nhận URL HTTP(S)/đường dẫn nội bộ.

## Các file tạo mới

| File | Vai trò |
|---|---|
| `backend/app/schemas/ai_comparison.py` | Contract snapshot có version, kiểm tra 2–3 SKU khác nhau và số ô khớp số cột |
| `backend/app/services/ai_comparison.py` | Chuẩn hóa thông số theo SKU; gọi `assess`/`evaluate` từ Recommendation Engine; dựng khác biệt, điểm mạnh, hạn chế và đề xuất |
| `backend/tests/test_ai_comparison.py` | 63 test Smart Compare trên SQLite độc lập và API FastAPI với model giả lập |
| `frontend/src/customer/components/AiComparison.jsx` | Bảng so sánh và phần AI PHÂN TÍCH |
| `frontend/src/customer/components/ai-comparison.js` | Kiểm tra metadata trước khi render, dùng chung với thread |
| `frontend/src/customer/components/AiComparison.test.jsx` | Test component, an toàn nội dung, dữ liệu lỗi và fallback |
| `frontend/src/test/ai-comparison.js` | Fixture giao diện dùng chung trong test |
| `docs/stage10-ai-smart-compare.md` | Báo cáo và hướng dẫn kiểm tra này |

## Các file chỉnh sửa

| File | Thay đổi |
|---|---|
| `backend/app/services/ai_intent.py` | Tham chiếu “vừa giới thiệu”, giới hạn số lượng, câu hỏi so sánh chưa có lịch sử, lưu/khôi phục lựa chọn phiên bản đang chờ |
| `backend/app/services/ai_tools.py` | Tra cứu tên rõ ràng bằng ProductService; khóa SKU tham chiếu; tạo bảng từ dữ liệu hiện tại; kiểm tra lại trước khi lưu |
| `backend/app/services/ai_chat.py` | Trả lời so sánh đã xác minh không qua Gemini, cooldown, lưu snapshot vào metadata |
| `backend/app/schemas/ai_chat.py` | Compare chỉ nhận 2–3 lựa chọn; cho phép hai SKU khác nhau của cùng một sản phẩm |
| `backend/app/schemas/chat.py` | Chỉ công khai snapshot hợp lệ của tin AI; giữ ẩn lease, usage, slots và tham chiếu nội bộ |
| `backend/app/prompts/vietech_ai_protocol.py` | Quy ước Smart Compare, đúng SKU và giới hạn ba sản phẩm |
| `backend/tests/test_ai_grounded.py` | Đổi câu hỏi của hai test lỗi tool sang đọc thông tin để tiếp tục kiểm tra lỗi tool, tránh nhánh làm rõ số lượng mới |
| `frontend/src/customer/components/AiChatThread.jsx` | Render bảng trong tin nhắn hiện tại; không lặp thêm các thẻ sản phẩm khi đã có bảng hợp lệ |
| `frontend/src/customer/components/AiChat.css` | Bố cục bảng, phân tích, cột tiêu chí cố định và vùng cuộn nội bộ |
| `frontend/src/customer/components/AiChat.test.jsx` | Test response có bảng, không lặp thẻ, tải lại hội thoại không tạo request AI mới |

Không sửa Recommendation Engine, cơ chế render văn bản AI, hook retry/recovery, API route, cấu trúc bảng database hay nghiệp vụ giỏ hàng/thanh toán/kho/đơn hàng. Không thêm dependency, migration hoặc trang `/so-sanh`.

## Luồng dữ liệu

1. Frontend gửi câu hỏi qua endpoint AI hiện có cùng `ClientRequestId`.
2. Backend đọc slots và `ProductReferences` đã lưu, phân tích ý định và số lượng.
3. `AiTools` giải quyết tên/tham chiếu qua ProductService. Tên hoặc phiên bản chưa rõ dẫn tới câu hỏi làm rõ, không tự chọn.
4. ProductService lấy dữ liệu công khai và giá sau khuyến mãi tự động qua PricingService hiện có. Bộ chuẩn hóa dùng đúng bộ nhớ/màu của SKU được chọn.
5. `assess` và `evaluate` quyết định điểm, bằng chứng đạt/chưa đạt và mức đầy đủ dữ liệu. Các cột giữ thứ tự khách đang tham chiếu.
6. Bảng và nhận xét cuối luôn được dựng bằng dữ liệu backend; văn bản so sánh tự do từ Gemini không được hiển thị. Vì vậy khi backend đã xác định đủ SKU ở bước 3, lượt hoàn tất không gọi Gemini. Gemini chỉ được gọi khi cần chọn sản phẩm bằng công cụ tra cứu (ví dụ “So sánh 2 mẫu laptop ASUS mới nhất”); lựa chọn đó phải là sản phẩm/phiên bản đã tra cứu trong lượt.
7. Trước khi hoàn tất, backend kiểm tra lại trạng thái request, sản phẩm, SKU, giá và tồn kho. Tin AI lưu `Metadata.Comparison` và tham chiếu nội bộ trong transaction hiện tại.
8. Response, replay cùng UUID, GET trạng thái và GET lịch sử đều dùng snapshot đã lưu. Frontend hiển thị bằng `AiComparison`.

Snapshot là ghi nhận tại thời điểm tư vấn; tải lại lịch sử không tự thay giá hoặc điểm cũ. Câu hỏi mới sẽ đọc dữ liệu hiện tại.

## Sửa sau nghiệm thu 29/10/2026

Trong lần chạy Gemini thật (`output/final-data-acceptance/`), 10/14 ca Smart Compare dừng ở câu hỏi lại. Đã sửa như sau; regression test nằm trong `backend/tests/test_ai_acceptance_fixes.py`:

- **C01, SC04.** "iPhone 17 Pro" khớp cả "iPhone 17 Pro 256GB" và "iPhone 17 Pro Max 512GB". `closest_products` (`ai_comparison.py`) loại tên có từ dòng máy không được gõ ngay sau tên khách gõ (Max, Plus, Ultra, Mini, Lite, Air…).
- **C02, SC01.** "MacBook Air M5 13 inch 16GB 512GB" khớp cả bản tiêu chuẩn và bản "… Sạc 70W". Nay chọn tên không có phụ kiện thêm. Nếu hai cấu hình thật sự khác nhau (C03: hai mã HP Victus 15) thì vẫn hỏi lại.
- **C04.** "So sánh camera của Xiaomi 17T Pro và …": cụm "camera/pin/màn hình/hiệu năng… của" không còn bị coi là tên sản phẩm.
- **C05–C07, SC02.** Câu hỏi chọn màu khi các phiên bản có cùng thông số và giá. Nay `colour_only_default` tự chọn phiên bản: ưu tiên còn hàng, sau đó theo tên. Phiên bản được chọn ghi trong `Caveats`. Nếu màu có giá khác nhau thì vẫn hỏi lại.
- Một kết quả tìm kiếm khớp đúng tên sản phẩm được dùng ngay, kể cả khi tìm kiếm trả nhiều kết quả khác.

## Rà soát 28/10/2026

Lỗi đã sửa, mỗi lỗi có test hồi quy trong `backend/tests/test_ai_comparison.py`:

- Hai sản phẩm cùng cần chọn phiên bản: câu trả lời “Chọn bản …” không bao giờ được nhận, khách bị hỏi lại cùng câu mãi. Nay câu trả lời áp cho sản phẩm vừa được hỏi.
- Sau câu hỏi chọn phiên bản, yêu cầu mới như “Tư vấn laptop RAM 16GB dưới 25 triệu” bị coi là câu trả lời phiên bản. Nay chỉ câu trả lời không phải yêu cầu mua sắm/ưu đãi/chính sách mới mới tiếp tục so sánh.
- “So sánh giữa A và B”, “So sánh giúp mình A với B”, “A và B khác nhau thế nào?”, “A với B thì nên chọn máy nào?”, “Giữa A và B, máy nào tốt hơn?” trả lời sai rằng sản phẩm không có tại VieTech.
- Gemini chọn so sánh hợp lệ (ví dụ “Máy thứ hai có gì hơn …”) bị thay bằng tham chiếu một sản phẩm của backend rồi hỏi lại “chọn từ 2 đến 3 sản phẩm”.
- Hàng “Tần số quét” hiển thị cả “Tính năng màn hình” không có Hz (Dynamic Island, HDR, ppi…). Nay chỉ lấy giá trị Hz.
- “16GB” và “16 GB” bị liệt kê là khác biệt.
- So sánh đã xác minh vẫn gọi Gemini một lượt rồi bỏ toàn bộ kết quả; thêm độ trễ, tốn quota và tạo trạng thái “diễn giải AI chưa hoàn tất” cho phần không bao giờ hiển thị.
- Câu hỏi xin một nhóm mới (“So sánh 2 mẫu laptop ASUS rẻ nhất”: hãng không có trong danh sách vừa xem, thứ tự giá, ngân sách hoặc danh mục khác) bị so sánh lại danh sách cũ (phát hiện khi chạy dữ liệu thật: trả bảng iPhone 16e/HONOR). Nay chỉ câu không nêu tiêu chí mới như “Máy nào pin tốt hơn?” mới dùng danh sách vừa xem.
- Giao diện: trong cửa sổ chat 460px, bảng hai sản phẩm bị ép rộng tối thiểu 560px nên sản phẩm thứ hai bị che. Nay độ rộng tối thiểu theo số cột: hai sản phẩm vừa khung (Chrome đo bảng 360px = vùng hiển thị 360px), ba sản phẩm hoặc màn hình điện thoại vẫn cuộn ngang trong bảng; dòng “Vuốt hoặc cuộn ngang” chỉ hiện khi bảng thực sự rộng hơn tin nhắn.

Kết quả chạy lại: toàn bộ `test_ai*.py` + `test_chat*.py` 440 passed; toàn bộ backend 1974 passed, 138 skipped, 3 failed ngoài phạm vi Smart Compare (`test_api_matrix.py` thiếu test thành công của nhóm return; hai test 503 của `test_internal_routes.py` chưa nhận trường `code`). Frontend: 4 file AI chat 46 passed; lint exit 0 (hai cảnh báo cũ); build thành công; toàn bộ Vitest (chia admin/còn lại, hai worker) 1339/1344 passed. Lỗi tái hiện khi chạy riêng chỉ có `PurchasesPage` và `HomePage` như bên dưới; `ReturnsPage`, `WarrantiesPage` và test marker phiên của `AiChat.test.jsx` chỉ lỗi khi chạy song song và qua khi chạy riêng.

Chạy thật 28/10/2026 trên database PostgreSQL dùng chung và Gemini `gemini-3.5-flash-lite`, trong một transaction bị rollback (khách hàng/hội thoại tạm; kiểm tra sau rollback còn 0 dòng):

- Tư vấn 2 laptop dưới 30 triệu (Gemini): 23,7–35 giây. So sánh từ danh sách, “nên mua máy nào”, “Máy nào pin tốt hơn?”, so sánh iPhone theo tên và câu “… khác nhau thế nào?”: 2–12 giây, không gọi Gemini. Giá và tồn kho mọi cột khớp đọc độc lập từ database; hỏi màu từng máy rồi ra bảng đúng; tải lại lịch sử hiện 6/6 bảng, không lộ dữ liệu nội bộ.
- Luồng Gemini tự chọn sản phẩm chưa xác minh được trên dữ liệu thật: Gemini trả HTTP 503 ở cả ba lần thử; hệ thống báo “AI tạm thời không khả dụng”, không dựng bảng đoán. Luồng này có test giả lập.
- Đã sửa sau lượt chạy: đề xuất “phù hợp hơn” từng liệt kê RAM/SSD/CPU giống nhau giữa hai máy, trong khi yếu tố quyết định là nhóm “Laptop lập trình” và giá trong ngân sách (ASUS VivoBook 14 so với MSI Cyborg 15). Nay chỉ nêu tiêu chí mẫu được chọn thực sự hơn, giá thấp hơn trong ngân sách khi có, và điểm mạnh hơn của mẫu còn lại. Dựng lại trên dữ liệu thật (chỉ đọc): “ASUS … phù hợp hơn theo tiêu chí của VieTech nhờ: thuộc nhóm Laptop lập trình; giá thấp hơn, trong ngân sách 30.000.000 đ. MSI … mạnh hơn về: CPU Intel Core i7-13620H (nhóm hiệu năng cao); pin 53,5 Wh; GPU NVIDIA GeForce RTX 3050 4GB.”

## Kết quả kiểm thử thực tế (bàn giao ban đầu)

| Kiểm tra | Kết quả |
|---|---|
| Toàn bộ các file `test_ai*.py` và `test_chat*.py` | **421 passed, 7 skipped, 45 subtests passed** |
| Trong đó test Smart Compare mới | **44 test** |
| `AiComparison`, `AiChat`, `AiChatText`, `CustomerChat` | **46 passed**, 4 file |
| Toàn bộ frontend, `npm test -- --maxWorkers=2` | **1.341 passed, 3 failed** / 1.344 test, 103 file |
| Chạy riêng ba bộ frontend lỗi cùng các test AI, một worker | **108 passed, 2 failed**; lỗi ReturnsPage không tái hiện |
| `npm run lint` | Exit 0; hai cảnh báo tại `AdminTable.jsx` và `useAdminQuery.js`, là các file không chỉnh sửa |
| `npm run build` | Thành công, 481 module; cảnh báo chunk lớn hơn 500 kB |
| Chrome headless: 320×640, 390×844, 1440×1000; bảng hai/ba cột, chat thường/phóng to | **6/6 bố cục qua**, không tràn trang/panel/log; bảng cuộn ngang khi cần; không có JavaScript exception |
| `git diff --check` | Thành công |

Hai lỗi frontend còn tái hiện:

- `src/admin/pages/PurchasesPage.test.jsx`: `actual receiving requires real serials and records a partial receipt without changing the ordered quantity` — test không tìm thấy `role=alert` trong dialog nhận hàng.
- `src/customer/pages/HomePage.test.jsx`: `choosing a menu price range applies it to all category results` — test không tìm thấy nút “Xem theo giá” sau chuyển trang.

Lượt chạy toàn bộ còn ghi nhận lỗi `ReturnsPage.test.jsx` ở test lọc theo tìm kiếm/ngày; chạy riêng bộ này thành công. Các module nghiệp vụ đó không được chỉnh sửa trong đợt Smart Compare.

Lượt chạy frontend và build song song ban đầu hết bộ nhớ khi Vitest tạo nhiều worker. Build chạy lại thành công; test toàn bộ được chạy lại với hai worker. Ba lỗi quyền thư mục Temp của pytest được khắc phục khi chạy lại với `--basetemp` riêng trong workspace. Không coi các lượt chạy lỗi này là thành công.

Kiểm thử backend dùng SQLite độc lập và Gemini giả lập. Bảy test PostgreSQL bị skip theo cơ chế opt-in an toàn; không kết nối hoặc sửa database production và không gọi Gemini thật. Cảnh báo backend đến từ deprecation của thư viện Starlette/httpx và google-genai. Repository không cấu hình lệnh lint backend riêng.

Ảnh và kết quả đo bố cục nằm tại `output/smart-compare/`, gồm `responsive-results.json`, `desktop-expanded-3.png`, `desktop-analysis.png`, `mobile-normal-3.png`. Đây là fixture cục bộ dùng component thật và API giả lập, không phải một trang tính năng mới của website.

## Cập nhật phần phân tích ngày 30/10/2026

Đã đổi cách trình bày theo tên từng sản phẩm, tách dòng camera, bỏ tiêu chí màu mặc định và bổ sung phân tích khác biệt gắn với nhu cầu sử dụng. Chi tiết phạm vi, nguồn đối chiếu và kết quả kiểm tra tại [So sánh sản phẩm chi tiết](ai-comparison-detail-20261030.md). Kết quả kiểm thử bàn giao ban đầu ở trên được giữ làm mốc lịch sử.

## Giới hạn còn lại

- Tên mơ hồ hoặc nhiều SKU vẫn cần khách làm rõ. Không tự chọn bản rẻ nhất hay bản còn hàng thay cho SKU đã nêu.
- Điểm phù hợp là tiêu chí tư vấn hiện có của VieTech, không phải benchmark. Chỉ đề xuất một mẫu trội hơn khi dữ liệu đủ, các mẫu cùng nhóm và chênh lệch có ý nghĩa; không cam kết chạy mượt Android Studio hoặc ứng dụng cụ thể.
- Không có số liệu thời lượng pin/chất lượng ảnh thực nghiệm thì không suy ra từ mAh/MP.
- Phần nhận xét so sánh hiện dùng câu và bằng chứng backend xác định. Không hiển thị diễn giải so sánh tự do của Gemini để tránh kết luận định tính không có căn cứ.
- Tên trực tiếp ngoài các cấu trúc có dấu phân cách rõ ràng có thể cần Gemini dùng công cụ hiện có hoặc hỏi lại. So sánh dựa trên sản phẩm thực sự có trong catalog; không bảo đảm các model ví dụ đang được bán.
- Chưa kiểm tra Gemini thật hoặc database PostgreSQL đang dùng bởi website. Toàn bộ frontend chưa xanh do các lỗi nêu trên.

## Chạy website và kiểm tra thủ công

Dùng cấu hình môi trường đã có, không chạy migration. Từ thư mục repository, mở hai terminal:

```powershell
# Terminal 1 — backend
.\.venv\Scripts\python.exe backend\scripts\run_dev.py
```

```powershell
# Terminal 2 — frontend
npm --prefix frontend run dev
```

Vào `http://127.0.0.1:5173`, đăng nhập tài khoản Customer rồi mở cửa sổ AI Chat hiện tại.

1. Hỏi “Tư vấn giúp tôi 2 laptop dưới 20 triệu để học lập trình”.
2. Khi có hai thẻ, hỏi “So sánh 2 laptop vừa giới thiệu”. Kiểm tra đúng SKU, giá, tồn kho và dữ liệu thiếu trong bảng.
3. Hỏi “Tôi học lập trình và mang đi học, trong 2 laptop đó nên mua máy nào?”. Kiểm tra phần điểm mạnh, hạn chế, đề xuất và các điều chưa thể kết luận.
4. Hỏi “Máy nào pin tốt hơn?” và “Máy thứ nhất và máy thứ hai khác nhau thế nào?”.
5. Với tên sản phẩm có thật trong catalog, thử “So sánh [tên A] và [tên B]”. Nếu có nhiều phiên bản, trả lời bằng tên phiên bản đầy đủ theo câu hỏi làm rõ.
6. Xin gợi ý ba mẫu rồi hỏi “So sánh 3 sản phẩm trên”. Thử yêu cầu bốn mẫu để kiểm tra thông báo giới hạn.
7. Refresh trình duyệt, mở lại hội thoại và kiểm tra bảng vẫn còn. Thử phóng to/thu nhỏ chat và màn hình điện thoại; cuộn ngang riêng bên trong bảng.
8. Gửi câu hỏi AI thông thường, xem giá/thông số một mẫu và mở lịch sử để kiểm tra luồng hiện có.

Không sửa dữ liệu production để tạo ca hết hàng, ẩn sản phẩm hoặc hết quota. Các ca đó đã có test cô lập trong `test_ai_comparison.py`.

Lệnh chạy lại test liên quan:

```powershell
Set-Location backend
$aiTestPaths = rg --files tests -g 'test_ai*.py' -g 'test_chat*.py'
..\.venv\Scripts\python.exe -m pytest @aiTestPaths -q
```

```powershell
Set-Location frontend
npm test -- src/customer/components/AiComparison.test.jsx src/customer/components/AiChat.test.jsx src/customer/components/AiChatText.test.jsx src/customer/components/CustomerChat.test.jsx --maxWorkers=2
npm run lint
npm run build
```

Nếu pytest không có quyền thư mục Temp trên Windows, truyền `--basetemp` tới một thư mục kiểm thử mới trong `output/`; không dùng thư mục có dữ liệu cần giữ vì pytest quản lý nội dung thư mục đó.
