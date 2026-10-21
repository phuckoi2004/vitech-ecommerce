# VieTech — Danh sách API nghiệp vụ (Giai đoạn 6)

Tài liệu sinh từ code router (`backend/app/routers`). Chạy backend rồi mở `/docs` để xem schema chi tiết và thử API.

## Quy ước

- **Xác thực:** gửi `Authorization: Bearer <access_token>` (lấy từ `/auth/login`).
- **Quyền:** `Công khai` không cần đăng nhập; `Công khai*` không cần đăng nhập nhưng Staff/Admin đăng nhập xem thêm dữ liệu ẩn (ví dụ `active_only=false`); `Đăng nhập` cần token (Service kiểm tra role và chủ sở hữu); `Staff/Admin` là mọi route `/admin/...`, Customer bị từ chối 403 trước khi vào Service.
- **Lỗi:** body `{"detail": "<thông báo tiếng Việt>", "code": "<mã lỗi>"}`. 400 vi phạm nghiệp vụ, 401 chưa đăng nhập, 403 không có quyền, 404 không tìm thấy, 409 trùng dữ liệu, 422 dữ liệu gửi lên sai, 429 quá giới hạn, 502 lỗi cổng thanh toán. Riêng 422 (dữ liệu sai định dạng hoặc vi phạm ràng buộc của schema) có body `{"detail": [<danh sách lỗi theo trường>]}`, không có `code`; lỗi database tạm thời trả 503 `{"detail": "..."}`, cũng không có `code`.
- **Phân trang:** `page` (≥ 1), `page_size` (1–100, thống kê tồn kho 1–200); kết quả `{Items, Total, Page, PageSize}`.
- **Tham số `status`** là bộ lọc trạng thái (tên query `status`).
- **Ngày giờ** gửi lên phải kèm múi giờ, ví dụ `2026-10-01T00:00:00+07:00` (thiếu múi giờ → 422). Tham số `date_from`/`date_to` của thống kê là ngày lịch Việt Nam `YYYY-MM-DD`, tính cả hai đầu. Khoảng ngày đảo ngược hoặc vượt giới hạn khi đổi sang UTC (ví dụ `date_from=0001-01-01`, `date_to=9999-12-31`) trả 400 với mã `invalid_statistics_period`.
- **Đăng nhập tùy chọn:** route `Công khai*` kiểm tra Bearer token có giá trị; token sai/hết hạn/bị thu hồi trả 401 (frontend làm mới token hoặc gọi lại không kèm token). Không có header Authorization, header Basic hoặc Bearer rỗng được xử lý như khách chưa đăng nhập. Route bắt buộc đăng nhập vẫn trả 401 khi thiếu Bearer token hợp lệ.
- Tên trường JSON giữ đúng tên cột (PascalCase), ví dụ `ProductVariantId`, `Quantity`.
- **Tiền:** VND. Giá bán, phí vận chuyển và giá trị tiền của khuyến mãi gửi lên phải là số nguyên đồng; xem mục [Tiền VND nguyên đồng và tiền giảm](#tiền-vnd-nguyên-đồng-và-tiền-giảm).

## Tài khoản: sổ địa chỉ, thông báo

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| GET | `/users/me/addresses` | Đăng nhập |  |  | `list[AddressResponse]` | `list_addresses` |
| GET | `/users/me/addresses/{address_id}` | Đăng nhập |  |  | `AddressResponse` | `get_address` |
| POST | `/users/me/addresses` | Đăng nhập | `AddressCreate` |  | `AddressResponse` | `create_address` |
| PATCH | `/users/me/addresses/{address_id}` | Đăng nhập | `AddressUpdate` |  | `AddressResponse` | `update_address` |
| DELETE | `/users/me/addresses/{address_id}` | Đăng nhập |  |  | `204` | `delete_address` |
| GET | `/users/me/notifications` | Đăng nhập |  | is_read, page, page_size | `PageResponse[NotificationResponse]` | `list_notifications` |
| GET | `/users/me/notifications/unread-count` | Đăng nhập |  |  | `NotificationCountResponse` | `count_unread` |
| POST | `/users/me/notifications/read-all` | Đăng nhập |  |  | `NotificationCountResponse` | `mark_all_read` |
| POST | `/users/me/notifications/{notification_id}/read` | Đăng nhập |  |  | `NotificationResponse` | `mark_read` |

Thông báo Admin/Staff mở chi tiết phiếu nhập, bảo hành và đổi trả bằng `ReferenceType` + `ReferenceId`, kiểm tra quyền xem tương ứng. Thông báo hàng đợi chat được chuyển thành đã xử lý trong cùng transaction khi hội thoại đã được nhận hoặc đóng; giữ lịch sử và dẫn về `/admin/support`. Khi mở thông báo chat, client dùng `ActionUrl` hiện tại từ kết quả đánh dấu đã đọc để tránh đi theo liên kết cũ đã hết quyền truy cập. Từng thông báo được đánh dấu độc lập, chống gửi lặp cùng ID; lỗi có nút thử lại và được giữ khi chuyển trang.

## Sản phẩm, danh mục, thương hiệu

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| GET | `/categories` | Công khai* |  | active_only, parent_id, roots_only | `list[CategoryResponse]` | `list_categories` |
| GET | `/categories/slug/{slug}` | Công khai* |  | active_only | `CategoryResponse` | `get_category_by_slug` |
| GET | `/categories/{category_id}` | Công khai* |  | active_only | `CategoryResponse` | `get_category` |
| GET | `/brands` | Công khai* |  | active_only | `list[BrandResponse]` | `list_brands` |
| GET | `/brands/slug/{slug}` | Công khai* |  | active_only | `BrandResponse` | `get_brand_by_slug` |
| GET | `/brands/{brand_id}` | Công khai* |  | active_only | `BrandResponse` | `get_brand` |
| GET | `/products` | Công khai |  | keyword, category_id, brand_id, include_descendants, min_price, max_price, page, page_size | `PageResponse[ProductSummary]` | `search_products` |
| GET | `/products/slug/{slug}` | Công khai |  |  | `ProductDetailResponse` | `get_product_detail_by_slug` |
| GET | `/products/{product_id}` | Công khai |  |  | `ProductDetailResponse` | `get_product_detail` |
| GET | `/products/{product_id}/images` | Công khai |  |  | `list[ProductImageResponse]` | `list_images` |
| POST | `/admin/categories` | Staff/Admin | `CategoryCreate` |  | `CategoryResponse` | `create_category` |
| PATCH | `/admin/categories/{category_id}` | Staff/Admin | `CategoryUpdate` |  | `CategoryResponse` | `update_category` |
| DELETE | `/admin/categories/{category_id}` | Staff/Admin |  |  | `204` | `delete_category` |
| POST | `/admin/brands` | Staff/Admin | `BrandCreate` |  | `BrandResponse` | `create_brand` |
| PATCH | `/admin/brands/{brand_id}` | Staff/Admin | `BrandUpdate` |  | `BrandResponse` | `update_brand` |
| DELETE | `/admin/brands/{brand_id}` | Staff/Admin |  |  | `204` | `delete_brand` |
| GET | `/admin/products` | Staff/Admin |  | keyword, category_id, brand_id, status, include_deleted, page, page_size | `PageResponse[AdminProductResponse]` | `admin_list_products` |
| GET | `/admin/products/{product_id}` | Staff/Admin |  |  | `AdminProductDetailResponse` | `admin_get_product` |
| POST | `/admin/products` | Staff/Admin | `ProductCreate` |  | `AdminProductResponse` | `create_product` |
| PATCH | `/admin/products/{product_id}` | Staff/Admin | `ProductUpdate` |  | `AdminProductResponse` | `update_product` |
| DELETE | `/admin/products/{product_id}` | Staff/Admin |  |  | `204` | `delete_product` |
| GET | `/admin/products/{product_id}/variants` | Staff/Admin |  | include_deleted | `list[AdminProductVariantResponse]` | `list_variants` |
| GET | `/admin/variants/{variant_id}` | Staff/Admin |  |  | `AdminProductVariantResponse` | `get_variant` |
| POST | `/admin/variants` | Staff/Admin | `ProductVariantCreate` |  | `AdminProductVariantResponse` | `create_variant` |
| PATCH | `/admin/variants/{variant_id}` | Staff/Admin | `ProductVariantUpdate` |  | `AdminProductVariantResponse` | `update_variant` |
| DELETE | `/admin/variants/{variant_id}` | Staff/Admin |  |  | `204` | `delete_variant` |
| POST | `/admin/products/{product_id}/images` | Staff/Admin | `ProductImageCreate` |  | `ProductImageResponse` | `add_image` |
| PATCH | `/admin/products/{product_id}/images/{image_id}` | Staff/Admin | `ProductImageUpdate` |  | `ProductImageResponse` | `update_image` |
| DELETE | `/admin/products/{product_id}/images/{image_id}` | Staff/Admin |  |  | `204` | `delete_image` |
| GET | `/admin/variants/{variant_id}/serials` | Staff/Admin |  | status, page, page_size | `PageResponse[ProductSerialResponse]` | `list_serials` |
| GET | `/admin/serials/lookup` | Staff/Admin |  | serial_number | `ProductSerialResponse` | `get_by_serial_number` |
| GET | `/admin/serials/{serial_id}` | Staff/Admin |  |  | `ProductSerialResponse` | `get_serial` |
| POST | `/admin/serials` | Staff/Admin | `ProductSerialCreate` |  | `ProductSerialResponse` | `create_serial` |
| PATCH | `/admin/serials/{serial_id}` | Staff/Admin | `ProductSerialUpdate` |  | `ProductSerialResponse` | `update_serial` |
| DELETE | `/admin/serials/{serial_id}` | Staff/Admin |  |  | `204` | `delete_serial` |

## Yêu thích và giỏ hàng

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| GET | `/wishlist` | Đăng nhập |  |  | `WishlistDetailResponse` | `get_wishlist` |
| POST | `/wishlist/items` | Đăng nhập | `WishlistItemCreate` |  | `WishlistItemDetailResponse` | `add_item` |
| DELETE | `/wishlist/items/{wishlist_item_id}` | Đăng nhập |  |  | `204` | `remove_item` |
| DELETE | `/wishlist/products/{product_id}` | Đăng nhập |  |  | `204` | `remove_product` |
| GET | `/cart` | Đăng nhập |  |  | `CartSummaryResponse` | `get_cart` |
| POST | `/cart/items` | Đăng nhập | `CartItemCreate` |  | `CartSummaryResponse` | `add_item` |
| PATCH | `/cart/items/{cart_item_id}` | Đăng nhập | `CartItemUpdate` |  | `CartSummaryResponse` | `update_item` |
| PUT | `/cart/selection` | Đăng nhập | `CartSelectAll` |  | `CartSummaryResponse` | `set_all_selected` |
| DELETE | `/cart/items/{cart_item_id}` | Đăng nhập |  |  | `CartSummaryResponse` | `remove_item` |

## Đơn hàng và vận chuyển

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| GET | `/shipping-methods` | Công khai* |  | active_only | `list[ShippingMethodResponse]` | `list_shipping_methods` |
| GET | `/shipping-methods/{shipping_method_id}` | Công khai* |  |  | `ShippingMethodResponse` | `get_shipping_method` |
| POST | `/orders` | Đăng nhập | `OrderCreate` |  | `OrderDetailResponse` | `create_order` |
| GET | `/orders` | Đăng nhập |  | order_code, order_status, ordered_from, ordered_to, page, page_size | `PageResponse[OrderSummary]` | `search_customer_orders` |
| GET | `/orders/items/{order_item_id}` | Đăng nhập |  |  | `OrderItemResponse` | `get_customer_order_item` |
| GET | `/orders/{order_id}` | Đăng nhập |  |  | `OrderDetailResponse` | `get_order` |
| GET | `/orders/{order_id}/history` | Đăng nhập |  |  | `list[OrderStatusHistoryResponse]` | `get_order_status_history` |
| POST | `/orders/{order_id}/cancel` | Đăng nhập | `OrderCancelRequest` |  | `OrderDetailResponse` | `cancel_customer_order` |
| POST | `/admin/shipping-methods` | Staff/Admin | `ShippingMethodCreate` |  | `ShippingMethodResponse` | `create_shipping_method` |
| PATCH | `/admin/shipping-methods/{shipping_method_id}` | Staff/Admin | `ShippingMethodUpdate` |  | `ShippingMethodResponse` | `update_shipping_method` |
| DELETE | `/admin/shipping-methods/{shipping_method_id}` | Staff/Admin |  |  | `204` | `delete_shipping_method` |
| GET | `/admin/orders` | Staff/Admin |  | order_code, customer_id, assigned_staff_id, order_status, payment_status, ordered_from, ordered_to, page, page_size | `PageResponse[AdminOrderResponse]` | `admin_list_orders` |
| GET | `/admin/orders/{order_id}` | Staff/Admin |  |  | `AdminOrderDetailResponse` | `admin_get_order` |
| GET | `/admin/orders/{order_id}/history` | Staff/Admin |  |  | `list[AdminOrderStatusHistoryResponse]` | `admin_get_order_status_history` |
| GET | `/admin/orders/{order_id}/cogs` | Staff/Admin |  |  | `OrderCogsResponse` | `get_order_cogs` |
| POST | `/admin/orders/{order_id}/status` | Staff/Admin | `OrderStatusUpdate` |  | `AdminOrderDetailResponse` | `update_order_status` |
| POST | `/admin/orders/{order_id}/confirm-cod-delivery` | Staff/Admin | `CodDeliveryConfirm` |  | `AdminOrderDetailResponse` | `confirm_cod_delivery` |
| PATCH | `/admin/orders/{order_id}` | Staff/Admin | `OrderAdminUpdate` |  | `AdminOrderDetailResponse` | `update_order_admin_info` |
| GET | `/admin/orders/{order_id}/serials` | Staff/Admin |  |  | `list[OrderItemSerialsResponse]` | `get_order_serials` |
| POST | `/admin/orders/{order_id}/serials` | Staff/Admin | `OrderSerialAssign` |  | `list[OrderItemSerialsResponse]` | `assign_order_serials` |
| DELETE | `/admin/orders/{order_id}/serials/{serial_number}` | Staff/Admin |  |  | `list[OrderItemSerialsResponse]` | `release_order_serial` |
| GET | `/admin/shipment-returns` | Staff/Admin |  | status, page, page_size | `PageResponse[ShipmentReturnResponse]` | `list_shipment_returns` |
| GET | `/admin/orders/{order_id}/shipment-return` | Staff/Admin |  |  | `ShipmentReturnResponse` | `get_shipment_return` |
| POST | `/admin/orders/{order_id}/shipment-return/receive` | Staff/Admin | `ShipmentReturnReceive` |  | `ShipmentReturnResponse` | `receive_shipment_return` |

### Đặt, xác nhận và hủy đơn

- **`POST /orders`**: tổng tiền = tạm tính − tiền giảm của coupon + phí vận chuyển của phương thức đã chọn. Phương thức khác COD (chuyển khoản qua QR) cần tổng tiền > 0; nếu không, trả 400 `order_total_zero` và không có gì được ghi: không tạo đơn, không trừ tồn kho, lượt dùng coupon được hoàn tác. Đơn COD không bị chặn bởi quy tắc này.
- **`POST /orders/{order_id}/cancel`** (khách hàng hủy đơn của chính mình):
  - Đơn không tồn tại hoặc không thuộc khách hàng: 404 `order_not_found`.
  - Chỉ hủy được đơn `Pending`; trạng thái khác trả 400 `order_not_cancellable`.
  - Đơn đã thanh toán (`PaymentStatus` = `Paid`) trả 400 `order_paid_not_cancellable`: khách cần liên hệ cửa hàng để được hỗ trợ.
- **`POST /admin/orders/{order_id}/status`** (Staff/Admin):
  - Chỉ chuyển sang trạng thái kế tiếp: `Pending` → `Confirmed` → `Processing` → `Shipping` → `Delivered` → `Completed`; bước khác trả 400 `invalid_status_transition`. `CancelReason` chỉ dùng khi hủy (400 `cancel_reason_not_allowed`).
  - Sang `Confirmed`: đơn không phải COD phải có `PaymentStatus` = `Paid`, nếu không trả 400 `order_not_paid`. Đơn chuyển khoản chưa thanh toán ở lại `Pending` cho tới khi được thanh toán hoặc bị tác vụ hết hạn QR hủy. Đơn COD được xác nhận trước khi thu tiền.
  - Sang `Shipping`: đơn không phải COD phải `Paid` (400 `order_not_paid`), và mọi sản phẩm quản lý Serial/IMEI phải đã được gán đủ (400 `order_serials_not_assigned`).
  - Đơn COD sang `Delivered` phải dùng `POST /admin/orders/{order_id}/confirm-cod-delivery` (400 `cod_delivery_requires_collection`).
  - Hủy (`Cancelled`) chỉ được trước `Delivered`; sau đó trả 400 `order_not_cancellable`.

## Thanh toán và hoàn tiền

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| GET | `/payment-methods` | Công khai* |  | active_only | `list[PaymentMethodResponse]` | `list_payment_methods` |
| GET | `/payment-methods/{payment_method_id}` | Công khai* |  |  | `PaymentMethodResponse` | `get_payment_method` |
| POST | `/orders/{order_id}/payments/qr` | Đăng nhập |  |  | `QrPaymentResponse` | `create_qr_payment` |
| GET | `/orders/{order_id}/payments` | Đăng nhập |  |  | `list[PaymentTransactionResponse]` | `list_order_transactions` |
| POST | `/payments/{payment_transaction_id}/cancel` | Đăng nhập |  |  | `PaymentTransactionResponse` | `cancel_qr_payment` |
| POST | `/admin/payment-methods` | Staff/Admin | `PaymentMethodCreate` |  | `PaymentMethodResponse` | `create_payment_method` |
| PATCH | `/admin/payment-methods/{payment_method_id}` | Staff/Admin | `PaymentMethodUpdate` |  | `PaymentMethodResponse` | `update_payment_method` |
| DELETE | `/admin/payment-methods/{payment_method_id}` | Staff/Admin |  |  | `204` | `delete_payment_method` |
| GET | `/admin/payment-transactions` | Staff/Admin |  | status, payment_method_id, transaction_type, page, page_size | `PageResponse[AdminPaymentTransactionResponse]` | `admin_list_transactions` |
| GET | `/admin/orders/{order_id}/payments` | Staff/Admin |  |  | `list[AdminPaymentTransactionResponse]` | `admin_list_order_transactions` |
| POST | `/admin/orders/{order_id}/payments/cod` | Staff/Admin |  |  | `AdminPaymentTransactionResponse` | `record_cod_payment` |
| GET | `/admin/refunds/awaiting-orders` | Staff/Admin |  | page, page_size | `PageResponse[AdminOrderResponse]` | `list_orders_awaiting_refund` |
| GET | `/admin/orders/{order_id}/refund-sources` | Staff/Admin |  |  | `list[RefundSourceResponse]` | `list_refund_sources` |
| POST | `/admin/orders/{order_id}/refunds` | Staff/Admin | `OrderRefundCreate` |  | `AdminPaymentTransactionResponse` | `refund_order` |
| POST | `/admin/refunds/{refund_transaction_id}/resolve` | Staff/Admin | `RefundResolution` |  | `AdminPaymentTransactionResponse` | `resolve_pending_refund` |
| GET | `/admin/payment-reconciliations` | Staff/Admin |  | status, issue_type, order_id, page, page_size | `PageResponse[PaymentReconciliationResponse]` | `list_reconciliations` |
| POST | `/admin/payment-reconciliations/{reconciliation_id}/resolve` | Staff/Admin | `PaymentReconciliationResolve` |  | `PaymentReconciliationResponse` | `resolve_reconciliation` |

### Tạo yêu cầu thanh toán QR

`POST /orders/{order_id}/payments/qr`: chỉ Customer, cho đơn của chính mình (role khác: 403 `permission_denied`), không có body. Trả **201** `QrPaymentResponse`, gồm các trường của `PaymentTransactionResponse` cộng thông tin chuyển khoản do server cấp. Client hiển thị nguyên văn, không suy ra từ URL trong `QrData`.

| Trường | Ý nghĩa |
|---|---|
| `QrData` | URL ảnh QR. |
| `TransferContent` | Nội dung chuyển khoản bắt buộc: mã thanh toán duy nhất của yêu cầu này. |
| `Bank`, `AccountNumber` | Tài khoản nhận tiền mà cổng thanh toán đã dùng khi tạo QR (`SEPAY_ACCOUNT_NUMBER`; với ngân hàng bắt buộc tài khoản ảo như MSB là số VA); `null` nếu không có (ví dụ yêu cầu tạo trước khi server lưu thông tin này). |
| `AccountName` | Tên chủ tài khoản nhận tiền (`SEPAY_ACCOUNT_NAME`) lưu lúc tạo QR, để khách đối chiếu; `null` nếu không cấu hình. Không nằm trong ảnh QR. |
| `TransferAmount` | Số tiền cần chuyển, số nguyên VND, bằng `Amount` (= `TotalAmount` của đơn). |
| `ExpiresAt` | Hạn thanh toán = `OrderedAt` + 15 phút khi đơn còn `Pending`; `null` khi đơn đã ở trạng thái khác. Đơn quá hạn chưa thanh toán bị tác vụ `/internal/orders/expire-unpaid-qr` hủy. |

- Gọi lại khi đơn đã có giao dịch `Pending` kèm QR: trả lại đúng giao dịch đó, không tạo giao dịch mới.
- Endpoint này không xác nhận thanh toán: chỉ webhook SePay đã xác thực mới chuyển đơn sang `Paid`.
- Lỗi:
  - 400 `payment_gateway_not_configured`: server chưa cấu hình cổng thanh toán.
  - 404 `order_not_found`: đơn không tồn tại hoặc không thuộc khách hàng đang đăng nhập.
  - 400 `payment_method_is_cod`: đơn thanh toán khi nhận hàng.
  - 400 `order_not_payable`: `OrderStatus` không thuộc `Pending`/`Confirmed`/`Processing`, hoặc `PaymentStatus` không thuộc `Pending`/`Failed`.
  - 400 `order_payment_expired`: đơn `Pending` đã quá `OrderedAt` + 15 phút.
  - 400 `order_total_zero`: `TotalAmount` ≤ 0. Đây là chốt chặn thứ hai cho đơn cũ; đơn mới đã bị chặn từ lúc tạo.
  - 400 `qr_amount_not_supported`: cổng SePay chỉ nhận số tiền là số nguyên VND lớn hơn 0.
  - 409 `qr_payment_in_progress`: đơn đang có giao dịch `Pending` chưa có QR (một yêu cầu khác đang xử lý hoặc bị gián đoạn); thử lại sau, hoặc hủy giao dịch đó bằng `POST /payments/{payment_transaction_id}/cancel` rồi tạo lại.
  - 502 `qr_payment_unavailable`: cổng thanh toán không tạo được QR; giao dịch giữ chỗ được hủy.
  - 502 `payment_code_collision`: mã thanh toán trùng với giao dịch khác; tạo lại yêu cầu.
  - 400 `payment_request_cancelled`: trong lúc gọi cổng, giao dịch đã bị hủy hoặc đơn không còn chờ thanh toán.

## Khuyến mãi và mã giảm giá

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| GET | `/cart/coupon-preview` | Đăng nhập |  | code | `CouponPreviewResponse` | `preview_cart_coupon` |
| GET | `/admin/promotions` | Staff/Admin |  | status, page, page_size | `PageResponse[AdminPromotionResponse]` | `list_promotions` |
| GET | `/admin/promotions/{promotion_id}` | Staff/Admin |  |  | `AdminPromotionDetailResponse` | `get_promotion` |
| POST | `/admin/promotions` | Staff/Admin | `PromotionCreate` |  | `AdminPromotionDetailResponse` | `create_promotion` |
| PATCH | `/admin/promotions/{promotion_id}` | Staff/Admin | `PromotionUpdate` |  | `AdminPromotionDetailResponse` | `update_promotion` |
| PUT | `/admin/promotions/{promotion_id}/targets` | Staff/Admin | `PromotionTargetsUpdate` |  | `AdminPromotionDetailResponse` | `update_targets` |
| POST | `/admin/promotions/{promotion_id}/cancel` | Staff/Admin |  |  | `AdminPromotionDetailResponse` | `cancel_promotion` |
| DELETE | `/admin/promotions/{promotion_id}` | Staff/Admin |  |  | `204` | `delete_promotion` |
| GET | `/admin/promotions/{promotion_id}/coupons` | Staff/Admin |  | is_active | `list[AdminCouponResponse]` | `list_coupons` |
| GET | `/admin/coupons/{coupon_id}` | Staff/Admin |  |  | `AdminCouponResponse` | `get_coupon` |
| POST | `/admin/coupons` | Staff/Admin | `CouponCreate` |  | `AdminCouponResponse` | `create_coupon` |
| PATCH | `/admin/coupons/{coupon_id}` | Staff/Admin | `CouponUpdate` |  | `AdminCouponResponse` | `update_coupon` |
| DELETE | `/admin/coupons/{coupon_id}` | Staff/Admin |  |  | `204` | `delete_coupon` |

### Tiền VND nguyên đồng và tiền giảm

- Các trường tiền **gửi lên** sau đây phải là VND nguyên đồng: ≥ 0, phần nguyên tối đa 13 chữ số (tổng 15 chữ số kể cả 2 chữ số thập phân), chấp nhận `"30000"` hoặc `"30000.00"`; có phần lẻ thì trả 422.
  - `Price` của `ProductVariantCreate`/`ProductVariantUpdate` (`POST /admin/variants`, `PATCH /admin/variants/{variant_id}`) và của `CatalogItemCreate`/`CatalogVariantWrite` (`POST /admin/catalog-items`, `PUT /admin/catalog-items/{variant_id}`; hai route này chưa có trong bảng sản phẩm ở trên).
  - `BaseFee` của `ShippingMethodCreate`/`ShippingMethodUpdate`.
  - `MinOrderValue`, `MaxDiscountAmount` của `PromotionCreate`/`PromotionUpdate`.
- Trường tiền trong **response** vẫn là số thập phân 2 chữ số, để đọc được dữ liệu cũ có phần lẻ.
- `DiscountValue` của khuyến mãi: loại `Percentage` được có phần thập phân nhưng không quá 100; loại `FixedAmount` phải nguyên đồng.
  - Khi body gửi cả `DiscountType` và `DiscountValue` (luôn đúng với `POST /admin/promotions`), vi phạm trả 422.
  - `PATCH /admin/promotions/{promotion_id}` được kiểm tra lại với giá trị đang lưu. Giảm cố định có phần lẻ (ví dụ chỉ gửi `DiscountValue` có phần lẻ cho khuyến mãi đang là `FixedAmount`), hoặc giảm theo phần trăm lớn hơn 100, trả 400 `invalid_discount_value`.
  - Kiểm tra giảm cố định nguyên đồng chỉ chạy khi `PATCH` có `DiscountType` hoặc `DiscountValue`, nên khuyến mãi cũ có phần lẻ vẫn đổi được tên, mô tả hoặc trạng thái.
- Tiền giảm của mã giảm giá (`GET /cart/coupon-preview` và khi đặt đơn):
  - `Percentage`: cơ sở × `DiscountValue` / 100; `FixedAmount`: `DiscountValue`.
  - Giới hạn bởi `MaxDiscountAmount` (nếu có) và không vượt giá trị cơ sở, rồi làm tròn **xuống** đến đồng.
  - Khi đặt đơn, tiền giảm được phân bổ vào các dòng đơn theo tỷ lệ giá trị dòng, theo đơn vị một đồng (dữ liệu cũ có giá trị lẻ xu thì theo đơn vị một xu). Tổng phân bổ đúng bằng tiền giảm và không dòng nào bị giảm quá giá trị của dòng.

## Nhập hàng và kho

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| GET | `/admin/suppliers` | Staff/Admin |  | active_only, page, page_size | `PageResponse[SupplierResponse]` | `list_suppliers` |
| GET | `/admin/suppliers/{supplier_id}` | Staff/Admin |  |  | `SupplierResponse` | `get_supplier` |
| POST | `/admin/suppliers` | Staff/Admin | `SupplierCreate` |  | `SupplierResponse` | `create_supplier` |
| PATCH | `/admin/suppliers/{supplier_id}` | Staff/Admin | `SupplierUpdate` |  | `SupplierResponse` | `update_supplier` |
| DELETE | `/admin/suppliers/{supplier_id}` | Staff/Admin |  |  | `204` | `delete_supplier` |
| GET | `/admin/purchase-orders` | Staff/Admin |  | code, status, supplier_id, created_by_user_id, page, page_size | `PageResponse[PurchaseOrderResponse]` | `list_purchase_orders` |
| GET | `/admin/purchase-orders/{purchase_order_id}` | Staff/Admin |  |  | `PurchaseOrderDetailResponse` | `get_purchase_order` |
| POST | `/admin/purchase-orders` | Staff/Admin | `PurchaseOrderCreate` |  | `PurchaseOrderDetailResponse` | `create_purchase_order` |
| PATCH | `/admin/purchase-orders/{purchase_order_id}` | Staff/Admin | `PurchaseOrderUpdate` |  | `PurchaseOrderDetailResponse` | `update_purchase_order` |
| POST | `/admin/purchase-orders/{purchase_order_id}/items` | Staff/Admin | `PurchaseOrderItemCreate` |  | `PurchaseOrderDetailResponse` | `add_item` |
| PATCH | `/admin/purchase-orders/{purchase_order_id}/items/{purchase_order_item_id}` | Staff/Admin | `PurchaseOrderItemUpdate` |  | `PurchaseOrderDetailResponse` | `update_item` |
| DELETE | `/admin/purchase-orders/{purchase_order_id}/items/{purchase_order_item_id}` | Staff/Admin |  |  | `PurchaseOrderDetailResponse` | `remove_item` |
| POST | `/admin/purchase-orders/{purchase_order_id}/resubmit` | Staff/Admin |  |  | `PurchaseOrderDetailResponse` | `resubmit_purchase_order` |
| POST | `/admin/purchase-orders/{purchase_order_id}/decision` | Staff/Admin | `PurchaseOrderDecision` |  | `PurchaseOrderDetailResponse` | `decide_purchase_order` |
| POST | `/admin/purchase-orders/{purchase_order_id}/cancel` | Staff/Admin |  |  | `PurchaseOrderDetailResponse` | `cancel_purchase_order` |
| POST | `/admin/purchase-orders/{purchase_order_id}/receive` | Staff/Admin | `PurchaseOrderReceive` |  | `PurchaseOrderDetailResponse` | `receive_items` |
| POST | `/admin/purchase-orders/{purchase_order_id}/close` | Staff/Admin | `PurchaseOrderClose` |  | `PurchaseOrderDetailResponse` | `close_purchase_order` |
| GET | `/admin/purchase-orders/{purchase_order_id}/receipts` | Staff/Admin |  |  | `list[PurchaseReceiptResponse]` | `list_receipts` |
| GET | `/admin/inventory/low-stock` | Staff/Admin |  | page, page_size | `PageResponse[LowStockVariantResponse]` | `list_low_stock` |
| GET | `/admin/inventory/adjustments` | Staff/Admin |  | variant_id, adjustment_type, page, page_size | `PageResponse[StockAdjustmentResponse]` | `list_adjustments` |
| POST | `/admin/variants/{variant_id}/stock-opening` | Staff/Admin | `StockOpeningCreate` |  | `StockAdjustmentResponse` | `declare_opening` |
| POST | `/admin/variants/{variant_id}/stock-adjustments` | Staff/Admin | `StockAdjustmentCreate` |  | `StockAdjustmentResponse` | `adjust_stock` |

## Đánh giá

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| GET | `/products/{product_id}/reviews` | Công khai |  | rating, page, page_size | `PageResponse[ReviewResponse]` | `list_product_reviews` |
| GET | `/reviews/mine` | Đăng nhập |  | page, page_size | `PageResponse[ReviewResponse]` | `list_my_reviews` |
| POST | `/reviews` | Đăng nhập | `ReviewCreate` |  | `ReviewResponse` | `create_review` |
| PATCH | `/reviews/{review_id}` | Đăng nhập | `ReviewUpdate` |  | `ReviewResponse` | `update_review` |
| GET | `/admin/products/{product_id}/reviews` | Staff/Admin |  | include_deleted, page, page_size | `PageResponse[AdminReviewResponse]` | `admin_list_product_reviews` |
| GET | `/admin/reviews/{review_id}` | Staff/Admin |  |  | `AdminReviewResponse` | `admin_get_review` |
| POST | `/admin/reviews/{review_id}/hide` | Staff/Admin | `ReviewDeleteRequest` |  | `AdminReviewResponse` | `moderate_review` |

## Chat

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| POST | `/conversations` | Đăng nhập | `ConversationCreate` |  | `ConversationResponse` | `start_conversation` |
| GET | `/conversations` | Đăng nhập |  | status, page, page_size | `PageResponse[ConversationResponse]` | `list_my_conversations` |
| GET | `/conversations/{conversation_id}` | Đăng nhập |  |  | `ConversationDetailResponse` | `get_conversation` |
| GET | `/conversations/{conversation_id}/messages` | Đăng nhập |  | page, page_size | `PageResponse[MessageResponse]` | `list_messages` |
| POST | `/conversations/{conversation_id}/messages` | Đăng nhập | `MessageCreate` |  | `MessageResponse` | `send_message` |
| POST | `/conversations/{conversation_id}/close` | Đăng nhập |  |  | `ConversationResponse` | `close_conversation` |
| GET | `/admin/conversations` | Admin |  | status, mode, page, page_size | `PageResponse[AdminConversationResponse]` | `admin_list_conversations` |
| GET | `/admin/conversations/unassigned` | Staff/Admin |  | page, page_size | `PageResponse[AdminConversationResponse]` | `list_unassigned_conversations` |
| GET | `/admin/conversations/assigned` | Staff/Admin |  | status, page, page_size | `PageResponse[AdminConversationResponse]` | `list_assigned_conversations` |
| POST | `/admin/conversations/{conversation_id}/claim` | Staff/Admin |  |  | `AdminConversationResponse` | `claim_conversation` |
| GET | `/admin/conversations/{conversation_id}` | Staff/Admin |  |  | `AdminConversationDetailResponse` | `get_conversation` |
| GET | `/admin/conversations/{conversation_id}/summary` | Staff/Admin, theo quyền hội thoại | | | `AdminConversationResponse` (không tải lịch sử, có `UnreadCount`) | `get_summary` |
| GET | `/admin/conversations/{conversation_id}/message-window` | Staff/Admin, theo quyền hội thoại | | limit (1–100), latest, after_sent_at + after_message_id, before_sent_at + before_message_id | `PageResponse[AdminMessageResponse]`, thứ tự tăng dần theo SentAt và MessageId | `message_window` |
| POST | `/admin/conversations/{conversation_id}/read` | Nhân viên/Admin đang phụ trách | `MessageReadRequest` (MessageIds, 1–100 UUID) | | `{Updated: int}`; chỉ đánh dấu tin Customer trong chính hội thoại này | `mark_messages_read` |
| GET | `/admin/conversations/{conversation_id}/messages` | Staff/Admin |  | page, page_size | `PageResponse[AdminMessageResponse]` | `list_messages` |
| POST | `/admin/conversations/{conversation_id}/messages` | Staff/Admin | `MessageCreate` |  | `AdminMessageResponse` | `send_message` |
| POST | `/admin/conversations/{conversation_id}/close` | Staff/Admin |  |  | `AdminConversationResponse` | `close_conversation` |

Trang hỗ trợ có Đang chờ, Đang hỗ trợ, Đã kết thúc; Admin có thêm Tất cả hội thoại. Staff chỉ xem lịch sử được gán cho mình; Admin xem mọi lịch sử nhưng không trả lời/đóng/đánh dấu đã đọc thay nhân viên khác. Khi mở hội thoại, tải 50 tin mới nhất; polling chỉ lấy tin sau cursor, lịch sử cũ tải theo yêu cầu. Cursor cần cả timestamp có múi giờ và UUID, không kết hợp hai hướng. Các API cũ giữ nguyên hành vi.

Hội thoại Staff mới tạo thông báo chờ hỗ trợ cho Staff/Admin đang hoạt động; mở lại hội thoại đang tồn tại không tạo thông báo trùng. Tin Customer gửi vào hội thoại đã gán tạo thông báo cho người phụ trách. Thông báo dùng bảng Notifications hiện có và cùng transaction với hội thoại/tin nhắn; không gửi email hoặc gọi dịch vụ ngoài. `UnreadCount` là số tin Customer chưa được người phụ trách đánh dấu đã đọc, không phải số hội thoại.

Khi nhân viên/Admin phụ trách gửi tin trả lời, Customer nhận thông báo `Chat`, tham chiếu `Conversation` và liên kết `/tu-van?conversation=<id>` trong cùng transaction. Liên kết mở chính hội thoại được tham chiếu, kể cả hội thoại đã đóng; không tự tạo hội thoại khác. Customer chỉ đọc được hội thoại và thông báo của chính mình.

## Bảo hành và đổi trả

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| POST | `/warranty-requests` | Đăng nhập | `WarrantyRequestCreate` |  | `WarrantyRequestDetailResponse` | `create_warranty_request` |
| GET | `/warranty-requests` | Đăng nhập |  | status, page, page_size | `PageResponse[WarrantyRequestResponse]` | `list_my_warranty_requests` |
| GET | `/warranty-requests/{request_id}` | Đăng nhập |  |  | `WarrantyRequestDetailResponse` | `get_my_warranty_request` |
| POST | `/warranty-requests/{request_id}/cancel` | Đăng nhập | `ServiceRequestNote` (tùy chọn, chỉ `Note`) |  | `WarrantyRequestDetailResponse` | `cancel_warranty_request` |
| POST | `/return-requests` | Đăng nhập | `ReturnRequestCreate` |  | `ReturnRequestDetailResponse` | `create_return_request` |
| GET | `/return-requests` | Đăng nhập |  | status, page, page_size | `PageResponse[ReturnRequestResponse]` | `list_my_return_requests` |
| GET | `/return-requests/{request_id}` | Đăng nhập |  |  | `ReturnRequestDetailResponse` | `get_my_return_request` |
| POST | `/return-requests/{request_id}/cancel` | Đăng nhập | `ServiceRequestNote` (tùy chọn, chỉ `Note`) |  | `ReturnRequestDetailResponse` | `cancel_return_request` |
| POST | `/admin/warranty-requests/{request_id}/advance` | Staff/Admin | `WarrantyProgressRequest` |  | `AdminWarrantyRequestDetailResponse` | `advance_status` |
| GET | `/admin/warranty-requests` | Staff/Admin |  | status, eligibility_status, customer_id, assigned_staff_id, supplier_id, page, page_size | `PageResponse[AdminWarrantyRequestResponse]` | `list_warranty_requests` |
| GET | `/admin/warranty-requests/{request_id}` | Staff/Admin |  |  | `AdminWarrantyRequestDetailResponse` | `get_warranty_request` |
| POST | `/admin/warranty-requests/{request_id}/receive` | Staff/Admin | `ServiceRequestNote` (tùy chọn) |  | `AdminWarrantyRequestDetailResponse` | `receive_status` (bước `New`) |
| POST | `/admin/warranty-requests/{request_id}/inspect` | Staff/Admin | `WarrantyEligibilityUpdate` |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |
| POST | `/admin/warranty-requests/{request_id}/hand-over` | Staff/Admin | `WarrantyHandoverCreate` |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |
| POST | `/admin/warranty-requests/{request_id}/start-processing` | Staff/Admin | `ServiceRequestNote` (tùy chọn) |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |
| POST | `/admin/warranty-requests/{request_id}/propose-result` | Staff/Admin | `WarrantyResultProposal` |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |
| POST | `/admin/warranty-requests/{request_id}/approve-result` | Staff/Admin | `ServiceRequestNote` (tùy chọn) |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |
| POST | `/admin/warranty-requests/{request_id}/reject-result` | Staff/Admin | `WarrantyResultRejection` |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |
| POST | `/admin/warranty-requests/{request_id}/reject` | Staff/Admin | `ServiceRequestRejection` |  | `AdminWarrantyRequestDetailResponse` | `reject_status` |
| POST | `/admin/warranty-requests/{request_id}/complete` | Staff/Admin | `WarrantyCompletion` (tùy chọn) |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |
| GET | `/admin/return-requests` | Staff/Admin |  | status, request_type, customer_id, assigned_staff_id, pending_first, page, page_size | `PageResponse[AdminReturnRequestResponse]` | `list_return_requests` |
| GET | `/admin/return-requests/{request_id}` | Staff/Admin |  |  | `AdminReturnRequestDetailResponse` | `get_return_request` |
| POST | `/admin/return-requests/{request_id}/advance` | Staff/Admin | `ReturnProgressRequest` |  | `AdminReturnRequestDetailResponse` | `advance_status` |
| POST | `/admin/return-requests/{request_id}/accept` | Staff/Admin | `ServiceRequestNote` (tùy chọn) |  | `AdminReturnRequestDetailResponse` | `advance_status` (Pending → Approved) |
| POST | `/admin/return-requests/{request_id}/reject` | Staff/Admin | `ServiceRequestRejection` |  | `AdminReturnRequestDetailResponse` | `reject_status` |
| POST | `/admin/return-requests/{request_id}/start-receiving` | Staff/Admin | `ServiceRequestNote` (tùy chọn) |  | `AdminReturnRequestDetailResponse` | `advance_status` (Approved → Receiving) |
| POST | `/admin/return-requests/{request_id}/receive` | Staff/Admin | `ReturnGoodsReceive` (bắt buộc, tối thiểu `{}`) |  | `AdminReturnRequestDetailResponse` | `advance_status` (Receiving → Processing) |
| POST | `/admin/return-requests/{request_id}/inspect` | Staff/Admin | `ReturnInspection` |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |
| POST | `/admin/return-requests/{request_id}/approve` | Staff/Admin | `ReturnApproval` |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |
| POST | `/admin/return-requests/{request_id}/refund` | Staff/Admin | `ReturnRefundCreate` (tùy chọn) |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |
| POST | `/admin/return-requests/{request_id}/confirm-refund` | Staff/Admin |  |  | 400 `service_workflow_paused` | Tạm dừng, không gọi Service |

### Luồng bảo hành đang hoạt động (từ 15/10/2026)

- **Chỉ cập nhật tiến trình:** mỗi bước đổi trạng thái/mốc thời gian của phiếu, ghi một dòng lịch sử và gửi thông báo cho khách. Không chuyển trạng thái serial, không nhập/xuất kho, không có thao tác tài chính; không có bước gửi trung tâm bảo hành hay người duyệt riêng.
- **Giai đoạn** (`ExpectedStage`, suy ra từ phiếu) và tác động của mỗi lần `POST .../advance`:
  - `New` (phiếu `New`, chưa tiếp nhận): ghi `ReceivedAt`; trạng thái vẫn `New`, giai đoạn chuyển sang `Inspecting`.
  - `Inspecting`: trạng thái `Processing`, `EligibilityStatus` = `Eligible`.
  - `Repairing`: bắt buộc `ResultType` (`Repaired`, `PartReplaced`, `NotRepairable`) và `ResultNote` không rỗng. Người thực hiện công bố kết quả ngay: lưu `ResultType`, `ResultNote`, `ResultProposedAt`/`ResultApprovedAt` và người thực hiện. Khách thấy kết quả từ lúc này.
  - `Finished`: trạng thái `Completed`, ghi `CompletedAt`.
  - Phiếu chưa có người phụ trách được gán `AssignedStaffId` là người thực hiện bước đó.
- **`POST .../advance`** với `{"ExpectedStage": "<giai đoạn hiện tại>"}` (kèm `ResultType`, `ResultNote` ở bước `Repairing`) là route giao diện quản trị đang dùng. Route này không nhận `Note`/`InternalNote`. `ResultNote` là nội dung khách xem được và có trong thông báo gửi khách.
- **`POST .../receive`** là bước `New` của luồng trên (`receive_status` gọi `advance_status` với `ExpectedStage` = `New`): ghi `ReceivedAt`, gán `AssignedStaffId` nếu phiếu chưa có người phụ trách, trạng thái vẫn `New`. Body tùy chọn `ServiceRequestNote`, lưu vào dòng lịch sử của bước này:
  - `Note` khách xem được, nối vào cột `Note` dạng `<sự kiện> Ghi chú: <Note>`.
  - `InternalNote` lưu ở cột `InternalNote` của cùng dòng, chỉ có trong response Staff/Admin; lịch sử trả cho khách không có trường này.
  - Ghi chú được bỏ khoảng trắng đầu/cuối; chuỗi rỗng coi như không gửi. Trường ngoài `Note`/`InternalNote` bị từ chối (422).
  - Ghi chú không đưa vào thông báo gửi khách. Route không đổi trạng thái serial. Gọi lại sau khi đã tiếp nhận trả 409 `service_request_stale`.
- **`POST .../reject`** với `{"Reason": "...", "InternalNote": "..." (tùy chọn)}`: từ chối phiếu `New` (kể cả trước khi tiếp nhận), `HandedOver` hoặc `Processing`. Trạng thái chuyển `Rejected`, `EligibilityStatus` = `Ineligible`, `Reason` được lưu vào `EligibilityReason`, khách xem được và có trong thông báo. `InternalNote` chỉ lưu trong lịch sử cho Staff/Admin, không có trong response của khách hay thông báo.
- **Khách hủy** (`POST /warranty-requests/{request_id}/cancel`): chỉ khi phiếu còn `New` và chưa được tiếp nhận; ngược lại trả 400 `warranty_not_cancellable`.
- **Lỗi:**
  - 401 khi thiếu Bearer token hợp lệ; 403 `permission_denied` khi Customer gọi route `/admin/...`.
  - 404 `warranty_request_not_found`.
  - 409 `service_request_stale`: giai đoạn hiện tại khác `ExpectedStage`. Gồm cả bấm lặp lại, gọi `/receive` khi đã tiếp nhận, và gọi `/advance` trên phiếu đã đóng.
  - 400 `warranty_result_required` (bước `Repairing` thiếu `ResultType`), `result_note_required` (`ResultNote` rỗng), `warranty_result_not_applicable` (gửi `ResultType`/`ResultNote` ở bước khác), `warranty_replacement_paused` (phiếu đổi máy cũ ở bước `Finished`), `service_request_closed` (từ chối phiếu đã đóng).
  - 422: body sai (trường lạ, `ExpectedStage`/`ResultType` ngoài danh sách, ví dụ `ProductReplaced`, `Reason` rỗng).
- **Tạm dừng:** `inspect`, `hand-over`, `start-processing`, `propose-result`, `approve-result`, `reject-result`, `complete` luôn trả 400 `service_workflow_paused` và không thay đổi phiếu. Phần cài đặt cũ được giữ trong Service để tham khảo, chờ quyết định nghiệp vụ.

### Luồng đổi/trả đang hoạt động (từ 15/10/2026)

- **Chỉ cập nhật tiến trình:** mỗi bước đổi trạng thái phiếu, ghi một dòng lịch sử và gửi thông báo cho khách. Không tạo giao dịch hoàn tiền, không nhập/xuất kho, không đổi trạng thái serial. `Completed` **không** có nghĩa là đã hoàn tiền.
- **Chuyển trạng thái** (mỗi lần tiến một bước): `Pending → Approved → Receiving → Processing → Completed`. Bước `Receiving → Processing` ghi `ReceivedAt`, bước `Processing → Completed` ghi `CompletedAt`. Phiếu chưa có người phụ trách được gán `AssignedStaffId` là người thực hiện bước đó.
- **`POST .../advance`** với `{"ExpectedStatus": "<trạng thái hiện tại>"}` là route giao diện quản trị đang dùng. Route này không nhận ghi chú: gửi thêm trường khác trả 422.
- **`POST .../accept`, `.../start-receiving`, `.../receive`** là các bước ứng với `ExpectedStatus` lần lượt `Pending`, `Approved`, `Receiving`, có thêm ghi chú tùy chọn:
  - `Note`: khách xem được, nối vào dòng lịch sử dạng `<sự kiện>. Ghi chú: <Note>`.
  - `InternalNote`: chỉ Staff/Admin thấy (trường `InternalNote` của lịch sử trong response admin), không có trong response của khách.
  - Ghi chú không được đưa vào nội dung thông báo gửi khách.
  - `/receive`: phải gửi body `ReturnGoodsReceive` (tối thiểu `{}`). `SerialNumber` được chấp nhận nhưng **hiện không được đối chiếu hay xử lý**: không kiểm tra khớp serial của phiếu và không đổi trạng thái serial. Việc đối chiếu serial khi nhận hàng chưa được chốt nghiệp vụ.
- **`POST .../reject`** với `{"Reason": "..."}`: từ chối phiếu ở trạng thái còn mở (`Pending`, `Approved`, `Receiving`, `Processing`). `Reason` khách xem được, được lưu vào `DecisionReason` và có trong thông báo. `InternalNote` (tùy chọn) chỉ lưu trong lịch sử cho Staff/Admin, không có trong response của khách hay thông báo.
- **Lỗi:**
  - 401 khi thiếu Bearer token hợp lệ; 403 `permission_denied` khi Customer gọi (bị chặn trước khi vào Service).
  - 404 `return_request_not_found`.
  - 409 `service_request_stale`: trạng thái hiện tại khác trạng thái mong đợi. Gồm cả bấm lặp lại, và gọi `/accept`, `/start-receiving`, `/receive` khi phiếu đã ở bước khác hoặc đã đóng.
  - 400 `service_request_closed`: gọi `/advance` với `ExpectedStatus` là trạng thái đã đóng (`Completed`, `Rejected`, `Cancelled`), hoặc từ chối phiếu đã đóng.
  - 422: body sai (trường lạ, sai kiểu, `ExpectedStatus` ngoài danh sách, `Reason` rỗng).
- **Tạm dừng:** `inspect`, `approve`, `refund`, `confirm-refund` luôn trả 400 `service_workflow_paused` và không thay đổi phiếu. Phần cài đặt tài chính/kiểm định cũ được giữ lại trong Service để tham khảo, chờ quyết định nghiệp vụ.

## Tin tức và banner

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| GET | `/news` | Công khai |  | page, page_size | `PageResponse[NewsArticleSummary]` | `list_published_articles` |
| GET | `/news/{slug}` | Công khai |  |  | `NewsArticleResponse` | `get_published_article` |
| POST | `/news/{slug}/views` | Công khai |  |  | `NewsArticleViewResponse` (`ViewCount`) | `record_article_view` |
| GET | `/banners` | Công khai |  |  | `list[BannerResponse]` | `list_display_banners` |
| GET | `/admin/news` | Staff/Admin |  | status, page, page_size | `PageResponse[AdminNewsArticleSummary]` | `admin_list_articles` |
| GET | `/admin/news/{article_id}` | Staff/Admin |  |  | `AdminNewsArticleResponse` | `admin_get_article` |
| POST | `/admin/news` | Staff/Admin | `NewsArticleCreate` |  | `AdminNewsArticleResponse` | `create_article` |
| PATCH | `/admin/news/{article_id}` | Staff/Admin | `NewsArticleUpdate` |  | `AdminNewsArticleResponse` | `update_article` |
| POST | `/admin/news/{article_id}/publish` | Staff/Admin |  |  | `AdminNewsArticleResponse` | `publish_article` |
| POST | `/admin/news/{article_id}/hide` | Staff/Admin |  |  | `AdminNewsArticleResponse` | `hide_article` |
| GET | `/admin/banners` | Staff/Admin |  | is_active | `list[AdminBannerResponse]` | `admin_list_banners` |
| GET | `/admin/banners/{banner_id}` | Staff/Admin |  |  | `AdminBannerResponse` | `admin_get_banner` |
| POST | `/admin/banners` | Staff/Admin | `BannerCreate` |  | `AdminBannerResponse` | `create_banner` |
| PATCH | `/admin/banners/{banner_id}` | Staff/Admin | `BannerUpdate` |  | `AdminBannerResponse` | `update_banner` |
| POST | `/admin/banners/{banner_id}/activate` | Staff/Admin |  |  | `AdminBannerResponse` | `activate_banner` |
| POST | `/admin/banners/{banner_id}/deactivate` | Staff/Admin |  |  | `AdminBannerResponse` | `deactivate_banner` |

## Thống kê

| Method | Đường dẫn | Quyền | Body | Query | Trả về | Service |
|---|---|---|---|---|---|---|
| GET | `/admin/statistics/orders` | Staff/Admin |  | date_from, date_to | `OrderStatisticsResponse` | `order_statistics` |
| GET | `/admin/statistics/revenue` | Staff/Admin |  | date_from, date_to | `RevenueStatisticsResponse` | `revenue_statistics` |
| GET | `/admin/statistics/cogs` | Staff/Admin |  | date_from, date_to | `CogsStatisticsResponse` | `cogs_statistics` |
| GET | `/admin/statistics/top-products` | Staff/Admin |  | date_from, date_to, rank_by, limit | `list[TopProductResponse]` | `top_products` |
| GET | `/admin/statistics/inventory` | Staff/Admin |  | page, page_size | `InventoryStatisticsResponse` | `inventory_statistics` |

## Điểm vào máy-với-máy (không dành cho frontend)

- `POST /webhooks/sepay`: webhook SePay, xác thực HMAC; trả 503 cho tới khi cấu hình `SEPAY_*`.
- `POST /internal/orders/expire-unpaid-qr` (query `limit` 1–1000, mặc định 100) và `POST /internal/payment-webhooks/process` (query `limit` 1–1000, mặc định 100; `older_than_minutes` 1–1440, mặc định 5): cho cron, header `X-Internal-Secret`; ẩn khỏi `/docs`.
  - 200 `{"Processed", "Selected", "Skipped", "Failed"}`. Khi `Failed` > 0, trả **500 kèm cùng body**: bản ghi lỗi đã được rollback, ghi log và sẽ được chọn lại ở lần chạy sau. Cron cần coi 500 là lần chạy thất bại.
  - 500 `job_selection_failed`: lỗi bất ngờ ở bước chọn bản ghi, chưa xử lý bản ghi nào. Lỗi database trả 503 (không có `code`).
  - 401 khi thiếu hoặc sai secret. 503 khi server chưa cấu hình secret (`INTERNAL_CRON_SECRET` ngắn hơn 32 byte), hoặc (riêng route webhook) chưa cấu hình SePay.
- Chi tiết: `docs/internal-endpoints.md`.

## Không mở qua API

- Use case nội bộ không mở cho client: `record_ai_reply`, `notify`, `change_stock`, `apply_bank_transfer` (chỉ qua webhook SePay), `handle_payment_callback`, `create_return_refund`, `apply_coupon_to_order`, `release_coupon_usage`, `receive_purchase_lines`.
- API Auth/hồ sơ/quản lý tài khoản của Giai đoạn 5 xem `docs/auth-spec.md`.


---

## Bổ sung hiện hành cho phần admin — 18/10/2026

Phần bổ sung này ghi các quyết định mới và hợp đồng đã đối chiếu với mã nguồn ngày 18/10/2026. Giữ nguyên nội dung gốc để lưu lịch sử; khi có khác biệt ở đúng chủ đề bên dưới, áp dụng phần bổ sung thay cho quy tắc cũ tương ứng. Đây là cập nhật tài liệu, không phải lệnh thay đổi source code, chạy migration hoặc sửa CSDL thật.

[2026-10-18-admin.md](updates/2026-10-18-admin.md) | [README.md](README.md)

### Phiếu nhập, người tạo và người duyệt

- Staff lập phiếu ở Pending, chờ Admin duyệt hoặc từ chối. Admin lập thì phiếu ở Approved ngay và có thể nhận hàng, không cần bước quyết định tự duyệt riêng.
- Phiếu chỉ sửa khi Pending/Rejected. Sửa đầu phiếu và toàn bộ dòng hàng gửi trong một PATCH tới `/admin/purchase-orders/{id}` với `SupplierId`, `Note`, `Items`.
- Backend khóa phiếu, kiểm tra lại trạng thái và lưu tất cả trong một transaction. Lỗi kiểm tra/ghi/commit thì hoàn tác toàn bộ. Giữ ID của dòng còn cùng ProductVariantId; thêm dòng mới, xóa dòng bị bỏ, tính lại tổng tiền ở backend. Gửi lại cùng bộ dòng không thêm trùng SKU.
- Bỏ `Items` trong PATCH là giữ nguyên dòng hiện có; `Items=[]` hoặc null bị từ chối. Trường ngày lập, người lập, thành tiền và thực nhận không phải đầu vào được phép sửa tùy ý.

### Bảo hành, đổi trả và các luồng tạm dừng

**Đổi trả hiện hành:** Staff/Admin tiếp nhận hoặc từ chối, sau đó chỉ chuyển tiến độ theo thứ tự `Pending → Approved → Receiving → Processing → Completed`. Customer hủy theo điều kiện của API khách. Rejected/Cancelled/Completed là phiếu đóng; không có chuyển lùi. Từ chối cần lý do. Backend kiểm tra trạng thái đang quan sát để bấm lặp hoặc form cũ không làm nhảy nhiều giai đoạn.

Luồng đổi trả hiện hành không bắt kiểm tra thiệt hại, duyệt tiền hoặc hoàn tiền để tiến bước; không tự cộng/trừ kho hay chuyển serial theo việc bấm chuyển trạng thái. Completed tại đây chỉ là hoàn tất tiến độ phiếu, không chứng nhận tiền đã được hoàn hoặc hàng đã nhập lại kho. Luồng tài chính cũ được giữ nhưng endpoint ghi theo luồng đó đang trả lỗi `service_workflow_paused`.

### Lưu tin tức và banner theo trạng thái

- Tạo/sửa tin tức gửi nội dung cùng Status trong một POST/PATCH tới `/admin/news` hoặc `/admin/news/{id}`. Mặc định tạo Draft; chọn Published thì đăng ngay khi lần lưu thành công. Backend tự ghi PublishedAt lần đầu, giữ khi ẩn rồi đăng lại; không nhận PublishedAt hoặc người tạo tùy ý từ client.
- Chuyển trạng thái tin tức vẫn theo quy tắc: Draft giữ Draft hoặc sang Published; Published giữ Published hoặc sang Hidden; Hidden giữ Hidden hoặc sang Published. Không đưa bài đã đăng về Draft. Bỏ Status trong PATCH thì giữ trạng thái đang có.
- Tạo/sửa banner gửi nội dung, khoảng hiển thị và IsActive cùng một POST/PATCH tới `/admin/banners` hoặc `/admin/banners/{id}`. Mặc định tạo true; nếu chọn ngừng thì bản ghi được tạo false ngay, không có bước tạo hoạt động rồi gửi lệnh tắt sau. Bỏ IsActive trong PATCH thì giữ cờ đang có.
- Mỗi lần lưu thuộc một transaction: lỗi kiểm tra, ghi hoặc commit hoàn tác nội dung và trạng thái cùng nhau. Form giữ dữ liệu nhập để thử lại, không dùng cơ chế lưu một phần rồi tiếp tục đổi trạng thái.
- Các nút đổi trạng thái riêng ở danh sách/chi tiết vẫn dùng publish/hide hoặc activate/deactivate. Form không cần gọi thêm các endpoint này sau lần lưu nội dung.
- API công khai chỉ trả bài Published; banner phải IsActive=true và đang trong [StartDate, EndDate], mốc null là không giới hạn. Trạng thái trong CSDL quyết định khả năng hiển thị, không phải việc trình duyệt đã từng bấm một nút Đăng.

### Báo cáo và lịch sử thanh toán

- API báo cáo hiện có `/admin/statistics/report-options`, `/admin/statistics/reports/revenue` và `/admin/statistics/reports/orders`, dùng cho Staff/Admin theo quyền. Chúng bổ sung cho các API thống kê cũ, không xóa API cũ.
- Hai màn hình báo cáo có lựa chọn từng tháng trong 12 tháng của năm hoặc 5 tháng gần nhất. Từng tháng hiển thị một cột, 5 tháng hiển thị 5 cột; nhãn là tháng cụ thể. Bộ lọc tác động đồng thời biểu đồ và bảng; kỳ bảng là tháng/năm, không chia tuần.
- Tạm bỏ lọc tài khoản, lọc nhà cung cấp và xuất báo cáo trên UI. Không suy ra giá trị bằng 0 khi API báo lỗi.
- Báo cáo doanh số theo sản phẩm dùng OrderItems.LineTotal của đơn Delivered/Completed theo DeliveredAt, có giao dịch Payment Success; không tính lặp doanh số khi một đơn có nhiều giao dịch. Báo cáo này không đồng nghĩa mọi chỉ số doanh thu thuần của StatisticsService: phí giao, hoàn tiền và giá vốn cần phân biệt theo từng API.


## Bổ sung ngày 21/10/2026 — đơn hàng và nội dung admin

- `GET /admin/orders?keyword=...`: tìm chuỗi liên tiếp trong mã đơn, tên tài khoản khách hoặc SĐT tài khoản, tối đa 255 ký tự. Bộ lọc cũ vẫn dùng được; không thêm tham số này vào API danh sách đơn của khách.
- POST đổi trạng thái dùng luồng mới `Pending → Processing → Shipping → Delivered` và đóng tại Delivered. COD vẫn qua `confirm-cod-delivery`; ghi doanh số và thời điểm đóng cùng giao dịch giao hàng thành công.
- Người xác nhận đầu tiên sở hữu bước tiếp theo; Admin có thể làm thay. Không cho PATCH thay người phụ trách để lách quyền. Các giá trị Confirmed/Completed cũ được giữ để đọc lịch sử.
- Tạo đơn gửi `NewOrder` cho Staff/Admin; mỗi người đọc riêng. Xác nhận/hủy đơn giải quyết thông báo NewOrder của tất cả người nhận trong cùng giao dịch. Tham chiếu mở thẳng `/admin/orders/{id}`.
- Các API đánh giá nội bộ, tin tức và banner cho Staff/Admin; `ReviewDeleteRequest.DeleteReason` bắt buộc, không trắng, tối đa 2.000 ký tự. API tin tức nội bộ trả thêm `CreatedByName`.
- API `POST /admin/product-image-uploads` cho Staff/Admin để dùng kho ảnh chung cho tin tức/banner; chỉ tải file, không cấp quyền sửa catalog.

Phạm vi, phần giữ lại và kết quả xác minh: [bản bổ sung](updates/2026-10-21-admin-orders-content.md).

### Bổ sung tiếp 21/10/2026 — sửa chay số tồn trong chi tiết sản phẩm

`PATCH /admin/variants/{variant_id}/stock` chỉ Admin: body `{"StockQuantity": 8, "ExpectedStockQuantity": 3}` đặt số tồn từ giá trị đang hiển thị 3 thành 8. Hai trường là số nguyên thực sự, không âm, tối đa 2.147.483.647. Trả `{"ProductVariantId": "...", "StockQuantity": 8}`. Không tạo lịch sử/phiếu điều chỉnh, không đổi giá vốn.

409 `stock_quantity_changed` khi số tồn đã khác số cũ, phải tải lại trước khi sửa. 400 `serial_stock_edit_not_enabled` với biến thể đang quản lý Serial/IMEI (người dùng yêu cầu giữ phần Serial chờ thống nhất). 403 cho Staff/Customer; 404 cho biến thể không có/đã xóa. Các API điều chỉnh kho có lịch sử cũ vẫn giữ nguyên và không được dùng bởi nút sửa chay này.

### Quyết định bổ sung 21/10/2026 — tự gán Serial và chỉnh tồn có Serial

Phần này cập nhật giới hạn Serial của mục ngay trước, giữ mục cũ làm lịch sử quyết định:

- Xác nhận đơn sang Processing tự chọn Serial Available chưa gắn đơn, đổi Reserved và gắn OrderItemId trong cùng giao dịch đổi trạng thái. Thiếu mã trả 400 `insufficient_available_serials`; mọi phần được hoàn tác. Delivered đổi mã sang Sold, giữ liên kết và không trừ tồn lần nữa.
- `GET /admin/orders/{id}/serials` trả mã do hệ thống gán. `POST /admin/orders/{id}/serials` và `DELETE /admin/orders/{id}/serials/{number}` không còn cho phép sửa, service trả 400 `order_serials_read_only` cho cả Staff/Admin có quyền xử lý đơn. Customer/nhân viên không phụ trách vẫn bị chặn quyền trước đó.
- `PATCH /admin/variants/{id}/stock` mở cho cả biến thể IsSerialTracked=true, chỉ Admin. Tăng từ 3 lên 5 gửi `{"StockQuantity":5,"ExpectedStockQuantity":3,"SerialNumbers":["REAL-1","REAL-2"]}`. Mỗi máy thêm cần một mã mới, không trùng. Sai số lượng: 400 `serial_count_mismatch`; mã đã tồn tại: 409 `serial_exists`; chuỗi rỗng/quá 100 ký tự: 422. Lỗi không lưu số lượng hoặc một phần Serial.
- Giảm tồn không gửi mã, hệ thống chọn ngẫu nhiên đúng số mã Available chưa gắn đơn và chuyển WrittenOff. Không xóa bản ghi, không lấy mã đang giữ/đã bán. Không cho gửi mã khi giảm tồn hoặc khi biến thể không quản lý Serial.
- Vẫn dùng ExpectedStockQuantity và khóa biến thể; dữ liệu Available/StockQuantity/đơn chưa gán mã không khớp trả 409 `serial_stock_mismatch`. Không tạo StockAdjustments hay đổi giá vốn. Không tự thay IsSerialTracked, không đổi schema và không cập nhật dữ liệu thật.

### Cập nhật tiếp 21/10/2026 — checkbox và tồn cũ không Serial

Quyết định mới thay điều kiện bắt đủ mã cho toàn bộ tồn của các mục trước:

- PATCH `/admin/variants/{id}/stock` nhận thêm IsSerialTracked và ExpectedIsSerialTracked tùy chọn. Ví dụ từ 10 máy không mã tăng lên 12 và bật yêu cầu Serial: `{"StockQuantity":12,"ExpectedStockQuantity":10,"IsSerialTracked":true,"ExpectedIsSerialTracked":false,"SerialNumbers":["NEW-1","NEW-2"]}`. Chỉ hai máy mới cần mã; không bắt bù mười mã cũ. Trả thêm IsSerialTracked bên cạnh ProductVariantId/StockQuantity.
- Cờ, số tồn và mã mới lưu trong một giao dịch. Cờ đã khác ExpectedIsSerialTracked trả 409 `serial_tracking_changed`; số tồn đã khác vẫn là 409 `stock_quantity_changed`. Thiếu mã mới là 400 `serial_count_mismatch`, mã đã tồn tại là 409 `serial_exists`; không lưu dở cờ hoặc số lượng.
- Giảm tồn tự trừ phần không mã trước, chỉ loại ngẫu nhiên mã Available chưa gắn đơn khi phần không mã không đủ. Cho phép số Serial nhỏ hơn số máy để giữ tồn cũ; chặn trường hợp số mã vượt số máy. Số lượng đã giữ cho Pending/Confirmed nhưng chưa gán mã được tính riêng; Processing/Shipping đã xác nhận không còn nằm trong nhóm máy chưa phân cho đơn.
- Xác nhận đơn ưu tiên mã khả dụng có sẵn, phần còn lại được bán không mã. GET `/admin/orders/{id}/serials` trả đúng các mã thực có trong SerialNumbers, có thể ít hơn Quantity hoặc rỗng. Không thêm chuỗi rỗng/mã giả vào API; frontend giữ nhãn Serial/IMEI: và để giá trị trống. Shipping không bắt nhập bù mã cho hàng cũ.
- Mã vẫn chỉ đọc với NV/QTV. Hủy khi đang giao và nhận lại hàng hỗ trợ cùng dòng đơn có cả phần có mã và không mã. Không sửa CSDL/migration, không tự bật hàng loạt, không đổi quy tắc giá vốn hoặc tạo lịch sử điều chỉnh.
