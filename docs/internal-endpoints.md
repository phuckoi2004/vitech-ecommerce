# VieTech — Endpoint nội bộ (dự kiến, CHƯA triển khai)

Tài liệu kỹ thuật mô tả hợp đồng dự kiến cho endpoint nội bộ do cron bên ngoài gọi. Chưa có Router/Auth trong
codebase; phần Service đã có và đã được kiểm thử bằng fake (không có database thật).

## Hết hạn thanh toán QR

| Mục | Dự kiến |
|---|---|
| Use case | `OrderService.expire_unpaid_qr_orders(limit=...)` |
| Phương thức/đường dẫn | `POST /internal/orders/expire-unpaid-qr` (tên chính xác chốt khi xây Router) |
| Bảo vệ | Không dùng JWT người dùng; xác thực bằng bí mật riêng cho cron (header), lấy từ biến môi trường, so sánh thời gian hằng; không ghi bí mật vào log. Chỉ mở trong mạng nội bộ nếu hạ tầng cho phép. |
| Đầu vào | `limit` (số nguyên > 0, mặc định 100) |
| Đầu ra | Số đơn đã hủy trong lần chạy |
| Quy tắc | Chỉ đơn `Pending`, `PaymentStatus` Pending/Failed, phương thức khác COD, `OrderedAt + 15 phút <= now` (UTC). Mỗi đơn một transaction; khóa đơn và kiểm tra lại; hoàn tồn kho/coupon đúng một lần; hủy giao dịch QR đang chờ. |
| Gọi lặp / chồng nhau | An toàn: đơn đã hủy hoặc đã thanh toán bị bỏ qua sau khi khóa. |
| Lỗi | Lỗi ở một đơn làm dừng lần chạy (các đơn trước đã commit); cron lần sau chạy tiếp. |

Callback thanh toán thành công đến sau khi đơn đã hết hạn: ghi nhận tiền, mở đối soát
`PaymentAfterCancellation`, thông báo Staff/Admin hoàn thủ công (`PaymentService.handle_payment_callback`).

## Webhook SePay (đã có router, CHƯA đăng ký trong app/main.py)

| Mục | Hợp đồng |
|---|---|
| Router | `app/routers/webhooks.py` → `POST /webhooks/sepay` (chỉ POST) |
| Xác thực | HMAC-SHA256 theo tài liệu SePay: `X-SePay-Timestamp` (Unix giây), `X-SePay-Signature: sha256=<hex>` của `"{timestamp}.{raw_body}"`; lệch tối đa 300 giây; so sánh hằng thời gian; dùng bytes gốc của body |
| Cấu hình | `SEPAY_WEBHOOK_SECRET`, `SEPAY_ACCOUNT_NUMBER` (thiếu → 503, không xử lý). QR: `SEPAY_BANK`, `SEPAY_QR_IMAGE_URL`, `SEPAY_PAYMENT_CODE_PREFIX`, `SEPAY_PAYMENT_CODE_LENGTH` |
| Body | JSON (cấu hình SePay phải chọn `application/json`) |
| Phản hồi | `200 {"success": true}` khi sự kiện đã lưu và xử lý xong (kể cả trùng, sai số tiền, không khớp đơn — đã vào đối soát). `401` sai chữ ký/timestamp, `400` payload sai, `503` thiếu cấu hình, `500` lỗi lưu/xử lý → SePay gửi lại |
| Idempotency | `PaymentWebhookEvents` UNIQUE (Provider, AccountNumber, id) |
| Xử lý | `PaymentWebhookService.receive_sepay` → `PaymentService.apply_bank_transfer` (không tự hoàn tiền) |
| Xử lý lại | `PaymentWebhookService.process_unprocessed()` cho sự kiện còn `Received` (dự kiến gọi qua endpoint nội bộ cho cron, chưa có) |

## Cần xác minh trước khi triển khai

- Tần suất cron (đề xuất mỗi 1 phút; độ trễ hủy tối đa ≈ 15 phút + chu kỳ cron).
- Cơ chế lưu/xoay bí mật cron và danh sách IP được phép.
