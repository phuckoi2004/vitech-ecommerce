# Bước 10.4 — Chat AI trên website

Đã nối khung “Chat với AI” vào API ngày 22/10/2026. Model vẫn do `GEMINI_MODEL` tại backend quyết định; frontend không chứa khóa Gemini và không gọi Gemini trực tiếp.

Cập nhật thiết kế theo yêu cầu: **không có nút hoặc luồng chuyển từ AI sang nhân viên**. Khung AI dùng màu xanh `accent-500`, chữ `ink-900`, nền/border của VieTech hiện có. Khung chat nhân viên ở website vẫn là tính năng độc lập.

## Thiết kế hiện tại

- Khung nổi 460px trên máy tính, có thể mở rộng tới 960px; điện thoại tự khớp chiều rộng màn hình. Không dùng thanh màu lớn và dãy nút chức năng chiếm chỗ phía trên tin nhắn.
- Thanh đầu gọn với biểu tượng lịch sử, tạo hội thoại, mở rộng/thu nhỏ và đóng cửa sổ.
- Màn hình mới có lời chào và bốn gợi ý. Bấm gợi ý chỉ điền vào ô nhập để khách chỉnh sửa, không tự gửi.
- Tin khách nằm bên phải trên nền nhẹ; câu trả lời AI có avatar, nội dung thoáng và thẻ sản phẩm. Ô nhập bo tròn, tự tăng chiều cao, nút gửi hình mũi tên; trạng thái chờ dùng ba chấm.
- Lịch sử mở từ bên trái, nhóm Hôm nay/Hôm qua/Trước đó. API `GET /conversations?mode=AI` lọc và phân trang đúng các phiên AI; `Title` lấy tối đa 90 ký tự từ tin Text đầu tiên của khách, không lấy từ câu trả lời AI. Phiên chưa có câu hỏi dùng nhãn mặc định.
- Title được truy vấn theo danh sách ID đã qua kiểm tra quyền, bằng một truy vấn cho cả trang; không tải toàn bộ tin nhắn của từng hội thoại. Không thêm cột hoặc migration cho tiêu đề.
- Mở/đóng lịch sử giữ nguyên bản nháp và request đang gửi. Escape trong lịch sử chỉ đóng lịch sử; không đóng cả panel.

Mẫu bố trí tham khảo: nút New Chat và hội thoại trong sidebar của [ChatGPT](https://help.openai.com/en/articles/9125172-the-chatgpt-home-page), lịch sử ở cột trái của [Claude](https://support.claude.com/en/articles/8230524-delete-or-rename-a-conversation), menu mở bảng lịch sử của [Gemini](https://support.google.com/gemini/answer/13666746?hl=en). Đây là các mẫu tương tác tham khảo; giao diện ứng dụng dùng token màu VieTech.

## Chạy và thử

1. Kiểm tra cấu hình Gemini theo [10.1](stage10-gemini-integration-guide.md), API theo [10.2](stage10-ai-chat.md), và dữ liệu catalog theo [10.3](stage10-ai-tools.md).
2. Migration chống trùng `d7a1e5c9b304` của 10.2 đã áp dụng lên database phát triển ngày 22/10/2026 (xem [10.2](stage10-ai-chat.md#migration)). Với database khác, kiểm tra revision và áp dụng trước khi dùng chat AI.
3. Khởi động backend và frontend trong hai terminal:

```powershell
# Terminal 1
Set-Location E:\vitech-ecommerce\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

```powershell
# Terminal 2
Set-Location E:\vitech-ecommerce\frontend
npm run dev
```

4. Mở `http://127.0.0.1:5173`, đăng nhập tài khoản Customer và chọn nút “Chat với AI” ở góc dưới bên phải. Khách chưa đăng nhập có liên kết đăng nhập, giữ đường dẫn quay lại trang đang xem; sau khi quay lại, chọn nút AI để tiếp tục.
5. Hỏi “Laptop ASUS dưới 20 triệu để học lập trình”, điều chỉnh theo sản phẩm thật trong catalog. Kết quả có văn bản và tối đa ba thẻ sản phẩm, giá của biến thể, ảnh và liên kết trang chi tiết.
6. Hỏi tiếp “Máy thứ hai có thông số gì?”. Đóng khung chat, mở lại, kiểm tra tin nhắn vẫn còn. Biểu tượng lịch sử ở đầu khung có nhãn truy cập “Lịch sử AI”; chọn để xem phiên trước. Phiên đã đóng chỉ cho đọc.
7. Biểu tượng tạo hội thoại ở đầu khung có nhãn “Hội thoại mới”; thao tác đóng phiên AI đang mở rồi tạo phiên AI mới. Mở rộng khung bằng biểu tượng bốn góc. Nếu đã có Staff Open, chỉ khi khách chọn rõ “Kết thúc phiên hiện tại và mở AI” mới đóng phiên đó để mở AI; không có thao tác từ AI chuyển sang Staff.

Giá/tồn kho trên thẻ là snapshot khi tư vấn; trang sản phẩm là nơi kiểm tra thông tin hiện tại. Trước ô nhập có thông báo nội dung chat được gửi tới Google Gemini. [Bước 10.5](stage10-ai-personalization.md) cá nhân hóa tự động ở backend từ danh sách yêu thích và đơn đã giao; giao diện không có nút cá nhân hóa, chỉ thêm câu ghi chú dưới ô nhập.

## Gửi, chờ và phục hồi

- Câu hỏi tối đa 1.000 ký tự. Enter gửi, Shift + Enter xuống dòng; Enter đang gõ bộ chữ IME không gửi. Ngay khi gửi, ô nhập được xóa và câu hỏi xuất hiện trong lịch sử đang chờ. Khi có lượt chưa xử lý xong, ô nhập bị khóa để tránh gửi chồng.
- Nút mũi tên chuyển thành hình vuông có nhãn “Dừng trả lời AI” trong lúc gửi/chờ/kiểm tra trạng thái. Bấm nút sẽ ngắt HTTP đang chờ ở trình duyệt và gửi lệnh dừng tới backend. Sau `Cancelled` hoặc `Completed`, nút trở lại mũi tên và ô nhập được mở. Phản hồi POST/GET cũ đến muộn không được cập nhật tin nhắn, xóa bản nháp mới hoặc phục hồi lượt đã dừng.
- Nếu chưa xác nhận được lệnh dừng do mất mạng, giữ marker `cancelRequested` và cho “Thử dừng lại”; không tự gửi lại câu hỏi. Đóng/mở panel khi đang dừng sẽ tiếp tục lệnh dừng cùng UUID. Câu hỏi đã dừng vẫn có trong lịch sử với ghi chú “Đã dừng trả lời.”.
- Mỗi câu hỏi tạo một `crypto.randomUUID()`. Thử lại giữ nguyên UUID và nội dung ban đầu; trước khi POST lại luôn GET trạng thái, nhận Completed thì chỉ hiển thị kết quả.
- Khi request Pending, giao diện đọc trạng thái mỗi khoảng hai giây. Mỗi HTTP request chờ tối đa 75 giây, dài hơn deadline backend mặc định 60 giây; timeout sẽ kiểm tra trạng thái thay vì tự gửi thêm câu hỏi.
- Lượt chưa xong được giữ trong `sessionStorage`, với khóa riêng theo customer và conversation. Đóng panel/tải lại trang trong cùng tab vẫn kiểm tra được lượt cũ. Marker được xóa sau Completed/Cancelled hoặc khi khách bỏ qua một lượt đã xác nhận thất bại. Nếu storage bị chặn, metadata trong lịch sử server vẫn phục hồi được request đã được tiếp nhận.
- Dữ liệu trình duyệt chỉ hỗ trợ phục hồi; backend vẫn kiểm tra quyền sở hữu. Không hiển thị marker của customer khác. Bản nháp dùng cơ chế hiện có, được xóa khi đổi tài khoản.
- Lỗi quota/rate limit có `Retry-After` sẽ hiển thị đếm ngược và khóa nút thử lại. Với lỗi chưa biết kết quả, chỉ cho kiểm tra/thử lại; với Failed/không tìm thấy request, có thể bỏ qua để hỏi câu khác. Hết số lần retry có thể bỏ qua, không tiếp tục POST cùng UUID.
- Tin nhắn ghép theo `MessageId`; thẻ gắn với văn bản bằng `AiAnswerMessageId` và sắp theo `Rank`. Nội dung được render bằng React text, không đưa câu trả lời vào HTML thô.

## Tệp chính

- `frontend/src/customer/components/CustomerChat.jsx`: mở/đóng panel AI và nhân viên.
- `AiChat.jsx`: đăng nhập, mở phiên AI, lịch sử và thanh điều khiển.
- `AiChatThread.jsx`: gửi câu hỏi, trạng thái, retry và hiển thị tin/thẻ.
- `ai-chat-state.js`: marker phục hồi theo tài khoản/phiên và ghép tin chống trùng.
- `AiChat.css`: bố cục panel và thẻ, hỗ trợ màn hình hẹp.
- `AiChatIcon.jsx`: bộ biểu tượng SVG cùng nét cho các thao tác chat.

## Kiểm thử

Chạy tại `frontend`:

```powershell
npm run lint
npm test -- --configLoader runner --maxWorkers 1 --pool forks
npm run build -- --configLoader runner
```

`--configLoader runner` là cách tránh lỗi Windows `spawn EPERM`/nạp native dependency ở trình bundle cấu hình Vite trong môi trường kiểm tra này; không cần thay dependency hoặc cấu hình ứng dụng.

Test AI dùng HTTP giả lập, không gọi Gemini/database dùng chung. Các ca gồm đăng nhập, tạo/reuse AI, Staff đang mở, gửi UUID, Pending nhiều vòng, thử lại sau mất mạng, timeout, phục hồi marker theo customer, quota/cooldown, HTML dạng văn bản, thẻ/giá/thứ tự và lịch sử phiên đóng. Kiểm thử tự động này chưa thay cho chạy xuyên suốt trình duyệt → backend → Gemini trên database đã migrate.

Kết quả trước lần thiết kế lại ngày 22/10/2026: **139/139 test trong 5 tệp đạt**, gồm 16 test AI, 43 test ShoppingRoutes, 26 test ProductPage, 28 test ProductReviews và 26 test CouponsPage. Lệnh kiểm tra nhóm này:

```powershell
npm test -- src/customer/components/AiChat.test.jsx src/customer/pages/ShoppingRoutes.test.jsx src/customer/pages/ProductPage.test.jsx src/customer/components/product/ProductReviews.test.jsx src/admin/pages/CouponsPage.test.jsx --configLoader runner --maxWorkers 1 --pool forks --testTimeout 15000
```

`npm run lint` đạt, còn hai cảnh báo có sẵn trong admin (`AdminTable.jsx`, `useAdminQuery.js`). Build production với `--configLoader runner` đạt, có cảnh báo chunk trên 500 kB. Báo cáo JSON local: `output/stage10-frontend-regression.json` ở gốc dự án.

Lượt chạy toàn bộ 92 tệp song song đạt 91 tệp nhưng worker của CouponsPage hết bộ nhớ; một lượt chạy tuần tự cũng gặp timeout ở ProductReviews. Hai tệp này đã được chạy lại đầy đủ và đạt trong nhóm 139 test phía trên. Không coi các lượt bị lỗi tài nguyên/thời gian đó là toàn bộ suite đạt.

Sau thiết kế lại: **87/87 test frontend đạt** (18 AI, 43 ShoppingRoutes, 26 ProductPage), **129 test backend và 47 subtest đạt** trong nhóm chat/AI/quyền xem. Lint đạt với hai cảnh báo admin có sẵn; build production đạt với cảnh báo chunk trên 500 kB. Báo cáo frontend mới ở `output/stage10-ai-redesign-tests.json`.

Đã kiểm tra bằng Edge headless với dữ liệu giả lập trong 8 trạng thái: màn hình chào, tin nhắn/thẻ, lịch sử và mở rộng trên desktop 1440×1000; màn hình chào, tin nhắn, lịch sử trên điện thoại 390×844; màn hình hẹp 320×640. Không tràn ngang, ô nhập nằm trong khung, không có nút chuyển nhân viên; không có lỗi JavaScript. Đây là kiểm tra trực quan component thật với HTTP giả lập, không gọi tài khoản/database/Gemini thật.

Ảnh local để xem thiết kế: [khung chat](../output/ai-chat-preview.png), [lịch sử](../output/ai-chat-history-preview.png), [điện thoại](../output/ai-chat-mobile-empty.png), [mở rộng](../output/ai-chat-desktop-expanded.png). Kết quả đo layout ở `output/ai-chat-visual-checks.json`. Các tệp trong `output` được Git bỏ qua.

Sau khi chuyển Gemini và sửa hồi quy bản nháp: **90/90 test** đạt (20 AI, 44 ShoppingRoutes, 26 ProductPage). Callback cập nhật/chuyển bản nháp ổn định trong cùng phiên tài khoản, nên gõ hoặc xóa bản nháp không mở lại hội thoại; callback của tài khoản đã đăng xuất vẫn bị bỏ qua. Lint không có lỗi, còn hai cảnh báo admin nêu trên. Production build đạt, còn cảnh báo chunk trên 500 kB. Website mặc định dùng Gemini 3.5 Flash-Lite; kết nối thật và luồng công cụ được xác minh riêng ở [10.7](stage10-ai-evaluation.md).
