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
| `Bank`, `AccountNumber` | Tài khoản nhận tiền mà cổng thanh toán đã dùng khi tạo QR; `null` nếu không có (ví dụ yêu cầu tạo trước khi server lưu thông tin này). |
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
