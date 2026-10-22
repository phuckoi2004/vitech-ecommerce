# Báo cáo triển khai chức năng bảo hành và đổi trả

**Dự án:** VieTech  
**Ngày báo cáo:** 21/10/2026  
**Phạm vi:** Phía khách hàng và kết nối với chức năng quản trị hiện có.

Đã bổ sung hai chức năng tạo và theo dõi yêu cầu bảo hành, đổi trả cho khách hàng. Giao diện được xây dựng dựa trên Figma, điều chỉnh theo nghiệp vụ đang áp dụng và sử dụng chung dữ liệu với các trang quản lý của admin. Khách hàng có thể gửi thông tin, xem tiến trình, nhận thông báo và hủy yêu cầu khi còn được phép.

## 1 Công việc bảo hành

### Nội dung đã thực hiện

- Đổi tên mục tài khoản từ “Tra cứu bảo hành và đổi trả” thành “Bảo hành và đổi trả”; thêm mục con “Tạo yêu cầu bảo hành” khi rê chuột hoặc sử dụng bàn phím.
- Xây dựng trang tạo yêu cầu theo bố cục Figma, tương thích desktop và điện thoại. Khách chọn sản phẩm từ đơn hàng đã giao, chọn Serial/IMEI đã gắn với dòng đơn, mô tả lỗi, ngày phát sinh và phụ kiện dự kiến gửi kèm.
- Hiển thị thời hạn bảo hành từ dữ liệu đơn hàng và thiết bị. Kiểm tra quyền sở hữu, tình trạng serial, yêu cầu bảo hành đang mở và xung đột với yêu cầu đổi trả.
- Bổ sung đính kèm ảnh minh chứng, xác nhận thông tin trước khi gửi, chặn gửi lặp và giữ nội dung form khi có lỗi.
- Hoàn thiện danh sách và trang chi tiết yêu cầu, gồm trạng thái, lịch sử công khai, minh chứng và kết quả đã được nhân viên công bố. Thông báo bảo hành dẫn trực tiếp đến đúng yêu cầu.

### Kết nối với admin

Yêu cầu hợp lệ được tạo qua API bảo hành hiện có và xuất hiện tại trang quản trị `/admin/warranties`. Admin hoặc nhân viên tiếp nhận, kiểm tra, xử lý, công bố kết quả và ghi nhận trả khách; khách xem tiến trình qua cùng hồ sơ yêu cầu.

Khách chỉ được hủy khi yêu cầu còn `New` và chưa có thời điểm tiếp nhận. Nếu admin vừa tiếp nhận trong lúc khách thao tác, giao diện báo lỗi và tải lại trạng thái. Ghi chú nội bộ và kết quả chưa công bố không hiển thị cho khách.

## 2 Công việc đổi trả

### Nội dung đã thực hiện

- Bổ sung mục con “Tạo yêu cầu đổi/trả” và thẻ “Đổi/trả” trong khu vực “Bảo hành và đổi trả”.
- Xây dựng trang tạo yêu cầu theo Figma, cho phép chọn hình thức đổi sản phẩm hoặc trả hàng, chọn sản phẩm đã nhận, số lượng, Serial/IMEI, lý do, tình trạng sử dụng và ảnh minh chứng.
- Lấy thời hạn đổi trả từ chính sách cấu hình của backend, xét theo ngày tại Việt Nam và tính ngày giao là ngày đầu tiên. Hiển thị hạn cuối và lý do không đủ điều kiện.
- Với hàng quản lý serial, mỗi yêu cầu áp dụng cho một thiết bị đã mua. Với hàng không quản lý serial, số lượng không vượt phần còn có thể yêu cầu sau khi trừ các phiếu chưa bị từ chối hoặc hủy.
- Kiểm tra yêu cầu trùng, thiết bị không còn ở trạng thái đã bán và sản phẩm đang bảo hành. Server xác minh lại các điều kiện khi tạo phiếu.
- Bổ sung danh sách, bộ lọc trạng thái, phân trang, trang chi tiết, lịch sử công khai, thông báo và thao tác hủy khi yêu cầu còn `Pending`.

### Kết nối với admin

Yêu cầu được tạo qua API đổi trả hiện có và xuất hiện tại `/admin/returns`. Luồng xử lý đang hoạt động được giữ nguyên: `Pending → Approved → Receiving → Processing → Completed`. Khách theo dõi trạng thái và phản hồi trên trang chi tiết; hai phía dùng chung bộ nhãn trạng thái.

Khung phương án mong muốn được điều chỉnh theo nghiệp vụ: đề nghị đổi cùng phiên bản đã mua hoặc trả lại sản phẩm. Việc hoàn tiền, nếu áp dụng, được xác nhận riêng; trạng thái `Completed` không có nghĩa đã hoàn tiền. Form không thu thông tin ngân hàng khi workflow hiện tại chưa lưu và xử lý các trường này.

## 3 Các phần tích hợp dùng chung

| Hạng mục | Kết quả |
|---|---|
| Điều hướng tài khoản | Hai mục tạo yêu cầu và hai thẻ theo dõi bảo hành, đổi trả |
| Chọn sản phẩm bảo hành | Bổ sung `GET /orders/{order_id}/warranty-items` |
| Chọn sản phẩm đổi trả | Bổ sung `GET /orders/{order_id}/return-items` |
| Tải minh chứng | Dùng chung `POST /service-request-image-uploads` và cấu hình kho ảnh hiện có |
| Dữ liệu hiển thị | Bổ sung tên sản phẩm, phiên bản, mã đơn và đúng Serial/IMEI vào response dành cho chủ yêu cầu |
| Thành phần giao diện | Dùng lại trường nhập, khung sản phẩm, upload ảnh, header, footer và logo của storefront |
| Cơ sở dữ liệu | Không bổ sung cột, FK hoặc migration; thêm quan hệ ORM chỉ đọc trên FK đã có cho phần đổi trả |

Thông tin liên hệ lấy từ tài khoản và có liên kết cập nhật hồ sơ. Nhân viên liên hệ khách để hướng dẫn gửi, nhận sản phẩm; không tạo thêm trường địa chỉ vận chuyển riêng khi workflow chưa lưu và vận hành dữ liệu đó.

## 4 Kết quả kiểm thử

| Nội dung kiểm tra | Đợt bảo hành | Đợt đổi trả và hồi quy liên quan |
|---|---|---|
| Frontend | 77 kiểm thử đạt | 98 kiểm thử đạt, có bao gồm bảo hành |
| Trang danh sách admin | 9 kiểm thử đạt khi chạy riêng | 7 kiểm thử đạt khi chạy riêng |
| Backend | 117 kiểm thử đạt | 131 kiểm thử đạt |
| Kiểm tra con của backend | 62 subtests đạt | 46 subtests đạt |
| Production build | Thành công | Thành công |

Các lượt chạy có phạm vi giao nhau; không cộng các số trên thành tổng số kiểm thử duy nhất. Đã kiểm tra ảnh dựng ở desktop 1440 px và điện thoại 390 px bằng dữ liệu giả; form trên điện thoại không tràn ngang.

Lint không phát sinh lỗi hoặc cảnh báo mới; còn hai cảnh báo có sẵn tại `AdminTable.jsx` và `useAdminQuery.js`. Trong đợt bảo hành, test bộ lọc ngày admin có lỗi timing khi chạy chung, đã được ghi nhận trong tài liệu trước đó; chạy riêng bộ test này đạt 9/9.

## 5 Giới hạn và phạm vi bàn giao

- Kiểm thử sử dụng dữ liệu giả, SQLite hoặc bộ nhớ và kho ảnh giả lập. Chưa tạo phiếu trên database đang vận hành hoặc thử upload vào Supabase thật của người dùng.
- Minh chứng mới hỗ trợ tối đa 5 ảnh JPG, PNG hoặc WEBP, mỗi ảnh tối đa 2 MiB theo chính sách kho ảnh hiện có. Video trong phiếu cũ vẫn mở được; chưa bổ sung upload video.
- Các bước hoàn tiền và xử lý tài chính đang tạm dừng theo quyết định nghiệp vụ hiện hành. Hai chức năng vừa bổ sung không mở lại các bước này.
- Giao diện, API chọn sản phẩm, liên kết quản trị, kiểm thử và tài liệu đã được bổ sung trong project để tiếp tục kiểm tra trên môi trường đang vận hành.

## 6 Đường dẫn bàn giao

| Chức năng | Đường dẫn |
|---|---|
| Tạo yêu cầu bảo hành | `/bao-hanh/tao-yeu-cau` |
| Theo dõi bảo hành | `/tai-khoan?section=service` |
| Tạo yêu cầu đổi trả | `/doi-tra/tao-yeu-cau` |
| Theo dõi đổi trả | `/tai-khoan?section=service&type=return` |
| Quản trị bảo hành | `/admin/warranties` |
| Quản trị đổi trả | `/admin/returns` |

Tài liệu chi tiết: [Bảo hành phía khách hàng](../customer-warranty.md), [Đổi trả phía khách hàng](../customer-return.md) và [Danh sách API](../api-endpoints.md).

Thiết kế tham chiếu: [Figma bảo hành](https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=874-368) và [Figma đổi trả](https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=874-405).
