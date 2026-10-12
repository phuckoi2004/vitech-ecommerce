# VieTech — Endpoint nội bộ và webhook

Tài liệu kỹ thuật cho các điểm vào máy-với-máy: endpoint nội bộ do cron bên ngoài gọi và webhook SePay. Đã triển khai
ở giai đoạn 6 (`app/routers/internal.py`, `app/routers/webhooks.py`, đăng ký trong `app/main.py`). Không dùng JWT
người dùng; mỗi loại có cơ chế xác thực riêng và tự tắt (503) khi chưa cấu hình.

## Xác thực endpoint nội bộ (`/internal/...`)

| Mục | Quy định |
|---|---|
| Bí mật | Biến môi trường `INTERNAL_CRON_SECRET`, tối thiểu 32 byte, ngẫu nhiên (ví dụ `python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| Gửi kèm | Header `X-Internal-Secret: <bí mật>` |
| So sánh | Thời gian hằng (`hmac.compare_digest`); không ghi bí mật vào log hay phản hồi |
| Chưa cấu hình / bí mật < 32 byte | `503`, không xử lý |
| Thiếu hoặc sai bí mật | `401` |
| Thứ tự kiểm tra | Bí mật được kiểm tra trước mọi thứ khác: người gọi không có bí mật không dò được cấu hình SePay |
| OpenAPI | Ẩn khỏi `/docs`; phản hồi có `Cache-Control: no-store` |
| Mạng | Nên chỉ mở trong mạng nội bộ hoặc giới hạn IP của dịch vụ cron nếu hạ tầng cho phép |

## Hết hạn thanh toán QR

| Mục | Hợp đồng |
|---|---|
| Đường dẫn | `POST /internal/orders/expire-unpaid-qr?limit=100` |
| Use case | `OrderService.expire_unpaid_qr_orders(limit=...)` |
| Đầu vào | `limit` (1–1000, mặc định 100) |
| Đầu ra | `200 {"Processed": <số đơn đã hủy>}` |
| Quy tắc | Chỉ đơn `Pending`, `PaymentStatus` Pending/Failed, phương thức khác COD, `OrderedAt + 15 phút <= now` (UTC). Mỗi đơn một transaction; khóa đơn và kiểm tra lại; hoàn tồn kho/coupon đúng một lần; hủy giao dịch QR đang chờ. |
| Gọi lặp / chồng nhau | An toàn: đơn đã hủy hoặc đã thanh toán bị bỏ qua sau khi khóa. |
| Lỗi | Lỗi ở một đơn làm dừng lần chạy (các đơn trước đã commit); cron lần sau chạy tiếp. |

Callback thanh toán thành công đến sau khi đơn đã hết hạn: ghi nhận tiền, mở đối soát
`PaymentAfterCancellation`, thông báo Staff/Admin hoàn thủ công (`PaymentService.apply_bank_transfer`).

## Xử lý lại webhook thanh toán

| Mục | Hợp đồng |
|---|---|
| Đường dẫn | `POST /internal/payment-webhooks/process?limit=100&older_than_minutes=5` |
| Use case | `PaymentWebhookService.process_unprocessed(older_than=..., limit=...)` |
| Đầu vào | `limit` (1–1000, mặc định 100); `older_than_minutes` (1–1440, mặc định 5): chỉ lấy sự kiện còn `Received` nhận trước mốc này |
| Đầu ra | `200 {"Processed": <số sự kiện đã xử lý>}` |
| Cấu hình | Cần `SEPAY_WEBHOOK_SECRET`, `SEPAY_ACCOUNT_NUMBER`; thiếu → `503` (sau khi đã qua kiểm tra bí mật cron) |

## Webhook SePay

| Mục | Hợp đồng |
|---|---|
| Router | `app/routers/webhooks.py` → `POST /webhooks/sepay` (chỉ POST), đã đăng ký trong `app/main.py` |
| Xác thực | HMAC-SHA256 theo tài liệu SePay: `X-SePay-Timestamp` (Unix giây), `X-SePay-Signature: sha256=<hex>` của `"{timestamp}.{raw_body}"`; lệch tối đa 300 giây; so sánh hằng thời gian; dùng bytes gốc của body |
| Cấu hình | `SEPAY_WEBHOOK_SECRET`, `SEPAY_ACCOUNT_NUMBER` (thiếu → 503, không xử lý). QR: `SEPAY_BANK`, `SEPAY_QR_IMAGE_URL`, `SEPAY_PAYMENT_CODE_PREFIX`, `SEPAY_PAYMENT_CODE_LENGTH` |
| Body | JSON (cấu hình SePay phải chọn `application/json`) |
| Phản hồi | `200 {"success": true}` khi sự kiện đã lưu và xử lý xong (kể cả trùng, sai số tiền, không khớp đơn — đã vào đối soát). `401` sai chữ ký/timestamp, `400` payload sai, `503` thiếu cấu hình, `500` lỗi lưu/xử lý → SePay gửi lại |
| Idempotency | `PaymentWebhookEvents` UNIQUE (Provider, AccountNumber, id) |
| Xử lý | `PaymentWebhookService.receive_sepay` → `PaymentService.apply_bank_transfer` (không tự hoàn tiền) |
| Xử lý lại | `POST /internal/payment-webhooks/process` (mục trên) cho sự kiện còn `Received` |

## Cấu hình cron gợi ý

- `POST /internal/orders/expire-unpaid-qr` mỗi 1 phút (độ trễ hủy tối đa ≈ 15 phút + chu kỳ cron).
- `POST /internal/payment-webhooks/process` mỗi 5 phút.
- Ví dụ: `curl -X POST -H "X-Internal-Secret: $INTERNAL_CRON_SECRET" https://<api>/internal/orders/expire-unpaid-qr`

## Cần xác minh trước khi triển khai

- Dịch vụ cron sẽ dùng (Render/Railway cron, GitHub Actions, cron máy chủ…) và cách lưu/xoay bí mật cron.
- Danh sách IP được phép gọi `/internal` và `/webhooks/sepay` nếu hạ tầng hỗ trợ.
- Đăng ký URL webhook và cấu hình HMAC trên trang quản trị SePay khi có tài khoản thật.
