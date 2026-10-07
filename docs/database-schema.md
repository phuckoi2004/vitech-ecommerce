# VieTech – Database Schema (đã chốt)

Tài liệu này là **SOURCE OF TRUTH** cho database schema của VieTech.
Nền tảng: `VieTech.docx` (mục 3.4.3) + các quyết định đã chốt của người dùng.
Khi khác với `VieTech.docx`, tài liệu này được ưu tiên (quyết định trực tiếp của người dùng).

Trạng thái: **chưa áp dụng vào database**, **chưa có SQLAlchemy Models**.

---

## 1. Quy ước chung

| Hạng mục | Quy ước |
|---|---|
| Tên bảng / column | Giữ nguyên PascalCase như `VieTech.docx`. Trong SQL phải đặt trong dấu ngoặc kép, ví dụ `"Users"."UserId"`. |
| Primary Key | `uuid`, `DEFAULT gen_random_uuid()`. Riêng bảng nối dùng PK ghép từ 2 FK (không có default). |
| Thời gian | Mọi cột thời điểm dùng `timestamptz`. Cột ngày thuần (`DateOfBirth`, `WarrantyStartDate`, `WarrantyEndDate`) giữ `date`. |
| `CreatedAt` | `NOT NULL DEFAULT now()` |
| Thời điểm phát sinh khác | `AddedAt`, `OrderedAt`, `ChangedAt`, `SentAt`, `UploadedAt`, `RequestedAt`: `NOT NULL DEFAULT now()` |
| `UpdatedAt` | `NOT NULL DEFAULT now()`, tự cập nhật bằng database trigger `BEFORE UPDATE` trên 4 bảng: Users, Products, Carts, Reviews. |
| Boolean default | `IsDeleted=false`, `IsActive=true`, `IsRead=false`, `IsEmailVerified=false`, `IsDefault=false`, `IsSelected=true` |
| Counter default | `TotalSpent=0`, `TotalOrders=0`, `AverageRating=0`, `ReviewCount=0`, `SoldQuantity=0`, `UsedCount=0` |
| Số lượng / thứ tự / phí default | `StockQuantity=0`, `MinStockLevel=0`, `DisplayOrder=0`, `ShippingFee=0` |
| Status | `varchar` + `CHECK (... IN (...))`. Không dùng PostgreSQL ENUM. |

### Chính sách ON DELETE

| Loại quan hệ | ON DELETE |
|---|---|
| Child phụ thuộc hoàn toàn vào parent (ảnh, dòng giỏ hàng, dòng chứng từ, bảng nối…) | `CASCADE` |
| Dữ liệu nghiệp vụ / lịch sử (đơn hàng, giao dịch, lịch sử trạng thái, đánh giá, bảo hành, đổi trả…) | `RESTRICT` |
| Master data đang được tham chiếu (danh mục, thương hiệu, biến thể, phương thức, nhà cung cấp, người tạo…) | `RESTRICT` |
| FK optional chỉ mang tính gán/ghi nhận (nhân viên phụ trách, người thay đổi, người xóa…) | `SET NULL` |

Ký hiệu trong các bảng dưới: **NN** = NOT NULL, **PK** = Primary Key, **FK** = Foreign Key, **UQ** = Unique.

---

## 2. Danh sách status

| Cột | Giá trị hợp lệ |
|---|---|
| `Orders.OrderStatus` | Pending, Confirmed, Processing, Shipping, Delivered, Completed, Cancelled |
| `Orders.PaymentStatus` | Pending, Paid, Failed, Refunded, Cancelled |
| `Products.Status` | Draft, Active, Inactive, Discontinued |
| `ProductSerials.Status` | Available, Reserved, Sold, Warranty, Returned |
| `Promotions.Status` | Draft, Scheduled, Active, Expired, Cancelled |
| `PurchaseOrders.Status` | Pending, Approved, Rejected, Receiving, Completed, Cancelled |
| `PaymentTransactions.Status` | Pending, Success, Failed, Cancelled, Refunded |
| `WarrantyRequests.EligibilityStatus` | Pending, Eligible, Ineligible |
| `WarrantyRequests.Status` | New, Rejected, HandedOver, Processing, Completed, Cancelled |
| `ReturnRequests.Status` | Pending, Approved, Rejected, Receiving, Processing, Completed, Cancelled |
| `Conversations.Status` | Open, Closed |
| `NewsArticles.Status` | Draft, Published, Hidden |
| `Promotions.DiscountType` | Percentage, FixedAmount |
| `Users.Role` | Customer, Staff, Admin, SuperAdmin (theo `VieTech.docx` và `README.md`) |
| `OrderStatusHistories.OldStatus` / `NewStatus` | Cùng tập giá trị với `Orders.OrderStatus` |

---

## 3. Đặc tả bảng

### 3.1. Users

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| UserId | uuid | x | gen_random_uuid() | PK |
| Email | varchar(255) | x | | UQ không phân biệt hoa thường: `UNIQUE INDEX ON "Users"(lower("Email"))` |
| PhoneNumber | varchar(20) | x | | UQ |
| PasswordHash | varchar(255) | x | | |
| FullName | varchar(255) | x | | |
| Gender | varchar(10) | | | |
| DateOfBirth | date | | | |
| AvatarUrl | varchar(500) | | | |
| Role | varchar(20) | x | | CHECK Role IN (Customer, Staff, Admin, SuperAdmin) |
| AccountStatus | varchar(20) | x | | |
| IsEmailVerified | boolean | x | false | |
| OtpCode | varchar(10) | | | |
| OtpExpiredAt | timestamptz | | | |
| LockReason | text | | | |
| LockedUntil | timestamptz | | | |
| TotalSpent | numeric(15,2) | x | 0 | CHECK TotalSpent >= 0 |
| TotalOrders | integer | x | 0 | CHECK TotalOrders >= 0 |
| CreatedAt | timestamptz | x | now() | |
| UpdatedAt | timestamptz | x | now() | Tự cập nhật |
| IsDeleted | boolean | x | false | |

### 3.2. Addresses

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| AddressId | uuid | x | gen_random_uuid() | PK |
| UserId | uuid | x | | FK → Users, ON DELETE CASCADE |
| ReceiverName | varchar(255) | x | | |
| ReceiverPhone | varchar(20) | x | | |
| Province | varchar(100) | x | | |
| Ward | varchar(100) | x | | |
| DetailAddress | varchar(255) | x | | |
| IsDefault | boolean | x | false | |
| IsDeleted | boolean | x | false | |

### 3.3. Notifications

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| NotificationId | uuid | x | gen_random_uuid() | PK |
| UserId | uuid | x | | FK → Users, ON DELETE CASCADE |
| Title | varchar(255) | x | | |
| Content | text | x | | |
| NotificationType | varchar(50) | x | | |
| ActionUrl | varchar(500) | | | |
| ReferenceType | varchar(50) | | | |
| ReferenceId | uuid | | | Không có FK (tham chiếu đa hình) |
| IsRead | boolean | x | false | |
| ReadAt | timestamptz | | | |
| CreatedAt | timestamptz | x | now() | |

### 3.4. Categories

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| CategoryId | uuid | x | gen_random_uuid() | PK |
| ParentCategoryId | uuid | | | FK → Categories, ON DELETE RESTRICT |
| Name | varchar(255) | x | | |
| Slug | varchar(300) | x | | UQ |
| Description | text | | | |
| DisplayOrder | integer | x | 0 | |
| IsActive | boolean | x | true | |

### 3.5. Brands

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| BrandId | uuid | x | gen_random_uuid() | PK |
| Name | varchar(255) | x | | |
| Slug | varchar(300) | x | | UQ |
| Description | text | | | |
| LogoUrl | varchar(500) | | | |
| IsActive | boolean | x | true | |

### 3.6. Products

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ProductId | uuid | x | gen_random_uuid() | PK |
| CategoryId | uuid | x | | FK → Categories, ON DELETE RESTRICT |
| BrandId | uuid | x | | FK → Brands, ON DELETE RESTRICT |
| Name | varchar(255) | x | | |
| Slug | varchar(300) | x | | UQ |
| Description | text | | | |
| Specifications | jsonb | | | |
| WarrantyMonths | integer | x | | |
| Status | varchar(30) | x | | CHECK IN (Draft, Active, Inactive, Discontinued) |
| AverageRating | numeric(3,2) | x | 0 | CHECK AverageRating BETWEEN 0 AND 5 |
| ReviewCount | integer | x | 0 | CHECK ReviewCount >= 0 |
| SoldQuantity | integer | x | 0 | CHECK SoldQuantity >= 0 |
| CreatedAt | timestamptz | x | now() | |
| UpdatedAt | timestamptz | x | now() | Tự cập nhật |
| IsDeleted | boolean | x | false | |

### 3.7. ProductVariants

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ProductVariantId | uuid | x | gen_random_uuid() | PK |
| ProductId | uuid | x | | FK → Products, ON DELETE CASCADE |
| Sku | varchar(50) | x | | UQ |
| VariantName | varchar(255) | x | | |
| Color | varchar(50) | | | |
| Storage | varchar(50) | | | |
| Price | numeric(15,2) | x | | CHECK Price >= 0 |
| CostPrice | numeric(15,2) | x | 0 | CHECK CostPrice >= 0 — giá vốn hiện tại (COGS) |
| StockQuantity | integer | x | 0 | CHECK StockQuantity >= 0 |
| MinStockLevel | integer | x | 0 | CHECK MinStockLevel >= 0 |
| IsActive | boolean | x | true | |
| IsDeleted | boolean | x | false | |

### 3.8. ProductImages

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ProductImageId | uuid | x | gen_random_uuid() | PK |
| ProductId | uuid | x | | FK → Products, ON DELETE CASCADE |
| ImageUrl | varchar(500) | x | | |
| DisplayOrder | integer | x | 0 | |
| IsDefault | boolean | x | false | |

### 3.9. ProductSerials

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ProductSerialId | uuid | x | gen_random_uuid() | PK |
| ProductVariantId | uuid | x | | FK → ProductVariants, ON DELETE RESTRICT |
| OrderItemId | uuid | | | FK → OrderItems, ON DELETE SET NULL |
| SerialNumber | varchar(100) | x | | UQ |
| WarrantyStartDate | date | | | |
| WarrantyEndDate | date | | | |
| Status | varchar(30) | x | | CHECK IN (Available, Reserved, Sold, Warranty, Returned) |

### 3.10. Wishlists

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| WishlistId | uuid | x | gen_random_uuid() | PK |
| UserId | uuid | x | | FK → Users, ON DELETE CASCADE; UQ |
| CreatedAt | timestamptz | x | now() | |

### 3.11. WishlistItems

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| WishlistItemId | uuid | x | gen_random_uuid() | PK |
| WishlistId | uuid | x | | FK → Wishlists, ON DELETE CASCADE |
| ProductId | uuid | x | | FK → Products, ON DELETE CASCADE |
| AddedAt | timestamptz | x | now() | |

UQ (WishlistId, ProductId)

### 3.12. Carts

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| CartId | uuid | x | gen_random_uuid() | PK |
| UserId | uuid | x | | FK → Users, ON DELETE CASCADE; UQ |
| CreatedAt | timestamptz | x | now() | |
| UpdatedAt | timestamptz | x | now() | Tự cập nhật |

### 3.13. CartItems

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| CartItemId | uuid | x | gen_random_uuid() | PK |
| CartId | uuid | x | | FK → Carts, ON DELETE CASCADE |
| ProductVariantId | uuid | x | | FK → ProductVariants, ON DELETE CASCADE |
| Quantity | integer | x | | CHECK Quantity > 0 |
| UnitPrice | numeric(15,2) | x | | CHECK UnitPrice >= 0 |
| IsSelected | boolean | x | true | |
| AddedAt | timestamptz | x | now() | |

UQ (CartId, ProductVariantId)

### 3.14. ShippingMethods

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ShippingMethodId | uuid | x | gen_random_uuid() | PK |
| Code | varchar(50) | x | | UQ |
| Name | varchar(255) | x | | |
| BaseFee | numeric(15,2) | x | | CHECK BaseFee >= 0 |
| EstimatedDays | integer | x | | |
| IsActive | boolean | x | true | |

### 3.15. Orders

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| OrderId | uuid | x | gen_random_uuid() | PK |
| OrderCode | varchar(50) | x | | UQ |
| CustomerId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| AssignedStaffId | uuid | | | FK → Users, ON DELETE SET NULL |
| AddressId | uuid | | | FK → Addresses, ON DELETE SET NULL |
| ShippingMethodId | uuid | x | | FK → ShippingMethods, ON DELETE RESTRICT |
| PaymentMethodId | uuid | x | | FK → PaymentMethods, ON DELETE RESTRICT |
| CouponId | uuid | | | FK → Coupons, ON DELETE RESTRICT |
| Subtotal | numeric(15,2) | x | | CHECK Subtotal >= 0 |
| ShippingFee | numeric(15,2) | x | 0 | CHECK ShippingFee >= 0 |
| DiscountAmount | numeric(15,2) | x | | CHECK DiscountAmount >= 0 |
| TotalAmount | numeric(15,2) | x | | CHECK TotalAmount >= 0 |
| OrderStatus | varchar(30) | x | | CHECK IN (Pending, Confirmed, Processing, Shipping, Delivered, Completed, Cancelled) |
| PaymentStatus | varchar(30) | x | | CHECK IN (Pending, Paid, Failed, Refunded, Cancelled) |
| ReceiverName | varchar(255) | x | | |
| ReceiverPhone | varchar(20) | x | | |
| ShippingAddress | varchar(500) | x | | |
| CustomerNote | text | | | |
| InternalNote | text | | | |
| CancelReason | text | | | |
| OrderedAt | timestamptz | x | now() | |
| ConfirmedAt | timestamptz | | | |
| ShippedAt | timestamptz | | | |
| DeliveredAt | timestamptz | | | |
| CompletedAt | timestamptz | | | |
| CancelledAt | timestamptz | | | |

### 3.16. OrderItems

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| OrderItemId | uuid | x | gen_random_uuid() | PK |
| OrderId | uuid | x | | FK → Orders, ON DELETE CASCADE |
| ProductVariantId | uuid | x | | FK → ProductVariants, ON DELETE RESTRICT |
| ProductName | varchar(255) | x | | |
| Sku | varchar(50) | x | | |
| VariantInfo | varchar(255) | x | | |
| WarrantyMonths | integer | x | | |
| Quantity | integer | x | | CHECK Quantity > 0 |
| UnitPrice | numeric(15,2) | x | | CHECK UnitPrice >= 0 |
| UnitCost | numeric(15,2) | x | 0 | CHECK UnitCost >= 0 — giá vốn tại thời điểm bán (COGS) |
| DiscountAmount | numeric(15,2) | x | | CHECK DiscountAmount >= 0 |
| LineTotal | numeric(15,2) | x | | CHECK LineTotal >= 0 |

COGS:
- `ProductVariants.CostPrice` = giá vốn hiện tại.
- `OrderItems.UnitCost` = giá vốn tại thời điểm bán; khi tạo OrderItem, `UnitCost` lấy từ `ProductVariants.CostPrice`.
- COGS của một dòng = `UnitCost * Quantity`.

### 3.17. OrderStatusHistories

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| OrderStatusHistoryId | uuid | x | gen_random_uuid() | PK |
| OrderId | uuid | x | | FK → Orders, ON DELETE RESTRICT |
| ChangedByUserId | uuid | | | FK → Users, ON DELETE SET NULL |
| OldStatus | varchar(30) | | | CHECK IN (tập OrderStatus) |
| NewStatus | varchar(30) | x | | CHECK IN (tập OrderStatus) |
| Note | text | | | |
| ChangedAt | timestamptz | x | now() | |

### 3.18. PaymentMethods

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PaymentMethodId | uuid | x | gen_random_uuid() | PK |
| Code | varchar(50) | x | | UQ |
| Name | varchar(255) | x | | |
| Description | text | | | |
| IsActive | boolean | x | true | |
| DisplayOrder | integer | x | 0 | |

### 3.19. PaymentTransactions

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PaymentTransactionId | uuid | x | gen_random_uuid() | PK |
| OrderId | uuid | x | | FK → Orders, ON DELETE RESTRICT |
| PaymentMethodId | uuid | x | | FK → PaymentMethods, ON DELETE RESTRICT |
| GatewayTransactionCode | varchar(100) | | | |
| TransactionType | varchar(20) | x | | |
| Amount | numeric(15,2) | x | | CHECK Amount >= 0 |
| Status | varchar(30) | x | | CHECK IN (Pending, Success, Failed, Cancelled, Refunded) |
| QrData | text | | | |
| ResponseData | jsonb | | | |
| PaidAt | timestamptz | | | |
| CreatedAt | timestamptz | x | now() | |

### 3.20. Promotions

Promotion là nơi duy nhất quản lý thông tin giảm giá.

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PromotionId | uuid | x | gen_random_uuid() | PK |
| CreatedByUserId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| Name | varchar(255) | x | | |
| Description | text | | | |
| DiscountType | varchar(20) | x | | CHECK IN (Percentage, FixedAmount) |
| DiscountValue | numeric(15,2) | x | | CHECK DiscountValue >= 0 |
| MinOrderValue | numeric(15,2) | x | | CHECK MinOrderValue >= 0 |
| MaxDiscountAmount | numeric(15,2) | | | CHECK MaxDiscountAmount >= 0; NULL = không giới hạn |
| StartDate | timestamptz | x | | |
| EndDate | timestamptz | x | | CHECK EndDate >= StartDate |
| Status | varchar(30) | x | | CHECK IN (Draft, Scheduled, Active, Expired, Cancelled) |
| CreatedAt | timestamptz | x | now() | |

CHECK `"DiscountType" <> 'Percentage' OR "DiscountValue" <= 100` (giảm theo phần trăm không quá 100).

### 3.21. PromotionProducts

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PromotionId | uuid | x | | PK; FK → Promotions, ON DELETE CASCADE |
| ProductId | uuid | x | | PK; FK → Products, ON DELETE CASCADE |

### 3.22. PromotionCategories

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PromotionId | uuid | x | | PK; FK → Promotions, ON DELETE CASCADE |
| CategoryId | uuid | x | | PK; FK → Categories, ON DELETE CASCADE |

### 3.23. Coupons

Coupon chỉ lưu thông tin mã coupon và tham chiếu Promotion (bắt buộc). Toàn bộ thông tin giảm giá (DiscountType, DiscountValue, MinOrderValue, MaxDiscountAmount) và thời gian hiệu lực (StartDate, EndDate) lấy từ Promotion.

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| CouponId | uuid | x | gen_random_uuid() | PK |
| PromotionId | uuid | x | | FK → Promotions, ON DELETE RESTRICT |
| CreatedByUserId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| Code | varchar(50) | x | | UQ |
| Name | varchar(255) | x | | |
| UsageLimit | integer | | | CHECK UsageLimit >= 0 |
| UsedCount | integer | x | 0 | CHECK UsedCount >= 0 |
| IsActive | boolean | x | true | |
| CreatedAt | timestamptz | x | now() | |

### 3.24. Suppliers

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| SupplierId | uuid | x | gen_random_uuid() | PK |
| SupplierCode | varchar(50) | x | | UQ |
| Name | varchar(255) | x | | |
| Email | varchar(255) | | | |
| PhoneNumber | varchar(20) | x | | |
| Address | varchar(500) | x | | |
| TaxCode | varchar(20) | | | |
| IsActive | boolean | x | true | |
| Note | text | | | |

### 3.25. PurchaseOrders

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PurchaseOrderId | uuid | x | gen_random_uuid() | PK |
| PurchaseOrderCode | varchar(50) | x | | UQ |
| SupplierId | uuid | x | | FK → Suppliers, ON DELETE RESTRICT |
| CreatedByUserId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| DecidedByUserId | uuid | | | FK → Users, ON DELETE SET NULL |
| TotalAmount | numeric(15,2) | x | | CHECK TotalAmount >= 0 |
| Status | varchar(30) | x | | CHECK IN (Pending, Approved, Rejected, Receiving, Completed, Cancelled) |
| Note | text | | | |
| RejectReason | text | | | |
| CreatedAt | timestamptz | x | now() | |
| DecidedAt | timestamptz | | | |

### 3.26. PurchaseOrderItems

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PurchaseOrderItemId | uuid | x | gen_random_uuid() | PK |
| PurchaseOrderId | uuid | x | | FK → PurchaseOrders, ON DELETE CASCADE |
| ProductVariantId | uuid | x | | FK → ProductVariants, ON DELETE RESTRICT |
| OrderedQuantity | integer | x | | CHECK OrderedQuantity > 0 |
| ReceivedQuantity | integer | x | | CHECK ReceivedQuantity >= 0 |
| UnitPrice | numeric(15,2) | x | | CHECK UnitPrice >= 0 |
| LineTotal | numeric(15,2) | x | | CHECK LineTotal >= 0 |
| Note | text | | | |

CHECK `"ReceivedQuantity" <= "OrderedQuantity"` (kết hợp CHECK ReceivedQuantity >= 0: `0 <= ReceivedQuantity <= OrderedQuantity`).

### 3.27. Reviews

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ReviewId | uuid | x | gen_random_uuid() | PK |
| UserId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| ProductId | uuid | x | | FK → Products, ON DELETE RESTRICT |
| OrderItemId | uuid | x | | FK → OrderItems, ON DELETE RESTRICT; UQ |
| Rating | smallint | x | | CHECK Rating BETWEEN 1 AND 5 |
| Content | text | x | | |
| IsDeleted | boolean | x | false | |
| DeleteReason | text | | | |
| DeletedByUserId | uuid | | | FK → Users, ON DELETE SET NULL |
| DeletedAt | timestamptz | | | |
| CreatedAt | timestamptz | x | now() | |
| UpdatedAt | timestamptz | x | now() | Tự cập nhật |

### 3.28. ReviewImages

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ReviewImageId | uuid | x | gen_random_uuid() | PK |
| ReviewId | uuid | x | | FK → Reviews, ON DELETE CASCADE |
| ImageUrl | varchar(500) | x | | |
| DisplayOrder | integer | x | 0 | |

### 3.29. Conversations

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ConversationId | uuid | x | gen_random_uuid() | PK |
| CustomerId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| AssignedStaffId | uuid | | | FK → Users, ON DELETE SET NULL |
| Mode | varchar(20) | x | | |
| Status | varchar(30) | x | | CHECK IN (Open, Closed) |
| CreatedAt | timestamptz | x | now() | |
| ClosedAt | timestamptz | | | |

### 3.30. Messages

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| MessageId | uuid | x | gen_random_uuid() | PK |
| ConversationId | uuid | x | | FK → Conversations, ON DELETE CASCADE |
| SenderUserId | uuid | | | FK → Users, ON DELETE SET NULL |
| SenderType | varchar(20) | x | | |
| MessageType | varchar(20) | x | | |
| Content | text | x | | |
| Metadata | jsonb | | | |
| IsRead | boolean | x | false | |
| SentAt | timestamptz | x | now() | |

### 3.31. WarrantyRequests

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| WarrantyRequestId | uuid | x | gen_random_uuid() | PK |
| RequestCode | varchar(50) | x | | UQ |
| CustomerId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| AssignedStaffId | uuid | | | FK → Users, ON DELETE SET NULL |
| OrderItemId | uuid | x | | FK → OrderItems, ON DELETE RESTRICT |
| ProductSerialId | uuid | | | FK → ProductSerials, ON DELETE RESTRICT |
| SupplierId | uuid | | | FK → Suppliers, ON DELETE RESTRICT |
| IssueDescription | text | x | | Mô tả lỗi |
| EligibilityStatus | varchar(30) | x | | CHECK IN (Pending, Eligible, Ineligible) — kết quả kiểm tra điều kiện bảo hành |
| EligibilityReason | text | | | |
| Status | varchar(30) | x | | CHECK IN (New, Rejected, HandedOver, Processing, Completed, Cancelled) — trạng thái xử lý yêu cầu |
| ReceivedAt | timestamptz | | | |
| HandoverCode | varchar(50) | | | |
| ServiceCenter | varchar(255) | | | |
| HandedOverAt | timestamptz | | | |
| ResultType | varchar(30) | | | |
| ResultNote | text | | | |
| RequestedAt | timestamptz | x | now() | |
| CompletedAt | timestamptz | | | |

Luồng xử lý (nghiệp vụ, không ràng buộc bằng CHECK):
- Đủ điều kiện: `Status=New, EligibilityStatus=Pending` → `EligibilityStatus=Eligible` → `Status=HandedOver` → `Processing` → `Completed`.
- Không đủ điều kiện: `EligibilityStatus: Pending → Ineligible`, `Status → Rejected`.
- `Approved` không thuộc `WarrantyRequests.Status`.

### 3.32. ReturnRequests

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ReturnRequestId | uuid | x | gen_random_uuid() | PK |
| RequestCode | varchar(50) | x | | UQ |
| CustomerId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| AssignedStaffId | uuid | | | FK → Users, ON DELETE SET NULL |
| OrderItemId | uuid | x | | FK → OrderItems, ON DELETE RESTRICT |
| RequestType | varchar(20) | x | | |
| Reason | text | x | | |
| Status | varchar(30) | x | | CHECK IN (Pending, Approved, Rejected, Receiving, Processing, Completed, Cancelled) |
| DecisionReason | text | | | |
| DamageAssessment | text | | | |
| ResolutionType | varchar(30) | | | |
| CompensationAmount | numeric(15,2) | | | CHECK CompensationAmount >= 0 |
| RequestedAt | timestamptz | x | now() | |
| ReceivedAt | timestamptz | | | |
| CompletedAt | timestamptz | | | |

### 3.33. ServiceRequestAttachments

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ServiceRequestAttachmentId | uuid | x | gen_random_uuid() | PK |
| WarrantyRequestId | uuid | | | FK → WarrantyRequests, ON DELETE CASCADE |
| ReturnRequestId | uuid | | | FK → ReturnRequests, ON DELETE CASCADE |
| FileUrl | varchar(500) | x | | |
| FileType | varchar(20) | x | | |
| UploadedAt | timestamptz | x | now() | |

CHECK `num_nonnulls("WarrantyRequestId", "ReturnRequestId") = 1` (thuộc đúng một loại yêu cầu).

### 3.34. ServiceRequestHistories

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ServiceRequestHistoryId | uuid | x | gen_random_uuid() | PK |
| WarrantyRequestId | uuid | | | FK → WarrantyRequests, ON DELETE RESTRICT |
| ReturnRequestId | uuid | | | FK → ReturnRequests, ON DELETE RESTRICT |
| ChangedByUserId | uuid | | | FK → Users, ON DELETE SET NULL |
| OldStatus | varchar(30) | | | |
| NewStatus | varchar(30) | x | | |
| Note | text | | | |
| ChangedAt | timestamptz | x | now() | |

CHECK `num_nonnulls("WarrantyRequestId", "ReturnRequestId") = 1` (thuộc đúng một loại yêu cầu).

### 3.35. NewsArticles

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| NewsArticleId | uuid | x | gen_random_uuid() | PK |
| CreatedByUserId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| Title | varchar(255) | x | | |
| Slug | varchar(300) | x | | UQ |
| Summary | text | | | |
| Content | text | x | | |
| ThumbnailUrl | varchar(500) | | | |
| Status | varchar(30) | x | | CHECK IN (Draft, Published, Hidden) |
| PublishedAt | timestamptz | | | |
| CreatedAt | timestamptz | x | now() | |

### 3.36. Banners

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| BannerId | uuid | x | gen_random_uuid() | PK |
| CreatedByUserId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| Title | varchar(255) | x | | |
| ImageUrl | varchar(500) | x | | |
| LinkUrl | varchar(500) | | | |
| DisplayOrder | integer | x | 0 | |
| StartDate | timestamptz | | | |
| EndDate | timestamptz | | | CHECK EndDate >= StartDate (bỏ qua khi một trong hai NULL) |
| IsActive | boolean | x | true | |
| CreatedAt | timestamptz | x | now() | |

---

## 4. Thay đổi so với VieTech.docx

| Bảng | Thay đổi |
|---|---|
| Users | Email unique không phân biệt hoa thường (unique index trên `lower("Email")`). Thêm CHECK cho Role. |
| WarrantyRequests | `IssueDescription`: boolean → text, NOT NULL. |
| Reviews | Xóa `IsVerifiedPurchase`. |
| Coupons | Xóa `DiscountType`, `DiscountValue`, `MinOrderValue`, `MaxDiscountAmount`, `StartDate`, `EndDate`. `PromotionId` đổi sang NOT NULL. |
| Promotions | Thêm `MaxDiscountAmount numeric(15,2) NULL`, CHECK >= 0. CHECK DiscountType IN (Percentage, FixedAmount); Percentage thì DiscountValue <= 100. |
| ProductVariants | Thêm `CostPrice numeric(15,2) NOT NULL DEFAULT 0`, CHECK >= 0. |
| OrderItems | Thêm `UnitCost numeric(15,2) NOT NULL DEFAULT 0`, CHECK >= 0. |
| WarrantyRequests | CHECK cho `EligibilityStatus` (Pending, Eligible, Ineligible) và `Status` (không có Approved). |
| PurchaseOrderItems | CHECK `ReceivedQuantity <= OrderedQuantity`. |
| Toàn bộ | `timestamp` → `timestamptz`; thêm default cho PK, CreatedAt, UpdatedAt, boolean, counter; thêm CHECK cho status và giá trị số; thêm ON DELETE cho mọi FK. |
| ServiceRequestAttachments, ServiceRequestHistories | Thêm CHECK thuộc đúng một trong WarrantyRequest / ReturnRequest. |
