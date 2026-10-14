# Quản lý sản phẩm và biến thể

Trang admin dùng React + Vite + JavaScript/JSX + Tailwind CSS, giữ cấu trúc FastAPI Router → Service → Repository và schema PostgreSQL/Supabase hiện có. Không thêm migration.

## Mô hình thống nhất giữa admin, khách hàng và giỏ hàng

- Products là thông tin chung của một mẫu sản phẩm: tên, danh mục, thương hiệu, bảo hành, mô tả, thông số, trạng thái và ảnh.
- ProductVariants là lựa chọn của sản phẩm: SKU duy nhất do người dùng đặt, một màu, dung lượng/cấu hình, giá bán, tồn kho, ngưỡng tồn, bật/tắt hoạt động và Serial/IMEI.
- Mỗi biến thể có đúng một ProductId bắt buộc. Một Product có thể có nhiều biến thể. Sản phẩm chỉ có một màu vẫn là một Product kèm một ProductVariant; form tạo sản phẩm mới luôn lưu cùng biến thể đầu tiên.
- Admin hiển thị mỗi biến thể thành một dòng riêng. Ví dụ mẫu X trắng/đen/hồng là ba dòng với SKU, giá và tồn riêng; tìm kiếm/bộ lọc/phân trang cũng theo biến thể.
- Phía khách dùng danh sách Products: một mẫu X là một sản phẩm. GET chi tiết trả các Variants đang hoạt động để giao diện khách chọn màu/cấu hình. Sản phẩm chỉ có một biến thể vẫn có danh sách Variants gồm một phần tử.
- Giỏ hàng dùng ProductVariantId: hai màu khác nhau thành hai dòng; thêm lại cùng biến thể cộng số lượng. Khóa duy nhất là (CartId, ProductVariantId).
- Không suy luận hay gộp Product theo tên, vì hai sản phẩm có thể trùng tên. Khi thêm biến thể, admin chọn chính xác sản phẩm đã có.

## Thao tác trên giao diện admin

Bảng giữ các cột Sản phẩm, Mã SP, Danh mục, Thương hiệu, Giá bán, Tồn kho, Trạng thái, Thao tác. Dòng phụ hiển thị màu và dung lượng; dữ liệu cũ thiếu cả hai dùng VariantName. Mã SP là SKU, UUID chỉ dùng làm khóa nội bộ.

Nút **Thêm sản phẩm** mở hai lựa chọn:

1. **Sản phẩm mới**: nhập thông tin chung, ảnh và biến thể đầu tiên rồi bấm Tạo sản phẩm. Backend lưu trong một transaction, lỗi bất kỳ bước nào hoàn tác toàn bộ.
2. **Biến thể của sản phẩm đã có**: tìm/chọn sản phẩm qua bộ chọn phân trang rồi nhập SKU, màu, cấu hình, giá. Chỉ tạo thêm biến thể dùng đúng ProductId đã chọn. Hỗ trợ cả Products cũ chưa có biến thể.

Trong chi tiết một dòng:

- **Sửa biến thể** chỉ sửa SKU, màu, dung lượng, giá, ngưỡng tồn, IsActive và quản lý serial. Thông tin sản phẩm chung chỉ được hiển thị để tham khảo. Không có trường chuyển ProductId.
- **Thêm biến thể cùng sản phẩm** mở form thêm, chọn sẵn ProductId của dòng đang xem.
- **Sửa thông tin chung** là form riêng, có thông báo rõ rằng tên, danh mục, thương hiệu, bảo hành, trạng thái, mô tả, thông số và ảnh áp dụng cho tất cả biến thể của Product đó.
- Xóa cần xác nhận và chỉ xóa mềm biến thể đang chọn, giữ Product và các biến thể khác.

Biến thể mới có tồn kho bằng 0. Form không sửa StockQuantity/CostPrice; cập nhật chúng qua nghiệp vụ kho hiện có. Giữ kiểm tra SKU duy nhất và điều kiện đổi Serial/IMEI.

Trạng thái Product quyết định cả sản phẩm có được bán hay không; IsActive quyết định từng biến thể có được chọn hay không. Một biến thể IsActive=true thuộc Product Draft/Inactive/Discontinued vẫn chưa được bán. Hết/sắp hết hàng được tính từ kho, không ghi đè Product.Status.

## API

- GET /admin/variants: danh sách theo SKU, Total đếm biến thể. Bộ lọc keyword/category_id/brand_id/status/min_price/max_price/stock chạy trong SQL trước LIMIT/OFFSET. Giá, tồn và ngưỡng lấy từ biến thể.
- POST /admin/catalog-items: nhận dữ liệu biến thể cùng **Product** (thông tin sản phẩm mới) hoặc **ProductId** (sản phẩm đã có), bắt buộc đúng một lựa chọn. Sản phẩm mới + biến thể đầu tiên + ảnh được lưu nguyên tử.
- GET /admin/catalog-items/{variantId}: đọc một biến thể cùng thông tin chung/ảnh để hiển thị.
- PUT /admin/catalog-items/{variantId}: chỉ nhận dữ liệu biến thể. Từ chối Name, Images, Status, ProductId, StockQuantity, CostPrice trong body; không tự clone/tách/chuyển Product.
- PUT /admin/catalog-products/{productId}: lưu toàn bộ thông tin chung và ảnh trong một transaction, giữ nguyên ProductId và mọi ProductVariantId.
- GET /admin/products: tìm/chọn Product đã có, có phân trang và gồm cả sản phẩm chưa có biến thể.
- GET /admin/products/{productId}: đọc thông tin chung cho form sửa riêng.
- DELETE /admin/variants/{variantId}: xóa mềm đúng biến thể.
- GET /categories?active_only=false và /brands?active_only=false: bộ chọn/bộ lọc.
- Các API Product/Variant/Image cũ vẫn được giữ cho các luồng hiện có.

Ví dụ thêm màu cho sản phẩm đã có:

~~~json
{
  "ProductId": "<UUID của Product đã chọn>",
  "Sku": "MODEL-X-PINK-256",
  "Color": "Hồng",
  "Storage": "256GB",
  "Price": "12000000",
  "MinStockLevel": 3,
  "IsActive": true,
  "IsSerialTracked": false
}
~~~

Các request dùng Bearer token và cơ chế refresh của AuthProvider. Staff xem cùng trang; thêm/sửa/xóa bị chặn ở UI, URL và backend.

Bộ lọc/trang lưu trên URL, hỗ trợ Back/Forward; tìm kiếm debounce 400ms hoặc Enter; mỗi trang 8 biến thể. Không dùng dữ liệu mẫu Figma. Dữ liệu rỗng giữ cột/số lượng 0; lỗi API có thông báo/thử lại riêng.

Ảnh hiện được quản lý ở cấp Product và dùng chung trong nhóm, theo schema ProductImages hiện có. Không tự thêm ảnh riêng cho từng biến thể hoặc sửa cấu trúc database. Avatar hồ sơ dùng Supabase Storage riêng.

## Phạm vi dữ liệu và kiểm tra

Không chạy migration, không gộp/chuyển dữ liệu đã có, không sửa đăng nhập hoặc cấu hình kho avatar trong thay đổi mô hình này. Nếu trước đó đã nhập các màu thành những Product riêng, cần xác định chính xác nhóm trước khi chuyển dữ liệu; không tự gộp theo tên.

Kiểm thử backend dùng SQLite trong bộ nhớ với repository/service/router/schema thật, cùng kiểm tra biên dịch SQL PostgreSQL; không truy cập hoặc ghi database ứng dụng và không thay thế integration PostgreSQL thật. Bao gồm:

- Một Product + biến thể đầu tiên, thêm các màu vào cùng ProductId.
- Phía khách một sản phẩm với danh sách biến thể; giỏ hàng tách hai biến thể và cộng số lượng khi thêm lại cùng biến thể.
- Sửa biến thể giữ nguyên cha/con, SKU khác và kho; sửa thông tin chung áp dụng cho mọi biến thể.
- Transaction hoàn tác, quyền Staff/Admin, dữ liệu không hợp lệ, SKU trùng, serial và sản phẩm đã xóa.

Vitest kiểm tra các form/thao tác/URL, quyền, trạng thái trống/lỗi, tìm/chọn sản phẩm có phân trang và hợp đồng HTTP. Chạy thêm build/lint frontend. Theo yêu cầu người dùng, không kiểm tra giao diện màn hình nhỏ/mobile.

Backend đang chạy không có --reload cần được nạp lại để nhận API. Khi tự phát triển, chạy hai terminal và giữ chúng mở:

~~~powershell
cd D:\vitech-ecommerce\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
~~~

~~~powershell
cd D:\vitech-ecommerce\frontend
npm.cmd run dev -- --configLoader native
~~~

Backend dùng auth state memory ở môi trường phát triển; khởi động lại backend có thể khiến phiên cũ hết hiệu lực và cần đăng nhập lại.
