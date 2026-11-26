# Admin tiếp quản đơn hàng — 26/11/2026

## Quy tắc

- Người đầu tiên xác nhận đơn `Pending` được lưu vào `Orders.AssignedStaffId` làm người phụ trách ban đầu.
- Nhân viên chỉ xử lý đơn đã gán cho mình, hoặc đơn `Pending` chưa có người phụ trách. Nếu Admin xác nhận đầu tiên, Staff không thể xử lý các bước tiếp theo.
- Admin được can thiệp ở mọi bước còn hiệu lực, kể cả khi Staff là người phụ trách. Admin không thay đổi người phụ trách ban đầu; sau thao tác Admin, Staff ban đầu vẫn có thể tiếp tục xử lý.
- Ghi chú nội bộ không nhận hoặc thay đổi người phụ trách. Với đơn cũ chưa có người phụ trách, Staff vẫn chỉ được nhận nếu đơn đang `Pending`; Admin có thể xử lý. Nếu Admin chuyển trạng thái hoặc xác nhận COD cho đơn cũ chưa có người phụ trách, Admin được ghi làm người phụ trách.
- Đơn bị hủy là trạng thái kết thúc, không còn bước xử lý tiếp theo.

## Cách thực hiện

Quyền được kiểm tra ở cả giao diện và backend. Backend khóa dòng đơn trước khi cập nhật trạng thái, nên hai lần xác nhận đơn Pending được tuần tự hóa theo từng đơn. Admin có quyền vượt qua quyền thao tác của Staff nhưng giữ nguyên người phụ trách ban đầu. Không thêm bảng/cột hay migration; dùng `AssignedStaffId` hiện có.

Với đơn cũ mà phiên bản trước đã ghi đè `AssignedStaffId` khi Admin can thiệp, hệ thống suy ra người phụ trách từ người thực hiện lần chuyển `Pending → Confirmed` đầu tiên trong lịch sử. Khi có thao tác cập nhật tiếp theo, backend khôi phục `AssignedStaffId` theo lịch sử này; giao diện cũng dùng cùng căn cứ để hiển thị quyền thao tác trước khi gửi yêu cầu.

Các sự kiện lịch sử trạng thái vẫn lưu người thực hiện thực tế trong `OrderStatusHistories.ChangedByUserId`, kể cả khi Admin làm thay nhân viên.
