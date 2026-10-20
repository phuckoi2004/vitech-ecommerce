# Danh mục, thương hiệu và quyền phiếu nhập — 20/10/2026

Phạm vi được người dùng cho phép trong yêu cầu này: frontend admin, backend/API và CSDL liên quan đến xóa danh mục/thương hiệu và quyền thao tác phiếu nhập. Không mở rộng sang chức năng khách hàng hoặc các nghiệp vụ khác.

## Danh mục và thương hiệu

- `IsActive=false` là ẩn với khách, vẫn xem được trong quản trị.
- Thêm `IsDeleted` vào `Categories` và `Brands`. Xóa đặt `IsDeleted=true`, `IsActive=false`; không xóa vật lý hoặc xóa sản phẩm liên quan.
- Danh sách, truy cập theo ID/slug và bộ chọn qua API loại bản ghi đã xóa, kể cả người gọi là Admin/Staff. Không có API khôi phục trong phạm vi này.
- Giữ liên kết sản phẩm và danh mục con để không xóa dây chuyền dữ liệu. Danh mục con vẫn có thể sửa mà giữ liên kết cha cũ; không cho chọn mới danh mục cha đã xóa. Slug của bản ghi xóa mềm vẫn được giữ, không tái sử dụng.

## Phiếu nhập

- Staff tạo phiếu; chỉ sửa và gửi lại phiếu mình tạo ở trạng thái cho phép. Backend kiểm tra quyền sở hữu cho sửa đầu phiếu, thêm/sửa/xóa dòng và gửi lại.
- Staff không có `purchases:delete`; frontend cũng kiểm tra `Role=Admin` để không hiện nút xóa kể cả phiên cũ còn danh sách quyền cũ.
- Bỏ API và nút hủy phiếu. Các bản ghi `Cancelled` cũ vẫn được giữ, không chuyển trạng thái dữ liệu lịch sử.
- Admin duyệt/từ chối theo luồng hiện có; từ chối giữ phiếu và lý do. Không đổi quy tắc Admin tạo phiếu được duyệt ngay.
- `DELETE /admin/purchase-orders/{id}` chỉ Admin được gọi, trả 204. Mọi trạng thái đều xóa được.
- Xóa đầu phiếu, các dòng sản phẩm và lịch sử nhận hàng trong cùng giao dịch; không hoàn tác tồn kho, giá vốn hoặc Serial/IMEI đã ghi nhận. Giao diện yêu cầu xác nhận và nêu rõ tác động.
- Khóa dòng phiếu trước khi xóa để tuần tự với sửa, duyệt và nhận hàng.
- FK lịch sử nhận hàng chuyển sang CASCADE. Trigger vẫn cấm sửa hoặc xóa riêng lịch sử; chỉ cho phép xóa dây chuyền khi đầu phiếu đã bị xóa.

## Phân quyền dùng chung khu vực admin

- Vai trò nằm tại `Users.Role`: `Customer`, `Staff`, `Admin`.
- Ma trận quyền nằm tại `backend/app/core/rbac.py`; không tách thư mục giao diện nhân viên riêng.
- Frontend dùng `RequireInternal`, `RequirePermission`, danh sách quyền để lọc menu và kiểm tra vai trò/người tạo cho từng thao tác.
- Backend dựng Actor từ người dùng đã xác thực và kiểm tra lại trong service. Ẩn nút không thay thế kiểm tra API.

## CSDL và migration

- File migration nguồn: `a6d2e8f4b190_catalog_soft_delete_purchase_delete.py`, sau `7e4c9b2d1a60`.
- CSDL thật đang ghi revision `93e7a2b0c518`, nhưng source được cung cấp chưa có file revision đó. Không tự stamp, sửa hoặc giả lập lịch sử migration này.
- Ngày 20/10/2026 đã áp dụng trực tiếp **đúng phần DDL của migration mới**, trong một transaction sau khi kiểm tra cột, tên FK và trigger hiện có. Giữ nguyên `alembic_version=93e7a2b0c518`.
- Đã xác minh hai cột xóa mềm và hai FK CASCADE. Số bản ghi các bảng liên quan, tồn kho, giá vốn và nội dung Serial giữ nguyên trước/sau áp dụng. Không xóa thử chứng từ trên CSDL thật.
- Cần nhận lại file migration `93e7a2b0c518` từ người phụ trách trước khi đồng bộ đồ thị migration toàn dự án. Migration mới cho phép cột `IsDeleted` đã tồn tại để hỗ trợ trường hợp DDL đã áp dụng.

## Kiểm thử

- 103 kiểm thử frontend thuộc danh mục, thương hiệu và phiếu nhập đã đạt khi chạy tuần tự. Build thành công; lint còn hai cảnh báo cũ ở `useAdminQuery.js` và `AdminTable.jsx`.
- 128 kiểm thử backend liên quan đã đạt, gồm service, quyền sở hữu, xóa/rollback, API, truy cập danh mục xóa mềm và đồ thị/SQL migration. Thay đổi kiểm thử bổ sung sau đó được chạy lại riêng.
- Chạy rộng backend không bật PostgreSQL integration: 1124 đạt, 17 bỏ qua và 4 thất bại ban đầu. Một thất bại do số lượng migration mới đã được cập nhật và kiểm thử lại thành công.
- Ba thất bại còn lại nằm trong `test_business_routers.py`: hai bài giả định mọi route đều gọi một `service.*`, không phù hợp route tải ảnh; một bài vẫn giả định receive bảo hành chuyển nguyên body `None` thay vì `WarrantyProgressRequest`. Các route và bài kiểm thử này không được sửa trong phạm vi này.
- Kiểm thử service dùng fake và kiểm thử catalog dùng SQLite; không thay thế kiểm thử khóa/cascade PostgreSQL đồng thời thực tế.
