# VieTech – Ma trận quyền

Ngày cập nhật: 09/10/2026. Căn cứ: báo cáo Bảng 3.2–3.38 bản mới, quyết định bắt đầu Giai đoạn 5 và quyết định ngày 09/10/2026 (Admin trả lời chat; Staff xem lịch sử nhập). **Quyền nghiệp vụ bên dưới là đặc tả cho các giai đoạn tiếp theo**, không có nghĩa endpoint nghiệp vụ đã được triển khai.

## 1. Quyền tài khoản

Giai đoạn 5 triển khai các dòng Auth/hồ sơ/quản trị; dòng địa chỉ mô tả quyền cho CRUD ở Giai đoạn 4.

| Thao tác | Customer | Staff | Admin |
|---|---|---|---|
| Đăng ký công khai | Tạo Customer qua OTP | Không | Không |
| Hồ sơ, đổi mật khẩu/email | Chính mình | Chính mình | Chính mình |
| Địa chỉ (theo Giai đoạn 4) | Chính mình | Không | Không |
| Xem danh sách/chi tiết người dùng phục vụ quản trị | Không | Không | Chỉ Customer/Staff |
| Tạo Staff | Không | Không | Có |
| Tạo Admin qua API | Không | Không | Không |
| Sửa/khóa/mở khóa/xóa mềm Customer hoặc Staff | Không | Không | Có |
| Sửa/khóa/mở khóa/xóa mềm Admin qua API quản trị | Không | Không | Không |
| Đổi role | Không | Không | Không |

Hệ thống chỉ có ba role `Customer`, `Staff`, `Admin`. Admin chỉ quản lý Customer/Staff; danh sách quản trị không trả tài khoản Admin. Admin đầu tiên được tạo bằng CLI quản trị riêng, không có API tạo thêm Admin hoặc nâng/hạ quyền. Tài khoản giữ nguyên role khi cập nhật; gửi role khác bị từ chối.

Không có thao tác quản trị khóa/xóa/đổi role chính mình. Hồ sơ cá nhân tách khỏi API quản trị. Thông tin trả về không có `PasswordHash`, OTP hoặc token phiên. Sửa người khác không cho đổi trực tiếp email/mật khẩu để bỏ qua các luồng xác minh; phạm vi trường sửa được phải được giới hạn trong request schema.

## 2. Quyền nghiệp vụ theo báo cáo đã chỉnh

| Nhóm | Customer | Staff | Admin |
|---|---|---|---|
| Sản phẩm, danh mục, thương hiệu | Xem dữ liệu công khai | Xem/tra cứu | Thêm/sửa/ẩn và xem |
| Khuyến mãi (B3.14) | Xem khuyến mãi công khai | Không | Thêm/sửa/ngừng áp dụng và xem |
| Nhà cung cấp (B3.16) | Không | Tra cứu để lập phiếu nhập | Thêm/sửa/ẩn và xem |
| Phiếu nhập | Không | Tạo, tìm kiếm, xem; sửa/gửi lại/hủy theo trạng thái | Tạo, xem, sửa theo trạng thái, duyệt/từ chối/hủy |
| Lịch sử nhập hàng | Không | Xem/lọc theo B3.18 | Xem/lọc theo B3.18 |
| Tồn kho, cảnh báo | Xem khả năng mua hàng | Xem | Xem và đặt ngưỡng |
| Giỏ hàng, yêu thích, đặt/thanh toán | Chính mình | Không thay Customer | Không thay Customer |
| Xem/tìm đơn hàng | Đơn của mình | Toàn hệ thống theo báo cáo | Toàn hệ thống |
| Xử lý đơn hàng | Hủy đơn mình theo điều kiện | Theo workflow và phạm vi được giao | Theo workflow |
| Bảo hành/đổi trả | Yêu cầu và theo dõi của mình | Tiếp nhận/xử lý; duyệt hoặc từ chối đổi trả | Tiếp nhận/xử lý; duyệt hoặc từ chối đổi trả |
| Cấu hình phương thức thanh toán | Không | Không (chỉ xem danh sách) | Có |
| Hoàn tiền | Nhận kết quả của mình | Thực hiện hoàn tiền | Thực hiện hoàn tiền; xác nhận thủ công giao dịch đang chờ |
| Xuất báo cáo | Không | Không | Có |
| Thống kê | Không | Xem | Xem |
| Đánh giá | Gửi/sửa đánh giá của mình khi đủ điều kiện | Không | Xem/lọc/ẩn (xóa mềm) vi phạm |
| Tin tức, banner | Xem nội dung công khai | Không | Thêm/sửa/xem/đăng/ẩn |
| Chat người thật | Hội thoại của mình | Nhận và trả lời hội thoại; xem lịch sử | Nhận và trả lời hội thoại; xem lịch sử |
| Chat AI | Hội thoại của mình | Không được nêu quyền | Không được nêu quyền |

Quyền từng role được cấp theo bảng này. Admin có mọi quyền nghiệp vụ của Staff, cộng thêm các quyền quản lý. Những quyền/luồng còn thiếu quy tắc nghiệp vụ vẫn chưa mở endpoint.

## 2a. Mã quyền

Mỗi chức năng quản trị có đủ năm thao tác **Xem / Thêm / Sửa – Cập nhật / Xóa / Xuất báo cáo**, mỗi ô là một mã quyền `chức-năng:thao-tác` trong `backend/app/core/rbac.py` (`view`, `create`, `update`, `delete`, `export`). Bảng dưới là **quyền của Staff**; Admin có tất cả các mã.

| Chức năng | Mã | Staff | Bảng |
|---|---|---|---|
| Tài khoản | `users:read`, `users:manage`, `users:export` | Không (chỉ Admin, cố định) | 3.8 |
| Sản phẩm | `products:*` (delete: ẩn) | Xem | 3.9–3.11 |
| Danh mục | `categories:*` | Xem | 3.12 |
| Thương hiệu | `brands:*` | Xem | 3.13 |
| Khuyến mãi và mã giảm giá | `promotions:*` (gồm Coupons) | Không | 3.14 |
| Nhà cung cấp | `suppliers:*` | Xem | 3.16 |
| Phiếu nhập hàng | `purchases:*` (update: sửa/gửi lại, duyệt/từ chối chỉ Admin; delete: hủy) | Xem, Thêm, Sửa, Xóa | 3.17 |
| Lịch sử nhập hàng | `purchase_history:*` | Xem | 3.18 |
| Kho hàng | `inventory:*` (update: mức cảnh báo) | Xem | 3.19 |
| Phương thức vận chuyển | `shipping_methods:*` | Xem | 3.21 |
| Đơn hàng | `orders:*` (update: trạng thái, hủy) | Xem, Sửa | 3.25, 3.26, 3.29 |
| Phương thức thanh toán | `payment_methods:*` | Xem | 3.23 |
| Hoàn tiền | `refunds:*` (create: thực hiện hoàn tiền; xác nhận thủ công chỉ Admin) | Xem, Thêm | 3.22, 3.28 |
| Bảo hành | `warranties:*` | Xem, Sửa | 3.27 |
| Đổi / Trả | `returns:*` | Xem, Sửa | 3.28 |
| Thống kê doanh thu | `revenue_reports:*` | Xem | 3.30 |
| Thống kê đơn hàng | `order_reports:*` | Xem | 3.31 |
| Đánh giá | `reviews:*` (delete: xóa mềm kèm lý do) | Không | 3.33, 3.34 |
| Tin tức | `news:*` | Không | 3.35 |
| Banner | `banners:*` | Không | 3.36 |
| Chat với khách hàng | `chat:*` (create: nhận và trả lời) | Xem, Thêm | 3.37 |

Quyết định 09/10/2026: mã giảm giá thuộc Khuyến mãi; **Xuất báo cáo** chỉ Admin; **Hoàn tiền** cấp cho Staff và Admin; Phương thức vận chuyển do Admin quản lý, Staff xem.

**Quyết định 11/10/2026:** quyền Staff trong bảng trên được đồng bộ theo kiểm tra quyền của các Service giai đoạn 4; ngoại lệ duy nhất là Staff được xem thống kê. Các bước duyệt (phiếu nhập, xác nhận hoàn tiền thủ công, duyệt bảo hành/đổi trả, đăng tin) vẫn chỉ Admin trong Service.

**Quyền cố định (quyết định 09/10/2026):** quyền của cả ba vai trò được khai báo trong `backend/app/core/rbac.py` và không có giao diện hay API để thay đổi. Muốn đổi quyền phải sửa code, chạy lại test và triển khai lại.

## 3. Phạm vi và điều kiện bổ sung

- Role cho phép nhóm thao tác; backend vẫn kiểm tra chủ sở hữu, nhân viên phụ trách, trạng thái hiện tại và điều kiện nghiệp vụ. Quyền xem không tự cho quyền cập nhật.
- B3.25–3.26 cho Staff xem đơn toàn hệ thống. Phạm vi cập nhật đơn/bảo hành/đổi trả theo người phụ trách cần chốt với workflow trước khi triển khai các service đó.
- Staff sửa/gửi lại/hủy phiếu nhập theo trạng thái nhưng không duyệt/từ chối (B3.17); được xem/lọc lịch sử nhập (B3.18). Xuất báo cáo nhập hàng mặc định chỉ Admin.
- Chat người thật (B3.37): Staff và Admin đều nhận/trả lời; nhận chat phải tránh hai người cùng nhận một hội thoại.
- Không cấp Customer quyền kiểm duyệt hoặc quản lý banner từ các lỗi tác nhân trong B3.33, B3.34, B3.36.
- Danh mục/thương hiệu/nhà cung cấp đã ẩn vẫn hiện với Staff/Admin ở trạng thái ẩn (B3.12, 3.13, 3.16), khách hàng không thấy.
- Luồng hoàn tiền (COD hoàn theo cách nào, công thức số tiền) vẫn cần đặc tả trước khi làm service. Quyền điều chỉnh tồn trực tiếp, duyệt đăng nội dung và chuyển người phụ trách vẫn cần mô tả riêng; chưa mở mặc định.
