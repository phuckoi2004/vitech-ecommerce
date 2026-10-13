# Giao diện tổng quan quản trị

Mở `/admin` sau khi đăng nhập bằng tài khoản Admin/Staff. Frontend dùng API client và cơ chế refresh phiên hiện có, qua proxy `/api` tới backend. Không cần migration hoặc dữ liệu mẫu.

Thiết kế theo frame Figma `196:2`: sidebar 248px, nền xanh navy, header 82px, bốn ô thống kê và hai bảng. Đã bỏ tìm kiếm, nút thông báo và biểu đồ doanh thu theo yêu cầu. Màn hình nhỏ tự xếp lại các ô và bảng.

Khung admin, trang tổng quan, bảng dữ liệu và các trang danh sách mới sử dụng utility class Tailwind CSS cho bố cục, khoảng cách, màu sắc, responsive và trạng thái tương tác. Màu VIETECH và font được khai báo bằng `@theme` trong `frontend/src/index.css`, sinh các utility như `bg-admin-navy`, `text-admin-muted`, `border-admin-border`, `font-admin`. Các class trạng thái đều viết đầy đủ để Tailwind phát hiện khi build. `AdminLayout.css` và `DashboardPage.css` đã được thay thế bằng utility class; CSS riêng của các trang tài khoản/hồ sơ có sẵn vẫn được dùng.

| Nội dung | API / trường dữ liệu |
|---|---|
| Tổng đơn hàng | `GET /admin/statistics/orders` → `TotalOrders` |
| Doanh thu | `GET /admin/statistics/revenue` → `NetRevenue` |
| Đơn chờ xử lý | `GET /admin/statistics/orders` → `ByStatus.Pending` |
| Sản phẩm sắp hết | `GET /admin/inventory/low-stock` → `Total` (toàn bộ biến thể, không phải số dòng của trang đầu) |
| Đơn hàng mới nhất | `GET /admin/orders?page=1&page_size=4`, backend sắp xếp ngày đặt giảm dần |
| Cảnh báo tồn kho | `GET /admin/inventory/low-stock?page=1&page_size=4`, tên sản phẩm từ `GET /admin/products/{id}` |

Ba chỉ số đơn hàng/doanh thu dùng tháng được chọn và ngày lịch Việt Nam, tính cả ngày cuối tháng. Tồn kho là số hiện tại; đơn hàng mới nhất lấy trên toàn bộ lịch sử. Doanh thu giữ đúng nghiệp vụ backend: tiền đã thu trừ tiền đã hoàn của đơn đủ điều kiện ghi nhận doanh thu.

API đơn hàng hiện trả `ReceiverName`, không có tên tài khoản khách hàng, nên cột tương ứng dùng tên **Người nhận**. Cảnh báo tồn kho có cột **Sản phẩm / Biến thể** và **Tồn kho**, hiển thị SKU để phân biệt các biến thể cùng sản phẩm.

Khi API trả dữ liệu rỗng, bốn chỉ số bằng 0, bảng giữ tiêu đề cột và thông báo chưa có dữ liệu. Khi đang tải hoặc API lỗi, giao diện hiển thị trạng thái tương ứng và nút thử lại; không biến lỗi kết nối thành số 0. Các yêu cầu cũ bị hủy khi chuyển trang/đổi tháng.

Sidebar dùng danh sách quyền từ phiên đăng nhập, có menu con Sản phẩm. Các mục nghiệp vụ mở bảng đọc dữ liệu API có phân trang/làm mới; Tin tức & Banner, Nhập hàng, Kho hàng và Thanh toán có các tab tương ứng. Đánh giá được xem theo sản phẩm. Hỗ trợ khách hàng của Staff hiển thị hội thoại được phân công; Admin xem toàn bộ hội thoại. Các form tạo/sửa và quy trình nghiệp vụ của các mục mới chưa nằm trong thay đổi này. Trang tài khoản và hồ sơ vẫn dùng phần triển khai sẵn có.

URL từng mục (`/admin/orders`, `/admin/products`, …) hỗ trợ tải lại và Back/Forward. Máy chủ triển khai frontend cần trả `index.html` cho các đường dẫn giao diện này, như cấu hình SPA hiện có của Vite.

Kiểm tra tại `frontend`:

```powershell
npm.cmd test
npm.cmd run build -- --configLoader native
```

Test mới kiểm tra hợp đồng API, ngày Việt Nam/năm nhuận, số đếm tồn kho qua phân trang, dữ liệu trống, trạng thái lỗi/thử lại, dữ liệu thật, hủy phản hồi cũ và thao tác dropdown. Các kiểm tra component dùng JSX thực và render HTML, chưa thay thế kiểm thử trực quan hoặc đăng nhập/API thật trên trình duyệt.
