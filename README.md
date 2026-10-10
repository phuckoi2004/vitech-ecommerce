# VieTech - Website bán hàng điện tử

## 1. Tổng quan dự án

VieTech là website thương mại điện tử kinh doanh các sản phẩm công nghệ và điện tử, hỗ trợ khách hàng tìm kiếm, lựa chọn và mua sắm sản phẩm trực tuyến; đồng thời cung cấp các chức năng quản trị hoạt động kinh doanh cho nhân viên và quản trị viên.

### Các chức năng chính

- Quản lý tài khoản, xác thực và phân quyền.
- Quản lý danh mục, thương hiệu và sản phẩm.
- Quản lý kho hàng, serial/IMEI và giá vốn hàng bán (COGS).
- Quản lý giỏ hàng, đơn hàng và vận chuyển.
- Quản lý thanh toán, đối soát và hoàn tiền.
- Quản lý nhà cung cấp, đơn đặt hàng nhập hàng và phiếu nhận hàng.
- Quản lý chương trình khuyến mãi và mã giảm giá.
- Quản lý đánh giá sản phẩm.
- Quản lý bảo hành, đổi trả và bồi thường.
- Quản lý nội dung website.
- AI Chatbot tư vấn sản phẩm.
- Product Recommendation Engine - hệ thống gợi ý sản phẩm.

### Tài liệu dự án

| Tài liệu | Mục đích |
|---|---|
| `README.md` | Tổng quan dự án, công nghệ, kiến trúc và quy tắc phát triển |
| `docs/business-requirements.md` | Đặc tả nghiệp vụ, quy trình xử lý và quy tắc của các chức năng |
| `docs/database-schema.md` | Nguồn chính thức về database schema |
| `docs/internal-endpoints.md` | Tài liệu về các điểm vào nội bộ và giới hạn sử dụng |
| `VieTech.docx` | Tài liệu tham khảo về yêu cầu tổng thể, ERD và thiết kế ban đầu (file bị `.gitignore` loại khỏi repository, không có sẵn khi clone) |

---

## 2. Công nghệ sử dụng

### 2.1. Frontend

- React
- Vite
- Tailwind CSS

### 2.2. Backend

- Python
- FastAPI
- SQLAlchemy
- Pydantic

### 2.3. Database

- Supabase
- PostgreSQL

### 2.4. Authentication và Authorization

- JWT - xác thực người dùng (triển khai ở Stage 5; chưa có trong source code hiện tại).
- RBAC - phân quyền dựa trên vai trò (Service Layer đã kiểm tra role qua `Actor`).

### 2.5. Công cụ phát triển

- Git
- GitHub
- Alembic - quản lý phiên bản thay đổi cấu trúc database.

---

## 3. Kiến trúc hệ thống

VieTech sử dụng kiến trúc Client–Server. Frontend giao tiếp với Backend thông qua HTTP API; Backend xử lý nghiệp vụ và truy cập PostgreSQL thông qua SQLAlchemy.

### 3.1. Kiến trúc tổng thể

```text
Customer / Staff / Admin
          |
          v
   Frontend React
          |
       HTTP API
          |
          v
    Backend FastAPI
          |
    +-----+------+
    |            |
  Router       Schema
    |
  Service
    |
 Repository
    |
   Model
    |
 SQLAlchemy
    |
    v
Supabase / PostgreSQL
```

AI Chatbot và Product Recommendation Engine là các thành phần nghiệp vụ dự kiến tích hợp vào hệ thống theo phạm vi triển khai tương ứng.

### 3.2. Các lớp Backend

**Router**

- Tiếp nhận HTTP request.
- Xác thực dữ liệu đầu vào thông qua Schema.
- Lấy thông tin người dùng và ngữ cảnh phân quyền.
- Gọi Service tương ứng.
- Chuyển kết quả hoặc lỗi nghiệp vụ thành HTTP response.

**Service**

- Xử lý logic nghiệp vụ.
- Kiểm tra điều kiện và trạng thái.
- Kiểm soát quyền truy cập theo Actor và RBAC.
- Điều phối nhiều Repository khi một nghiệp vụ liên quan đến nhiều bảng.
- Quản lý các thao tác cần tính nhất quán giao dịch.

**Repository**

- Thực hiện truy vấn và thao tác dữ liệu.
- Đóng gói các thao tác với SQLAlchemy.
- Hạn chế việc truy vấn database trực tiếp từ Service.

**Model**

- Ánh xạ bảng PostgreSQL bằng SQLAlchemy ORM.
- Khai báo cột, khóa, quan hệ và các cấu hình tương ứng với đặc tả database.

**Schema**

- Sử dụng Pydantic để kiểm tra dữ liệu request.
- Định nghĩa cấu trúc response.
- Kiểm soát dữ liệu được phép trả về cho từng nhóm người dùng.

### 3.3. Quy tắc phụ thuộc

Luồng phụ thuộc nghiệp vụ:

```text
Router → Service → Repository → Model
```

Schema được sử dụng tại ranh giới request/response. Service không tự ý thực hiện truy vấn SQL trực tiếp hoặc bỏ qua Repository để truy cập database.

Các điểm vào nội bộ phục vụ callback, webhook hoặc tác vụ nền phải tuân theo thiết kế bảo mật riêng, không mặc nhiên được phép công khai thành API.

---

## 4. Cấu trúc thư mục dự án

```text
VieTech/
├── README.md
├── VieTech.docx                  # tài liệu tham khảo, bị .gitignore
│
├── docs/
│   ├── business-requirements.md
│   ├── database-schema.md
│   └── internal-endpoints.md
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── customer/
│   │   │   ├── pages/
│   │   │   ├── components/
│   │   │   ├── layouts/
│   │   │   └── routes/
│   │   │
│   │   ├── admin/
│   │   │   ├── pages/
│   │   │   ├── components/
│   │   │   ├── layouts/
│   │   │   └── routes/
│   │   │
│   │   ├── components/
│   │   │   └── shared/
│   │   │
│   │   ├── services/
│   │   │   └── api/
│   │   │
│   │   ├── auth/
│   │   ├── assets/
│   │   ├── App.jsx
│   │   └── main.jsx
│   │
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── backend/
│   ├── app/
│   │   ├── core/                 # hiện chỉ có .gitkeep
│   │   ├── integrations/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── routers/
│   │   │   ├── customer/         # hiện chỉ có .gitkeep (Stage 6)
│   │   │   ├── admin/            # hiện chỉ có .gitkeep (Stage 6)
│   │   │   └── webhooks.py       # chưa đăng ký trong main.py
│   │   ├── database.py
│   │   └── main.py
│   │
│   ├── alembic/
│   │   └── versions/
│   ├── alembic.ini
│   ├── tests/
│   ├── .env                      # bí mật, bị .gitignore, không commit
│   ├── .env.example
│   └── requirements.txt
│
└── .gitignore
```

Cấu trúc trên mô tả các nhóm thư mục chính. Một số thư mục hoặc module có thể tiếp tục được bổ sung theo tiến độ phát triển. Cần kiểm tra source code thực tế trước khi tạo mới hoặc thay đổi cấu trúc.

### Vai trò các thư mục

- `frontend/src/customer/`: giao diện dành cho khách hàng.
- `frontend/src/admin/`: giao diện quản trị dành cho Staff và Admin theo quyền được cấp.
- `frontend/src/services/api/`: các module giao tiếp với Backend.
- `frontend/src/auth/`: quản lý trạng thái xác thực và quyền truy cập phía client.
- `backend/app/core/`: cấu hình, bảo mật và các thành phần dùng chung.
- `backend/app/models/`: SQLAlchemy Models.
- `backend/app/schemas/`: Pydantic Schemas.
- `backend/app/repositories/`: truy vấn và thao tác dữ liệu.
- `backend/app/services/`: xử lý nghiệp vụ.
- `backend/app/routers/`: các điểm tiếp nhận HTTP request.
- `backend/app/integrations/`: tích hợp với hệ thống bên ngoài.
- `backend/alembic/versions/`: các phiên bản migration.
- `backend/tests/`: bộ kiểm thử tự động.
- `docs/`: tài liệu đặc tả và hướng dẫn dự án.

---

## 5. Database và quản lý migration

### 5.1. Nguyên tắc database

VieTech sử dụng Supabase PostgreSQL làm hệ quản trị cơ sở dữ liệu.

Thông tin kết nối được cấu hình thông qua biến môi trường:

```text
DATABASE_URL
```

Quy định bảo mật:

- Không hard-code database credentials trong source code.
- Không commit `backend/.env` hoặc các file chứa bí mật.
- `backend/.env.example` chỉ chứa giá trị mẫu và không được chứa credentials thật.
- Không in hoặc tiết lộ thông tin kết nối trong log, response API hoặc báo cáo.
- Chỉ kết nối database thực tế khi được yêu cầu hoặc cho phép.

### 5.2. Nguồn chính thức về database schema

`docs/database-schema.md` là **SOURCE OF TRUTH cho database schema**.

Mọi thay đổi liên quan đến cấu trúc database phải đối chiếu tài liệu này, bao gồm:

- Tên bảng và tên cột.
- Kiểu dữ liệu, giá trị mặc định và tính nullable.
- Primary key, foreign key và quan hệ.
- Unique constraint, CHECK constraint và index.
- Quy tắc ON DELETE.
- Các trạng thái và ràng buộc dữ liệu ở mức database.

Không tự ý thêm, xóa, đổi tên bảng hoặc cột, hay thay đổi quan hệ giữa các bảng.

Nếu phát hiện schema trong Model, migration hoặc database thực tế khác với đặc tả, phải báo cáo và xác định nguyên nhân trước khi sửa.

### 5.3. Quản lý migration

Migration nằm trong:

```text
backend/alembic/versions/
```

Các nguyên tắc:

- Duy trì chuỗi migration tuyến tính theo lịch sử đã thống nhất.
- Kiểm tra `revision` và `down_revision` trước khi thêm migration.
- Không tạo revision trùng, thiếu dependency hoặc nhiều head ngoài chủ đích.
- Không sửa migration đã được áp dụng trên môi trường dùng chung nếu chưa có kế hoạch xử lý phù hợp.
- Không chạy migration khi chưa được yêu cầu.
- Không mặc định database thực tế đang ở revision mới nhất.
- Trước khi triển khai, kiểm tra `alembic_version`, dữ liệu hiện có và điều kiện tiền kiểm trên bản sao staging.

### 5.4. Trạng thái migration hiện tại

Theo trạng thái dự án đã được rà soát trước khi commit Stage 4:

- Chuỗi migration gồm 19 file, tuyến tính, một root (`2cb2e7418b06`) và một head (`b81569bc34b0`); không có revision trùng hoặc dependency bị thiếu.
- 2 file đã có trong lịch sử Git trước Stage 4 (`2cb2e7418b06`, `4ee28b0095ef`); 17 file còn lại được bổ sung trong commit Stage 4 (`9489aac`).
- `docs/database-schema.md` ghi các migration từ `763f153af842` trở đi là chưa áp dụng. Trạng thái của các migration trước đó trên database thực tế chưa được ghi nhận, phải kiểm tra bằng `alembic_version`.
- Chưa có migration nào trong 17 file mới được áp dụng hoặc kiểm thử trên PostgreSQL thật. Các kiểm tra offline (đọc tĩnh chuỗi revision, phát lại thao tác so với Model) không thay thế cho việc kiểm thử trên database thực tế.

Toàn bộ chuỗi migration (`*` = bổ sung trong Stage 4):

```text
2cb2e7418b06    khởi tạo schema
    ↓
4ee28b0095ef    bảo mật bảng alembic_version
    ↓
b5d3a7c912e4 *  bỏ role SuperAdmin
    ↓
dd773e03e503 *  CHECK AccountStatus
    ↓
9b10f42fc70d *  CHECK TransactionType
    ↓
213feab4a632 *  mã coupon duy nhất, không phân biệt hoa thường
    ↓
763f153af842 *  tồn kho, điều chỉnh kho, quản lý serial
    ↓
d3326a8fbc5c *  đối soát thanh toán
    ↓
4c2d9e7a1f53 *  liên kết Refund với khoản thanh toán gốc
    ↓
8b7e3d1c5a29 *  serial WrittenOff, serial của phiếu điều chỉnh
    ↓
5d1f9a3c7e64 *  hàng hoàn vận chuyển
    ↓
e2b8c4f6a913 *  phiếu nhận hàng, trạng thái Closed
    ↓
a7c3e9d1f285 *  OTP
    ↓
c8d2f4a6b1e3 *  hội thoại đang mở, CHECK chat
    ↓
d4f7b2e9a6c1 *  bảo hành: máy thay thế, duyệt kết quả
    ↓
f3b8d1a5c7e2 *  đổi trả: serial, số lượng, bồi thường
    ↓
e6a2d9c4b8f1 *  bảo hành: người đề xuất, ghi chú nội bộ
    ↓
a9f4c2e7b513 *  xác nhận hoàn tiền (người lập, người xác nhận, bằng chứng)
    ↓
b81569bc34b0 *  webhook SePay, đối soát UnmatchedPayment (luôn cuối chuỗi)
```

Migration `a9f4c2e7b513` bổ sung thông tin phục vụ quy trình xác nhận hoàn tiền trong `PaymentTransactions`, gồm người lập, người xác nhận, thời điểm xác nhận, nguồn xác nhận, bằng chứng và ghi chú.

Migration SePay `b81569bc34b0` phải tiếp tục đứng cuối chuỗi theo thiết kế hiện tại. Nếu bổ sung migration mới, phải kiểm tra dependency và xác nhận lại cách duy trì chuỗi trước khi thực hiện.

Một số migration có điều kiện dừng khi dữ liệu cũ không thể được chuyển đổi an toàn. Cần đọc docstring và nội dung từng migration trước khi triển khai.

---

## 6. Các nhóm bảng trong database

Danh sách dưới đây tóm tắt các nhóm bảng của hệ thống. Thuộc tính, khóa, kiểu dữ liệu, constraint và quan hệ chính thức được xác định tại `docs/database-schema.md`.

### 6.1. Quản lý người dùng

- `Users`
- `Addresses`
- `Notifications`
- `OtpChallenges`

`OtpChallenges` phục vụ quy trình OTP. Migration `a7c3e9d1f285` chưa được áp dụng theo trạng thái đã ghi nhận.

### 6.2. Quản lý danh mục và sản phẩm

- `Categories`
- `Brands`
- `Products`
- `ProductVariants`
- `ProductImages`
- `ProductSerials`
- `StockAdjustments`
- `StockAdjustmentSerials`

`StockAdjustments` lưu lịch sử điều chỉnh tồn kho. `StockAdjustmentSerials` ghi nhận serial thuộc phiếu điều chỉnh In/Out.

Các migration liên quan gồm `763f153af842` và `8b7e3d1c5a29`; chưa được áp dụng theo trạng thái đã ghi nhận.

### 6.3. Quản lý yêu thích và giỏ hàng

- `Wishlists`
- `WishlistItems`
- `Carts`
- `CartItems`

### 6.4. Quản lý đơn hàng và vận chuyển

- `ShippingMethods`
- `Orders`
- `OrderItems`
- `OrderStatusHistories`
- `ShipmentReturns`
- `ShipmentReturnItems`

`ShipmentReturns` và `ShipmentReturnItems` hỗ trợ ghi nhận hàng của đơn đã hủy trong quá trình giao hàng cần quay về kho. Migration `5d1f9a3c7e64` chưa được áp dụng theo trạng thái đã ghi nhận.

### 6.5. Quản lý thanh toán và đối soát

- `PaymentMethods`
- `PaymentTransactions`
- `PaymentReconciliations`
- `PaymentWebhookEvents`

`PaymentTransactions` lưu các giao dịch thanh toán và thông tin liên quan đến hoàn tiền.

`PaymentReconciliations` ghi nhận các khoản thanh toán bất thường cần được đối soát.

`PaymentWebhookEvents` lưu sự kiện nhận từ webhook thanh toán SePay. Tích hợp SePay hiện chưa được kích hoạt trong ứng dụng.

Các migration liên quan gồm:

- `4c2d9e7a1f53`: liên kết giao dịch Refund với khoản thanh toán gốc.
- `a9f4c2e7b513`: thông tin xác nhận hoàn tiền.
- `d3326a8fbc5c`: đối soát thanh toán.
- `b81569bc34b0`: sự kiện webhook SePay và các thay đổi liên quan.

Các migration này chưa được áp dụng theo trạng thái đã ghi nhận.

### 6.6. Quản lý khuyến mãi

- `Promotions`
- `PromotionProducts`
- `PromotionCategories`
- `Coupons`

### 6.7. Quản lý nhà cung cấp và nhập hàng

- `Suppliers`
- `PurchaseOrders`
- `PurchaseOrderItems`
- `PurchaseReceipts`
- `PurchaseReceiptItems`

Các bảng phiếu nhận hàng ghi nhận lịch sử từng lần nhận hàng. Migration `e2b8c4f6a913` chưa được áp dụng theo trạng thái đã ghi nhận.

### 6.8. Quản lý đánh giá

- `Reviews`
- `ReviewImages`

### 6.9. Quản lý chatbot

- `Conversations`
- `Messages`

Hội thoại của khách hàng với chatbot AI hoặc với nhân viên. Ràng buộc mỗi khách hàng tối đa một hội thoại đang mở và CHECK cho chế độ/loại tin nhắn thuộc migration `c8d2f4a6b1e3` (chưa áp dụng theo trạng thái đã ghi nhận).

### 6.10. Quản lý bảo hành và đổi trả

- `WarrantyRequests`
- `ReturnRequests`
- `ServiceRequestAttachments`
- `ServiceRequestHistories`

### 6.11. Quản lý nội dung

- `NewsArticles`
- `Banners`

Tổng số bảng theo tài liệu và báo cáo kiểm tra hiện tại là 45 bảng. Khi thay đổi schema, phải xác minh lại số lượng và cấu trúc thực tế thay vì dựa vào con số cố định này.

---

## 7. Các quan hệ dữ liệu chính

Các quan hệ dưới đây là phần tóm tắt để dễ hình dung. Cardinality, khóa ngoại và các quan hệ còn lại phải được xác nhận theo `docs/database-schema.md`.

```text
Users 1 - N Addresses
Users 1 - N Notifications

Categories 1 - N Categories
Categories 1 - N Products
Brands 1 - N Products

Products 1 - N ProductVariants
Products 1 - N ProductImages
ProductVariants 1 - N ProductSerials

Users 1 - 1 Wishlists
Wishlists 1 - N WishlistItems
Products 1 - N WishlistItems

Users 1 - 1 Carts
Carts 1 - N CartItems
ProductVariants 1 - N CartItems

Users 1 - N Orders
Orders 1 - N OrderItems
Orders 1 - N OrderStatusHistories

Orders 1 - N PaymentTransactions
PaymentMethods 1 - N PaymentTransactions

Promotions N - N Products
Promotions N - N Categories
Promotions 1 - N Coupons

Suppliers 1 - N PurchaseOrders
PurchaseOrders 1 - N PurchaseOrderItems

Users 1 - N Reviews
Products 1 - N Reviews
Reviews 1 - N ReviewImages
```

Các quan hệ bổ sung liên quan đến tồn kho, thanh toán, đối soát, nhập hàng, vận chuyển, bảo hành, đổi trả và các chức năng khác được xác định trong tài liệu schema chính thức.

Không dùng danh sách tóm tắt này để tự tạo hoặc thay đổi khóa ngoại.

---

## 8. Người dùng và phân quyền

Hệ thống có ba vai trò:

- `Customer`: khách hàng.
- `Staff`: nhân viên.
- `Admin`: quản trị viên.

VieTech sử dụng RBAC để kiểm soát quyền truy cập.

Các nguyên tắc:

- Backend là nơi thực thi kiểm tra quyền có tính bảo mật.
- Không dựa vào việc ẩn nút hoặc ẩn trang trên Frontend để bảo vệ dữ liệu.
- Kiểm tra quyền sở hữu tài nguyên trước khi cho phép khách hàng xem hoặc thay đổi dữ liệu.
- Các thao tác quản trị phải xác minh role và quyền tương ứng.
- Không sử dụng role `SuperAdmin`.
- Các điểm vào nội bộ không có Actor phải được bảo vệ bằng cơ chế xác thực phù hợp với từng loại callback, webhook hoặc tác vụ nền; không được tự ý công khai.

Quy tắc nghiệp vụ chi tiết về vai trò, quyền hạn và điều kiện xử lý được đặc tả trong `docs/business-requirements.md`.

---

## 9. Quy tắc phát triển

### 9.1. Đọc tài liệu trước khi thay đổi

- Đọc `README.md` trước khi thực hiện task.
- Đọc `docs/database-schema.md` khi task liên quan đến database schema, Model, Repository có truy vấn dữ liệu, constraint hoặc migration.
- Đọc `docs/business-requirements.md` khi task liên quan đến quy trình nghiệp vụ, điều kiện xử lý, trạng thái hoặc quyền hạn.
- Đọc `docs/internal-endpoints.md` khi task liên quan đến callback, webhook hoặc các điểm vào nội bộ.
- Đọc `VieTech.docx` khi cần tham khảo yêu cầu tổng thể, ERD hoặc thiết kế ban đầu.
- Kiểm tra source code hiện tại trước khi sửa.

### 9.2. Bảo vệ database và dữ liệu

- Không tự ý thay đổi database schema.
- Không tự ý chạy migration.
- Không kết nối hoặc thay đổi database thật khi chưa được yêu cầu hoặc cho phép.
- Không hard-code secret.
- Không commit `.env`.
- Không in hoặc tiết lộ credentials.
- Nếu schema thực tế khác đặc tả, báo cáo sự khác biệt trước khi thay đổi.

### 9.3. Bảo toàn kiến trúc

- Tuân thủ kiến trúc Router → Service → Repository → Model.
- Giữ ranh giới trách nhiệm giữa các lớp.
- Không đưa logic nghiệp vụ phức tạp trực tiếp vào Router.
- Không để Service tự ý truy vấn database ngoài Repository.
- Không trả dữ liệu nội bộ hoặc thông tin nhạy cảm trong response.
- Không mở điểm vào nội bộ thành API công khai nếu chưa được thiết kế và phê duyệt.

### 9.4. Kiểm thử và thay đổi code

- Ưu tiên thay đổi nhỏ, rõ ràng và đúng phạm vi.
- Bổ sung hoặc cập nhật test khi thay đổi logic nghiệp vụ.
- Chạy các bài kiểm thử phù hợp bằng môi trường hiện có.
- Bộ test hiện tại dùng `unittest` (thư viện chuẩn của Python); `pytest` chưa có trong dependency. Từ thư mục `backend`:

  ```powershell
  .\.venv\Scripts\python.exe -m unittest discover -s tests -t .
  ```

- Bộ test chạy trên fake/in-memory, không kết nối database và không gọi cổng thanh toán thật.
- Phân biệt kết quả unit test, kiểm tra tĩnh và integration test.
- Không tuyên bố đã kiểm thử với PostgreSQL thật nếu chỉ chạy test bằng fake hoặc kiểm tra offline.
- Báo cáo rõ những phần chưa thể kiểm thử.

---

## 10. Source of Truth

Mỗi tài liệu có phạm vi chính thức riêng. Không mặc định một tài liệu có thể thay thế toàn bộ các tài liệu còn lại.

### 10.1. Thứ tự ưu tiên chung

1. **Yêu cầu trực tiếp của người dùng:** xác định mục tiêu, phạm vi và quyết định của task hiện tại.
2. **`docs/database-schema.md`:** nguồn chính thức cho cấu trúc database.
3. **`docs/business-requirements.md`:** nguồn chính thức cho nghiệp vụ.
4. **`VieTech.docx`:** tài liệu tham khảo về yêu cầu tổng thể, ERD và thiết kế ban đầu.
5. **Database thực tế thông qua Supabase MCP:** dùng để xác minh trạng thái triển khai khi được yêu cầu hoặc cho phép.
6. **`README.md`:** tổng quan dự án và quy tắc phát triển.
7. **Source code hiện tại:** phản ánh cách hệ thống đang được triển khai, nhưng không mặc nhiên có nghĩa là mọi hành vi hiện tại đều đúng với đặc tả.

### 10.2. Phạm vi của từng nguồn

**`docs/database-schema.md`**

Là nguồn chính thức về bảng, cột, kiểu dữ liệu, khóa, quan hệ, constraint, index và các quy tắc ở mức database.

**`docs/business-requirements.md`**

Là nguồn chính thức về chức năng, quy trình nghiệp vụ, điều kiện xử lý, trạng thái, quyền hạn và quy tắc của các chức năng.

**`VieTech.docx`**

Là tài liệu tham khảo về yêu cầu tổng thể, ERD và thiết kế ban đầu. Không dùng tài liệu này để tự ý ghi đè schema hoặc các quy tắc nghiệp vụ đã được cập nhật trong tài liệu chính thức.

**Database thực tế thông qua Supabase MCP**

Phản ánh trạng thái triển khai thực tế tại thời điểm kiểm tra. Không tự động thay thế đặc tả đã thống nhất và không được tự ý sửa dữ liệu hoặc schema khi chưa được phép.

**`README.md` và source code**

README cung cấp bối cảnh chung. Source code cho biết trạng thái triển khai hiện tại. Nếu code khác đặc tả, phải xác định đó là lỗi triển khai, thay đổi chưa cập nhật tài liệu hay quyết định đã được phê duyệt.

### 10.3. Quy tắc xử lý mâu thuẫn

Khi các nguồn mâu thuẫn nhau, phải báo cáo mâu thuẫn và chờ xác nhận trước khi thực hiện bất kỳ thay đổi nào có ảnh hưởng. Thứ tự ưu tiên dưới đây dùng để xác định nguồn cần đối chiếu, không phải để tự ý sửa cho các nguồn khớp nhau.

- Mâu thuẫn về database schema: ưu tiên `docs/database-schema.md`.
- Mâu thuẫn về nghiệp vụ: ưu tiên `docs/business-requirements.md`.
- Mâu thuẫn về thiết kế tổng thể hoặc ERD ban đầu: đối chiếu `VieTech.docx` với các đặc tả chính thức hiện hành.
- Mâu thuẫn giữa database thực tế và đặc tả: báo cáo trạng thái thực tế và đề xuất hướng xử lý, không tự động thay đổi một trong hai.
- Mâu thuẫn giữa source code và tài liệu: xác định phạm vi ảnh hưởng và báo cáo trước khi sửa.
- Nếu yêu cầu trực tiếp có vẻ mâu thuẫn với đặc tả đã thống nhất hoặc có ảnh hưởng đến dữ liệu, bảo mật hay kiến trúc, phải nêu rõ mâu thuẫn và chờ xác nhận trước khi thực hiện thay đổi có ảnh hưởng.

Không tự ý suy đoán hoặc âm thầm thay đổi yêu cầu để làm cho các tài liệu khớp nhau.

---

## 11. Trạng thái phát triển dự án

Theo trạng thái đã ghi nhận tại thời điểm hoàn thành Stage 4:

### Đã hoàn thành

- Khởi tạo repository Git và cấu trúc dự án.
- Thiết lập nền tảng Backend FastAPI.
- Xây dựng SQLAlchemy Models.
- Xây dựng Pydantic Schemas và Repositories.
- Triển khai Service Layer cho các nhóm nghiệp vụ chính.
- Bổ sung xử lý đơn hàng, vận chuyển, thanh toán, hoàn tiền, kho, nhập hàng, đánh giá, hội thoại chat, bảo hành, đổi trả, nội dung và thống kê.
- Hội thoại chat mới có nghiệp vụ lưu trữ/phân công; chưa tích hợp nhà cung cấp AI.
- Mã tích hợp SePay (`backend/app/integrations/sepay.py`, `backend/app/routers/webhooks.py`) đã có nhưng chưa được đăng ký và kích hoạt trong ứng dụng.
- Bổ sung bộ kiểm thử tự động.
- Bổ sung tài liệu nghiệp vụ, schema và điểm vào nội bộ.
- Commit Stage 4 tại commit `9489aac`.

### Kết quả kiểm thử được báo cáo

- 684 test chạy thành công bằng `unittest` trong môi trường hiện có.
- Bộ test được báo cáo đã chạy lặp lại thành công.
- Chưa có integration test xác nhận toàn bộ hệ thống trên PostgreSQL thật.
- Các migration mới chưa được áp dụng vào database thật.

### Công việc tiếp theo

- Stage 5: Authentication và Authorization.
- Stage 6: Router/API.
- Tích hợp Frontend với Backend.
- Kiểm thử tích hợp trên môi trường staging.
- Kiểm tra và áp dụng migration theo quy trình được phê duyệt.
- Phát triển AI Chatbot và Product Recommendation Engine theo kế hoạch.

Trạng thái trên là mốc tiến độ đã ghi nhận, không thay thế việc kiểm tra Git và source code thực tế trước mỗi task.

---

## 12. Quy trình thực hiện task

Khi nhận một task mới, thực hiện theo thứ tự:

1. Đọc yêu cầu trực tiếp và xác định phạm vi.
2. Đọc các tài liệu liên quan, đặc biệt là `docs/business-requirements.md` và `docs/database-schema.md` khi cần.
3. Kiểm tra source code và các thay đổi đang tồn tại.
4. Xác định các file dự kiến sửa, ảnh hưởng đến kiến trúc và rủi ro dữ liệu.
5. Nếu phát hiện mâu thuẫn hoặc thiếu thông tin quan trọng, báo cáo trước khi sửa.
6. Thực hiện thay đổi nhỏ nhất đáp ứng yêu cầu.
7. Bổ sung hoặc cập nhật test.
8. Chạy kiểm thử phù hợp trong môi trường hiện có.
9. Báo cáo file đã thay đổi, kết quả kiểm thử, vấn đề còn lại và bước tiếp theo.

Không tự ý mở rộng phạm vi task, thay đổi schema hoặc thực hiện thao tác có ảnh hưởng đến database ngoài phạm vi đã được cho phép.