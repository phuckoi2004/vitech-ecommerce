# Bảo hành phía khách hàng

Cập nhật ngày 21/10/2026. Tham chiếu giao diện Figma `aLG7De0fgbWCfaIpzIrPii`, frame `874:368` và luồng đang hoạt động trong `docs/api-endpoints.md` (15/10/2026).

## Giao diện và đường dẫn

- Tài khoản: đổi nhãn thành **Bảo hành và đổi trả** (`/tai-khoan?section=service`). Rê chuột hoặc đưa focus bàn phím vào mục này sẽ mở mục con **Tạo yêu cầu bảo hành**. Trên điện thoại, mục con nằm ngay dưới mục cha khi được focus; danh sách cũng có nút tạo rõ ràng.
- Tạo yêu cầu: `/bao-hanh/tao-yeu-cau`, bắt buộc đăng nhập Customer. Bố cục hai cột theo Figma, dùng lại header/footer, logo, ảnh sản phẩm theo biến thể và các thành phần hiện có.
- Chi tiết: `/tai-khoan?section=service&request=<WarrantyRequestId>`. Hiển thị tiến trình, mô tả, minh chứng, lịch sử công khai, kết quả đã công bố và nút hủy trước khi tiếp nhận.
- Thông báo `WarrantyRequest` dẫn thẳng đến chi tiết yêu cầu của khách. Danh sách/chi tiết tải lại khi lấy lại focus hoặc khi bấm Làm mới.

## Gửi và xử lý

1. Danh sách đơn sử dụng `GET /orders` với `order_status=Delivered&order_status=Completed`, có phân trang.
2. `GET /orders/{order_id}/warranty-items` trả các dòng đơn và Serial/IMEI thực sự gắn với từng dòng. Chỉ Customer sở hữu đơn đã giao được đọc. Không trả serial trong kho hay đơn của người khác.
3. Thời hạn, xung đột yêu cầu đang mở/đổi trả và tình trạng serial lấy từ các quy tắc hiện có của `WarrantyService`. API đọc trả `CanRequest`, `Reason`, ngày bảo hành và danh sách thiết bị; không ghi database. Hệ thống vẫn xác minh lại toàn bộ ở bước tạo để xử lý thay đổi đồng thời.
4. Gửi `POST /warranty-requests` với đúng `OrderItemId`, `ProductSerialId` (hoặc null với hàng không quản lý serial), `IssueDescription`, `Attachments`. Loại lỗi, ngày phát sinh và phụ kiện nếu có được ghi rõ trong mô tả. Không tạo thêm cột hoặc trạng thái database.
5. Yêu cầu xuất hiện trong `/admin/warranties` qua API quản trị hiện có. Admin/Staff tiếp nhận, kiểm tra, sửa, công bố kết quả và trả khách bằng workflow đã có. Hai phía dùng chung hàm suy ra giai đoạn từ `Status`, `ReceivedAt`, `ResultApprovedAt`.
6. Khách đọc bằng API `/warranty-requests` và `/warranty-requests/{id}`; hủy bằng `POST /warranty-requests/{id}/cancel` chỉ khi `Status=New` và `ReceivedAt=null`. Nếu admin vừa tiếp nhận, giao diện báo lỗi và tải lại trạng thái.

Response của khách bổ sung `ProductName`, `VariantInfo`, `OrderId`, `OrderCode`, `SerialNumber` của chính sản phẩm đã yêu cầu. Không bổ sung `CustomerId`, người phụ trách, ghi chú nội bộ, nhà cung cấp hay người duyệt. Kết quả chỉ hiện khi `ResultApprovedAt` đã có; backend tiếp tục lọc lịch sử nội bộ.

## Điều chỉnh mẫu Figma theo nghiệp vụ

- Serial/IMEI là lựa chọn từ dữ liệu đơn hàng, không nhập chuỗi tự do. Hàng không quản lý serial không phải nhập trường này.
- Thông tin liên hệ đọc từ tài khoản và có liên kết cập nhật hồ sơ. Không hỏi địa chỉ nhận lại riêng vì API bảo hành hiện tại chưa lưu hoặc vận hành thông tin vận chuyển đó. Nhân viên liên hệ khách để hướng dẫn gửi/nhận.
- Minh chứng tùy chọn nhận tối đa 5 ảnh JPG/PNG/WEBP, mỗi ảnh 2 MiB. `POST /service-request-image-uploads` nhận raw file, kiểm tra kích thước cả header và stream, nhận diện loại ảnh từ dữ liệu rồi lưu vào namespace `service-requests/<user-id>/...` trong kho ảnh hiện có. Trả `{FileUrl, FileType: "Image"}` để đính vào yêu cầu và admin xem bằng giao diện hiện có. Không mở thêm cấu hình bucket hoặc migration.
- Upload dùng cấu hình Supabase Storage đã có của avatar/ảnh sản phẩm. Khi kho ảnh chưa cấu hình hoặc lỗi, hiển thị lỗi có thể tải lại; có thể xóa ảnh lỗi và gửi yêu cầu không kèm ảnh. Không hiển thị nút tải video do chính sách bucket hiện tại chỉ nhận ảnh tối đa 2 MiB. Video trong yêu cầu cũ vẫn mở được từ chi tiết.
- Giữ nội dung form khi máy chủ trả lỗi, chặn gửi lặp trong lúc chờ, yêu cầu xác nhận thông tin trước khi gửi, và không gửi ảnh chưa tải thành công.

Phạm vi đợt bảo hành là bảo hành. Luồng tạo/theo dõi đổi/trả được bổ sung ở đợt tiếp theo cùng ngày, xem [customer-return.md](customer-return.md).

## Kiểm tra

- 77 kiểm thử frontend liên quan đến tạo/theo dõi bảo hành, tài khoản, thông báo và điều hướng đạt.
- 9 kiểm thử danh sách bảo hành admin chạy riêng đạt. Khi chạy chung, test bộ lọc ngày có lỗi timing đã được ghi nhận trước đó trong `docs/customer-pricing-verification.md`; không sửa bộ lọc admin trong đợt này.
- 117 kiểm thử backend liên quan đến bảo hành, upload, phân quyền và router đạt, cùng 62 subtests. Dùng fake storage và SQLite/in-memory, không ghi vào dữ liệu thật.
- Production build thành công. Lint không có lỗi/cảnh báo mới; còn hai cảnh báo có sẵn tại `AdminTable.jsx` và `useAdminQuery.js`.
- Đã xem ảnh dựng desktop 1440 px và mobile 390 px với dữ liệu giả. Viewport mobile có `clientWidth=scrollWidth=390`, form rộng 358 px, không tràn ngang.
- Chưa thử upload vào Supabase thật hoặc tạo phiếu trên database đang vận hành của người dùng.
