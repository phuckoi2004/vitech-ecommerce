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
| `ProductSerials.Status` | Available, Reserved, Sold, Warranty, Returned, WrittenOff (WrittenOff: migration `8b7e3d1c5a29`, chưa áp dụng) |
| `Promotions.Status` | Draft, Scheduled, Active, Expired, Cancelled |
| `PurchaseOrders.Status` | Pending, Approved, Rejected, Receiving, Completed, Cancelled, Closed (Closed: migration `e2b8c4f6a913`, chưa áp dụng) |
| `PaymentTransactions.Status` | Pending, Success, Failed, Cancelled, Refunded |
| `PaymentTransactions.TransactionType` | Payment, Refund |
| `PaymentTransactions.ResolutionSource` | Gateway, Manual; NULL = chưa có kết quả hoặc dữ liệu cũ; chỉ với Refund `Success`/`Failed` (CHECK: migration `a9f4c2e7b513`, chưa áp dụng) |
| `WarrantyRequests.EligibilityStatus` | Pending, Eligible, Ineligible |
| `WarrantyRequests.Status` | New, Rejected, HandedOver, Processing, Completed, Cancelled |
| `WarrantyRequests.ResultType` | Repaired, ProductReplaced, PartReplaced, NotRepairable (CHECK: migration `d4f7b2e9a6c1`, chưa áp dụng) |
| `ServiceRequestAttachments.FileType` | Image, Video (CHECK: migration `d4f7b2e9a6c1`, chưa áp dụng) |
| `ReturnRequests.Status` | Pending, Approved, Rejected, Receiving, Processing, Completed, Cancelled |
| `ReturnRequests.RequestType` | Exchange, Return (CHECK: migration `f3b8d1a5c7e2`, chưa áp dụng) |
| `Conversations.Status` | Open, Closed |
| `Conversations.Mode` | AI, Staff (CHECK: migration `c8d2f4a6b1e3`, chưa áp dụng) |
| `Messages.SenderType` | Customer, Staff, AI (CHECK: migration `c8d2f4a6b1e3`, chưa áp dụng) |
| `Messages.MessageType` | Text, Image, Product (CHECK: migration `c8d2f4a6b1e3`, chưa áp dụng) |
| `NewsArticles.Status` | Draft, Published, Hidden |
| `Promotions.DiscountType` | Percentage, FixedAmount |
| `Users.Role` | Customer, Staff, Admin |
| `Users.AccountStatus` | Active, Locked |
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
| Role | varchar(20) | x | | CHECK Role IN (Customer, Staff, Admin) |
| AccountStatus | varchar(20) | x | | CHECK AccountStatus IN (Active, Locked) |
| IsEmailVerified | boolean | x | false | |
| OtpCode | varchar(10) | | | Không còn dùng từ đợt 5.1 (OTP băm ở `OtpChallenges`) |
| OtpExpiredAt | timestamptz | | | Không còn dùng từ đợt 5.1 |
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
| IsSerialTracked | boolean | x | false | Biến thể quản lý Serial/IMEI (thêm bởi migration `763f153af842`, chưa áp dụng) |

`StockQuantity` và `CostPrice` không sửa qua CRUD biến thể: chỉ thay đổi qua đơn hàng, nhận hàng (giá vốn bình quân gia quyền), khai báo tồn đầu kỳ và điều chỉnh kho (`StockAdjustments`).

Bật/tắt `IsSerialTracked` chỉ khi `StockQuantity = 0`. Tắt (đợt 5.8, không đổi schema) còn bị từ chối (`serial_tracking_in_use`) khi biến thể có serial trạng thái khác `WrittenOff`, có bất kỳ dòng `OrderItems` nào (mọi trạng thái đơn: `OrderItems` không lưu dòng nào từng gắn serial và `ProductSerials.OrderItemId` chỉ giữ liên kết hiện tại), có yêu cầu bảo hành/đổi trả đang mở hoặc phiếu `ShipmentReturns` `AwaitingReturn`. Không xóa/đổi trạng thái serial hay lịch sử; cần bán không theo serial thì tạo biến thể mới.

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
| Status | varchar(30) | x | | CHECK IN (Available, Reserved, Sold, Warranty, Returned, WrittenOff) |

Thời hạn bảo hành (Service Layer `app/services/warranty_period.py`, đợt 5.1.1 — không đổi schema):
- Số tháng lấy từ `OrderItems.WarrantyMonths` (chụp lúc mua); `0` = không bảo hành (`WarrantyStartDate`/`WarrantyEndDate` đều NULL).
- Máy ban đầu: `WarrantyStartDate` = ngày lịch Việt Nam của `Orders.DeliveredAt`; `WarrantyEndDate` = bắt đầu + số tháng − 1 ngày; vượt cuối tháng đích thì lấy ngày cuối tháng đích trước khi trừ 1 ngày (31/01/2027 + 1 tháng → 27/02/2027).
- Còn bảo hành khi `WarrantyStartDate <= ngày (lịch Việt Nam) <= WarrantyEndDate`.
- Máy thay thế: thời hạn mới từ ngày Staff xác nhận bàn giao máy thay thế cho khách; không ghi đè ngày của serial cũ. Liên kết và thời điểm bàn giao lưu ở `WarrantyRequests.ReplacementProductSerialId` / `ReplacementHandedOverAt` / `ReplacementHandedOverByUserId` (migration `d4f7b2e9a6c1`, chưa áp dụng; `HandedOverAt` là bàn giao cho trung tâm bảo hành). Serial thay thế: `Sold`, gắn `OrderItemId` của dòng đơn gốc; serial cũ chuyển `Returned` (đã thu về, không phải hàng bán được — đợt 5.4.1), giữ ngày bảo hành và `OrderItemId`.

Sửa số Serial/IMEI nhập nhầm (`ProductSerialService.update_serial`, đợt 5.10 — không đổi schema): chỉ serial `Available`, chưa gắn dòng đơn và chưa có lịch sử ở `WarrantyRequests`, `ReturnRequests` hoặc `ShipmentReturnItems` (mọi trạng thái); serial đã bán rồi trả về/nhập lại tồn giữ số gốc. Serial `Returned` (máy cũ thu về khi đổi bảo hành, hàng hỏng của hàng hoàn vận chuyển) hiện chưa có luồng xử lý tiếp (sửa để bán lại hay loại bỏ): điều chỉnh kho chỉ nhận serial mới (tăng) hoặc serial `Available` (giảm), nên không thể chuyển `Returned` thành `Available`/`WrittenOff` qua đó.
- `Products.WarrantyMonths`/`OrderItems.WarrantyMonths` không có CHECK >= 0 trong database; Schema và Service chặn giá trị âm.

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
| EstimatedDays | integer | x | | Service: 0..30 (không có CHECK trong database) |
| IsActive | boolean | x | true | |

Nghiệp vụ (`ShippingMethodService`, đợt 5.10 — không đổi schema): chỉ Admin thêm/sửa/xóa; khách chỉ xem phương thức `IsActive = true`, xem tất cả cần Staff/Admin. `Code`/`Name` bỏ khoảng trắng đầu/cuối, không rỗng; `Code` duy nhất, phân biệt hoa thường như UQ. `EstimatedDays` là số nguyên từ 0 đến 30 (0 = giao trong ngày; đợt 5.13, kiểm tra ở Service, không đổi schema). Đổi `BaseFee` chỉ áp dụng cho đơn đặt sau (`Orders.ShippingFee` đã chụp). Ngừng sử dụng bằng `IsActive = false`; chỉ xóa được khi chưa có đơn hàng nào (mọi trạng thái) tham chiếu.

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

Chuyển `Delivered → Completed` (OrderService, đợt 5.9; không đổi schema): bị từ chối (`order_has_open_returns`) khi đơn còn `ReturnRequests` ở `Pending`/`Approved`/`Receiving`/`Processing` (gồm yêu cầu đổi hàng và yêu cầu có Refund `Pending`/`Failed` chưa hoàn tất); yêu cầu `Completed`/`Rejected`/`Cancelled` không chặn. Khi Completed: `Users.TotalSpent += TotalAmount`, `Users.TotalOrders += 1`, `Products.SoldQuantity +=` số lượng — số liệu lịch sử, cộng một lần; trả hàng/hoàn tiền không điều chỉnh (đã chốt ở đợt 5.12: số liệu lịch sử). `Coupons.UsedCount` chỉ được trả lại khi hủy đơn.

Hủy đơn (OrderService, đợt 5.13; không đổi schema): mọi đường hủy (khách, Staff/Admin, hết hạn QR) chuyển giao dịch `Payment` còn `Pending` (yêu cầu QR) sang `Cancelled`, giữ `GatewayTransactionCode`/`QrData`/`ResponseData` để đối soát; không đụng giao dịch `Success`/`Failed`/`Cancelled` và giao dịch Refund. `Cancelled` không chứng minh khách không thể chuyển khoản: tiền đến sau (callback/webhook) vẫn được ghi nhận `Success`, đơn giữ `Cancelled`, `PaymentStatus = Paid` (đã nhận tiền, chờ hoàn thủ công) và mở đối soát `PaymentAfterCancellation`; sai số tiền → `AmountMismatch`; không tự hoàn tiền.

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
| TransactionType | varchar(20) | x | | CHECK TransactionType IN (Payment, Refund) |
| Amount | numeric(15,2) | x | | CHECK Amount >= 0 |
| Status | varchar(30) | x | | CHECK IN (Pending, Success, Failed, Cancelled, Refunded) |
| QrData | text | | | |
| ResponseData | jsonb | | | |
| PaidAt | timestamptz | | | |
| CreatedAt | timestamptz | x | now() | |
| RefundOfPaymentTransactionId | uuid | | | FK → PaymentTransactions, ON DELETE RESTRICT — khoản Payment gốc của giao dịch Refund (migration `4c2d9e7a1f53`, chưa áp dụng) |
| CreatedByUserId | uuid | | | FK → Users, ON DELETE RESTRICT — người lập giao dịch Refund (migration `a9f4c2e7b513`, chưa áp dụng) |
| ResolvedByUserId | uuid | | | FK → Users, ON DELETE RESTRICT — Admin xác nhận thủ công |
| ResolvedAt | timestamptz | | | Thời điểm ghi kết quả (cổng hoặc thủ công) |
| ResolutionSource | varchar(20) | | | CHECK IN (Gateway, Manual) |
| EvidenceReference | varchar(255) | | | Mã tham chiếu bằng chứng của xác nhận thủ công |
| ResolutionNote | text | | | Ghi chú của xác nhận thủ công |

Liên kết hoàn tiền (migration `4c2d9e7a1f53`, **chưa áp dụng**):
- CHECK `(TransactionType = 'Refund' AND RefundOfPaymentTransactionId IS NOT NULL) OR (TransactionType <> 'Refund' AND RefundOfPaymentTransactionId IS NULL)`.
- Trigger `TR_PaymentTransactions_RefundSource`: nguồn phải là giao dịch `Payment` cùng `OrderId`; liên kết không đổi sau khi tạo; Payment đã có Refund không đổi loại/đơn.
- Index `("RefundOfPaymentTransactionId")`.
- Số còn có thể hoàn của một khoản Payment = `Amount` − tổng Refund `Success` − tổng Refund `Pending` trỏ tới khoản đó; Refund `Failed`/`Cancelled` không giữ tiền (PaymentService, khóa Order rồi khoản nguồn).
- Hoàn phần thu vượt của đơn chưa hủy (đợt 5.8, không đổi schema): còn hoàn được = (Σ Payment `Success` − `Orders.TotalAmount`) − Refund `Success`/`Pending` **không** liên kết `ReturnRequests.RefundPaymentTransactionId`, đồng thời không vượt Σ Payment `Success` − mọi Refund `Success`/`Pending`. Refund trả hàng hoàn giá trị hàng nên không làm giảm phần thu vượt.
- Khoản Payment gốc giữ `Status = Success` sau khi được hoàn (khoản thu đã xảy ra); giá trị `Refunded` của `PaymentTransactions.Status` hiện **không được sử dụng** — trạng thái hoàn của khoản gốc suy ra từ các Refund liên kết.
- Upgrade dừng nếu đã có giao dịch Refund cũ (chưa có liên kết, không suy đoán); downgrade dừng nếu đã có Refund liên kết.

Xác nhận kết quả Refund (đợt 5.11, phương án D2; migration `a9f4c2e7b513`, **chưa áp dụng**):
- Mọi giao dịch Refund tạo ở `Pending` với `CreatedByUserId` (Staff/Admin lập). Chỉ chuyển `Success`/`Failed` theo một trong hai cách: cổng thanh toán trả kết quả (`ResolutionSource = Gateway`, `ResolvedAt`; bằng chứng là `GatewayTransactionCode`/`ResponseData` của cổng, không có người xác nhận) hoặc Admin **khác người tạo** xác nhận thủ công (`ResolutionSource = Manual`, `ResolvedByUserId`, `ResolvedAt`, `EvidenceReference` và `ResolutionNote` bắt buộc; không ghi vào `GatewayTransactionCode`/`ResponseData`).
- Hoàn trực tiếp không qua cổng (ví dụ COD) và cổng không có API hoàn tiền (SePay) chỉ thành `Success` qua xác nhận thủ công. `Pending`/`Failed` không phải đã hoàn: không tính vào tiền đã hoàn, không đổi `Orders.PaymentStatus`, yêu cầu trả hàng chưa hoàn tất.
- Chỉ giao dịch còn `Pending` mới ghi được kết quả (khóa Order rồi giao dịch); kết quả cổng đến sau xác nhận thủ công (hoặc ngược lại) không ghi đè. Xác nhận thủ công `Success` kiểm tra lại tổng Refund `Success` không vượt số đã thu của đơn và của khoản nguồn.
- CHECK: `ResolutionSource_Valid`; `Resolution_Consistent` (chưa có kết quả thì mọi trường xác nhận NULL; có kết quả thì là Refund `Success`/`Failed` và có `ResolvedAt`); `GatewayResolution_NoManualFields`; `ManualResolution_Complete` (người xác nhận, mã bằng chứng, ghi chú không rỗng); `ManualResolution_NotByCreator` (bỏ qua khi `CreatedByUserId` NULL). Vai trò Admin do Service kiểm tra.
- Dữ liệu cũ: các cột mới để NULL (không suy diễn người tạo/xác nhận), thỏa mọi CHECK nên upgrade không dừng; Refund cũ đang `Pending` chưa có người tạo vẫn cần Admin và bằng chứng. Downgrade dừng nếu đã có dữ liệu người tạo/kết quả xác nhận.

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
| Code | varchar(50) | x | | UQ không phân biệt hoa thường: `UNIQUE INDEX ON "Coupons"(lower("Code"))` |
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
| ClosedByUserId | uuid | | | FK → Users, ON DELETE SET NULL (migration `e2b8c4f6a913`, chưa áp dụng) |
| ClosedAt | timestamptz | | | Thời điểm Admin đóng phiếu còn thiếu |
| CloseReason | text | | | Lý do đóng; CHECK Closed ⇔ ClosedAt và CloseReason (không rỗng) có giá trị |

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
| Mode | varchar(20) | x | | CHECK IN (AI, Staff) |
| Status | varchar(30) | x | | CHECK IN (Open, Closed) |
| CreatedAt | timestamptz | x | now() | |
| ClosedAt | timestamptz | | | |

`UNIQUE INDEX "UX_Conversations_CustomerId_Open" ON "Conversations"("CustomerId") WHERE "Status" = 'Open'`: mỗi Customer tối đa một hội thoại Open (migration `c8d2f4a6b1e3`, chưa áp dụng; upgrade dừng nếu dữ liệu cũ vi phạm — không tự đóng/xóa hội thoại).

Dữ liệu trả cho Customer (đợt 5.10): không có `AssignedStaffId`; tin nhắn của nhân viên/AI không kèm `Messages.SenderUserId` (định danh nhân viên là nội bộ, như `AssignedStaffId` ở Orders/WarrantyRequests/ReturnRequests). Staff/Admin dùng schema `Admin*` đầy đủ.

### 3.30. Messages

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| MessageId | uuid | x | gen_random_uuid() | PK |
| ConversationId | uuid | x | | FK → Conversations, ON DELETE CASCADE |
| SenderUserId | uuid | | | FK → Users, ON DELETE SET NULL |
| SenderType | varchar(20) | x | | CHECK IN (Customer, Staff, AI) |
| MessageType | varchar(20) | x | | CHECK IN (Text, Image, Product) |
| Content | text | x | | |
| Metadata | jsonb | | | |
| IsRead | boolean | x | false | |
| SentAt | timestamptz | x | now() | |

- CHECK `SenderType <> 'AI' OR SenderUserId IS NULL`: tin AI không gắn tài khoản người dùng (migration `c8d2f4a6b1e3`, chưa áp dụng).
- Metadata (ChatService): Image `{"ImageUrl": "https://..."}`; Product `{"ProductId", "ProductName", "Slug"}` do server ghi sau khi kiểm tra sản phẩm đang hiển thị; Text không có Metadata.
- Content tối đa 5.000 ký tự sau khi bỏ khoảng trắng đầu/cuối (Schema + ChatService, không tự cắt ngắn; không áp cho URL/Metadata). Không có thao tác cập nhật hội thoại tổng quát: AssignedStaffId chỉ đổi qua `claim_conversation`, Status qua `close_conversation` (Customer đóng hội thoại của mình; Staff/Admin đóng hội thoại được gán cho mình), Mode không đổi sau khi mở.

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
| ResultType | varchar(30) | | | CHECK IN (Repaired, ProductReplaced, PartReplaced, NotRepairable) |
| ResultNote | text | | | |
| RequestedAt | timestamptz | x | now() | |
| CompletedAt | timestamptz | | | |
| ResultApprovedByUserId | uuid | | | FK → Users, ON DELETE SET NULL — Admin duyệt kết quả |
| ResultApprovedAt | timestamptz | | | |
| ReplacementProductSerialId | uuid | | | FK → ProductSerials, ON DELETE RESTRICT — máy thay thế |
| ReplacementHandedOverAt | timestamptz | | | Staff xác nhận bàn giao máy thay thế cho khách |
| ReplacementHandedOverByUserId | uuid | | | FK → Users, ON DELETE SET NULL |
| ResultProposedByUserId | uuid | | | FK → Users, ON DELETE SET NULL — người đề xuất kết quả (migration `e6a2d9c4b8f1`) |
| ResultProposedAt | timestamptz | | | (migration `e6a2d9c4b8f1`) |

Năm cột cuối, CHECK và index dưới đây: migration `d4f7b2e9a6c1` (chưa áp dụng; upgrade dừng nếu dữ liệu cũ có ResultType/FileType ngoài danh sách, yêu cầu `Completed` chưa có thông tin duyệt, hoặc nhiều yêu cầu đang xử lý cho cùng serial/dòng đơn — không tự sửa dữ liệu).
- CHECK `Replacement_OnlyProductReplaced`: `ReplacementProductSerialId`/`ReplacementHandedOverAt` chỉ có khi `ResultType = 'ProductReplaced'`.
- CHECK `Approval_RequiresResult`: có `ResultApprovedAt` thì phải có `ResultType`.
- CHECK `Completed_RequiresApprovedResult`: `Completed` cần `CompletedAt`, `ResultType`, `ResultApprovedAt`; đổi máy cần thêm `ReplacementHandedOverAt`.
- Migration `e6a2d9c4b8f1` (chưa áp dụng; upgrade DỪNG nếu đã có dòng mang `ResultType` vì không xác định được người đề xuất): CHECK `Proposal_Recorded` (`ResultType IS NULL OR ResultProposedAt IS NOT NULL`); CHECK `Approval_NotByProposer` (người duyệt khác người đề xuất; bỏ qua khi một trong hai đã bị SET NULL).
- `UNIQUE INDEX "UX_WarrantyRequests_Serial_Open" ("ProductSerialId") WHERE "ProductSerialId" IS NOT NULL AND "Status" IN ('New', 'HandedOver', 'Processing')`; `UNIQUE INDEX "UX_WarrantyRequests_OrderItem_Open_NoSerial" ("OrderItemId") WHERE "ProductSerialId" IS NULL AND "Status" IN (...)`: mỗi serial / mỗi dòng đơn không quản lý serial tối đa một yêu cầu đang xử lý.

Luồng xử lý (WarrantyService, đợt 5.4; mỗi bước ghi `ServiceRequestHistories` — bước không đổi Status ghi OldStatus = NewStatus):
- Khách gửi (đơn Delivered/Completed): hệ thống kiểm tra thời hạn theo `warranty_period`. Còn hạn → `Status=New, EligibilityStatus=Pending`. Hết hạn / 0 tháng → hệ thống tự từ chối: `Rejected/Ineligible` + `EligibilityReason`, lịch sử `ChangedByUserId = NULL`, thông báo khách.
- Staff tiếp nhận (`ReceivedAt`, serial `Sold → Warranty`) → kiểm tra thực tế: `Eligible` (giữ New) hoặc `Ineligible` + lý do → `Rejected` (serial `→ Sold`).
- `New → HandedOver` (bàn giao trung tâm: `ServiceCenter`, `HandoverCode`, `SupplierId`, `HandedOverAt`) → `Processing`.
- Staff/Admin đề xuất `ResultType`/`ResultNote` (ghi `ResultProposedByUserId/At`; lịch sử nội bộ); một Admin KHÁC người đề xuất duyệt (`ResultApprovedAt/By`) hoặc từ chối đề xuất (xóa đề xuất, lý do lưu lịch sử nội bộ). Người đề xuất không tự duyệt/từ chối.
- `Processing → Completed` khi kết quả đã duyệt: trả máy cũ (serial `Warranty → Sold`) hoặc bàn giao máy thay thế (serial thay thế cùng biến thể, `Available`, chưa gắn đơn; tồn kho − 1; bảo hành mới từ ngày bàn giao; serial cũ `Warranty → Returned`). Đổi khác biến thể và đổi máy cho hàng không serial vẫn bị từ chối.
- Admin từ chối toàn bộ yêu cầu đã tiếp nhận, kết quả chưa duyệt (New/HandedOver/Processing → `Rejected`, `EligibilityStatus = Ineligible`, lý do công khai bắt buộc; serial `→ Sold`: trả khách theo khả năng hiện có, chưa có bước ghi nhận bàn giao vật lý).
- Customer chỉ hủy (`Cancelled`) khi còn New và chưa tiếp nhận sản phẩm (chưa có quy trình trả lại sản phẩm đã tiếp nhận). `Approved` không thuộc `WarrantyRequests.Status`.
- Khách hàng chỉ thấy `ResultType`/`ResultNote` sau khi kết quả được duyệt, và chỉ lịch sử công khai (xem 3.34).

### 3.32. ReturnRequests

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ReturnRequestId | uuid | x | gen_random_uuid() | PK |
| RequestCode | varchar(50) | x | | UQ |
| CustomerId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| AssignedStaffId | uuid | | | FK → Users, ON DELETE SET NULL |
| OrderItemId | uuid | x | | FK → OrderItems, ON DELETE RESTRICT |
| RequestType | varchar(20) | x | | CHECK IN (Exchange, Return) |
| Reason | text | x | | |
| Status | varchar(30) | x | | CHECK IN (Pending, Approved, Rejected, Receiving, Processing, Completed, Cancelled) |
| DecisionReason | text | | | Lý do từ chối |
| DamageAssessment | text | | | Đánh giá hư hại khi kiểm tra |
| ResolutionType | varchar(30) | | | (chưa dùng: chưa có danh sách giá trị) |
| CompensationAmount | numeric(15,2) | | | CHECK CompensationAmount >= 0 — số tiền dự kiến do server tính (không phải giao dịch) |
| RequestedAt | timestamptz | x | now() | |
| ReceivedAt | timestamptz | | | Hàng thực tế đã về cửa hàng |
| CompletedAt | timestamptz | | | |
| ProductSerialId | uuid | | | FK → ProductSerials, ON DELETE RESTRICT — serial thực tế được trả (NULL: hàng không quản lý serial) |
| Quantity | integer | x | | CHECK > 0; có serial thì = 1 |
| RestockedQuantity | integer | | | Số đạt khi kiểm tra (nhập lại tồn khi Admin duyệt) |
| DamagedQuantity | integer | | | Số hỏng (không nhập tồn) |
| CompensationBasis | jsonb | | | Căn cứ tính tiền (giá trị lịch sử dòng đơn, khấu trừ, công thức) |
| CompensationApprovedAt | timestamptz | | | Admin duyệt số tiền |
| CompensationApprovedByUserId | uuid | | | FK → Users, ON DELETE SET NULL |
| RefundPaymentTransactionId | uuid | | | FK → PaymentTransactions, ON DELETE RESTRICT, UQ — giao dịch Refund của yêu cầu |

Chín cột cuối, CHECK và index dưới đây: migration `f3b8d1a5c7e2` (chưa áp dụng; upgrade DỪNG nếu đã có dòng ReturnRequests vì không xác định được serial/số lượng của dữ liệu cũ; downgrade dừng nếu đã có dòng).
- CHECK `Inspection_Consistent`: RestockedQuantity/DamagedQuantity cùng NULL, hoặc >= 0 và cộng lại = Quantity; `Inspection_RequiresReceipt`: chỉ có sau khi `ReceivedAt`.
- CHECK `Approval_RequiresAssessment`: duyệt cần CompensationAmount và kết quả kiểm tra; `Refund_RequiresApprovedReturn`: liên kết hoàn tiền chỉ cho Return đã duyệt; `Completed_RequiresApproval`: Completed cần `CompletedAt` và đã duyệt.
- `UNIQUE INDEX "UX_ReturnRequests_Serial_Open" ("ProductSerialId") WHERE "ProductSerialId" IS NOT NULL AND "Status" IN ('Pending', 'Approved', 'Receiving', 'Processing')`: mỗi serial tối đa một yêu cầu đổi/trả đang xử lý.

Luồng xử lý (ReturnService, đợt 5.4; mỗi bước ghi `ServiceRequestHistories`):
- `Pending` (khách gửi; đơn Delivered/Completed; trong thời hạn `ReturnPolicy.window_days` — cấu hình ứng dụng `RETURN_WINDOW_DAYS` qua `ReturnPolicy.from_env`, mặc định 7 ngày, ngày giao (lịch Việt Nam) là ngày thứ nhất; Service không được truyền chính sách thì từ chối tạo; `DeliveredAt` thiếu múi giờ hoặc sau hiện tại → dữ liệu giao hàng không hợp lệ; không trùng yêu cầu đổi/trả hoặc bảo hành đang xử lý; hàng không serial: Quantity <= phần còn có thể trả) → `Approved` (Staff/Admin tiếp nhận) → `Receiving` (điều phối nhận hàng) → `Processing` (Staff xác nhận hàng thực tế đã về, quét đúng serial; serial `Sold → Returned`).
- Kiểm tra: số đạt/hỏng, đánh giá hư hại; server tính CompensationAmount + CompensationBasis từ `OrderItems.LineTotal` (phân bổ lũy kế theo số đã duyệt, không dùng giá catalog, không gồm phí vận chuyển, chưa có khấu trừ). Có hàng hỏng: chưa tính tiền (chưa có chính sách khấu trừ). Đổi hàng: chênh lệch = 0 (cùng biến thể, giá lịch sử). Số tiền tính ở bước kiểm tra là đề xuất nội bộ: schema của khách chỉ trả `CompensationAmount` khi đã có `CompensationApprovedAt` (đợt 5.10, cùng nguyên tắc với kết quả bảo hành chưa duyệt).
- Admin duyệt đúng số tiền đã tính → nhập lại tồn hàng đạt (serial `Returned → Available`, bỏ `OrderItemId`; StockQuantity + số đạt), một lần. Đổi hàng / có hàng hỏng: chưa duyệt được (thiếu quy tắc). Admin từ chối sau khi nhận hàng: trả hàng cho khách (serial `→ Sold`).
- Hoàn tiền qua PaymentService (Refund có `RefundOfPaymentTransactionId`) → `Completed` khi Refund `Success`; Refund `Pending` chưa phải đã hoàn. Rejected: Staff/Admin trước khi nhận hàng, Admin sau khi nhận hàng (bắt buộc lý do). Cancelled: khách hủy khi còn Pending.
- An toàn hoàn tiền (đợt 5.4.1): cổng chỉ được gọi sau khi commit; lỗi/timeout không bị coi là thất bại (Refund giữ `Pending`, vẫn giữ tiền, ghi lịch sử nội bộ); đang `Pending`/`Success` thì không tạo giao dịch mới; `Failed`/`Cancelled` mới tạo lại. Cổng hiện không có idempotency key/tra cứu trạng thái → đối soát thủ công (`resolve_pending_refund`, từ đợt 5.11 chỉ Admin khác người lập, kèm bằng chứng) trước khi thử lại. Hoàn trực tiếp (COD) cũng tạo `Pending` và chỉ hoàn tất yêu cầu sau khi Admin xác nhận rồi `confirm_return_refund`. Tổng Refund (Pending + Success) của đơn không vượt số đã thu. PaymentStatus của đơn đã giao không tự đổi; phí vận chuyển không hoàn.

### 3.33. ServiceRequestAttachments

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ServiceRequestAttachmentId | uuid | x | gen_random_uuid() | PK |
| WarrantyRequestId | uuid | | | FK → WarrantyRequests, ON DELETE CASCADE |
| ReturnRequestId | uuid | | | FK → ReturnRequests, ON DELETE CASCADE |
| FileUrl | varchar(500) | x | | URL https do client đã tải lên (Service kiểm tra) |
| FileType | varchar(20) | x | | CHECK IN (Image, Video) — migration `d4f7b2e9a6c1`, chưa áp dụng |
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
| Note | text | | | Nội dung khách hàng được xem |
| InternalNote | text | | | Chỉ Staff/Admin xem (migration `e6a2d9c4b8f1`) |
| IsInternal | boolean | x | false | Cả dòng chỉ Staff/Admin xem, ví dụ đề xuất/từ chối đề xuất kết quả (migration `e6a2d9c4b8f1`) |
| ChangedAt | timestamptz | x | now() | |

CHECK `num_nonnulls("WarrantyRequestId", "ReturnRequestId") = 1` (thuộc đúng một loại yêu cầu).
CHECK `Internal_NoPublicNote`: `NOT "IsInternal" OR "Note" IS NULL` (migration `e6a2d9c4b8f1`). Dòng cũ mặc định công khai. Schema dành cho khách chỉ trả dòng `IsInternal = false` và không có `InternalNote`; `ServiceRequestHistoryRepository.list_by_*` mặc định bỏ dòng nội bộ (`include_internal=True` cho Staff/Admin).

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

Nghiệp vụ (ContentService, đợt 5.5; không đổi schema):
- Chỉ Admin tạo/sửa/đăng/ẩn và xem bài chưa đăng. Bài mới luôn `Draft`; client không gửi `Status`/`PublishedAt`/`CreatedByUserId`.
- Đăng: `Draft`/`Hidden → Published`; `PublishedAt` = thời điểm đăng lần đầu (đăng lại sau khi ẩn giữ nguyên). Ẩn: `Published → Hidden`.
- Công khai: chỉ bài `Published` (danh sách theo `PublishedAt` mới nhất; xem theo `Slug`). Slug không rỗng, không có khoảng trắng, không trùng (UQ).
- Chưa có căn cứ, chưa triển khai: xóa bài, đưa bài đã đăng về `Draft`, hẹn giờ đăng, quyền nội dung của Staff.

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

Nghiệp vụ (ContentService, đợt 5.5; không đổi schema):
- Chỉ Admin tạo/sửa/kích hoạt/ngừng và xem toàn bộ. Banner mới theo mặc định `IsActive = true`; client không gửi `IsActive`/`CreatedByUserId`.
- Công khai: `IsActive` và thời điểm hiện tại trong `[StartDate, EndDate]` (tính cả hai mốc; mốc NULL = không giới hạn), sắp theo `DisplayOrder`.
- `StartDate`/`EndDate` phải có múi giờ, `EndDate >= StartDate` (kiểm tra với giá trị đang lưu khi chỉ sửa một mốc). `ImageUrl` là URL https; `LinkUrl` là URL https hoặc đường dẫn nội bộ bắt đầu bằng `/`.
- Chưa có căn cứ, chưa triển khai: xóa banner (ngừng bằng `IsActive = false`).

### 3.37. StockAdjustments

Lịch sử khai báo tồn đầu kỳ (Opening) và điều chỉnh kho thủ công của Admin. Thêm bởi migration `763f153af842` (**chưa áp dụng vào database**). Không phải sổ kho đầy đủ: nhập/bán vẫn truy vết qua PurchaseOrderItems/OrderItems.

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| StockAdjustmentId | uuid | x | gen_random_uuid() | PK |
| ProductVariantId | uuid | x | | FK → ProductVariants, ON DELETE RESTRICT |
| AdjustedByUserId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| AdjustmentType | varchar(20) | x | | CHECK IN (Opening, Increase, Decrease) |
| QuantityBefore | integer | x | | CHECK >= 0 |
| QuantityChange | integer | x | | CHECK QuantityChange = QuantityAfter − QuantityBefore; Increase > 0; Decrease < 0 |
| QuantityAfter | integer | x | | CHECK >= 0 |
| CostPriceBefore | numeric(15,2) | x | | CHECK >= 0 |
| CostPriceAfter | numeric(15,2) | x | | CHECK >= 0; khác CostPriceBefore chỉ khi AdjustmentType = Opening |
| Reason | text | x | | CHECK length(btrim(Reason)) > 0 |
| CreatedAt | timestamptz | x | now() | |

- `UNIQUE INDEX ON "StockAdjustments"("ProductVariantId") WHERE "AdjustmentType" = 'Opening'`: mỗi biến thể chỉ khai báo tồn đầu kỳ một lần.
- Index `("ProductVariantId", "CreatedAt")`.
- Chỉ ghi thêm: trigger `BEFORE UPDATE OR DELETE` từ chối sửa/xóa. RLS bật, REVOKE quyền của anon/authenticated như các bảng khác.

### 3.38. PaymentReconciliations

Khoản thanh toán bất thường cần Staff/Admin đối soát thủ công (không tự hoàn tiền). Thêm bởi migration `d3326a8fbc5c` (**chưa áp dụng vào database**).

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PaymentReconciliationId | uuid | x | gen_random_uuid() | PK |
| OrderId | uuid | | | FK → Orders, ON DELETE RESTRICT — NULL chỉ với `UnmatchedPayment` |
| PaymentTransactionId | uuid | | | FK → PaymentTransactions, ON DELETE RESTRICT — NULL chỉ với `UnmatchedPayment` |
| PaymentWebhookEventId | uuid | | | FK → PaymentWebhookEvents, ON DELETE RESTRICT (migration `b81569bc34b0`, chưa áp dụng) |
| IssueType | varchar(30) | x | | CHECK IN (AmountMismatch, DuplicatePayment, PaymentAfterCancellation, UnmatchedPayment) |
| GatewayTransactionCode | varchar(100) | x | | Mã giao dịch của cổng trong callback |
| ExpectedAmount | numeric(15,2) | | | CHECK >= 0 — NULL chỉ với `UnmatchedPayment` |
| ReceivedAmount | numeric(15,2) | x | | CHECK >= 0 |
| ResponseData | jsonb | | | Phản hồi (đã xác minh) của cổng |
| Status | varchar(20) | x | | CHECK IN (Open, Resolved) |
| ResolutionNote | text | | | |
| ResolvedByUserId | uuid | | | FK → Users, ON DELETE SET NULL |
| ResolvedAt | timestamptz | | | |
| CreatedAt | timestamptz | x | now() | |

- `UNIQUE ("GatewayTransactionCode", "IssueType")`: callback gửi lặp không tạo bản ghi trùng.
- CHECK `(Status = 'Open' AND ResolvedAt IS NULL) OR (Status = 'Resolved' AND ResolvedAt IS NOT NULL)`.
- CHECK `Matched_References_Required`: `IssueType = 'UnmatchedPayment' OR (OrderId IS NOT NULL AND PaymentTransactionId IS NOT NULL AND ExpectedAmount IS NOT NULL)`.
- Bảng trên là trạng thái sau toàn bộ chuỗi migration; phiên bản ban đầu (`d3326a8fbc5c`) có `OrderId`/`PaymentTransactionId`/`ExpectedAmount` NOT NULL và chưa có `UnmatchedPayment`/`PaymentWebhookEventId` (xem đoạn dưới).
- Index `("Status", "CreatedAt")`, `("OrderId")`. RLS bật, REVOKE quyền của anon/authenticated.

Thay đổi bởi migration `b81569bc34b0` (**chưa áp dụng**): thêm IssueType `UnmatchedPayment` (tiền vào không xác định được duy nhất một đơn/giao dịch); `OrderId`, `PaymentTransactionId`, `ExpectedAmount` cho phép NULL **chỉ** với `UnmatchedPayment` (CHECK `IssueType = 'UnmatchedPayment' OR (OrderId IS NOT NULL AND PaymentTransactionId IS NOT NULL AND ExpectedAmount IS NOT NULL)`); thêm `PaymentWebhookEventId uuid NULL` FK → PaymentWebhookEvents, ON DELETE RESTRICT. Với SePay, `GatewayTransactionCode` = `sepay:{AccountNumber}:{id}`.

### 3.39. PaymentWebhookEvents

Giao dịch ngân hàng nhận từ webhook (hiện tại: SePay), lưu bền vững trước khi xử lý nghiệp vụ. Thêm bởi migration `b81569bc34b0` (**chưa áp dụng vào database**). `Payload` chứa dữ liệu cá nhân (tên/nội dung chuyển khoản): không ghi log.

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PaymentWebhookEventId | uuid | x | gen_random_uuid() | PK |
| Provider | varchar(30) | x | | CHECK IN (SePay) |
| ProviderTransactionId | varchar(100) | x | | SePay `id` (không đổi qua các lần gửi lại) |
| AccountNumber | varchar(50) | x | | Tài khoản nhận |
| TransferType | varchar(10) | x | | CHECK IN (in, out) |
| TransferAmount | numeric(15,2) | x | | CHECK >= 0 |
| PaymentCode | varchar(100) | | | SePay `code` (NULL nếu không trích được) |
| ReferenceCode | varchar(100) | | | |
| TransactionDate | timestamptz | | | Giờ Việt Nam từ SePay, lưu UTC |
| Payload | jsonb | x | | Payload đã parse |
| Status | varchar(20) | x | | CHECK IN (Received, Processed, Ignored) |
| ProcessingNote | text | | | Kết quả xử lý (paid, amount_mismatch, unmatched, …) |
| PaymentTransactionId | uuid | | | FK → PaymentTransactions, ON DELETE RESTRICT |
| ReceivedAt | timestamptz | x | now() | |
| ProcessedAt | timestamptz | | | CHECK: NULL khi và chỉ khi Status = Received |

- `UNIQUE ("Provider", "AccountNumber", "ProviderTransactionId")` (tên `UQ_PaymentWebhookEvents_ProviderTxn`): chống xử lý trùng khi SePay gửi lại. Gồm `AccountNumber` vì phạm vi duy nhất của `id` SePay chưa được xác nhận.
- Index `("Status", "ReceivedAt")`, `("PaymentCode")`. RLS bật, REVOKE quyền của anon/authenticated.

### 3.40. StockAdjustmentSerials

Serial/IMEI thuộc từng phiếu điều chỉnh kho. Thêm bởi migration `8b7e3d1c5a29` (**chưa áp dụng vào database**).

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| StockAdjustmentId | uuid | x | | PK; FK → StockAdjustments, ON DELETE RESTRICT |
| ProductSerialId | uuid | x | | PK; FK → ProductSerials, ON DELETE RESTRICT |
| Direction | varchar(10) | x | | CHECK IN (In, Out) — In: Opening/Increase; Out: Decrease |

- `UNIQUE ("ProductSerialId", "Direction")`: một serial không bị nhập hai lần hoặc loại khỏi kho hai lần.
- Trigger `TR_StockAdjustmentSerials_Guard`: hướng khớp loại phiếu, serial cùng biến thể với phiếu; chỉ ghi thêm (chặn UPDATE/DELETE). RLS bật, REVOKE quyền của anon/authenticated.
- Điều chỉnh giảm biến thể quản lý serial: serial Available, chưa gắn đơn → `WrittenOff` + liên kết Out (cùng transaction với tồn kho và phiếu).
- Serial chỉ được tạo qua nhận hàng, tồn đầu kỳ hoặc điều chỉnh tăng; không xóa cứng; chỉ sửa `SerialNumber` khi serial Available, chưa gắn đơn, chưa có yêu cầu bảo hành.

### 3.41. ShipmentReturns

Hàng của đơn bị hủy khi đang giao (`Shipping`), chờ quay về kho. Thêm bởi migration `5d1f9a3c7e64` (**chưa áp dụng vào database**).

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ShipmentReturnId | uuid | x | gen_random_uuid() | PK |
| OrderId | uuid | x | | FK → Orders, ON DELETE RESTRICT; UQ (mỗi đơn tối đa một hồ sơ) |
| Status | varchar(20) | x | | CHECK IN (AwaitingReturn, Received) |
| CreatedByUserId | uuid | | | FK → Users, ON DELETE SET NULL (người hủy đơn) |
| CreatedAt | timestamptz | x | now() | |
| ReceivedByUserId | uuid | | | FK → Users, ON DELETE SET NULL |
| ReceivedAt | timestamptz | | | CHECK: NULL khi và chỉ khi Status = AwaitingReturn |
| Note | text | | | Ghi chú kiểm tra |

Index `("Status", "CreatedAt")`. RLS bật, REVOKE quyền của anon/authenticated.

### 3.42. ShipmentReturnItems

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| ShipmentReturnItemId | uuid | x | gen_random_uuid() | PK |
| ShipmentReturnId | uuid | x | | FK → ShipmentReturns, ON DELETE CASCADE |
| OrderItemId | uuid | x | | FK → OrderItems, ON DELETE RESTRICT |
| ProductSerialId | uuid | | | FK → ProductSerials, ON DELETE RESTRICT — một dòng mỗi serial |
| ExpectedQuantity | integer | x | | CHECK > 0; = 1 khi có ProductSerialId |
| RestockedQuantity | integer | | | Số nhập lại kho (NULL đến khi nhận hàng) |
| DamagedQuantity | integer | | | Số hỏng, không nhập tồn |

- CHECK: chưa nhận (cả hai NULL) hoặc `RestockedQuantity + DamagedQuantity = ExpectedQuantity` (đều >= 0).
- `UNIQUE INDEX (ShipmentReturnId, OrderItemId) WHERE ProductSerialId IS NULL`; `UNIQUE INDEX (ShipmentReturnId, ProductSerialId) WHERE ProductSerialId IS NOT NULL`; index `(ProductSerialId)`.
- Nghiệp vụ (OrderService): hủy trước Shipping hoàn tồn ngay; hủy khi đang Shipping không hoàn tồn, serial giữ Reserved, mở hồ sơ. Nhận lại (một lần): hàng đạt cộng tồn, serial → Available; hàng hỏng không cộng tồn, serial → Returned (không tự WrittenOff). Đơn đã Paid bị hủy giữ Paid và vào danh sách chờ hoàn tiền.

### 3.43. PurchaseReceipts

Mỗi lần nhận hàng thực tế của phiếu nhập. Thêm bởi migration `e2b8c4f6a913` (**chưa áp dụng vào database**). Chỉ ghi thêm (trigger `TR_PurchaseReceipts_AppendOnly`).

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PurchaseReceiptId | uuid | x | gen_random_uuid() | PK |
| PurchaseOrderId | uuid | x | | FK → PurchaseOrders, ON DELETE RESTRICT |
| ReceivedByUserId | uuid | x | | FK → Users, ON DELETE RESTRICT |
| ReceivedAt | timestamptz | x | now() | |
| Note | text | | | |

Index `("PurchaseOrderId", "ReceivedAt")`. RLS bật, REVOKE quyền của anon/authenticated.

### 3.44. PurchaseReceiptItems

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| PurchaseReceiptId | uuid | x | | PK; FK → PurchaseReceipts, ON DELETE CASCADE |
| PurchaseOrderItemId | uuid | x | | PK; FK → PurchaseOrderItems, ON DELETE RESTRICT |
| Quantity | integer | x | | CHECK > 0 — số thực nhận của dòng trong lần nhận |
| UnitPrice | numeric(15,2) | x | | CHECK >= 0 — đơn giá nhập dùng tính giá vốn |

Index `("PurchaseOrderItemId")`. Chỉ ghi thêm (trigger `TR_PurchaseReceiptItems_AppendOnly`). Các lần nhận trước migration không có lịch sử (không suy đoán dữ liệu cũ).

### 3.45. OtpChallenges

Mỗi lần gửi OTP theo tài khoản + mục đích. Thêm bởi migration `a7c3e9d1f285` (**chưa áp dụng vào database**).

| Column | Type | NN | Default | Ràng buộc |
|---|---|---|---|---|
| OtpChallengeId | uuid | x | gen_random_uuid() | PK |
| UserId | uuid | x | | FK → Users, ON DELETE CASCADE |
| Purpose | varchar(20) | x | | CHECK IN (Registration, PasswordReset) |
| CodeHash | varchar(255) | x | | Bản băm OTP (PasswordHasher); không lưu OTP văn bản thuần |
| ExpiresAt | timestamptz | x | | CreatedAt + 5 phút |
| FailedAttempts | integer | x | 0 | CHECK >= 0; mang sang lần gửi lại (trong 1 giờ, chưa dùng, chưa bị khóa) |
| LockedUntil | timestamptz | | | Khóa xác minh 15 phút sau 5 lần sai; trong lúc khóa cũng chặn gửi OTP mới |
| ConsumedAt | timestamptz | | | Đã xác minh thành công (dùng một lần) |
| CreatedAt | timestamptz | x | now() | Dùng cho giới hạn 60 giây/lần và 5 lần/giờ |

Index `("UserId", "Purpose", "CreatedAt")`. RLS bật, REVOKE quyền của anon/authenticated. UserService khóa dòng Users khi gửi/xác minh. `Users.OtpCode`/`OtpExpiredAt` giữ theo thiết kế nhưng không còn được dùng (migration xóa giá trị cũ).

---

## 4. Thay đổi so với VieTech.docx

| Bảng | Thay đổi |
|---|---|
| Users | Email unique không phân biệt hoa thường (unique index trên `lower("Email")`). Thêm CHECK cho Role (Customer, Staff, Admin) và AccountStatus (Active, Locked). |
| WarrantyRequests | `IssueDescription`: boolean → text, NOT NULL. |
| Reviews | Xóa `IsVerifiedPurchase`. |
| Coupons | Xóa `DiscountType`, `DiscountValue`, `MinOrderValue`, `MaxDiscountAmount`, `StartDate`, `EndDate`. `PromotionId` đổi sang NOT NULL. |
| Promotions | Thêm `MaxDiscountAmount numeric(15,2) NULL`, CHECK >= 0. CHECK DiscountType IN (Percentage, FixedAmount); Percentage thì DiscountValue <= 100. |
| ProductVariants | Thêm `CostPrice numeric(15,2) NOT NULL DEFAULT 0`, CHECK >= 0. |
| OrderItems | Thêm `UnitCost numeric(15,2) NOT NULL DEFAULT 0`, CHECK >= 0. |
| WarrantyRequests | CHECK cho `EligibilityStatus` (Pending, Eligible, Ineligible) và `Status` (không có Approved). |
| PaymentTransactions | CHECK `TransactionType` IN (Payment, Refund). |
| Coupons | `Code` unique không phân biệt hoa thường (unique index trên `lower("Code")`, thay UNIQUE thường). |
| PurchaseOrderItems | CHECK `ReceivedQuantity <= OrderedQuantity`. |
| Toàn bộ | `timestamp` → `timestamptz`; thêm default cho PK, CreatedAt, UpdatedAt, boolean, counter; thêm CHECK cho status và giá trị số; thêm ON DELETE cho mọi FK. |
| ServiceRequestAttachments, ServiceRequestHistories | Thêm CHECK thuộc đúng một trong WarrantyRequest / ReturnRequest. |
| ProductVariants | Thêm `IsSerialTracked boolean NOT NULL DEFAULT false` (migration `763f153af842`, chưa áp dụng). |
| StockAdjustments (mới) | Lịch sử Opening/điều chỉnh kho thủ công (migration `763f153af842`, chưa áp dụng). |
| PaymentReconciliations (mới) | Đối soát thanh toán sai số tiền/trùng/đến sau khi hủy (migration `d3326a8fbc5c`, chưa áp dụng). |
| PaymentReconciliations | Thêm `UnmatchedPayment`, cột tham chiếu NULL theo CHECK, `PaymentWebhookEventId` (migration `b81569bc34b0`, chưa áp dụng). |
| PaymentWebhookEvents (mới) | Sự kiện webhook ngân hàng (SePay), idempotent theo nhà cung cấp + tài khoản + id (migration `b81569bc34b0`, chưa áp dụng). |
| ProductSerials, StockAdjustmentSerials (mới) | Thêm trạng thái `WrittenOff`; bảng serial thuộc phiếu điều chỉnh In/Out (migration `8b7e3d1c5a29`, chưa áp dụng). |
| ShipmentReturns, ShipmentReturnItems (mới) | Hàng của đơn hủy khi đang giao chờ quay về kho; nhận lại + kiểm tra mới nhập tồn (migration `5d1f9a3c7e64`, chưa áp dụng). |
| PurchaseOrders, PurchaseReceipts, PurchaseReceiptItems (mới) | Trạng thái `Closed` + `ClosedByUserId`/`ClosedAt`/`CloseReason` (CHECK `Closed_Consistent`: Closed ⇔ có thời điểm và lý do không rỗng); lịch sử nhận hàng chỉ ghi thêm (migration `e2b8c4f6a913`, chưa áp dụng). |
| OtpChallenges (mới), Users | OTP băm theo mục đích, giới hạn gửi/nhập sai; `Users.OtpCode`/`OtpExpiredAt` không còn dùng (migration `a7c3e9d1f285`, chưa áp dụng). |
| Conversations, Messages | CHECK cho Mode/SenderType/MessageType, tin AI không gắn người dùng; partial UNIQUE một hội thoại Open mỗi Customer (migration `c8d2f4a6b1e3`, chưa áp dụng). |
| WarrantyRequests, ServiceRequestAttachments | Thêm cột Admin duyệt kết quả và máy thay thế; CHECK ResultType/FileType và nhất quán duyệt/hoàn tất/đổi máy; partial UNIQUE một yêu cầu đang xử lý mỗi serial / dòng đơn không serial (migration `d4f7b2e9a6c1`, chưa áp dụng). |
| ReturnRequests | Thêm serial/số lượng trả, kết quả kiểm tra, căn cứ và duyệt số tiền, liên kết giao dịch hoàn tiền (UNIQUE); CHECK RequestType và nhất quán kiểm tra/duyệt/hoàn tiền/hoàn tất; partial UNIQUE một yêu cầu đang xử lý mỗi serial (migration `f3b8d1a5c7e2`, chưa áp dụng). |
| WarrantyRequests, ServiceRequestHistories | Người/thời điểm đề xuất kết quả, CHECK người duyệt khác người đề xuất; ghi chú nội bộ `InternalNote` và dòng nội bộ `IsInternal` (migration `e6a2d9c4b8f1`, chưa áp dụng). |
| PaymentTransactions | Thêm `RefundOfPaymentTransactionId` (FK tự tham chiếu), CHECK nhất quán Refund/nguồn, trigger nguồn hoàn (migration `4c2d9e7a1f53`, chưa áp dụng). Thứ tự chuỗi: … → `d3326a8fbc5c` → `4c2d9e7a1f53` → `8b7e3d1c5a29` → `5d1f9a3c7e64` → `e2b8c4f6a913` → `a7c3e9d1f285` → `c8d2f4a6b1e3` → `d4f7b2e9a6c1` → `f3b8d1a5c7e2` → `e6a2d9c4b8f1` → `a9f4c2e7b513` → `b81569bc34b0` (SePay luôn cuối). |
| PaymentTransactions | Thêm `CreatedByUserId`, `ResolvedByUserId` (FK → Users, RESTRICT), `ResolvedAt`, `ResolutionSource` (Gateway/Manual), `EvidenceReference`, `ResolutionNote`; CHECK xác nhận thủ công đủ bằng chứng và khác người lập (migration `a9f4c2e7b513`, chưa áp dụng). |

## 5. Nguồn dữ liệu thống kê (StatisticsService, đợt 5.6 — không đổi schema)

Chỉ Admin; chỉ đọc (không đổi trạng thái đơn/thanh toán/tồn kho); tổng hợp trong SQL (`StatisticsRepository`). Khoảng thời gian là ngày lịch Việt Nam, tính cả ngày bắt đầu và ngày kết thúc, truy vấn dạng nửa mở `[00:00 ngày bắt đầu, 00:00 ngày sau ngày kết thúc)` giờ Việt Nam (đổi sang UTC).

| Chỉ số | Nguồn / cách tính |
|---|---|
| Đơn hàng | `Orders` theo `OrderedAt`; đếm theo `OrderStatus`. Hoàn tất = `Completed`; đã giao chưa hoàn tất = `Delivered`; đang xử lý = `Pending` + `Confirmed` + `Processing` + `Shipping`; hủy = `Cancelled`. |
| Đơn ghi nhận doanh thu | `OrderStatus` IN (`Delivered`, `Completed`), `DeliveredAt` trong khoảng, có ít nhất một `PaymentTransactions` Payment `Success`. |
| Giá trị đơn / phí giao | Σ `Orders.TotalAmount` / Σ `Orders.ShippingFee` của các đơn ghi nhận doanh thu. |
| Doanh thu gộp (tiền đã thu) | Σ Payment `Success` (cộng theo đơn trong subquery rồi mới JOIN — một đơn nhiều giao dịch không bị tính trùng). Payment `Pending`/`Failed` không tính. |
| Tiền hoàn đã hoàn tất | Σ Refund `Success` của các đơn ghi nhận doanh thu (mọi thời điểm hoàn đến lúc truy vấn). Refund `Pending` báo riêng, không trừ; `Failed`/`Cancelled` không tính. |
| Doanh thu thuần | Doanh thu gộp − tiền hoàn đã hoàn tất. Không phải lợi nhuận. |
| Giá vốn (COGS) | Σ `OrderItems.UnitCost` × `Quantity` (snapshot lúc đặt hàng) của các đơn ghi nhận doanh thu; `UnitCost = 0` = thiếu giá vốn → không trả tổng. Chưa trừ giá vốn hàng trả lại; không tính lợi nhuận. |
| Sản phẩm bán chạy | Nhóm `OrderItems` của các đơn ghi nhận doanh thu theo biến thể: Σ `Quantity`, Σ `LineTotal`. Số đã trả lại = Σ `ReturnRequests.Quantity` (Return, `Completed`) — chỉ tham khảo, không đổi thứ hạng. |
| Tồn kho | `ProductVariants.StockQuantity` (tồn khả dụng) của biến thể chưa xóa; serial theo `ProductSerials.Status` (Available/Reserved/Sold/Warranty/Returned/WrittenOff). Hàng không serial không có dữ liệu riêng cho đang giữ/trả về/hỏng; `Returned` không tách hàng hỏng. |
