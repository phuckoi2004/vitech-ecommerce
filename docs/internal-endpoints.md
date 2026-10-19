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
| Đầu ra | `200 {"Processed", "Selected", "Skipped", "Failed"}` (số đơn đã hủy, được chọn, bỏ qua vì không còn đủ điều kiện khi khóa, lỗi); `Failed > 0` → `500` kèm cùng số liệu |
| Quy tắc | Chỉ đơn `Pending`, `PaymentStatus` Pending/Failed, phương thức khác COD, `OrderedAt + 15 phút <= now` (UTC); tối đa `limit` đơn, cũ nhất trước. Mỗi đơn một transaction; khóa đơn và kiểm tra lại; hoàn tồn kho/coupon đúng một lần; hủy giao dịch QR đang chờ. |
| Gọi lặp / chồng nhau | An toàn: đơn đã hủy hoặc đã thanh toán bị bỏ qua sau khi khóa. |
| Lỗi | Đơn lỗi được rollback toàn bộ, ghi log và đếm vào `Failed`; các đơn sau vẫn được xử lý; đơn lỗi giữ nguyên và được chọn lại ở lần chạy sau. Lỗi ở bước chọn đơn (chưa xử lý đơn nào, nên không có số liệu): lỗi database → `503 {"detail"}`; lỗi bất ngờ khác → `500 {"detail", "code": "job_selection_failed"}`; lỗi nghiệp vụ giữ mã HTTP và `code` của nó. |
| Timeout | Mỗi transaction của tác vụ: `lock_timeout` 5 giây, `statement_timeout` 30 giây (`SET LOCAL`, chỉ trong transaction đó; giá trị giả định, xem `app/services/internal_jobs.py`). |
| Log | Logger `app.jobs`: bắt đầu/kết thúc (số liệu, thời gian), từng bản ghi lỗi (id nội bộ, loại lỗi database/business/unexpected, SQLSTATE hoặc mã lỗi; vi phạm ràng buộc DB là database kèm SQLSTATE, kể cả khi đã được đổi thành lỗi nghiệp vụ); không ghi secret, dữ liệu cá nhân, payload hay nội dung lỗi của driver. Kết thúc có lỗi ghi ở mức WARNING. |

Tiền về đúng số tiền sau hạn 15 phút (`PaymentService.apply_bank_transfer`): thứ quyết định là đơn đã bị hủy hay chưa.
- Đơn chưa bị hủy (tác vụ này chưa chạy tới): vẫn giữ hàng và coupon, nên được ghi nhận `Paid` như thường; tác vụ
  này bỏ qua đơn đã thanh toán.
- Đơn đã bị hủy (hết hạn, khách hoặc Staff/Admin hủy): ghi nhận tiền (`Success`), `PaymentStatus` `Paid`, mở đối soát
  `PaymentAfterCancellation`, thông báo Staff/Admin hoàn thủ công; không khôi phục đơn.

## Xử lý lại webhook thanh toán

| Mục | Hợp đồng |
|---|---|
| Đường dẫn | `POST /internal/payment-webhooks/process?limit=100&older_than_minutes=5` |
| Use case | `PaymentWebhookService.process_unprocessed(older_than=..., limit=...)` |
| Đầu vào | `limit` (1–1000, mặc định 100); `older_than_minutes` (1–1440, mặc định 5): chỉ lấy sự kiện còn `Received` nhận trước mốc này |
| Đầu ra | Như tác vụ hết hạn: `200 {"Processed", "Selected", "Skipped", "Failed"}`; `Failed > 0` → `500` kèm số liệu. `Skipped`: sự kiện đã được xử lý ở nơi khác (SePay gửi lại) |
| Lỗi | Sự kiện lỗi được rollback, ghi log, đếm vào `Failed` và giữ nguyên `Received` để lần chạy sau thử lại (không đánh dấu, không bỏ); các sự kiện sau vẫn được xử lý. Timeout và log như tác vụ hết hạn. |
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
