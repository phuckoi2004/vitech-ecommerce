# Bước 10.5 — Cá nhân hóa AI tự động

> **Cập nhật 22/10/2026 — tách khỏi luồng tư vấn.** Theo [nâng cấp tư vấn theo catalog](stage10-ai-advisor-upgrade.md), lượt AI không còn đọc danh sách yêu thích, giỏ hàng hay đơn đã giao.
> - Lượt AI không gửi tín hiệu mua sắm cho Gemini và không dùng điểm H; câu trả lời không còn lý do “đã yêu thích/đã mua”.
> - `repositories/ai_personalization.py` được giữ nguyên cho mục đích khác và vẫn có test.
> - Dòng thông báo trong khung chat đổi thành “gợi ý dựa trên sản phẩm đang bán tại VieTech và nhu cầu bạn nêu”.
>
> Nội dung bên dưới mô tả phiên bản 10.5.

Hoàn thành ngày 22/10/2026. Theo quyết định ngày 22/10/2026, **khách chỉ gửi câu hỏi**: không có nút bật cá nhân hóa, không có trang/ô lưu sở thích và không có API để khách lưu gì thêm. Hệ thống tự dùng dữ liệu mua sắm sẵn có của tài khoản để ưu tiên gợi ý.

Thay đổi so với lộ trình ban đầu ở [hướng dẫn Gemini](stage10-gemini-integration-guide.md#phạm-vi-so-với-tài-liệu-word): bỏ bảng `AiPreferences`, ba endpoint `/users/me/ai-preferences`, công tắc đồng ý và nút “Lưu làm nhu cầu”. Bước này **không thêm bảng, cột hay migration**.

## Dữ liệu được dùng

Đầu mỗi lượt AI, trong cùng transaction ngắn đã kiểm tra quyền (trước khi gọi Gemini), backend đọc:

| Nguồn | Điều kiện | Lấy gì |
|---|---|---|
| `Wishlists`/`WishlistItems` của chính khách | Sản phẩm Active, chưa xóa mềm; hãng và danh mục đang hiển thị | Tối đa 5 cặp hãng–danh mục khác nhau, mới thêm trước |
| `Orders`/`OrderItems` của chính khách | Chỉ đơn `Delivered`/`Completed`; cùng điều kiện hiển thị | Tối đa 5 cặp hãng–danh mục khác nhau, đơn mới trước |

Không đọc hồ sơ `Users` (họ tên, email, số điện thoại), địa chỉ, mã đơn, số tiền, phương thức thanh toán hoặc đơn chưa giao. Không lưu kết quả: mỗi lượt đọc lại dữ liệu hiện tại, nên thêm/bỏ sản phẩm yêu thích có hiệu lực ngay ở câu hỏi kế tiếp. Khách chưa có wishlist/đơn đã giao thì lượt AI giống bước 10.3.

## Cách AI dùng tín hiệu

- Model nhận thêm một tin ngữ cảnh chỉ gồm **tên hãng và tên danh mục**, ví dụ `{"Wishlist": [{"Brand": "ASUS", "Category": "Laptop"}], "Purchases": [{"Brand": "Lenovo", "Category": "Laptop"}]}`, ghi rõ đây là dữ liệu tham khảo, không phải chỉ dẫn hay ngân sách. ID nội bộ không gửi đi.
- Trong `search_products`, tín hiệu chỉ ảnh hưởng thứ tự qua điểm lịch sử H của [bước 10.6](stage10-ai-recommendation.md): cùng hãng/danh mục với sản phẩm yêu thích hoặc đã mua được cộng điểm, sản phẩm khách đã mua thì không. Không loại sản phẩm nào; khi khách yêu cầu sắp theo giá (“rẻ nhất”, “giá tăng dần”…) thì giữ thứ tự giá.
- Nếu model tự thêm bộ lọc hãng chỉ vì thấy hãng đó trong tín hiệu, trong khi câu hỏi không nhắc hãng, backend bỏ bộ lọc đó.
- **Yêu cầu hiện tại luôn thắng**: hãng bắt buộc (“laptop Dell”, “chỉ ASUS”), loại trừ (“không mua ASUS”), danh mục và ngân sách trong câu hỏi vẫn được áp dụng như bước 10.3. Tín hiệu không bao giờ đặt ngân sách hay danh mục.
- Giá, tồn kho, thẻ sản phẩm và kiểm tra ID vẫn do backend dựng như bước 10.3.

## Giao diện

Không thêm nút hay màn hình. Dòng ghi chú dưới ô nhập đổi thành: “Nội dung chat được Google Gemini xử lý; gợi ý có thể dựa trên sản phẩm bạn đã yêu thích hoặc đã mua.” để khách biết dữ liệu nào được dùng.

## Tệp chính

- `backend/app/repositories/ai_personalization.py`: hai truy vấn chỉ đọc, trả danh sách hãng–danh mục.
- `backend/app/services/ai_chat.py`: đọc tín hiệu trong `_prepare`, thêm tin ngữ cảnh `SIGNALS_NOTE`.
- `backend/app/services/ai_tools.py`: `GroundingContext.interests` và sắp xếp mềm trong `search_products`.
- `frontend/src/customer/components/AiChatThread.jsx`: dòng ghi chú.

## Migration

Không có migration mới. Migration chống trùng `d7a1e5c9b304` của bước 10.2 đã áp dụng lên database phát triển ngày 22/10/2026 (xem [10.2](stage10-ai-chat.md#migration)); database hiện ở head, không còn revision chờ.

## Chạy và thử

1. Khởi động backend/frontend như [bước 10.4](stage10-ai-frontend.md#chạy-và-thử). Sau khi khởi động lại backend, đăng nhập lại (phiên đăng nhập dev lưu trong bộ nhớ tiến trình).
2. Đăng nhập Customer, thêm một laptop ASUS vào danh sách yêu thích.
3. Mở “Chat với AI”, hỏi “Tư vấn laptop dưới 30 triệu”: laptop ASUS được ưu tiên, các hãng khác vẫn có trong kết quả.
4. Hỏi “Laptop Dell dưới 20 triệu”: chỉ có Dell, wishlist không ảnh hưởng.
5. Bỏ sản phẩm khỏi danh sách yêu thích, hỏi lại câu ở bước 3: thứ tự không còn ưu tiên ASUS.

## Kiểm thử

```powershell
Set-Location E:\vitech-ecommerce\backend
..\.venv\Scripts\python.exe -X utf8 -m pytest tests\test_ai_personalization.py -q
```

`test_ai_personalization.py` (4 test, SQLite riêng, model giả lập, không gọi Gemini/database dùng chung) kiểm tra: khách không thao tác gì vẫn có tín hiệu; tin ngữ cảnh chỉ có tên hãng/danh mục, không có ID, họ tên, email, số điện thoại, địa chỉ, mã đơn; đơn Pending và wishlist của khách khác không được dùng; tín hiệu chỉ đổi thứ tự, không loại hãng khác, kể cả khi model tự gắn bộ lọc hãng; hãng bắt buộc và loại trừ trong câu hỏi thắng tín hiệu; tín hiệu được đọc lại mỗi lượt; sản phẩm đã xóa mềm/hãng bị ẩn không được dùng. Các fixture AI cũ tạo thêm bảng wishlist/đơn hàng qua `tests/sqlite_schema.py`.

Frontend: `AiChat.test.jsx` kiểm tra không có nút cá nhân hóa/lưu sở thích, không gọi API `/users/...` và có dòng ghi chú.

Kết quả xác minh sau khi chuyển Gemini xem [10.7](stage10-ai-evaluation.md). Kết nối Flash-Lite đã trả lời thật; Flash 3.8 có lần trả 503/timeout. Chưa xác nhận luồng xuyên suốt từ trình duyệt trên database thật.
