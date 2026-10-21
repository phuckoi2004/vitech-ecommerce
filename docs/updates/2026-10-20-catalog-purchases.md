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

## Bổ sung: quyền sửa áp dụng cho cả QTV và nhân viên

- Theo yêu cầu tiếp theo trong mục 3.17, bỏ ngoại lệ cho phép Admin sửa/gửi lại phiếu của người khác. Cả Staff và Admin phải là `CreatedByUserId` của phiếu mới được sửa đầu phiếu, thêm/sửa/xóa dòng hoặc gửi lại.
- Frontend áp dụng cùng điều kiện cho nút sửa/gửi lại và URL mở thẳng form; backend vẫn kiểm tra trước khi ghi. Admin vẫn được duyệt/từ chối và xóa phiếu của người khác theo quyền riêng.
- Người dùng yêu cầu giữ phần trạng thái để xem xét luồng trước: chưa đổi tập trạng thái, điều kiện sửa Pending/Rejected, quy tắc Admin tạo được Approved ngay hay luồng nhận hàng/đóng thiếu.
- Vì vậy Admin tạo phiếu mới được Approved ngay thì không sửa nội dung sau khi tạo; Admin chỉ sửa được phiếu của chính mình còn Pending/Rejected, ví dụ phiếu được lập trước khi đổi vai trò.
- Không có migration hoặc thao tác CSDL thật trong lần bổ sung quyền này.

## Đính chính tiếp theo: từ chối là kết thúc, không gửi lại

- Yêu cầu mới nhất của người dùng: chỉ phiếu `Pending` do chính mình tạo được sửa, áp dụng cho cả Staff/Admin. Phiếu `Rejected` đóng, giữ nguyên người xử lý, thời điểm và lý do; muốn nhập hàng phải lập phiếu mới.
- Đã bỏ API `/resubmit`, hàm service và nút/form Gửi lại. Không đổi danh sách trạng thái trong CSDL, quy tắc Admin tạo được duyệt ngay, phần nhận hàng hoặc đóng thiếu. Không có migration hay ghi thử dữ liệu thật.
- Bản báo cáo đầy đủ được cung cấp có `OrderedQuantity` và `ReceivedQuantity` trong `PurchaseOrderItems`; mô tả `PurchaseOrders.Status` chỉ có chờ duyệt / đã duyệt / từ chối. Bảng đặc tả 3.17 không có bước sửa hoặc gửi lại phiếu bị từ chối.
- Báo cáo có dữ liệu để ghi chênh lệch đặt/thực nhận, nhưng chưa đặc tả nhận nhiều đợt hay đóng phiếu thiếu. `PurchaseReceipts`, `PurchaseReceiptItems`, các trường đóng phiếu và các trạng thái `Receiving`/`Completed`/`Closed` là phần mở rộng hiện có của hệ thống.

## Đồng bộ source với nhánh giá và khuyến mãi

- Source đã nhận lại hai revision `82d6f1a9b407` (cách áp dụng khuyến mãi) và `93e7a2b0c518` (giá niêm yết của biến thể). Giữ nguyên mã revision và quan hệ cha của các migration đã có.
- Revision nối lịch sử mới `c3a9f5e7d206` có hai cha `93e7a2b0c518` và `b2f8c6d4e901`, đưa source về một head. Bản thân revision nối không có DDL hoặc thay đổi dữ liệu; kiểm thử kiểm tra đường nâng cấp từ cả hai nhánh mà không chạy lại migration của nhánh đã áp dụng.
- Lần pull/merge này chỉ cập nhật mã nguồn, chưa chạy migration hoặc thay đổi CSDL thật. Các ghi nhận DDL đã áp dụng ở trên vẫn là lịch sử theo thời điểm.
- Giữ giá niêm yết trong quản trị cùng quy tắc giá nhập VND nguyên đồng. Giá giảm tự động và xem thử coupon dùng làm tròn xuống đến đồng; phân bổ coupon dùng chung quy tắc với checkout để không tạo phần lẻ đồng cho dữ liệu giá nguyên đồng.
