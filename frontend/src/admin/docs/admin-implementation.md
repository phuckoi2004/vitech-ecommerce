# VIETECH — Tài liệu triển khai và giao tiếp hệ thống Admin

Ngày cập nhật: 18/10/2026. Phạm vi: phần quản trị viên/nhân viên đã làm và tích hợp trong dự án hiện tại.

Tài liệu mô tả cách xây dựng, tổ chức mã nguồn, các quyết định nghiệp vụ và cách giao diện admin trao đổi dữ liệu với API, backend và CSDL. Đây là tài liệu bàn giao kỹ thuật, không phải danh sách lỗi hay cam kết mọi tình huống đã được kiểm thử trên CSDL thật. Nội dung lấy từ mã nguồn hiện tại và những yêu cầu đã chốt trong trao đổi; chức năng đã thay đổi được mô tả theo quyết định mới nhất.

## 1. Mục tiêu và phạm vi phần đã làm

Khu vực nội bộ dùng chung cho Admin và Staff. Người dùng đăng nhập vào cổng nội bộ; hệ thống xác định vai trò và danh sách quyền để hiện menu, cho xem dữ liệu và cho thực hiện từng thao tác.

Các nhóm đã xây dựng gồm tổng quan, tài khoản và hồ sơ, sản phẩm/biến thể, danh mục, thương hiệu, nhà cung cấp, nhập hàng, đơn hàng, đổi trả, bảo hành, đánh giá, tin tức, banner, phương thức thanh toán, phương thức vận chuyển, hỗ trợ khách hàng, báo cáo và khuyến mãi/mã giảm giá.

Phần giao diện khách hàng không thuộc tài liệu này. Khi mô tả việc khách áp mã, nhận thông báo hoặc xem trạng thái, đó là đầu ra nghiệp vụ mà backend cung cấp, không khẳng định đã hoàn thiện toàn bộ màn hình khách hàng tương ứng.

Các chức năng được người dùng để sau như hoàn tiền, đối soát, xuất báo cáo doanh thu và tự phát mã theo điều kiện khách hàng không được coi là đã triển khai trong giao diện admin hiện hành.

## 2. Công nghệ và kiến trúc

| Thành phần | Công nghệ/cách sử dụng | Vai trò |
|---|---|---|
| Giao diện admin | React, JavaScript, React Router | Trang, component, điều hướng và trạng thái form |
| Công cụ frontend | Vite | Chạy phát triển, proxy API và build |
| Trình bày | Tailwind CSS | Bố cục, màu, khoảng cách và trạng thái giao diện của các trang quản trị được xây dựng theo Figma |
| Phần giao diện dùng lại | Component/hook và một số CSS có sẵn | Dùng tiếp các phần tài khoản, hồ sơ và xác thực trong cấu trúc dự án |
| API/backend | Python, FastAPI | Nhận HTTP request và tổ chức các điểm vào nghiệp vụ |
| Kiểm tra dữ liệu | Pydantic | Schema request/response, kiểu dữ liệu và ràng buộc đầu vào |
| Truy cập CSDL | SQLAlchemy | Model, repository, transaction và khóa dòng |
| CSDL | PostgreSQL trên Supabase | Lưu dữ liệu nghiệp vụ và ràng buộc quan hệ |
| Kho ảnh | Supabase Storage | Nhận file ảnh, lưu đối tượng và cấp URL công khai |
| Phiên đăng nhập | JWT, refresh cookie HttpOnly, CSRF | Xác thực người gọi API và khôi phục phiên |

Luồng xử lý thông thường:

```text
Người dùng nội bộ
  -> Trang/component React
  -> Hook đọc dữ liệu hoặc service frontend
  -> HTTP client dùng chung
  -> API FastAPI
  -> Schema + Service nghiệp vụ
  -> Repository SQLAlchemy
  -> PostgreSQL/Supabase
  -> Response JSON
  -> Cập nhật bảng, form, thông báo và trạng thái nút
```

Frontend phụ trách hiển thị và thu thập thao tác. Backend quyết định quyền, chuyển trạng thái, số tiền, số lượt dùng và cập nhật kho. Việc ẩn một nút trên frontend không thay thế kiểm tra quyền trong backend.

## 3. Cấu trúc mã nguồn và cách phân chia trách nhiệm

| Vị trí | Trách nhiệm |
|---|---|
| `frontend/src/admin/routes` | Menu, URL, quyền vào trang và các route con |
| `frontend/src/admin/layouts` | Khung admin chung: sidebar, header, avatar và vùng nội dung |
| `frontend/src/admin/pages` | Trang danh sách, chi tiết, thêm/sửa và ghép các thành phần nghiệp vụ |
| `frontend/src/admin/components` | Bảng, form, dialog, nút, nhãn trạng thái, ảnh và trình soạn thảo |
| `frontend/src/admin/hooks` | Đọc dữ liệu, điều phối thao tác, polling và giữ trạng thái xử lý |
| `frontend/src/admin/services` | Hàm gọi API cho từng nghiệp vụ admin |
| `frontend/src/admin/lib` | Lọc, định dạng, tính toán hiển thị và chuyển dữ liệu form thành payload |
| `frontend/src/admin/assets` | Icon và hình ảnh dùng trong admin |
| `frontend/src/admin/docs` | Tài liệu văn bản phục vụ bàn giao và ghi nhận quyết định |
| `frontend/src/services/api` | HTTP client và API dùng chung của ứng dụng |
| `frontend/src/auth` | Phiên đăng nhập và các lớp bảo vệ route dùng chung |
| `backend/app/routers` | URL, HTTP method, dependency xác thực và gọi service |
| `backend/app/schemas` | Cấu trúc request/response |
| `backend/app/services` | Quy tắc nghiệp vụ và ranh giới transaction |
| `backend/app/repositories` | Truy vấn và ghi dữ liệu |
| `backend/app/models` | Ánh xạ bảng, cột, khóa ngoại và quan hệ |

`AdminHomePage` giữ khung trang và hiển thị nội dung con bằng `Outlet`. Vì vậy khi sang trang chi tiết, thêm hoặc sửa, menu trái vẫn được giữ lại. Một số trang con được tải bằng lazy import để chỉ tải khi cần.

## 4. Cách triển khai từ thiết kế đến chức năng

1. Đọc frame Figma và xác định đó là trang đầy đủ hay hộp thoại nhỏ nằm trên trang hiện tại.
2. Đối chiếu trường trên thiết kế với model, schema và API đang có. Tên hiển thị trên Figma không tự quyết định tên cột trong CSDL.
3. Dùng khung admin, bộ định tuyến và component hiện có; triển khai phần trình bày bằng Tailwind theo cấu trúc dự án.
4. Tách form, bảng, dialog và phần gọi API để mỗi phần có nhiệm vụ rõ ràng.
5. Nối dữ liệu thật; không dùng bản ghi mẫu để giả dữ liệu kinh doanh. Khi chưa có dữ liệu, giữ tiêu đề cột và hiển thị trạng thái rỗng; số đếm lấy từ dữ liệu thật.
6. Kiểm tra quyền cho đường dẫn và thao tác; khóa nút phù hợp khi đang gửi hoặc khi trạng thái nghiệp vụ không cho phép.
7. Nếu API thiếu dữ liệu hoặc thao tác cần thiết, xác định phạm vi backend rồi xin phép trước khi thay đổi ngoài frontend admin.
8. Chạy kiểm thử phù hợp, lint và build. Những bước kiểm thử không tự chứng minh đã triển khai trên CSDL thật.

Các thiết kế nhỏ như xác nhận xóa, xem đánh giá và thông báo lỗi được triển khai dưới dạng dialog ở giữa màn hình, làm tối/mờ phần phía sau. Chi tiết/thêm/sửa tin tức và banner là trang con trong cùng khung admin. Khuyến mãi và mã giảm giá dùng popup cho cả xem, thêm, sửa và xác nhận xóa theo yêu cầu đã chốt.

## 5. Giao tiếp HTTP và phiên đăng nhập

### 5.1. Frontend và backend là hai tiến trình

Khi phát triển trên máy, Vite chạy ở `http://127.0.0.1:5173`, backend thường chạy ở `http://127.0.0.1:8000`. Mở source code trong IDE chỉ mở file; phải chạy tiến trình backend thì API mới phục vụ đăng nhập và các chức năng quản trị.

Theo cấu hình hiện tại, frontend gọi đường dẫn có tiền tố `/api`. Vite chuyển tiếp tới backend và bỏ tiền tố đó. Ví dụ:

```text
Trình duyệt: /api/admin/orders
Vite proxy:  http://127.0.0.1:8000/admin/orders
```

`VITE_API_URL` có thể thay đổi gốc API khi triển khai. Cấu hình proxy phát triển không tự trở thành reverse proxy của máy chủ production.

### 5.2. Đăng nhập nội bộ

Giao diện admin dùng cơ chế auth chung của dự án, với cổng đăng nhập nội bộ dành cho Staff/Admin. Access token, CSRF token và thông tin phiên được giữ trong bộ nhớ frontend; refresh cookie HttpOnly giúp khôi phục phiên sau khi tải lại trang.

`RequireInternal` kiểm tra người dùng thuộc khu vực nội bộ. `RequirePermission` kiểm tra quyền vào từng chức năng. `visibleMenu` lọc menu theo danh sách quyền backend trả về. Backend vẫn kiểm tra vai trò hoặc quyền trên mỗi request.

Các thao tác có xác thực thường đi qua `auth.withAccessToken(...)`. Khi access token hết hạn và API trả 401, lớp quản lý phiên xử lý refresh và việc thử lại theo cơ chế chung; từng trang không tự xây một cơ chế đăng nhập riêng.

### 5.3. Quy ước request/response

| Trường hợp | Cách truyền |
|---|---|
| Đọc danh sách/chi tiết | GET; bộ lọc và phân trang nằm trong query string |
| Tạo mới | POST với JSON |
| Sửa thông tin | PATCH với các trường cần cập nhật |
| Thay toàn bộ một tập liên kết | PUT khi endpoint tương ứng được thiết kế như vậy |
| Xóa | DELETE; thành công có thể trả 204, HTTP client chuyển thành `null` |
| Thao tác nghiệp vụ | POST tới endpoint riêng như `/advance`, `/receive`, `/claim` |
| Tải ảnh | Gửi nội dung file thô, Content-Type theo file, không gửi đường dẫn file của máy admin |
| Xác thực API | Header `Authorization: Bearer ...`; cookie được gửi kèm khi cần |

Danh sách thường trả `Items`, `Total`, `Page`, `PageSize`; một số API danh mục/phương thức trả mảng trực tiếp. UUID phục vụ định danh nội bộ. Những mã dễ đọc như SKU, mã phiếu, mã đơn và coupon code là dữ liệu nghiệp vụ riêng, không thay thế UUID.

### 5.4. Đọc dữ liệu và xử lý thao tác

`useAdminQuery` và `useAdminLoad` cung cấp dữ liệu, trạng thái đang tải, lỗi và hàm làm mới. Request đọc có tín hiệu hủy để không dùng kết quả của truy vấn cũ sau khi người dùng chuyển trang hoặc đổi bộ lọc.

Một số danh sách dùng phân trang/lọc từ backend; một số đọc hết các trang API rồi lọc, sắp xếp và phân trang tại frontend. Vì vậy không thể mặc định rằng mọi bảng đều chỉ gọi một request cho một trang đang hiển thị.

Form giữ bản nháp trong state. Nhấn Lưu mới gửi payload nghiệp vụ. Những thao tác quan trọng dùng dialog xác nhận. Trong lúc ghi, nhiều luồng dùng cả trạng thái `busy` và khóa bằng ref để ngăn gửi trùng ngay cả trước lần render kế tiếp.

Lỗi API được chuyển thành thông báo tiếng Việt. API nghiệp vụ có thể trả `detail` và `code`; schema 422 trả danh sách lỗi theo trường. Các trang dựa trên mã lỗi để xử lý trường hợp cụ thể như mã trùng hoặc dữ liệu đã được đơn hàng tham chiếu.

## 6. Menu, trang con và phân quyền

| Nhóm/trang | URL chính | Nội dung |
|---|---|---|
| Tổng quan | `/admin` | Bốn thống kê, doanh thu năm tháng và các bảng tóm tắt |
| Tài khoản | `/admin/users` | Danh sách, thêm nhân viên, xem/sửa, khóa/mở khóa, xóa theo quyền |
| Hồ sơ cá nhân | `/admin/profile` | Thông tin của người đang đăng nhập, avatar, đổi mật khẩu |
| Danh sách sản phẩm | `/admin/products` | Quản lý từng SKU/biến thể; xem, thêm, sửa và xóa |
| Danh mục | `/admin/categories` | Danh mục, danh mục cha, trạng thái và thứ tự |
| Thương hiệu | `/admin/brands` | Tên, slug, mô tả, logo và trạng thái |
| Chương trình khuyến mãi | `/admin/promotions` | Điều kiện giảm giá và phạm vi áp dụng |
| Mã giảm giá | `/admin/coupons` | Mã con thuộc chương trình, hạn mức và lượt dùng |
| Đơn hàng | `/admin/orders` | Danh sách, chi tiết, trạng thái, serial và COD |
| Nhập hàng | `/admin/purchases` | Phiếu nhập, duyệt, nhận hàng, thực nhận và lịch sử |
| Nhà cung cấp | `/admin/suppliers` | Hồ sơ và trạng thái nhà cung cấp |
| Đổi trả | `/admin/returns` | Danh sách và xử lý từng yêu cầu theo giai đoạn |
| Bảo hành | `/admin/warranties` | Danh sách, giai đoạn và kết quả gửi khách |
| Đánh giá | `/admin/reviews` | Xem đánh giá và xóa mềm theo lý do |
| Tin tức | `/admin/news` | Danh sách, chi tiết, thêm/sửa, đăng/ẩn và xóa |
| Banner | `/admin/banners` | Ảnh, liên kết, lịch hiển thị và trạng thái |
| Báo cáo | `/admin/reports` | Doanh thu và số lượng đơn theo tháng |
| Hỗ trợ khách hàng | `/admin/support` | Hàng chờ và các cuộc trò chuyện chính mình đang hỗ trợ |
| Thanh toán | `/admin/payments` | Phương thức thanh toán; danh sách giao dịch cũ qua `?tab=1` |
| Vận chuyển | `/admin/shipping-methods` | Thêm/sửa và bật/ngừng phương thức |

Sidebar Sản phẩm chứa sản phẩm, danh mục, thương hiệu. Sidebar Khuyến mãi là nhóm riêng chứa chương trình khuyến mãi và mã giảm giá. Tin tức & Banner là một dropdown riêng. Nhà cung cấp thay vị trí Kho hàng trên menu; Nhập hàng là mục độc lập. Đường dẫn kho cũ vẫn được giữ để phục vụ liên kết sâu hiện có.

Không cần tạo hai bản giao diện giống nhau cho Admin và Staff. Cùng trang được dùng lại, nhưng menu và thao tác phụ thuộc quyền. Ví dụ Staff có thể xử lý đơn, nhập hàng và hỗ trợ; quản lý chương trình/mã giảm giá, nội dung và chỉnh phương thức thanh toán/vận chuyển thuộc quyền Admin theo backend hiện tại.

## 7. Tổng quan và cảnh báo tồn kho

Bốn ô tổng quan lấy dữ liệu về tổng đơn, doanh thu, đơn chờ và sản phẩm sắp hết. Khi dữ liệu thực sự rỗng, số liệu có thể là 0; khi đang tải hoặc tải lỗi thì hiển thị trạng thái tương ứng thay vì giả dữ liệu.

Năm tháng gần nhất trên tổng quan được tạo bằng JavaScript từ lịch máy người dùng. Frontend chuyển các tháng thành kỳ truy vấn rồi gọi các API thống kê. Nhãn tháng là dữ liệu hiển thị; số đơn và tiền doanh thu vẫn lấy từ backend.

Cảnh báo gắn với `ProductVariants.StockQuantity` và `MinStockLevel`. Backend tạo thông báo khi thao tác thay đổi kho vượt ngưỡng theo quy tắc tồn thấp. Trường hợp ngưỡng bằng 0 được xử lý theo quy tắc backend hiện có. Trạng thái hết hàng được phân biệt với sắp hết trong danh sách sản phẩm.

Thông báo tồn kho mang tham chiếu `ProductVariantId`, không suy ra SKU từ nội dung chữ. Khi bấm thông báo, admin mở đúng biến thể tại `/admin/products?dialog=view&variant=...`. Người có quyền xem sản phẩm được điều hướng tới chi tiết; thông báo được đánh dấu đã đọc qua API riêng.

Danh sách/số thông báo được đọc định kỳ và khi quay lại cửa sổ. Đây là polling HTTP, không phải kết nối WebSocket đẩy tức thời.

API chính: `/admin/statistics/orders`, `/admin/statistics/revenue`, `/admin/orders`, `/admin/inventory/low-stock`, `/users/me/notifications` và `/users/me/notifications/unread-count`.

## 8. Sản phẩm, biến thể và bộ ảnh

### 8.1. Quan hệ cha–con

Một `Product` chứa thông tin chung: tên, danh mục, thương hiệu, mô tả, thông số, thời hạn bảo hành và trạng thái. Một `ProductVariant` thuộc đúng một `Product`, chứa SKU, màu, dung lượng, giá, tồn kho, ngưỡng cảnh báo và cờ quản lý serial.

Danh sách admin hiển thị từng biến thể thành từng dòng. Ba màu là ba dòng quản lý, mỗi dòng có SKU riêng do người dùng đặt. UUID do hệ thống sinh chỉ phục vụ liên kết dữ liệu. Kể cả sản phẩm chỉ có một lựa chọn, luồng tạo mới vẫn tạo một Product và một ProductVariant đầu tiên.

### 8.2. Thêm, sửa và xem

Tạo sản phẩm mới dùng API tổng hợp `POST /admin/catalog-items` để tạo Product cùng biến thể đầu tiên. Thêm biến thể vào sản phẩm sẵn có gửi `ProductId` của cha thay vì tạo cha mới. Biến thể đầu tiên của sản phẩm mới được đặt làm mặc định.

Sửa biến thể dùng `PATCH /admin/catalog-items/{variantId}` cho SKU, màu, dung lượng, giá, trạng thái và ảnh đã chọn. Sửa thông tin chung dùng API sản phẩm của catalog; thay đổi này ảnh hưởng toàn bộ biến thể thuộc cha đó. Trang chi tiết đọc dữ liệu tổng hợp từ `GET /admin/catalog-items/{variantId}`.

Tồn kho trong form là ô chỉ đọc. Biến thể mới bắt đầu với tồn kho bằng 0; tồn kho tăng qua nhận hàng. Màu sắc là thuộc tính của một biến thể; người dùng không nhập nhiều màu vào cùng một SKU.

### 8.3. Một bộ ảnh cha, nhiều tập ảnh cho biến thể

Tất cả ảnh nằm trong bộ ảnh Product và bảng `ProductImages`. Khi chỉnh một biến thể, người dùng chọn nhiều ảnh có sẵn từ bộ ảnh cha và chọn một ảnh đại diện cho biến thể đó. Ảnh tải thêm được đưa vào bộ ảnh cha trước khi tham gia tập ảnh của SKU.

Theo quyết định không thêm bảng/cột để liên kết ảnh biến thể, cấu hình lựa chọn được lưu trong cột JSON `Product.Specifications`, ở vùng do hệ thống quản lý `_vietech_variant_media`. Vùng này lưu biến thể mặc định, danh sách URL được chọn theo UUID biến thể và URL ảnh đại diện. Đây là sử dụng dữ liệu JSON hiện có, không phải tạo bảng `ProductVariantImages`.

Backend kiểm tra ảnh được chọn phải thuộc Product tương ứng, đồng thời tách vùng metadata nội bộ khỏi phần thông số kỹ thuật hiển thị qua schema. Sản phẩm/biến thể cũ chưa có cấu hình riêng dùng cơ chế fallback đã định trong `catalog_media.py`.

Nguồn xử lý chính: `ProductWorkspace.jsx`, `VariantImageSelection.jsx`, `catalog_item.py`, `catalog_media.py` và các schema catalog.

## 9. Ảnh local và Supabase Storage

Đường đi của ảnh:

```text
Admin chọn file trên máy
  -> Frontend gửi byte của file tới API upload
  -> Backend kiểm tra quyền, kích thước và định dạng nội dung
  -> Backend tải file lên Supabase Storage
  -> Supabase có địa chỉ ảnh công khai
  -> API trả ImageUrl/AvatarUrl
  -> Form dùng URL đó để xem trước và lưu vào bản ghi nghiệp vụ
```

Đường dẫn dạng `C:\...` hoặc `D:\...` của máy admin không được ghi làm ảnh của sản phẩm. Supabase lưu file và backend xây/trả URL ảnh; không phải lấy một URL ảnh bất kỳ trên Internet để biến thành ảnh local.

Ảnh sản phẩm, logo thương hiệu, tin tức và banner dùng bộ chọn ảnh và API `POST /admin/product-image-uploads`. API hiện dùng kho ảnh đã cấu hình, lưu trong namespace `products/{userId}/...`. Backend chấp nhận JPG, PNG, WEBP theo kiểm tra chữ ký nội dung và giới hạn 2 MB. API này thuộc quyền Admin.

Ảnh chèn trong mô tả sản phẩm cũng chọn file local hoặc dán/kéo thả file để upload. Trình soạn thảo không có ô nhập URL ảnh; khi dán HTML từ web, ảnh trong HTML không được chèn trực tiếp. Ảnh đã lưu vẫn hiển thị và cho sửa mô tả ảnh hoặc thay bằng file mới. Ô địa chỉ liên kết dành cho hyperlink vẫn được giữ riêng.

Avatar dùng `PUT /users/me/avatar` và có luồng lưu riêng. Việc đổi avatar được gửi/lưu qua thao tác upload; nút Lưu hồ sơ phụ trách các trường hồ sơ đang thay đổi, không phải bước bắt buộc để lưu lại cùng một avatar vừa upload thành công.

Upload file và lưu bản ghi nghiệp vụ là hai bước khác nhau. File có thể đã có trên Storage trước khi bấm Lưu form. Transaction PostgreSQL không bao phủ tự động việc ghi đối tượng lên Storage.

`DATABASE_URL` dùng để kết nối PostgreSQL. Cấu hình Supabase URL và khóa backend cho Storage phục vụ HTTP upload vào kho file. Chỉ có đường dẫn kết nối CSDL không đủ để thực hiện thao tác Storage. Tài liệu không sao chép giá trị bí mật từ file môi trường.

## 10. Danh mục, thương hiệu và nhà cung cấp

Danh mục có tên, slug, mô tả, danh mục cha, thứ tự và trạng thái. Frontend gợi ý slug từ tên; backend kiểm tra tính hợp lệ, trùng lặp và quan hệ cây. Danh sách cha được lọc để không tạo quan hệ vòng.

Thương hiệu có tên, slug, mô tả, logo và trạng thái. Logo lấy từ luồng upload local. Việc xóa danh mục/thương hiệu có thể bị từ chối nếu dữ liệu đã được sản phẩm sử dụng; khi phù hợp quyền, giao diện cung cấp thao tác ẩn riêng thay vì âm thầm chuyển yêu cầu xóa thành thao tác khác.

Nhà cung cấp có mã, tên, email, số điện thoại, địa chỉ, mã số thuế, ghi chú và trạng thái. Staff/Admin được đọc để dùng cho phiếu nhập; Admin quản lý thông tin. Thao tác xóa nhà cung cấp trong luồng hiện tại là xóa mềm/ngừng hiển thị theo API, giữ liên kết lịch sử.

API chính: `/categories`, `/brands`, `/admin/categories`, `/admin/brands`, `/admin/suppliers`. Trường hợp đọc công khai và đọc nội bộ khác nhau ở quyền và lựa chọn lấy cả dữ liệu đã ẩn.

## 11. Phiếu nhập, thực nhận và cập nhật kho

### 11.1. Tạo phiếu

Người lập chọn nhà cung cấp và biến thể có sẵn. Mã phiếu và thời điểm tạo do hệ thống ghi. Ngày lập trên form chỉ đọc; frontend không gửi một ngày tùy ý để ghi đè `CreatedAt`.

Mỗi dòng ghi biến thể, số lượng đặt, đơn giá nhập và ghi chú. Thành tiền dòng là số lượng đặt nhân đơn giá nhập; tổng phiếu là tổng thành tiền các dòng. Frontend dùng tính toán đơn vị xu để hạn chế sai số dấu phẩy động trong phần hiển thị, backend kiểm tra và tính lại dữ liệu được lưu.

### 11.2. Trạng thái và người xử lý

Theo backend hiện tại, Staff lập phiếu ở trạng thái `Pending`, Admin quyết định duyệt hoặc từ chối; từ chối cần lý do. Phiếu bị từ chối được sửa và gửi lại để duyệt.

Phiếu do Admin lập được tạo ở `Approved` và có thể nhận hàng ngay; không cần tạo một quyết định tự duyệt. Chỉ phiếu `Pending`/`Rejected` được sửa theo quy tắc hiện tại. Phiếu đã duyệt muốn thay đổi theo cách khác phải đi qua thao tác được backend cho phép, không chỉnh thẳng trạng thái từ frontend.

API chi tiết phiếu trả `CreatedByName` và `DecidedByName` từ tài khoản liên kết sẵn, không cần quyền quản lý tài khoản để xem tên người duyệt. Trong chi tiết, dòng Người duyệt để trống khi chờ duyệt; sau khi duyệt hiện tên Admin xử lý. Phiếu Admin lập được duyệt ngay thì hiển thị tên người tạo và thời điểm tạo ở phần duyệt, không ghi thêm quyết định vào CSDL. Từ chối được ghi riêng để không nhầm người từ chối với người duyệt.

### 11.3. Thực nhận

`PurchaseOrderItems.ReceivedQuantity` là tổng số lượng đã nhận của dòng phiếu. Cột thực nhận trong form tạo/sửa là chỉ đọc. Muốn cập nhật, người xử lý mở Nhận hàng vào kho và nhập lượng nhận trong lần này, không nhập lại tổng cộng dồn.

Nếu biến thể quản lý serial/IMEI, số mã nhập phải khớp số lượng thực nhận. Một lần nhận có thể chỉ nhận một phần. Backend khóa phiếu, kiểm tra không vượt số đặt, cập nhật kho/giá vốn và ghi lịch sử `PurchaseReceipts`/`PurchaseReceiptItems` trong cùng transaction.

Nhận đủ đưa phiếu về `Completed`; nhận thiếu đưa về `Receiving`. Admin có thể đóng phần thiếu với lý do để thành `Closed`; lượng thiếu không được tự coi là đã nhận và không cộng vào tồn kho. Hủy phiếu chưa nhận hàng giữ lại lịch sử.

Các API tiêu biểu: `POST /admin/purchase-orders`, các endpoint `/items`, `/decision`, `/resubmit`, `/receive`, `/close`, `/cancel` và `GET .../receipts`.

### 11.4. Cách lưu form sửa đang sử dụng

Form sửa chỉ giữ thay đổi trong bộ nhớ đến khi bấm Cập nhật phiếu. Hàm `savePurchaseDraft` gửi một `PATCH /admin/purchase-orders/{id}` gồm `SupplierId`, `Note` và toàn bộ `Items` mong muốn. Bấm Hủy trước khi lưu không gửi các thay đổi này.

Backend khóa phiếu và kiểm tra trạng thái còn cho sửa, cập nhật đầu phiếu cùng các dòng trong một transaction. Dòng còn giữ SKU được giữ ID; dòng mới được thêm, dòng bị bỏ được xóa; tổng tiền do backend tính lại. Lỗi kiểm tra, ghi dữ liệu hoặc commit đều rollback toàn bộ. Khi gửi lại cùng danh sách sau khi mất phản hồi, hệ thống không thêm trùng dòng SKU. Thực nhận và tồn kho không được sửa qua form này. PATCH chỉ có đầu phiếu vẫn tương thích: bỏ qua `Items` nghĩa là giữ nguyên các dòng; danh sách rỗng hoặc null bị từ chối.

## 12. Quản lý đơn hàng

Danh sách đọc đơn từ API; lọc theo trạng thái và các tiêu chí hiện có. Xem chi tiết mở `/admin/orders/{orderId}` trong cùng khung admin. Trang chi tiết hiển thị người nhận, địa chỉ, các dòng SKU, tiền hàng, giảm giá, vận chuyển, tổng tiền và lịch sử chuyển trạng thái.

Luồng đơn tuần tự hiện có là `Pending -> Confirmed -> Processing -> Shipping -> Delivered -> Completed`, với nhánh hủy theo điều kiện backend. Các nút gọi API chuyển trạng thái, không sửa trực tiếp cột trong CSDL.

Khi đóng gói, hàng có quản lý serial cần được gán đủ serial/IMEI trước khi giao. Frontend có thao tác gán/gỡ mã; backend kiểm tra mã và dữ liệu kho. Đơn thanh toán trực tuyến cần đáp ứng điều kiện thanh toán trước khi giao; COD có thao tác xác nhận đã thu tiền khi xác nhận giao thành công.

Ghi chú nội bộ được lưu riêng qua PATCH. Lịch sử trạng thái có người/thời điểm xử lý do backend ghi. Quy tắc đổi/trả đang mở, thanh toán và khả năng hủy vẫn được kiểm tra phía server, không chỉ dựa vào nút đang hiển thị.

API chính: `GET /admin/orders`, `GET/PATCH /admin/orders/{id}`, `POST .../status`, `POST .../confirm-cod-delivery`, `GET/POST .../serials` và DELETE từng serial đã gán.

## 13. Đổi trả và bảo hành

### 13.1. Đổi trả

Yêu cầu có thông tin khách, đơn, sản phẩm/biến thể và lý do. Danh sách ưu tiên mọi yêu cầu `Pending` lên đầu; trong từng nhóm sắp thời điểm mới nhất trước. Việc lọc/phân trang không được làm mất ưu tiên chỉ vì yêu cầu nằm ở trang API sau.

Luồng hiện hành: `Pending -> Approved -> Receiving -> Processing -> Completed`. Frontend hiển thị các tên giai đoạn theo giao diện. Khi đang chờ có thao tác tiếp nhận hoặc từ chối. Các giai đoạn sau dùng Giai đoạn kế tiếp; từ chối yêu cầu lý do. `Completed`, `Rejected`, `Cancelled` là trạng thái đóng, không có nút chuyển tiếp.

Giao diện admin dùng `POST /admin/return-requests/{id}/advance` với `ExpectedStatus`. Backend khóa phiếu và so trạng thái hiện tại để tránh một thao tác cũ chuyển nhầm giai đoạn. Nếu người khác đã xử lý, trả lỗi và yêu cầu tải lại.

Theo quyết định mới nhất, chuyển giai đoạn đổi/trả là ghi nhận tiến độ gửi khách. Nó không tự tạo hoàn tiền, không tự điều chuyển hàng/serial và không yêu cầu trung tâm bảo hành. Luồng tài chính cũ được giữ để tham khảo và các điểm vào liên quan được tạm dừng; `Completed` của luồng này không có nghĩa đã hoàn tiền.

### 13.2. Bảo hành

Giai đoạn giao diện: Mới -> Đang kiểm tra -> Đang sửa -> Hoàn tất -> Đã trả khách. Các giai đoạn này được suy ra từ `Status` và những trường như `ReceivedAt`, `ResultApprovedAt`; không phải mỗi nhãn đều tương ứng một giá trị enum riêng trong CSDL.

Nút Tiếp nhận bắt đầu xử lý, sau đó đổi thành Giai đoạn kế tiếp. Khi kết thúc sửa, người xử lý bắt buộc chọn `Repaired` (sửa chữa), `PartReplaced` (thay linh kiện) hoặc `NotRepairable` (không thể sửa chữa) và nhập nội dung kết quả gửi khách. Không đưa đổi máy vào dropdown hiện hành.

Backend ghi người và thời điểm xác nhận kết quả, nội dung, lịch sử và thông báo cho khách. Theo luồng đã chốt, không yêu cầu thêm một Admin độc lập duyệt kết quả và không bắt nhập trung tâm bảo hành trên form này.

API chuyển tiếp nhận `ExpectedStage`; việc từ chối đi qua `/reject` với lý do. Phiếu đã trả, từ chối hoặc hủy được đóng. Hủy của khách được tiếp nhận dưới dạng trạng thái từ hệ thống, không tạo một nút hủy thay khách trong admin.

## 14. Đánh giá, tin tức và banner

### 14.1. Đánh giá

Danh sách đọc thông tin đánh giá từ API, có bộ lọc và phân trang. Chi tiết hiện trong dialog trên danh sách với màn sau tối/mờ. Không đưa dòng “đã xác thực mua hàng” vào giao diện chi tiết; điều kiện đã mua là quy tắc server kiểm tra khi khách được quyền đánh giá.

Xóa đánh giá là thao tác theo quyền, có xác nhận và lý do theo API xóa mềm. Lỗi thao tác mở thông báo, giữ trang hiện tại và không tự giả trạng thái xóa thành công. API quản trị thuộc nhóm `/admin/reviews`.

### 14.2. Tin tức

Tin tức có tiêu đề, slug, tóm tắt, nội dung, ảnh đại diện và trạng thái. Danh sách, chi tiết, thêm và sửa đã có đường dẫn riêng; xóa và thông báo lỗi là popup trên trang đang mở.

Form gửi một `POST /admin/news` hoặc `PATCH /admin/news/{id}` chứa nội dung và `Status` đã chọn. Backend lưu cả hai trong cùng transaction; lỗi kiểm tra, ghi hoặc commit đều hoàn tác toàn bộ. Tạo mới mặc định `Draft`, hoặc có thể chọn `Published` để đăng ngay khi lưu thành công. `PublishedAt` do server ghi lần đăng đầu, giữ nguyên khi ẩn rồi đăng lại. Bỏ `Status` trong PATCH thì giữ trạng thái cũ. Các nút đổi trạng thái riêng ở danh sách/chi tiết vẫn dùng `/publish` và `/hide`; form không gọi tiếp các endpoint này sau khi lưu nội dung. Khách chỉ xem được bài `Published`.

Ảnh đại diện đi qua upload local rồi dùng URL trả về. API chính: `/admin/news`, `/admin/news/{id}`, `/publish`, `/hide` và DELETE bài.

### 14.3. Banner

Banner gồm tiêu đề, ảnh, link khi bấm, thứ tự, mốc bắt đầu/kết thúc và cờ hoạt động. Form thêm/sửa và trang chi tiết nằm trong khung admin; xóa và thông báo dùng dialog.

Khả năng hiển thị của banner phụ thuộc cả `IsActive` và khung thời gian. Một mốc thời gian có thể để trống để không giới hạn phía đó. Cờ bật/tắt vẫn độc lập với lịch hiển thị.

Form gửi một `POST /admin/banners` hoặc `PATCH /admin/banners/{id}` chứa nội dung, thời gian và `IsActive` đã chọn. Backend kiểm tra và lưu tất cả trong cùng transaction; lỗi ở bất kỳ phần nào đều hoàn tác toàn bộ. Banner tạo ở trạng thái ngừng có `IsActive=false` ngay từ đầu, không tạo hoạt động rồi gửi lệnh ngừng sau đó. Bỏ `IsActive` trong PATCH thì giữ cờ hiện có. Các nút bật/ngừng riêng vẫn dùng `/activate` và `/deactivate`. Tên người tạo và thời điểm tạo do server ghi.

API chính: `/admin/banners`, `/admin/banners/{id}`, `/activate`, `/deactivate` và DELETE banner.

## 15. Phương thức thanh toán và vận chuyển

Phương thức thanh toán phục vụ cấu hình các lựa chọn như COD hoặc phương thức trực tuyến. Admin thêm/sửa dữ liệu theo API, gồm mã, tên, mô tả, thứ tự và trạng thái. Xóa có xác nhận và vẫn phụ thuộc việc dữ liệu đã được đơn hàng sử dụng. Giao dịch thanh toán là đối tượng khác với phương thức; bảng giao dịch cũ dùng `/admin/payment-transactions`.

Phương thức vận chuyển có mã, tên, mô tả, phí cơ bản, số ngày dự kiến và trạng thái. Giao diện hiện hành chỉ cung cấp thêm/sửa và bật/ngừng theo yêu cầu; không đưa nút xóa vào danh sách. Đang hoạt động dùng icon mở khóa xanh, ngừng hoạt động dùng khóa đóng đỏ.

Thay phí phương thức không sửa ngược phí vận chuyển đã chụp trong đơn cũ. Backend giữ quy tắc tham chiếu và kiểm tra quyền. Staff xem các phương thức; quyền chỉnh sửa thuộc Admin theo cấu hình hiện tại.

Nhóm API đọc là `/payment-methods`, `/shipping-methods`; API quản trị tạo/sửa thuộc các route `/admin/...` tương ứng.

## 16. Hỗ trợ khách hàng

Trang có hai danh sách: Đang chờ và Đang hỗ trợ. Đang chờ lấy các hội thoại Staff đang mở, chưa có người nhận. Đang hỗ trợ chỉ lấy hội thoại đang mở có `AssignedStaffId` bằng UUID người đang đăng nhập; số bên cạnh tab là tổng của tập dữ liệu đó, không phải tổng mọi nhân viên.

Khi bấm tiếp nhận, frontend gọi `/admin/conversations/{id}/claim`. Backend khóa dòng hội thoại và kiểm tra chưa ai nhận. Nếu người khác nhận trước, trả xung đột; không để hai người cùng tiếp nhận hợp lệ. Kể cả Admin cũng phải là người nhận hội thoại mới được gửi tin theo luồng này.

API nội bộ bổ sung tên/email khách và tin nhắn gần nhất để danh sách không phải tự tra từng khách bằng quyền quản lý tài khoản. Chi tiết, tin nhắn và danh sách được đọc bằng polling; không mô tả cơ chế hiện tại là WebSocket.

Gửi tin văn bản qua `POST .../messages`. Bản nháp được giữ theo hội thoại; khi gửi lỗi hiện dialog làm mờ màn sau và giữ nội dung để thử lại. Trong lúc gửi khóa thao tác lặp. Đóng hội thoại qua `/close`.

API chính: `/admin/conversations/unassigned`, `/assigned`, `/{id}`, `/{id}/messages`, `/{id}/claim`, `/{id}/close`.

## 17. Báo cáo doanh thu và số lượng đơn

Hai tab dùng cùng kiểu bộ lọc thời gian: chọn từng tháng trong 12 tháng của năm hoặc năm tháng gần nhất. Một tháng hiển thị một cột, năm tháng hiển thị năm cột. Nhãn ghi rõ Tháng m/yyyy, không dùng nhãn “Tháng này”.

Bộ lọc hiện hành gồm thời gian, danh mục, thương hiệu và sản phẩm. Lọc sản phẩm phụ thuộc các lựa chọn danh mục/thương hiệu. Đã bỏ lọc tài khoản, nhà cung cấp và xuất báo cáo theo yêu cầu.

Nhấn Áp dụng gửi kỳ và các ID lọc tới `/admin/statistics/reports/revenue` hoặc `/orders`. Backend dùng cùng bộ điều kiện để tính tóm tắt, biểu đồ và bảng chi tiết; frontend không chỉ thay biểu đồ rồi giữ nguyên bảng dưới.

Bảng chi tiết thể hiện kỳ theo tháng, ví dụ Tháng 10/2026. Với phản hồi biểu đồ một tháng gồm các điểm ngắn hơn, frontend dùng tổng kỳ để tạo một cột theo yêu cầu hiển thị. Backend vẫn tổng hợp bảng chi tiết theo tháng lịch.

Doanh số báo cáo hiện tính sau giảm giá, thuộc đơn đã giao và đã xác nhận thanh toán, theo ngày giao hàng; không gồm phí vận chuyển và chưa trừ hoàn tiền. Báo cáo số lượng dựa trên ngày đặt đơn. Do đó phải đọc đúng định nghĩa chỉ tiêu, không mặc định mọi ô “doanh thu” ở mọi màn hình đều có cùng phạm vi tính.

## 18. Chương trình khuyến mãi và mã giảm giá

### 18.1. Dữ liệu và quan hệ

| Bảng | Vai trò và thuộc tính chính |
|---|---|
| `Promotions` | Tên/mô tả, loại và giá trị giảm, đơn tối thiểu, giảm tối đa, bắt đầu/kết thúc, trạng thái, người/ngày tạo |
| `PromotionProducts` | Liên kết chương trình với các Product được giảm |
| `PromotionCategories` | Liên kết chương trình với các danh mục được giảm |
| `Coupons` | Mã Code, tên Name, PromotionId, UsageLimit, UsedCount, IsActive, người/ngày tạo |

Một chương trình có nhiều mã. Tạo chương trình không tự tạo mã mặc định và không đổi quan hệ về một–một. Khách chủ động nhập mã; luồng hiện hành không tự giảm mọi đơn và không tự cấp voucher theo lịch sử mua của từng khách.

### 18.2. Phạm vi áp dụng

Dropdown danh mục có Tất cả. Khi chọn tất cả danh mục, sản phẩm tự là tất cả và bị khóa. Khi chọn một danh mục, chỉ liệt kê sản phẩm của danh mục đó; người dùng chọn toàn bộ hoặc nhiều Product cụ thể.

Backend hiểu danh sách sản phẩm và danh mục theo phép hợp. Vì vậy payload phải giữ đúng ý nghĩa: toàn bộ là hai tập rỗng; toàn bộ một danh mục là CategoryIds; một số sản phẩm là ProductIds và không gửi kèm CategoryIds của cả danh mục. Nhờ đó chọn một số sản phẩm không vô tình mở rộng thành toàn danh mục.

Phạm vi liên kết theo Product cha, không theo một SKU riêng. Chương trình đang Active khóa các trường điều kiện, giá trị, thời gian và phạm vi theo backend; tên, mô tả và trạng thái được xử lý theo quy tắc cho phép.

### 18.3. Form mã con

Name và Code là hai trường riêng. Admin chọn chương trình mẹ có sẵn. Nếu không có chương trình, dropdown thực sự trống và không thể lưu mã hợp lệ.

Loại giảm, giá trị, đơn tối thiểu, giảm tối đa, thời gian và mô tả được lấy từ mẹ; ô xám chỉ đọc. Các trường này không được gửi để sao chép thành điều kiện riêng trong Coupon. Người tạo và ngày tạo lấy từ server, được xem trong chi tiết.

Lượt sử dụng hiển thị `UsedCount/UsageLimit`, ví dụ `7/100`. NULL là không giới hạn, hiển thị `x/∞`; giới hạn 0 là `0/0`, không coi là không giới hạn. Admin nhập hạn mức, backend quản lý số lượt đã dùng và không cho hạn mức nhỏ hơn lượt đã dùng.

### 18.4. Bốn trạng thái hiện hành

| Trạng thái mã | Quy tắc chính | IsActive |
|---|---|---|
| Hết chương trình | Mẹ hết hạn/bị hủy hoặc đã qua ngày kết thúc | false |
| Hết lượt | Chưa hết chương trình và UsedCount đạt/vượt UsageLimit hữu hạn | false |
| Đang áp dụng | Còn lượt, mẹ được áp dụng và đang trong kỳ | true |
| Chưa bắt đầu | Những trường hợp chưa đủ điều kiện bắt đầu còn lại | false |

Đã bỏ trạng thái Tạm ngừng và ô chỉnh riêng trạng thái mã theo quyết định mới nhất. `IsActive` là kết quả backend tính, không phải công tắc do admin tự đặt. Mã hết chương trình được ưu tiên hơn hết lượt.

Promotion Scheduled/Active được đồng bộ theo giờ máy chủ; Draft và Cancelled vẫn là quyết định quản trị. API admin trả trạng thái và thời điểm đánh giá. Danh sách/chi tiết đọc lại mỗi 30 giây và khi quay lại cửa sổ; form đang nhập không bị tự đọc lại rồi mất bản nháp.

Đồng bộ cột dữ liệu được thực hiện khi API quản lý được gọi. Khi khách áp mã, backend tính lại hiệu lực ngay cả khi admin chưa mở trang. Hiện không có cron riêng ghi trạng thái đúng mốc thời gian lúc hoàn toàn không có request.

### 18.5. Lưu và sử dụng mã

Sửa chương trình gửi thông tin và phạm vi trong một PATCH. Backend kiểm tra và lưu trong cùng transaction; lỗi ở bất kỳ bước nào hoàn tác toàn bộ. Frontend giữ form để thử lại khi lưu lỗi và không gửi riêng phạm vi trước như cách cũ.

Xem thử mã trên giỏ không trừ lượt. Khi đặt đơn thành công có áp mã, backend khóa dòng Coupon, kiểm tra thời gian/phạm vi/giá trị đơn/hạn mức, tính giảm và tăng UsedCount trong transaction đơn hàng. Đạt lượt cuối làm IsActive=false. Hủy đơn hợp lệ trả lượt; mã được tính lại và có thể áp dụng trở lại nếu mẹ còn hiệu lực.

Không xóa cứng mã đã được đơn tham chiếu. Chương trình có mã liên kết cũng có quy tắc ngăn xóa; hủy chương trình là thao tác riêng ảnh hưởng các mã con.

API chính: `/admin/promotions`, `/admin/promotions/{id}`, `/{id}/cancel`, `/{id}/coupons`, `/admin/coupons`, `/admin/coupons/{id}`. API xem thử mã là `/cart/coupon-preview`, do backend nghiệp vụ đơn hàng dùng cùng cách tính.

## 19. Tính nhất quán dữ liệu và thời gian

Mỗi use case ghi của backend dùng ranh giới transaction phù hợp. Service được gọi lồng nhau trên cùng Session có thể tham gia transaction của use case ngoài cùng. Lỗi dẫn tới rollback; ràng buộc unique, khóa ngoại và CHECK được dùng cùng kiểm tra nghiệp vụ.

Các thao tác cạnh tranh như lấy tồn kho, dùng lượt coupon, nhận phiếu, chuyển giai đoạn và nhận hội thoại dùng khóa/kiểm tra trạng thái phù hợp. Một giao diện vẫn phải xử lý phản hồi xung đột vì dữ liệu có thể bị người khác thay đổi sau lúc mở trang.

Nhiều HTTP request liên tiếp không tự hợp thành một transaction PostgreSQL. Sửa Promotion, sửa phiếu nhập và lưu form tin tức/banner đều dùng một API lưu nguyên khối trong từng transaction. Tin tức và banner vẫn là hai loại nội dung độc lập, mỗi form chỉ lưu bản ghi của nó. Việc upload Storage vẫn nằm ngoài transaction của CSDL quan hệ; file được tải lên trước khi lưu bản ghi.

Giờ máy khách được dùng cho lựa chọn kỳ báo cáo/tổng quan theo yêu cầu giao diện. Giờ server quyết định hiệu lực mã và thời điểm nghiệp vụ. Dữ liệu ngày giờ từ API được định dạng khi hiển thị; không coi nhãn tháng do frontend tạo là số liệu kế toán.

## 20. Ma trận giao tiếp giữa các nghiệp vụ

| Thao tác admin/hệ thống | Dữ liệu chính được tác động | Đầu ra/liên kết |
|---|---|---|
| Thêm sản phẩm mới | Products + ProductVariants + ProductImages/metadata | Có cha, biến thể đầu và lựa chọn mặc định |
| Chọn ảnh biến thể | Bộ ảnh cha + metadata JSON | Mỗi SKU có tập ảnh và ảnh đại diện riêng |
| Lập phiếu nhập | PurchaseOrders + PurchaseOrderItems | Phiếu với số đặt và giá nhập |
| Nhận hàng | ReceivedQuantity + ProductVariants + serial + receipt | Tăng tồn theo thực nhận, cập nhật giá vốn và lịch sử |
| Thay đổi kho chạm ngưỡng | ProductVariants + Notifications | Thông báo cho nội bộ, mở đúng chi tiết SKU |
| Xử lý đơn | Orders + history + dữ liệu serial/thanh toán phù hợp | Trạng thái, tiền và lịch sử nhất quán theo use case |
| Tiến giai đoạn đổi trả | ReturnRequests + history + notification | Tiến độ gửi khách, không tự hoàn tiền |
| Ghi kết quả bảo hành | WarrantyRequests + history + notification | Kết quả, người/thời điểm ghi nhận gửi khách |
| Nhận hội thoại | Conversations.AssignedStaffId | Một người hỗ trợ tại một thời điểm |
| Gửi tin | Messages | Lưu nội dung, người gửi và thời điểm |
| Tạo chương trình/mã | Promotions + liên kết phạm vi + Coupons | Điều kiện ở mẹ, danh tính/hạn mức ở con |
| Đặt/hủy đơn có mã | Orders + Coupons.UsedCount/IsActive | Dùng/trả lượt trong transaction nghiệp vụ |
| Xem báo cáo | Truy vấn dữ liệu đơn và dòng hàng | Tổng hợp, biểu đồ và bảng theo cùng bộ lọc |

## 21. Cách đọc và cập nhật tài liệu về sau

Các file ghi chú không được import vào chương trình và không được backend thực thi. Sửa nội dung Word/Markdown không tự thay đổi API, CSDL hay trạng thái nghiệp vụ. Ngược lại, khi thay đổi quy tắc trong code, cần cập nhật tài liệu để người bàn giao không dựa vào mô tả cũ.

File này và bản Word cùng tên mô tả cách triển khai tổng thể. `promotion-coupon-notes.md` là ghi chú đã lưu riêng cho khuyến mãi/mã giảm giá; phần quyết định hiện hành ở đầu file có giá trị hơn các ghi chú lịch sử được giữ ở dưới.

Các tài liệu nền như `docs/auth-setup.md`, `docs/database-schema.md`, `docs/business-requirements.md`, `docs/api-endpoints.md`, `docs/admin-products.md` và `docs/admin-dashboard.md` vẫn có thể tham khảo. Cần đối chiếu mã nguồn và các quyết định gần đây khi một tài liệu nền chưa được cập nhật theo luồng admin mới.

Khi làm tiếp: trong frontend admin có thể triển khai theo yêu cầu đã được giao; thay đổi backend, CSDL hoặc phần source ngoài frontend admin cần xin phép theo giới hạn người dùng đặt. Tài liệu này không phải sự cho phép thực hiện một migration hay bật chức năng đang tạm dừng.

## Phụ lục A. Nguồn thiết kế giao diện chính

File Figma: https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI

| Chức năng | Node mẫu chính đã nhận trong trao đổi |
|---|---|
| Tổng quan | `196:2` |
| Danh sách sản phẩm | `213:44` |
| Chi tiết/thêm/sửa sản phẩm | `309:174`, `348:252`, `309:408` |
| Danh mục, thương hiệu | `352:278`, `399:371` |
| Đơn hàng và chi tiết | `229:122`, `229:548` |
| Nhà cung cấp | `552:671` |
| Nhập hàng và chi tiết | `551:559`, `551:800` |
| Thêm/sửa phiếu nhập | `551:1041`, `551:1282` |
| Đánh giá và chi tiết | `610:850`, `610:1262` |
| Tin tức | `614:882`, `614:1260`, `614:1296`, `614:1328` |
| Banner | `614:1369`, `614:1752`, `614:1788`, `614:1824` |
| Thanh toán và phương thức | `667:1106`, `667:1399`, `667:1427` |
| Hỗ trợ và đang hỗ trợ | `658:1036`, `658:1263` |
| Đổi trả và chi tiết | `494:507`, `494:750` |
| Bảo hành và chi tiết | `489:453`, `489:741` |
| Báo cáo doanh thu/số lượng | `598:780`, `598:1025` |
| Vận chuyển và form | `799:1406`, `804:1486`, `804:1527` |
| Chương trình khuyến mãi | `445:412`, `445:690`, `445:727`, `445:780`, `445:833` |
| Mã giảm giá | `791:1141`, `894:1876`, `894:1913`, `894:2019` |

Figma là nguồn trình bày giao diện. Những điều chỉnh đã chốt về SKU, thực nhận, trạng thái, phạm vi giảm, điều kiện bảo hành/đổi trả và cách upload ảnh được ưu tiên khi khác hình mẫu. Phụ lục lưu nguồn đã nhận, không có nghĩa từng frame được mở lại trong lần lập tài liệu này.
