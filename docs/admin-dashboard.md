# Tổng quan quản trị — cấu trúc frontend Stage 8.2

Trang `/admin` triển khai frame Figma `196:2` bằng Tailwind, sử dụng React Router, AuthProvider, API client và các component dùng chung của bản frontend hiện tại. Sidebar/header, bốn ô thống kê, biểu đồ doanh thu, bảng đơn mới, cảnh báo tồn kho và chuông thông báo đều hoạt động. Không sửa luồng đăng nhập hoặc backend trong thay đổi này.

## Tháng và dữ liệu thật

- `new Date()` lấy đồng hồ và múi giờ địa phương của trình duyệt. Biểu đồ gồm tháng hiện tại và bốn tháng trước, tự xử lý đổi năm và tháng 2 năm nhuận. Ví dụ đồng hồ ở tháng 10/2026 sẽ hiển thị 06–10/2026. Tháng được cập nhật mỗi 30 giây và khi quay lại cửa sổ/tab.
- Đồng hồ máy chọn khoảng thời gian; số liệu doanh thu lấy từ API, không suy ra từ đồng hồ. API thống kê vẫn nhận ngày lịch Việt Nam, tính cả ngày cuối tháng.
- Tổng đơn hàng và doanh thu dùng tháng hiện tại. Đơn chờ xử lý là toàn bộ đơn Pending. Tồn kho là số hiện tại. Đơn mới nhất lấy trên toàn bộ lịch sử.
- Khi chưa có dữ liệu: chỉ số bằng 0, không tạo cột biểu đồ/bản ghi giả; vẫn giữ nhãn tháng, tiêu đề cột và thông báo trống. Khi API lỗi: hiển thị lỗi và nút thử lại, không coi lỗi là số 0.
- So sánh tháng trước chỉ hiển thị khi có giá trị gốc dương; không tạo tỷ lệ tăng khi tháng trước bằng 0. Doanh thu thuần có thể âm do hoàn tiền; biểu đồ hỗ trợ cột âm.

## API và component

| Nội dung | API |
|---|---|
| Tổng đơn, so sánh tháng trước | `/admin/statistics/orders?date_from=...&date_to=...` |
| Doanh thu và biểu đồ 5 tháng | `/admin/statistics/revenue?date_from=...&date_to=...` |
| Đơn chờ xử lý | `/admin/orders?order_status=Pending&page_size=1` → `Total` |
| Đơn hàng mới nhất | `/admin/orders?page=1&page_size=4` |
| Cảnh báo tồn kho | `/admin/inventory/low-stock?page=1&page_size=4` → `Items`, `Total` |
| Tên sản phẩm trong cảnh báo | `/admin/products/{id}`; gộp các biến thể cùng sản phẩm để không đọc trùng |
| Thông báo cá nhân | `/users/me/notifications`, `/users/me/notifications/unread-count` |
| Đánh dấu đã đọc | POST `/users/me/notifications/{id}/read`, `/users/me/notifications/read-all` |

API helper ở `frontend/src/services/api/admin.js`; hook đọc dữ liệu ở `frontend/src/admin/hooks/`; lịch ở `frontend/src/lib/dashboard-periods.js`. Các request dùng `withAccessToken`, cho phép AuthProvider refresh khi hết hạn; request cũ bị hủy khi đổi trang/tháng. Chuông cập nhật số chưa đọc mỗi phút và khi quay lại cửa sổ, có phân trang, đóng bằng Escape/click ngoài. Liên kết thông báo chỉ mở trong khu vực admin.

Cột tên trong bảng đơn dùng **Người nhận** vì API trả `ReceiverName`, không trả tên tài khoản khách hàng. Các SVG chuông và cảnh báo tải trực tiếp từ frame Figma, lưu ở `frontend/src/assets/admin/` (24px, 10px). Avatar trên thanh trên và trang hồ sơ cùng dùng ảnh tài khoản; khi chưa có ảnh, hiển thị chữ viết tắt của tên.

## Admin và Staff

Cùng một `/admin` và cùng component DashboardPage cho cả Admin và Staff. Sidebar lấy quyền từ phiên đăng nhập backend; route có RequirePermission để chặn cả truy cập URL trực tiếp. Staff chỉ thấy các nhóm được cấp quyền, không có quản lý tài khoản, đánh giá, nội dung hoặc khuyến mãi khi không được cấp quyền. Backend vẫn kiểm tra quyền từng yêu cầu. Chuông chỉ đọc thông báo của chính người đăng nhập.

Các mục sidebar mới mở danh sách API có làm mới/phân trang, menu Sản phẩm mở/đóng tại chỗ. Tab nghiệp vụ được lưu trong URL để tải lại và Back/Forward giữ đúng mục. Trang tài khoản và hồ sơ sử dụng phần triển khai sẵn có. Trang danh sách sản phẩm đã được triển khai riêng theo [admin-products.md](admin-products.md), gồm bộ lọc và thao tác thêm/xem/sửa/xóa theo quyền. Các biểu mẫu/quy trình của những mục khác có thể tiếp tục triển khai trên cấu trúc dùng chung.

## Kiểm tra

Chạy `npm.cmd test` và `npm.cmd run build -- --configLoader native` trong `frontend`. Test bao gồm khoảng tháng, năm nhuận, dữ liệu rỗng/thật, API lỗi/thử lại, hủy request, thông báo đã đọc, dropdown, quyền Staff, chặn URL thiếu quyền và Back/Forward.

Đã kiểm tra trực quan bằng Chrome headless trên desktop (1440×1080) và mobile (viewport 390px), với dữ liệu kiểm thử trong bộ dựng tạm đã xóa. Mobile không tràn ngang toàn trang; bảng đơn cuộn ngang riêng. Không dùng tài khoản/mật khẩu thật và không ghi dữ liệu mẫu vào database.
