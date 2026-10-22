# Đổi/trả phía khách hàng

Cập nhật ngày 21/10/2026. Tham chiếu Figma `aLG7De0fgbWCfaIpzIrPii`, frame `874:405`; quy tắc đang hoạt động trong `ReturnService`, `ReturnPolicy` và `docs/api-endpoints.md`.

## Giao diện

- `/doi-tra/tao-yeu-cau`: trang tạo yêu cầu theo bố cục hai cột của Figma, có ba bước hướng dẫn, chọn sản phẩm, hình thức đổi/trả, lý do, tình trạng, ảnh minh chứng, phương án mong muốn và thông tin liên hệ từ tài khoản.
- Menu **Bảo hành và đổi trả** có thêm mục con **Tạo yêu cầu đổi/trả**. Khu vực tài khoản có hai thẻ liên kết **Bảo hành** và **Đổi/trả**.
- `/tai-khoan?section=service&type=return`: danh sách yêu cầu đổi/trả của khách, lọc trạng thái và phân trang trên server.
- `/tai-khoan?section=service&type=return&request=<id>`: chi tiết, lịch sử công khai, trạng thái, sản phẩm/Serial/IMEI và thao tác hủy khi còn `Pending`.
- Thông báo `ReturnRequest` mở trực tiếp chi tiết của khách. Danh sách/chi tiết tải lại khi cửa sổ nhận focus hoặc khi bấm Làm mới.

## API và liên kết admin

1. Chọn từ đơn đã giao (`Delivered` hoặc `Completed`) qua `GET /orders`, có phân trang.
2. API mới `GET /orders/{order_id}/return-items` chỉ cho Customer sở hữu đơn đã giao đọc. Trả từng dòng gồm thông tin sản phẩm lịch sử, `Quantity`, `MaxQuantity`, `IsSerialTracked`, `ReturnDeadline`, `WindowDays`, `CanRequest`, `Reason`, và danh sách `Serials` thực tế gắn với dòng đơn.
3. Thời hạn dùng chính sách `ReturnPolicy` đang cấu hình. Ngày giao là ngày đầu tiên, xét ngày tại Việt Nam, nhận yêu cầu đến hết ngày `ReturnDeadline`. Không lấy số ngày demo từ Figma để thay cấu hình. Thiếu dữ liệu giao hàng/chính sách hoặc hết hạn được trả thành lý do rõ ràng, không tự suy ra điều kiện.
4. Hàng có serial: chọn thiết bị thuộc dòng đơn, mỗi yêu cầu đúng một thiết bị. Chặn thiết bị không ở trạng thái `Sold`, có yêu cầu đổi/trả hoặc bảo hành đang mở; không trả serial trong kho hoặc của đơn khác.
5. Hàng không quản lý serial: số lượng tối đa bằng số đã mua trừ lượng trong các phiếu chưa bị từ chối/hủy. Chặn dòng đang bảo hành. Hủy hoặc từ chối giải phóng số lượng theo logic có sẵn.
6. Gửi `POST /return-requests` với `OrderItemId`, `ProductSerialId` (hoặc null), `Quantity`, `RequestType` (`Exchange`/`Return`), `Reason`, `Attachments`. Lý do, mô tả, tình trạng và phụ kiện được ghi thành nội dung rõ ràng trong `Reason`. Server kiểm tra lại toàn bộ điều kiện khi tạo.
7. Phiếu `Pending` xuất hiện trong `/admin/returns` qua API quản trị có sẵn. Workflow `Pending → Approved → Receiving → Processing → Completed` không thay đổi. Hai giao diện dùng chung bộ nhãn trạng thái.
8. Khách đọc bằng `/return-requests` và `/return-requests/{id}`, hủy bằng `POST /return-requests/{id}/cancel`. Nếu admin vừa tiếp nhận, giao diện báo lỗi và tải lại trạng thái. Chặn gửi lặp và giữ nội dung khi lỗi.

Response khách bổ sung `ProductName`, `VariantInfo`, `OrderId`, `OrderCode`, `SerialNumber` của đúng phiếu đang được phép đọc. Không trả người phụ trách, dữ liệu người dùng khác, ghi chú nội bộ hoặc căn cứ tính tiền. Bổ sung quan hệ ORM chỉ đọc cho `ProductSerialId` đã tồn tại; không thay cột, FK, migration hoặc dữ liệu.

## Điều chỉnh Figma theo workflow hiện tại

- Khung phương án xử lý phản ánh hình thức **Đổi sản phẩm cùng phiên bản đã mua** hoặc **Trả hàng**. Kết quả cụ thể được VieTech xác nhận sau kiểm tra.
- Không thu số tài khoản/ngân hàng hoặc sản phẩm thay thế tùy ý trong form vì request hiện tại không lưu các trường đó và các endpoint hoàn tiền vẫn đang tạm dừng. `Completed` không có nghĩa đã hoàn tiền; nội dung giao diện nêu rõ việc xác nhận hoàn tiền riêng nếu áp dụng.
- Thông tin liên hệ lấy từ tài khoản, có liên kết cập nhật hồ sơ. Không hỏi địa chỉ lấy/nhận riêng khi workflow chưa lưu và vận hành trường đó.
- Ảnh minh chứng dùng chung `/service-request-image-uploads`: tối đa 5 JPG/PNG/WEBP, mỗi ảnh 2 MiB, theo chính sách kho Supabase đã có. Có thể tải lại hoặc xóa ảnh lỗi; không gửi tệp chưa tải thành công. Video trong phiếu cũ vẫn mở được ở chi tiết; không hiển thị nút tải video khi kho chỉ hỗ trợ ảnh.
- Dùng lại thành phần field, ảnh sản phẩm theo biến thể và upload của bảo hành. Header/footer và logo của storefront được giữ theo giao diện project.

## Kiểm tra

- 98 kiểm thử frontend liên quan tới tạo/theo dõi đổi/trả, bảo hành, tài khoản, thông báo và route đạt; 7 kiểm thử trang đổi/trả admin chạy riêng đạt.
- 131 kiểm thử backend liên quan đạt, cùng 46 subtests. Bao gồm hạn cuối theo ngày Việt Nam, chính sách cấu hình khác 7 ngày, số lượng còn lại, phiếu trùng, xung đột bảo hành, quyền sở hữu và đúng Serial/IMEI khi đọc chi tiết.
- Production build thành công; lint không có lỗi/cảnh báo mới. Hai cảnh báo có sẵn ở `AdminTable.jsx` và `useAdminQuery.js` vẫn còn.
- Đã xem ảnh dựng desktop 1440 px và mobile 390 px với dữ liệu giả. Mobile có `clientWidth=scrollWidth=390`, form rộng 358 px, không tràn ngang. Ảnh kiểm tra lưu local trong `output/customer-return-20261021/`.
- Không tạo phiếu hoặc upload vào database/kho Supabase đang vận hành của người dùng trong quá trình kiểm thử.
