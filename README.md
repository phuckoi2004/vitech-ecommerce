# VieTech - Website bán hàng điện tử

## 1. Tổng quan

VieTech là website thương mại điện tử kinh doanh các sản phẩm công nghệ và điện tử.

Hệ thống gồm:
- Quản lý tài khoản và phân quyền.
- Quản lý danh mục, thương hiệu và sản phẩm.
- Quản lý kho và giá vốn hàng bán (COGS).
- Quản lý giỏ hàng và đơn hàng.
- Quản lý thanh toán.
- Quản lý khuyến mãi và mã giảm giá.
- Quản lý đánh giá sản phẩm.
- Quản lý bảo hành và đổi trả.
- AI Chatbot tư vấn sản phẩm.
- Product Recommendation Engine.

Tài liệu đặc tả chính:

`VieTech.docx`

---

## 2. Công nghệ

### Frontend
- React
- Vite
- Tailwind CSS

### Backend
- Python
- FastAPI
- SQLAlchemy

### Database
- Supabase
- PostgreSQL

### Authentication
- JWT
- RBAC

### Version Control
- Git
- GitHub

---

## 3. Kiến trúc Backend

Backend sử dụng kiến trúc phân lớp:

```text
Router
   ↓
Service
   ↓
Repository
   ↓
Model
   ↓
Supabase / PostgreSQL
```

### Router
Tiếp nhận HTTP request và trả response.

### Service
Xử lý logic nghiệp vụ.

### Repository
Truy vấn và thao tác với database.

### Model
SQLAlchemy ORM mapping với database.

### Schema
Pydantic dùng để validate request/response.

---

## 4. Cấu trúc project

```text
VieTech/
├── README.md
├── VieTech.docx
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── customer/            # Giao diện khách hàng
│   │   │   ├── pages/
│   │   │   ├── components/
│   │   │   ├── layouts/
│   │   │   └── routes/
│   │   │
│   │   ├── admin/               # Giao diện nhân viên / quản trị viên
│   │   │   ├── pages/
│   │   │   ├── components/
│   │   │   ├── layouts/
│   │   │   └── routes/
│   │   │
│   │   ├── components/
│   │   │   └── shared/          # Component dùng chung
│   │   │
│   │   ├── services/
│   │   │   └── api/             # Gọi API backend
│   │   │
│   │   ├── auth/                # Xác thực, JWT, phân quyền phía client
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
│   │   ├── core/                # Cấu hình, bảo mật, dependency dùng chung
│   │   ├── models/              # SQLAlchemy Models
│   │   ├── schemas/             # Pydantic Schemas
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── routers/
│   │   │   ├── customer/        # API cho khách hàng
│   │   │   └── admin/           # API cho nhân viên / quản trị viên
│   │   │
│   │   ├── database.py
│   │   └── main.py
│   │
│   ├── .env
│   ├── .env.example
│   └── requirements.txt
│
└── .gitignore
```

---

## 5. Database

Database sử dụng Supabase PostgreSQL.

Kết nối database thông qua biến môi trường:

```text
DATABASE_URL
```

Không hard-code database credentials.

`backend/.env` chứa thông tin bí mật và không được commit lên GitHub.

Thiết kế database phải bám theo `VieTech.docx`.

Không tự ý:
- Thêm hoặc xóa bảng.
- Thêm hoặc xóa thuộc tính.
- Đổi tên bảng hoặc column.
- Thay đổi quan hệ giữa các bảng.

Nếu phát hiện mâu thuẫn giữa tài liệu và database thực tế, phải báo cáo trước khi thay đổi.

---

## 6. Các nhóm bảng

### Quản lý người dùng
- Users
- Addresses
- Notifications

### Quản lý danh mục và sản phẩm
- Categories
- Brands
- Products
- ProductVariants
- ProductImages
- ProductSerials

### Quản lý yêu thích và giỏ hàng
- Wishlists
- WishlistItems
- Carts
- CartItems

### Quản lý đơn hàng và vận chuyển
- ShippingMethods
- Orders
- OrderItems
- OrderStatusHistories

### Quản lý thanh toán
- PaymentMethods
- PaymentTransactions

### Quản lý khuyến mãi
- Promotions
- PromotionProducts
- PromotionCategories
- Coupons

### Quản lý nhà cung cấp và nhập hàng
- Suppliers
- PurchaseOrders
- PurchaseOrderItems

### Quản lý đánh giá
- Reviews
- ReviewImages

### Quản lý chatbot
- Conversations
- Messages

### Quản lý bảo hành và đổi trả
- WarrantyRequests
- ReturnRequests
- ServiceRequestAttachments
- ServiceRequestHistories

### Quản lý nội dung
- NewsArticles
- Banners

Chi tiết thuộc tính, kiểu dữ liệu, khóa và ràng buộc phải được đối chiếu từ `VieTech.docx`.

---

## 7. Quan hệ chính

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

Các quan hệ khác được xác định theo `VieTech.docx`.

---

## 8. Người dùng và phân quyền

Hệ thống có các role:

- Customer
- Staff
- Admin
- SuperAdmin

Sử dụng RBAC để kiểm soát quyền truy cập theo role.

---

## 9. Quy tắc phát triển

- Đọc `README.md` trước khi thực hiện task.
- Đọc `VieTech.docx` khi task liên quan đến nghiệp vụ hoặc database.
- Kiểm tra source code hiện tại trước khi sửa.
- Kiểm tra database thực tế thông qua Supabase MCP khi cần.
- Không tự ý thay đổi kiến trúc.
- Không tự ý thay đổi database schema.
- Không hard-code secret.
- Không commit `.env`.
- Không in hoặc tiết lộ database credentials.
- Không chạy migration khi chưa được yêu cầu.
- Nếu phát hiện mâu thuẫn hoặc thiếu thông tin, phải báo cáo trước khi thay đổi.
- Ưu tiên thay đổi nhỏ, rõ ràng và đúng phạm vi task.

---

## 10. Source of Truth

Khi thực hiện task, ưu tiên theo thứ tự:

1. Yêu cầu trực tiếp của người dùng.
2. `VieTech.docx`
3. Database thực tế thông qua Supabase MCP.
4. `README.md`
5. Source code hiện tại.

Nếu có mâu thuẫn giữa các nguồn, **không tự ý quyết định**. Hãy báo cáo sự khác biệt và chờ xác nhận.
