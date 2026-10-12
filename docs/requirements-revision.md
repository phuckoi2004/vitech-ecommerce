# VieTech – Bản chỉnh yêu cầu chức năng Bảng 3.2–3.38

Ngày cập nhật: 10/10/2026. Nguồn: bản báo cáo đã sửa do người dùng cung cấp ngày 08/10/2026 và các quyết định trực tiếp trong hội thoại.

Tài liệu này ghi nội dung thay thế/bổ sung để cập nhật báo cáo; các phần không nêu thay đổi giữ theo bản mới. Người dùng đã yêu cầu thực hiện các chỉnh sửa và bắt đầu Giai đoạn 5. Các dòng **cần chốt** vẫn là quyết định nghiệp vụ còn thiếu, không tự bổ sung số ngày, quyền hoàn tiền hoặc schema mới.

Giai đoạn 5 triển khai backend tài khoản/Auth/RBAC theo [auth-spec.md](auth-spec.md) và [auth-rbac.md](auth-rbac.md). Các nội dung mua bán bên dưới chuẩn bị đặc tả cho service nghiệp vụ ở giai đoạn tương ứng; frontend đầy đủ thuộc Giai đoạn 8. Quyết định tài khoản hiện tại chỉ giữ `Customer`, `Staff`, `Admin`; schema chuẩn tương ứng ở [database-schema.md](database-schema.md), thay đổi ràng buộc role được quản lý qua Alembic.

## 1. Quy tắc chung của báo cáo

- Họ tên lưu tại `FullName`. Đăng nhập bằng email hoặc số điện thoại; form quên mật khẩu chỉ dùng email (quyết định 10/10/2026). Bỏ mọi tham chiếu tới username/tên tài khoản như một trường định danh riêng.
- Bỏ hạng thành viên và tích điểm. Không nhầm `TotalOrders`/`TotalSpent` với chương trình điểm thưởng.
- Mật khẩu ít nhất 8 ký tự, có chữ hoa, số và ký tự đặc biệt. OTP đăng ký 6 số/90 giây, reset 6 số/60 giây; giới hạn 5 lần sai/chờ 3 phút. Các mặc định vận hành bổ sung ở đặc tả Auth.
- `AccountStatus` dùng `Active`/`Locked`; tự mở khi hết `LockedUntil`; xóa mềm bằng `IsDeleted`.
- Admin chỉ quản lý Customer/Staff, tạo Staff; không tạo/quản lý Admin khác hoặc nâng/hạ role. Admin đầu tiên được khởi tạo bằng CLI riêng.
- Mọi chức năng có xác thực cần tài khoản còn hoạt động và quyền phù hợp. Chức năng đọc danh sách/báo cáo được mở ngay cả khi chưa có dữ liệu, trả danh sách rỗng hoặc tổng 0.
- Phân biệt `OrderStatus`, `PaymentStatus`, trạng thái giao dịch và trạng thái xử lý bảo hành/đổi trả. Nhãn giao diện không được tạo giá trị database ngoài bộ trạng thái hiện có.
- Sản phẩm/tài khoản/đánh giá dùng cờ xóa mềm phù hợp. Danh mục/thương hiệu/nhà cung cấp/phương thức thanh toán dùng `IsActive=false`; không xóa vật lý dữ liệu đã được lịch sử tham chiếu.

## 2. Nội dung cập nhật theo từng bảng

| Bảng | Nội dung đúng sau chỉnh |
|---|---|
| 3.2 – Đăng ký | Email, số điện thoại, họ tên, mật khẩu và xác nhận. Kiểm tra trùng/định dạng; gửi OTP 6 số/90 giây; chỉ tạo Customer sau xác minh. Thêm xử lý OTP hết hạn/đã dùng và gửi lại. |
| 3.3 – Đăng nhập | Email hoặc số điện thoại + mật khẩu; kiểm tra xóa mềm/khóa/portal. Tự mở khi khóa hết hạn; sai 5 lần chờ 3 phút theo bộ đếm riêng. |
| 3.4 – Đăng xuất | Thu hồi phiên hiện tại ở server, xóa cookie/token của phiên trên client; chuyển về trang đăng nhập/trang công khai tương ứng portal. |
| 3.5 – Đổi mật khẩu | Đầu vào đủ mật khẩu hiện tại, mật khẩu mới, xác nhận. Không trùng mật khẩu cũ; cập nhật hash và thu hồi mọi phiên. |
| 3.6 – Quên mật khẩu | Form chỉ nhận email đã đăng ký. Tìm tài khoản rồi gửi OTP 6 số/60 giây tới email của tài khoản đó; không gửi SMS. Bỏ “tên tài khoản” khỏi luồng và lỗi. |
| 3.7 – Hồ sơ | Đổi “tên tài khoản” thành họ tên. Giới hạn các trường tự sửa; email mới phải xác minh bằng luồng riêng. Địa chỉ thuộc bảng Addresses, CRUD ở UserService Giai đoạn 4; không ghi thông tin thẻ thanh toán vào Users. |
| 3.8 – Quản lý tài khoản | Admin chỉ xem/quản lý Customer/Staff và tạo Staff. Không tạo hoặc quản lý Admin khác; không nâng/hạ/chuyển role, không tự khóa/xóa chính mình. Admin đầu tiên tạo bằng CLI riêng. Xóa mềm; khóa cần lý do/thời hạn. |
| 3.9 – Tìm sản phẩm | Giữ tìm/lọc công khai cho khách chưa đăng nhập; dữ liệu nội bộ chỉ theo quyền. |
| 3.10 – Chi tiết sản phẩm | Khách xem dữ liệu công khai; Staff/Admin xem dữ liệu phục vụ công việc. Không biến quyền xem thành quyền sửa. |
| 3.11 – Sản phẩm | Admin thêm/sửa/ẩn; giữ lịch sử sản phẩm/biến thể đã bán. Các thao tác biến thể cần kiểm tra SKU, giá và ràng buộc dữ liệu. |
| 3.12 – Danh mục | Admin quản lý; ẩn bằng IsActive=false. Staff được tra cứu cho công việc; mục đã ẩn vẫn giữ liên kết dữ liệu cũ. |
| 3.13 – Thương hiệu | Đổi luồng “xóa dữ liệu” thành ngừng hoạt động/ẩn; đầu ra thống nhất dữ liệu vẫn được lưu. |
| 3.14 – Khuyến mãi | Admin quản lý; ngừng áp dụng bằng trạng thái Cancelled hoặc kết thúc thời hạn theo workflow, giữ lịch sử đã sử dụng. Bỏ đầu ra “xóa khỏi hệ thống”. |
| 3.15 – Yêu thích | Chỉ Customer thao tác danh sách của mình; thêm/xóa không sửa hay xóa sản phẩm gốc. |
| 3.16 – Nhà cung cấp | Admin quản lý; Staff tra cứu để tạo phiếu nhập. Ẩn bằng IsActive=false; sửa lỗi “không có danh mục” thành “không có nhà cung cấp”. |
| 3.17 – Phiếu nhập | Staff tạo/tìm/xem; **chỉ Admin sửa** phiếu theo trạng thái, duyệt/từ chối/hủy. Tạo Pending; duyệt không tự cộng tồn; tồn tăng theo hàng thực nhận. Không xóa phiếu đã nhận hàng. |
| 3.18 – Lịch sử nhập | **Staff và Admin** xem/lọc lịch sử và số thực nhận (quyết định 09/10/2026). Sửa tác nhân ở “Sự kiện kích hoạt”, “Đầu vào”, “Điều kiện cần” thành Quản trị viên, nhân viên cho khớp. Xuất báo cáo: Admin (quyết định 09/10/2026). |
| 3.19 – Cảnh báo tồn | Staff/Admin xem, Admin đặt ngưỡng. Theo StockQuantity/MinStockLevel của biến thể; điều kiện phát thông báo lặp cần quy định trước khi làm service. |
| 3.20 – Giỏ hàng | Customer quản giỏ của mình; số lượng >0 và hợp lệ. Giá/tổng tiền do backend tính lại, không tin tổng client gửi. |
| 3.21 – Đặt hàng | Chọn phương thức thanh toán **trước khi lưu đơn** vì PaymentMethodId bắt buộc. Tạo OrderStatus=Pending và PaymentStatus=Pending, lưu đơn/dòng đơn trước giao dịch thanh toán. |
| 3.22 – Thanh toán | Xử lý phương thức đã chọn cho đơn của Customer. COD giữ PaymentStatus=Pending; online thành công Paid, thất bại Failed. Không ghi “Đã thanh toán” vào OrderStatus. |
| 3.23 – Phương thức thanh toán | Admin thêm/sửa/ngừng sử dụng. Phương thức đã có đơn/giao dịch tham chiếu không xóa vật lý; IsActive=false để không được chọn cho đơn mới. |
| 3.24 – Theo dõi đơn | Customer chỉ đọc đơn của mình và lịch sử/trạng thái tương ứng. |
| 3.25 – Chi tiết đơn | Sửa tiêu đề “chi tiết hơn hàng” thành “chi tiết đơn hàng”. Customer xem đơn của mình; Staff/Admin xem đơn toàn hệ thống theo báo cáo. |
| 3.26 – Tìm đơn | Bộ lọc giới hạn theo quyền. Đầu ra Customer chỉ xem và hủy khi đủ điều kiện; xác nhận đơn thuộc Staff/Admin. Đổi “tên tài khoản” thành họ tên khách hàng nếu là bộ lọc. |
| 3.27 – Bảo hành | Kiểm tra dòng đơn thuộc khách, điều kiện/serial/hạn bảo hành. Tách EligibilityStatus khỏi Status; ánh xạ trạng thái theo mục 3.3. Giữ serial và lịch sử gốc khi có đổi máy/linh kiện. |
| 3.28 – Đổi trả | Sửa kích hoạt thành “yêu cầu đổi trả”; điều kiện đơn/dòng hàng thuộc khách và đã giao. Staff/Admin đều được tiếp nhận, duyệt/từ chối. Kết quả là đổi hàng hoặc trả hàng/hoàn tiền, không dùng “đã trả máy” như trạng thái chung. |
| 3.29 – Trạng thái đơn | Dùng bộ OrderStatus hiện có; phân biệt xác nhận, xử lý, giao, đã giao và hoàn thành. Ghi lịch sử/người đổi; xuất/hoàn kho và thu COD phải gắn với thao tác thực tế, tránh lặp. |
| 3.30 – Doanh thu | Staff/Admin xem. Không cần có khách đã mua để mở báo cáo. Phải chốt công thức, thời điểm ghi nhận và trừ hoàn tiền trước triển khai; không tính doanh thu nhà cung cấp bằng liên kết tùy ý. |
| 3.31 – Số đơn | Đầu ra “số lượng và tỷ lệ đơn theo bộ lọc”, không phải “lợi nhuận”. Tách đơn nhập/đơn bán theo quyền xem; dữ liệu rỗng trả 0. Không thêm DeliveryFailed khi schema chưa có. |
| 3.32 – Đánh giá | Customer chọn **1–5 sao** và nhập nhận xét, sau giao hàng hợp lệ. Một đánh giá cho mỗi OrderItem; chỉ sửa của mình, không sửa đánh giá của người khác. |
| 3.33 – Kiểm duyệt | Tác nhân kích hoạt Staff/Admin; xóa mềm đánh giá vi phạm kèm lý do/người/thời điểm xóa. Không cấp quyền này cho Customer. |
| 3.34 – Lọc đánh giá | Staff/Admin lọc theo sao/thời gian. Sửa tác nhân kích hoạt bị ghi nhầm Customer; danh sách rỗng không phải lỗi. |
| 3.35 – Tin tức | Staff/Admin thêm/sửa/xem/ẩn; Draft/Published/Hidden quyết định nội dung khách thấy. Quy trình duyệt đăng và phạm vi sửa bài người khác còn cần chốt. |
| 3.36 – Banner | Staff/Admin vào **quản lý banner**, không phải quản lý tin tức; bỏ Customer khỏi tác nhân quản trị. Dùng IsActive và thời gian hiển thị hiện có. |
| 3.37 – Chat người thật | Customer hội thoại của mình; Staff và Admin nhận/trả lời và xem lịch sử (quyết định 09/10/2026). Hàng chờ có thể là Open và AssignedStaffId rỗng; nhận chat phải tránh hai người cùng nhận. |
| 3.38 – Chat AI | Customer hội thoại của mình; lỗi AI có thông báo phù hợp. Không tự cấp quyền AI cho vai trò khác hoặc thêm luồng chuyển giao chưa được mô tả. |

## 3. Luồng nghiệp vụ khớp trạng thái hiện có

### 3.1. Đặt hàng và thanh toán

1. Customer chọn hàng, địa chỉ, vận chuyển và phương thức thanh toán còn hoạt động; backend tính lại giá/khuyến mãi/tổng tiền và kiểm tra tồn.
2. Lưu Orders và OrderItems trong transaction: `OrderStatus=Pending`, `PaymentStatus=Pending`, có `PaymentMethodId`.
3. COD chờ xác nhận/thu tiền; online tạo giao dịch gắn với OrderId đã tồn tại. Callback được xác minh và xử lý lặp an toàn trước khi cập nhật giao dịch/PaymentStatus.
4. Online thành công: giao dịch `Success`, đơn `PaymentStatus=Paid`; thất bại: giao dịch `Failed`, đơn `PaymentStatus=Failed`. Không thay OrderStatus chỉ để biểu diễn kết quả thanh toán.
5. Luồng xử lý đơn thông thường: `Pending → Confirmed → Processing → Shipping → Delivered → Completed`. Nhánh hủy dùng `Cancelled` theo điều kiện từng bước; hủy sau xuất kho phải đối soát hàng/tiền, không chỉ đổi trạng thái.

Customer chỉ được yêu cầu hủy đơn của mình ở Pending/Confirmed/Processing khi chưa xuất kho. Sau Shipping, Staff/Admin xử lý theo quy trình vận chuyển và hàng trả về. Điều kiện hoàn thành, thời gian giữ hàng/chờ thanh toán, cách chống vượt tồn và xử lý giao thất bại cần đặc tả riêng; không tự thêm OrderStatus mới trong Giai đoạn 5.

### 3.2. Nhập hàng

`Pending → Approved → Receiving → Completed`; từ Pending có thể `Rejected` hoặc `Cancelled` bởi Admin theo điều kiện. Phiếu bị từ chối có thể sửa/gửi lại khi workflow cho phép, không sửa dữ liệu đã nhận để xóa dấu vết kho.

Approved là duyệt kế hoạch, chưa cộng kho. Mỗi lần nhận thực tế tăng `ReceivedQuantity` và `StockQuantity` bằng phần nhận mới trong cùng transaction; không vượt OrderedQuantity. Completed khi hoàn thành nhận hàng. Phiếu đã Receiving/Completed giữ lịch sử, không xóa vật lý. Người được phép ghi nhận hàng thực nhận và cơ chế điều chỉnh sai lệch cần chốt trước service kho.

### 3.3. Bảo hành và đổi trả

| Nghiệp vụ | Cách dùng trạng thái hiện có |
|---|---|
| Bảo hành mới/đang kiểm tra điều kiện | Status=New, EligibilityStatus=Pending; ghi ReceivedAt khi thực nhận. |
| Đủ/không đủ điều kiện bảo hành | EligibilityStatus=Eligible/Ineligible; không đủ thì Status=Rejected kèm lý do. |
| Bàn giao trung tâm bảo hành | Status=HandedOver và thông tin/thời điểm bàn giao. |
| Trung tâm xử lý/đang hoàn tất trả hàng | Status=Processing; ghi kết quả trong ResultType/ResultNote và lịch sử. |
| Hoàn tất giao trả cho khách | Status=Completed và CompletedAt; “đã trả khách” là nhãn mô tả hoàn tất, không tạo trạng thái mới. |
| Hủy bảo hành còn được phép | Status=Cancelled. |
| Đổi trả | Pending → Approved → Receiving → Processing → Completed; nhánh Rejected/Cancelled theo điều kiện. |

Đổi trả phải ghi kết quả xử lý đổi hàng/hoàn tiền, đánh giá thiệt hại và khoản chênh lệch theo chính sách. Không mặc định CompensationAmount là toàn bộ tiền hoàn hoặc tự cộng mọi hàng trả vào kho có thể bán. Các trường hợp trả một phần, serial thay thế, tiền hoàn và phiếu thanh toán cần thiết kế trước triển khai.

## 4. Quyết định còn thiếu cho các service nghiệp vụ

| Vấn đề | Cần xác định trước khi triển khai |
|---|---|
| Tồn kho | Giữ hàng khi đặt hay khi xác nhận, thời hạn giữ, kho khả dụng, hoàn kho khi hủy/trả, quyền điều chỉnh. |
| Giao hàng | Phân biệt Delivered/Completed; xử lý giao thất bại/giao lại và thời điểm đóng đơn. |
| Bảo hành/đổi trả | Số ngày đổi trả, điều kiện áp dụng, số lượng trả một phần, serial và hàng đổi; không tự chọn 7/14/30 ngày. |
| Hoàn tiền | Staff và Admin thực hiện (quyết định 09/10/2026). Còn cần: COD hoàn theo cách nào; công thức sau khuyến mãi, phí vận chuyển và thiệt hại. |
| Thống kê | Trạng thái/ngày ghi doanh thu, doanh thu gộp/ròng, khoản hoàn và nguồn giá vốn. Doanh thu theo nhà cung cấp cần nguồn truy xuất lô hàng, schema hiện chưa thể gán chính xác mọi hàng bán. |
| Phạm vi Staff | Xem đơn toàn hệ thống đã có; quyền sửa theo AssignedStaffId, phạm vi hội thoại/lịch sử và dữ liệu thống kê cần nêu rõ. Staff xem phiếu (B3.17) và lịch sử nhập (B3.18). |
| Nội dung | Staff đăng trực tiếp hay cần duyệt; sửa bài/banner của người khác, lịch hiển thị và quyền khôi phục. |
| Phân quyền nghiệp vụ | Router từng nghiệp vụ kiểm tra quyền và phạm vi bản ghi của Customer/Staff/Admin. Chat người thật do Staff và Admin nhận/trả lời; quyền chưa đủ quy tắc không tự mở. |

Các điểm này không chặn xây dựng Auth/RBAC tài khoản của Giai đoạn 5. Chưa mở endpoint nghiệp vụ theo những quyền hoặc công thức còn thiếu.
