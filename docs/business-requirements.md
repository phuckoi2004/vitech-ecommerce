# VieTech — Business Requirements for Service Layer

> **Mục đích:** Tài liệu nghiệp vụ triển khai trực tiếp cho Claude Code khi xây dựng Service Layer của VieTech.
>
> **Nguồn nghiệp vụ chính:** `Quy trình nghiệp vụ.docx`, đặc biệt mục 2.3 (quy trình nghiệp vụ), mục 2.4 (yêu cầu chức năng) và mục 3.2 (đặc tả chức năng).
>
> **Nguồn dữ liệu chính:** `docs/database-schema.md`, SQLAlchemy Models, Pydantic Schemas và Repositories hiện có trong dự án.
>
> **Nguyên tắc:** Báo cáo mô tả nghiệp vụ; schema hiện tại xác định dữ liệu có thể lưu. Không tự ý thay đổi schema hoặc âm thầm sửa khác biệt giữa hai nguồn. Nếu có xung đột, ghi rõ xung đột, nêu phương án và yêu cầu quyết định trước khi tạo migration.

---

## 1. Quy tắc làm việc bắt buộc cho Claude Code

1. Trước khi code, đọc tài liệu này, `docs/database-schema.md`, Models, Schemas, Repositories và các Service liên quan.
2. Giữ kiến trúc `Router → Service → Repository → Model`.
3. Service chứa nghiệp vụ, kiểm tra quyền nghiệp vụ, quản lý transaction và phối hợp nhiều Repository. Repository chỉ truy vấn/thao tác dữ liệu.
4. Không đưa `HTTPException`, `Request`, `Response` hoặc logic HTTP vào Service/Repository. Service dùng lỗi nghiệp vụ thống nhất theo pattern đang có trong dự án.
5. Không gọi `SessionLocal` bên trong Service. Dùng `Session` được truyền từ Router/dependency.
6. Không `commit()`/`rollback()` tùy tiện trong Repository. Tuân theo transaction convention hiện có; chỉ tầng được quy định mới được commit/rollback.
7. Dùng SQLAlchemy 2.x, không dùng `Query.query()` kiểu cũ, không viết raw SQL nếu ORM đáp ứng được.
8. Tiền dùng `Decimal`, phù hợp `numeric(15,2)`. Không dùng `float` cho tiền.
9. Không tin giá, tổng tiền, phí giao hàng, tiền giảm giá, giá vốn, trạng thái hoặc quyền do frontend gửi. Server tự tính và kiểm tra lại.
10. Với nghiệp vụ nhiều bảng, xác định transaction boundary và khóa dòng trước khi sửa. Một phần thất bại thì toàn bộ nghiệp vụ phải rollback.
11. Kiểm tra quyền ở backend. Không coi việc ẩn nút trên giao diện là phân quyền.
12. Không in/log `.env`, `DATABASE_URL`, mật khẩu, `PasswordHash`, OTP, JWT secret hoặc service-role key.
13. Không tự sửa Models, Schemas, Repositories, migration hay `docs/database-schema.md` ngoài phạm vi yêu cầu. Nếu phát hiện thiếu trường/constraint để đáp ứng báo cáo, dừng ở điểm đó và báo cụ thể.
14. Mỗi nhóm Service phải có kiểm thử thành công, dữ liệu không hợp lệ, sai quyền, sai trạng thái, gọi lặp và rollback. Chạy regression tests của các nhóm phụ thuộc.
15. Sau khi hoàn tất, báo: file tạo/sửa, phương thức thêm, quy tắc đã triển khai, lệnh test và kết quả, vấn đề còn mở. Không commit/push trừ khi được yêu cầu rõ.

## 2. Vai trò và phạm vi quyền

### Customer
- Đăng ký, xác thực OTP, đăng nhập, đăng xuất, quên/đổi mật khẩu và sửa thông tin cá nhân.
- Xem/tìm sản phẩm; quản lý giỏ hàng và wishlist.
- Đặt hàng, thanh toán, xem đơn hàng của chính mình và yêu cầu hủy trong điều kiện cho phép.
- Đánh giá sản phẩm đã nhận theo điều kiện trong schema/nghiệp vụ hiện hành.
- Gửi/theo dõi yêu cầu bảo hành và đổi trả của sản phẩm thuộc đơn hàng của mình.
- Sử dụng chatbot AI hoặc chat nhân viên.

### Staff
- Dùng các chức năng chung được báo cáo nêu.
- Lập phiếu nhập hàng, sửa/gửi lại phiếu theo trạng thái, nhận hàng theo quyền đã cấp.
- Xem lịch sử nhập hàng và cảnh báo tồn kho.
- Xử lý đơn hàng, cập nhật trạng thái theo luồng cho phép.
- Tiếp nhận và xử lý bảo hành/đổi trả; hỗ trợ khách hàng.
- Xem thống kê/báo cáo theo quyền được cấp.

### Admin
- Kế thừa các chức năng của Staff theo phạm vi được mô tả trong báo cáo.
- Quản lý tài khoản, sản phẩm, danh mục, thương hiệu, nhà cung cấp, khuyến mãi/mã giảm giá, phương thức thanh toán, quảng cáo/nội dung và thống kê.
- **Có quyền lập phiếu nhập hàng**, ngoài quyền xem và phê duyệt/từ chối phiếu theo quy trình nhập hàng.
- Phê duyệt/từ chối phiếu nhập và xử lý các nghiệp vụ quản trị theo đặc tả.

> Phạm vi nghiệp vụ trong tài liệu này chỉ xác định các vai trò Customer, Staff và Admin. Không tự bổ sung vai trò hoặc quy tắc phân quyền không được mô tả trong báo cáo.

## 3. Quy tắc chung về dữ liệu và trạng thái

- Các trạng thái phải dùng đúng giá trị đã khai báo trong Models/schema. Không tự thêm enum/status mới chỉ vì báo cáo dùng tên hiển thị tiếng Việt khác.
- Khi báo cáo dùng nhãn như “Chờ xác nhận”, “Đang xử lý”, “Đang giao”, hãy ánh xạ sang giá trị status trong Model (ví dụ `Pending`, `Processing`, `Shipping`) tại lớp nghiệp vụ/API.
- Không xóa cứng bản ghi đã có lịch sử hoặc đang được FK tham chiếu. Dùng soft delete/`IsActive` nếu schema hỗ trợ.
- Tạo/cập nhật dữ liệu phải kiểm tra các ràng buộc UNIQUE, CHECK, FK và trạng thái.
- Các danh sách lớn cần phân trang; bộ lọc phải được thực hiện ở Repository/database, không tải toàn bộ dữ liệu về rồi lọc trong Python.
- Các thao tác tăng/giảm tồn kho, `UsedCount`, thanh toán và nhận hàng cần bảo vệ khỏi gọi đồng thời hoặc gọi lặp.
- Không gửi thông báo “thành công” trước khi transaction dữ liệu đã hoàn tất.

## 4. Tài khoản và xác thực

Khi tích hợp giai đoạn 4 và 5, người dùng chọn giữ chính sách Auth/RBAC giai đoạn 5. `auth-spec.md` và `auth-rbac.md` quy định chi tiết chính sách tài khoản đang áp dụng; các nghiệp vụ khác tiếp tục theo tài liệu này. Luồng tài khoản/OTP cũ trong Service Layer giai đoạn 4 được thay thế bằng `AuthService` và `UserService` giai đoạn 5. Quyền của các Service nghiệp vụ giai đoạn 4 (sản phẩm, đơn hàng, nhập hàng, nội dung, đánh giá, thanh toán, sổ địa chỉ...) giữ nguyên theo giai đoạn 4 như mô tả trong tài liệu này. Ngoại lệ: Staff được xem thống kê (mục 15).

### Đăng ký
1. Khách nhập họ tên, email, số điện thoại và mật khẩu.
2. Kiểm tra định dạng và trùng email/số điện thoại.
3. Băm mật khẩu bằng cơ chế bảo mật hiện có; không lưu mật khẩu thô.
4. Gửi OTP qua email và giữ đăng ký đang chờ trong state store; chưa tạo dòng `Users`.
5. Xác thực OTP: đúng và còn hạn thì tạo Customer đã xác minh; sai hoặc hết hạn thì trả lỗi phù hợp và cho phép gửi lại theo chính sách OTP. Mặc định OTP đăng ký/đổi email có hạn 90 giây, reset mật khẩu 60 giây; 5 lần sai khóa xác minh 180 giây.
6. Không trả `PasswordHash`, `OtpCode` hoặc `OtpExpiredAt` trong response.

### Đăng nhập, quên mật khẩu, đổi mật khẩu
- Đăng nhập kiểm tra tài khoản, trạng thái tài khoản và thông tin xác thực.
- Đăng nhập nhận email hoặc số điện thoại, tách portal khách hàng/nội bộ; không bắt buộc email đã xác minh.
- Quên mật khẩu: nhận email, xác minh tài khoản theo cách không làm lộ việc email có tồn tại nếu chính sách bảo mật yêu cầu; xác thực OTP rồi cho đặt mật khẩu mới.
- Đổi mật khẩu: yêu cầu đăng nhập; xác minh mật khẩu hiện tại nếu luồng/schema hiện có yêu cầu.
- OTP phải có thời hạn, không dùng lại sau khi thành công; giới hạn gửi/nhập OTP nếu có cơ chế tương ứng.

### Quản lý tài khoản
- Admin chỉ tìm kiếm/lọc, sửa, khóa có thời hạn hoặc xóa mềm Customer/Staff; chỉ tạo Staff qua API quản trị.
- Không quản lý Admin khác, không đổi role; Admin đầu tiên được khởi tạo bằng CLI. Admin sửa hồ sơ của mình qua API hồ sơ.
- Khóa/xóa tài khoản thu hồi refresh session; không cho tài khoản tự nâng role.
- Khi xóa/khóa tài khoản, giữ nguyên dữ liệu nghiệp vụ và lịch sử liên quan.

## 5. Danh mục, thương hiệu, sản phẩm và biến thể

### Danh mục và thương hiệu
- Admin xem danh sách, tìm kiếm/lọc, tạo, sửa và xóa mềm/ẩn khi phù hợp.
- Kiểm tra tên/slug duy nhất theo schema.
- Không xóa nếu có sản phẩm hoặc dữ liệu tham chiếu khiến thao tác vi phạm FK; trả lỗi nghiệp vụ dễ hiểu.
- Danh mục cha/con phải tuân theo quan hệ hiện có; không cho tạo chu trình cha-con.

### Sản phẩm và biến thể
- Admin tạo/sửa/ẩn sản phẩm, quản lý hình ảnh và biến thể.
- Kiểm tra danh mục, thương hiệu, SKU/slug, giá bán, tồn kho và các trường bắt buộc.
- Không cho tồn kho âm.
- Không xóa cứng sản phẩm/biến thể đã được dùng trong đơn hàng, đánh giá, phiếu nhập hoặc serial.
- Cập nhật tồn kho thông qua nghiệp vụ kho dùng chung; không để nhiều Service tự sửa `StockQuantity` theo các cách khác nhau.
- `ProductVariants.CostPrice` là giá vốn hiện tại; `OrderItems.UnitCost` là snapshot giá vốn tại thời điểm bán, không được cập nhật lại khi giá vốn hiện tại thay đổi.

## 6. Wishlist và giỏ hàng

### Wishlist
- Mỗi Customer chỉ thao tác wishlist của chính mình.
- Thêm sản phẩm không tạo bản ghi trùng; xóa item chỉ tác động wishlist của người dùng hiện tại.
- Kiểm tra sản phẩm tồn tại và đáp ứng điều kiện hiển thị.

### Giỏ hàng
- Customer thêm, chọn/bỏ chọn, đổi số lượng và xóa item trong giỏ của mình.
- Kiểm tra biến thể còn hoạt động và số lượng hợp lệ.
- Giỏ hàng không phải nguồn đáng tin cậy cho giá cuối cùng: khi tạo đơn phải đọc lại giá, tồn kho, khuyến mãi và giá vốn từ database.
- Xem trước mã giảm giá chỉ tính trên các dòng đang chọn và còn đủ điều kiện mua; không tăng `UsedCount` và không giữ chỗ coupon.
- Không để thao tác thêm/sửa giỏ của Customer tác động đến giỏ của người khác.

## 7. Promotion và Coupon

### Promotion
- Admin tạo, xem, sửa, hủy và quản lý phạm vi áp dụng theo sản phẩm/danh mục.
- Kiểm tra `StartDate <= EndDate`, kiểu/giá trị giảm giá và giới hạn giảm tối đa theo schema.
- Promotion chỉ được áp dụng khi trạng thái và khoảng thời gian hiệu lực thỏa điều kiện.
- Promotion đang Active bị khóa các trường ảnh hưởng trực tiếp đến cách tính giảm giá/phạm vi áp dụng nếu đây là quy tắc đã triển khai trong `PromotionService`.
- Không xóa Promotion đang được Coupon tham chiếu; dùng hủy/ẩn theo quy tắc hiện có.

### Coupon
- Coupon tham chiếu Promotion; không tạo logic giảm giá độc lập ngoài Promotion.
- Kiểm tra mã, trạng thái kích hoạt, giới hạn sử dụng, thời hạn và giá trị đơn tối thiểu.
- Việc tra cứu mã không phân biệt hoa thường nếu functional unique index và Repository hiện tại đã được triển khai theo cách này.
- Khi áp dụng vào đơn, khóa dòng Coupon và kiểm tra lại `UsedCount < UsageLimit` trong cùng transaction.
- Tăng lượt dùng khi đơn được tạo và coupon được gắn thành công; trả lại lượt khi đơn bị hủy hợp lệ theo chính sách hiện hành.
- Không xóa Coupon đã được sử dụng nếu quy tắc FK/lịch sử ngăn việc xóa; đặt `IsActive = false`.
- Phân bổ giảm giá vào từng OrderItem phải bảo đảm tổng phân bổ đúng bằng tổng giảm giá, không tạo sai lệch do làm tròn.

## 8. Nhà cung cấp và nhập hàng

### 8.1. Quản lý nhà cung cấp
- Admin xem, tìm kiếm, tạo và cập nhật thông tin nhà cung cấp.
- Xóa theo cơ chế soft delete/ẩn nếu schema hỗ trợ.
- Không xóa nhà cung cấp đang được phiếu nhập hoặc yêu cầu bảo hành tham chiếu; nếu ngừng hợp tác thì đặt `IsActive = false`.

### 8.2. Quyền lập phiếu nhập
- **Cả Staff và Admin đều được tạo phiếu nhập hàng.** Đây là yêu cầu trong đặc tả chức năng của báo cáo.
- Người lập chọn nhà cung cấp, các biến thể/sản phẩm, số lượng đặt và đơn giá nhập.
- Server tự tính `LineTotal = UnitPrice × OrderedQuantity` và `TotalAmount`; không nhận tổng tiền do client tính làm nguồn chuẩn.
- Phiếu mới ở trạng thái `Pending` (nhãn giao diện “Chờ phê duyệt/Chờ xác nhận”).
- Hệ thống lưu phiếu và thông báo cho Admin có phiếu cần xử lý.

### 8.3. Phê duyệt/từ chối
- Admin xem chi tiết phiếu và quyết định Approved hoặc Rejected theo các giá trị trạng thái hiện có.
- Khi từ chối, lưu lý do nếu trường tương ứng có trong schema và thông báo người lập.
- Phiếu Rejected có thể được sửa và gửi lại thành Pending.
- Phiếu đã nhận hàng không được sửa số lượng đã nhận thông qua chức năng sửa phiếu.
- Người lập không được tự phê duyệt phiếu của chính mình là quy tắc kiểm soát nội bộ được chốt cho triển khai; nếu database không có trường cần thiết để kiểm tra người lập thì dùng trường người tạo hiện có, không tự thêm cột.

### 8.4. Nhận hàng và tồn kho
- Chỉ nhận hàng ở trạng thái `Approved` hoặc `Receiving`.
- Người dùng gửi một hoặc nhiều dòng cần nhận; mỗi dòng là **số lượng nhận thêm trong lần này**, phải lớn hơn 0.
- Khóa phiếu nhập (`FOR UPDATE`), kiểm tra toàn bộ các dòng, cộng dồn dòng trùng nếu có, và bảo đảm `ReceivedQuantity <= OrderedQuantity`.
- Cập nhật `PurchaseOrderItems.ReceivedQuantity` và tăng tồn kho biến thể đúng bằng số lượng thực nhận; không tăng tồn kho khi tạo hoặc phê duyệt phiếu.
- Khóa các biến thể theo thứ tự ID để hạn chế deadlock.
- Nhận nhiều dòng trong một transaction; nếu một dòng lỗi thì rollback toàn bộ lần nhận.
- Nếu nhận đủ tất cả các dòng, chuyển phiếu sang `Completed`; nếu mới nhận một phần, giữ `Receiving`.
- **Giao thiếu:** theo quy tắc mặc định, phiếu giữ trạng thái `Receiving` đến khi nhận đủ. Không tự giảm số lượng đặt hoặc tự đóng phiếu vì báo cáo chưa mô tả thao tác đóng phiếu giao thiếu.
- **Giá vốn:** khi nhận hàng, cập nhật `ProductVariants.CostPrice` theo bình quân gia quyền liên tục nếu quyết định triển khai này vẫn được giữ: `(tồn trước nhận × giá vốn trước nhận + số nhận × giá nhập) / (tồn trước nhận + số nhận)`. Tính bằng Decimal và làm tròn nhất quán 2 chữ số thập phân. Đây là quyết định kỹ thuật bổ sung, không phải mô tả trực tiếp của báo cáo. Nếu công thức không tương thích với nghiệp vụ/Model đang có, dừng và báo thay vì tự đổi schema.
- **Serial/IMEI:** quy trình báo cáo bảo hành yêu cầu nhận diện serial khi xử lý thiết bị. Tuy nhiên, quy trình nhập hàng chưa đặc tả rõ cách nhập serial. Trước khi tích hợp, kiểm tra `ProductSerials` và các liên kết hiện có. Không tự tạo cột/FK/migration. Nếu chưa thể liên kết nguồn nhập đúng cách, ghi nhận là việc cần quyết định riêng.

### 8.5. Lịch sử nhập hàng và cảnh báo tồn kho
- Staff/Admin xem lịch sử phiếu nhập, chi tiết, lọc theo thời gian/nhà cung cấp/sản phẩm và người thực hiện nếu dữ liệu có sẵn.
- Cảnh báo khi tồn kho chạm ngưỡng theo `MinStockLevel`; không gửi cảnh báo nếu ngưỡng đặt bằng 0 theo đặc tả báo cáo.
- Tránh gửi lặp thông báo liên tục nếu không có thay đổi trạng thái tồn kho cần cảnh báo.

## 9. Đặt hàng

1. Customer chọn biến thể và số lượng, thêm vào giỏ hoặc mua ngay.
2. Yêu cầu đăng nhập trước khi đặt hàng.
3. Server kiểm tra sản phẩm/biến thể còn hoạt động và tồn kho đủ.
4. Hiển thị/xác nhận thông tin nhận hàng, địa chỉ, phương thức vận chuyển và phương thức thanh toán.
5. Nếu có Coupon, kiểm tra lại hiệu lực Promotion/Coupon và tính giảm giá phía server.
6. Tính giá bán, phí vận chuyển, giảm giá, tổng tiền, `UnitCost` snapshot và `LineTotal` phía server.
7. Khóa các biến thể cần thiết theo thứ tự ổn định; kiểm tra tồn kho lại trong transaction để ngăn bán vượt tồn.
8. Tạo Order, OrderItems, lịch sử trạng thái và bản ghi thanh toán phù hợp; giảm tồn kho theo quy tắc đang dùng trong OrderService.
9. Chỉ xóa/bỏ chọn các dòng giỏ đã đặt thành công sau khi transaction tạo đơn hoàn tất.
10. Gửi thông báo đơn hàng thành công sau khi dữ liệu được commit.

### Phương thức thanh toán
- Hỗ trợ COD và QR theo phạm vi báo cáo và các phương thức đã cấu hình.
- COD: đơn được tạo ở trạng thái chờ xác nhận; trạng thái thanh toán là Pending cho đến khi thu tiền theo luồng xử lý đơn.
- QR: chỉ đánh dấu Paid khi xác minh được kết quả giao dịch đáng tin cậy; không tin callback không xác thực hoặc dữ liệu từ trình duyệt.
- Callback phải idempotent: cùng một giao dịch gửi nhiều lần không tạo nhiều giao dịch hoặc cập nhật trạng thái sai.
- Khi lỗi thanh toán, không được tạo ra đơn đã thanh toán giả. Hành vi giữ/hủy đơn và hoàn coupon phải theo luồng Payment/Order hiện có; nếu báo cáo và schema khác nhau, nêu rõ trước khi sửa.

## 10. Xử lý đơn hàng, hủy đơn và giao hàng

### Xem/tìm đơn
- Customer chỉ xem/tìm đơn của chính mình.
- Staff/Admin được xem/tìm đơn toàn hệ thống theo quyền.
- Hỗ trợ lọc theo mã, khách hàng, trạng thái và thời gian khi Repository có khả năng.

### Luồng xử lý
- Đơn mới ở trạng thái `Pending` (nhãn “Chờ xác nhận”).
- Staff/Admin kiểm tra đơn và tồn kho; nếu đủ điều kiện thì chuyển sang `Confirmed`/`Processing` theo mapping trạng thái hiện có.
- Khi bàn giao vận chuyển, chuyển sang `Shipping`.
- Giao thành công: chuyển sang `Delivered` hoặc `Completed` theo mô hình trạng thái hiện tại; đơn COD được ghi nhận đã thanh toán khi xác nhận thu tiền.
- Giao thất bại: ghi nhận kết quả; nếu luồng nghiệp vụ quyết định hủy đơn, chuyển `Cancelled`, hoàn tồn kho và xử lý hoàn tiền nếu đã thanh toán.
- Mọi thay đổi trạng thái phải ghi `OrderStatusHistories` với người thực hiện, thời điểm và ghi chú nếu schema hỗ trợ.

### Hủy đơn
- Customer chỉ hủy khi trạng thái cho phép theo Service hiện tại; không cho hủy tùy ý khi đơn đã giao.
- Staff/Admin chỉ hủy theo quyền và trạng thái cho phép.
- Trong cùng transaction: khóa Order, kiểm tra trạng thái, cập nhật trạng thái, hoàn tồn kho đúng một lần, giải phóng lượt Coupon theo quy tắc, ghi lịch sử và thông báo.
- Không hoàn tiền bằng cách chỉ đổi `PaymentStatus`; phải dùng nghiệp vụ thanh toán/hoàn tiền riêng nếu có giao dịch đã thành công.
- Chống hoàn tồn kho hoặc giải phóng Coupon nhiều lần khi thao tác hủy bị gọi lặp.

## 11. Đánh giá sản phẩm

- Theo quy trình báo cáo, khách hàng đánh giá sau khi xác thực đã nhận hàng.
- Kiểm tra rating từ 1 đến 5 và độ dài nội dung theo schema.
- Nếu `OrderItemId` được dùng để xác minh đơn hàng, suy ra ProductId từ OrderItem ở server, kiểm tra đơn thuộc Customer và trạng thái giao hàng hợp lệ.
- Chỉ cho tạo đánh giá nếu đáp ứng điều kiện hiện hành; không tin ProductId/OrderItemId từ client nếu có thể suy ra từ dữ liệu đã xác thực.
- Khi xóa đánh giá, tuân thủ soft delete và FK; cập nhật thống kê rating nếu logic hiện tại yêu cầu.
- Gửi thông báo yêu cầu đánh giá sau khi đơn được giao thành công nếu chức năng thông báo đã có.

## 12. Bảo hành

### Gửi yêu cầu
- Customer đăng nhập, chọn sản phẩm từ đơn hàng đã giao, mô tả lỗi và đính kèm hình ảnh/video nếu có.
- Server xác minh đơn hàng thuộc Customer, sản phẩm thuộc đơn và Serial/IMEI khớp nếu có.
- Kiểm tra điều kiện/thời hạn bảo hành dựa trên dữ liệu hiện có. Nếu thiếu ngày bắt đầu/kết thúc bảo hành hoặc chính sách xác định thời hạn, không tự suy ra; trả về trạng thái không đủ dữ liệu và báo cần quyết định nghiệp vụ.
- Nếu đủ điều kiện, tạo yêu cầu trạng thái `New`; nếu không đủ điều kiện, trả lý do phù hợp.
- Customer chỉ được hủy yêu cầu khi còn `New`.

### Nhân viên xử lý
- Tiếp nhận sản phẩm, ghi lịch sử và chuyển sang trạng thái kiểm tra theo mapping có trong Model.
- Nếu không đủ điều kiện sau kiểm tra thực tế, chuyển `Rejected`, ghi lý do và thông báo khách.
- Nếu đủ điều kiện, bàn giao nhà cung cấp/trung tâm bảo hành, cập nhật trạng thái xử lý.
- Khi có kết quả, ghi nhận sửa chữa/đổi sản phẩm/đổi linh kiện hoặc không thể bảo hành; cập nhật Serial/IMEI mới và thông tin bảo hành nếu schema hỗ trợ.
- Ghi lịch sử mọi chuyển trạng thái và thông báo khách.
- Trạng thái trong báo cáo và các status được phép trong Model có thể khác tên hoặc số lượng; dùng giá trị trong Model, không tự thêm status nếu chưa có migration được duyệt.

## 13. Đổi trả

- Customer gửi yêu cầu cho sản phẩm thuộc đơn hàng đã giao, kèm lý do.
- Staff/Admin xem xét và tiếp nhận hoặc từ chối; khi từ chối cần ghi lý do và thông báo khách.
- Khi tiếp nhận, cập nhật các trạng thái tiến trình theo mapping hiện có: chờ, đã tiếp nhận, đang điều phối, đang đánh giá hư hại, đã trả máy/đóng phiếu.
- Lưu lịch sử trạng thái và ghi chú.
- Báo cáo có đề cập bù tiền tùy theo thiệt hại và chênh lệch giá trị sản phẩm đổi. Không tự triển khai hoàn tiền/bù tiền nếu chưa có quy tắc tính, phê duyệt, nguồn tiền và mapping `CompensationAmount`; cần xác định riêng trước khi code.
- Không đồng nhất yêu cầu đổi trả với hủy đơn hàng. Hoàn tiền phải là nghiệp vụ riêng có kiểm soát.

## 14. Chatbot AI và chat nhân viên

- Customer có thể chọn Chatbot AI hoặc chat với nhân viên.
- Chatbot: nhận câu hỏi, lấy ngữ cảnh liên quan (sản phẩm/khuyến mãi/thông tin công khai), gọi nhà cung cấp AI qua service tích hợp, trả câu trả lời và lưu lịch sử nếu schema hỗ trợ.
- Không gửi bí mật, thông tin thanh toán nhạy cảm hoặc dữ liệu khách hàng khác vào prompt AI nếu không cần thiết.
- Chat nhân viên: tạo/tìm Conversation, lưu Message, gán nhân viên theo cơ chế hiện có, giữ lịch sử và đóng phiên khi xử lý xong.
- Kiểm tra quyền truy cập Conversation/Message để Customer không xem cuộc trò chuyện của người khác.
- Lỗi từ AI provider không được làm hỏng transaction lưu dữ liệu cốt lõi; xử lý lỗi ngoài và thông báo phù hợp.
- Bước 10.2: API AI chỉ cho Customer trong hội thoại AI của chính mình; mỗi lượt có ClientRequestId. Retry cùng mã/nội dung trả kết quả đã lưu, Pending trả trạng thái đang xử lý, Failed được thử lại tối đa số lần cấu hình. Mã cũ với nội dung khác bị từ chối. Một hội thoại chỉ xử lý một lượt AI; lease hết hạn có thể khôi phục và worker cũ không được ghi đè kết quả mới.
- Bước 10.2 chỉ hỗ trợ hội thoại/làm rõ nhu cầu và tư vấn chung; công cụ đọc catalog/giá/khuyến mãi thuộc bước 10.3. Chỉ gửi nội dung chat cần thiết, không gửi hồ sơ người dùng; che email/số điện thoại nhận diện được trong văn bản trước khi gọi model.
- Bước 10.3 đã thêm search_products/get_product/list_offers chỉ đọc qua service hiện có. Backend kiểm tra lại ID/phiên bản/giá/tồn trước khi lưu nội dung và tối đa ba thẻ; thông tin quan trọng được dựng từ dữ liệu chuẩn. Lưu tham chiếu có thứ tự để hiểu câu hỏi “máy thứ hai”; coupon luôn nêu điều kiện, chưa phải cam kết áp dụng. Chi tiết giới hạn và kiểm thử tại `docs/stage10-ai-tools.md`.
- Bước 10.5: khách chỉ gửi câu hỏi; không có nút bật cá nhân hóa hay thao tác lưu sở thích. Mỗi lượt AI tự đọc tối đa 5 cặp hãng–danh mục từ danh sách yêu thích và từ đơn đã giao của chính khách, chỉ dùng để ưu tiên thứ tự gợi ý; yêu cầu trong câu hỏi (hãng, loại trừ, danh mục, ngân sách) luôn thắng. Chỉ gửi tên hãng/danh mục tới AI, không gửi họ tên, email, số điện thoại, địa chỉ hay thông tin đơn hàng. Khung chat ghi rõ gợi ý có thể dựa trên sản phẩm đã yêu thích hoặc đã mua. Không thêm bảng/migration. Chi tiết tại `docs/stage10-ai-personalization.md`.
- Cập nhật 22/10/2026 (`docs/stage10-ai-advisor-upgrade.md`): tư vấn AI chỉ dựa trên catalog và nhu cầu khách nêu.
  - Wishlist, giỏ hàng và đơn hàng không tham gia quyết định gợi ý; câu trả lời không nêu lý do “đã yêu thích/đã mua”. Khách mới chưa có lịch sử nhận tư vấn đầy đủ như mọi khách.
  - Khi khách xin thêm lựa chọn, hệ thống không lặp sản phẩm đã giới thiệu trong cùng nhóm nhu cầu; hết sản phẩm phù hợp thì nói rõ.
  - Giá, thông số và ưu đãi trong câu trả lời phải có trong dữ liệu catalog.
- Bước 10.6: gợi ý theo hai tầng. Lọc cứng (đang bán, còn hàng, trong ngân sách, đúng danh mục, hãng bắt buộc) rồi xếp hạng tối đa 20 ứng viên bằng `Score = Σwᵢsᵢ/Σwᵢ` với N nhu cầu 0,40, B ngân sách 0,25, T hãng ưu tiên mềm 0,20, H lịch sử 0,15; tiêu chí không áp dụng được loại và chuẩn hóa lại. Thiếu thông số không tính là đạt; không chấm camera theo MP; không đẩy sản phẩm khách đã mua. Câu hỏi yêu cầu thứ tự (“rẻ nhất”…) giữ thứ tự đó. Thẻ gợi ý sắp theo điểm và có dòng lý do dựng từ dữ liệu catalog. Cụm nhu cầu trùng tên nhóm con (“Điện thoại pin trâu”) là tiêu chí mềm, không phải bộ lọc cứng. Chi tiết tại `docs/stage10-ai-recommendation.md`.

## 15. Thống kê, nội dung và quảng cáo

### Thống kê
- Staff/Admin xem tổng số hàng bán, số đơn, doanh thu và đơn gần đây; lọc theo khoảng thời gian và các tiêu chí được Repository hỗ trợ.
- Chỉ tính các đơn/trạng thái phù hợp với định nghĩa doanh thu hiện hành. Không suy ra doanh thu từ mọi đơn đã tạo.
- Dùng Decimal cho tổng tiền; tránh truy vấn N+1 và truy vấn toàn bộ dữ liệu không cần thiết.

### Banner/tin tức/quảng cáo
- Admin quản lý nội dung theo các trường và trạng thái hiện có.
- Chỉ hiển thị nội dung đang hoạt động/được xuất bản theo điều kiện schema và Service.
- Không tự thêm trạng thái hoặc trường lịch xuất bản nếu Model chưa hỗ trợ.

## 16. Thông báo

- Tạo thông báo cho sự kiện nghiệp vụ chính: OTP, đặt hàng, thay đổi trạng thái đơn, phiếu nhập cần duyệt/kết quả duyệt, bảo hành/đổi trả và chat.
- Dữ liệu thông báo trong database nên được ghi trong cùng transaction khi nó là một phần của nghiệp vụ; gửi email hoặc gọi hệ thống bên ngoài sau commit hoặc bằng cơ chế retry/outbox nếu dự án có.
- Không báo thành công cho người dùng nếu transaction chính đã rollback.
- Thông báo phải được gửi đúng người nhận; không để Customer đọc thông báo của tài khoản khác.

## 17. Các điểm cần đối chiếu trước khi code

Những điểm sau có thể khác giữa câu chữ báo cáo và schema/code. Claude Code phải xác minh trong repo trước khi triển khai, không tự âm thầm hòa giải:

1. **Trạng thái đơn hàng:** báo cáo có các nhãn “Giao hàng thất bại”, “Hoàn thành”, trong khi Model dùng các giá trị trạng thái đã khai báo. Cần mapping rõ ràng, không thêm status tùy tiện.
2. **Trạng thái bảo hành:** báo cáo mô tả “Đang kiểm tra”, “Đang sửa”, “Hoàn tất”, “Đã trả khách”; đối chiếu với CHECK/Literal status trong schema.
3. **Nhập hàng:** báo cáo có đoạn mô tả cập nhật tồn kho sau phê duyệt; đặc tả chi tiết hiện được triển khai theo quyết định tồn kho tăng khi nhận hàng thực tế. Dùng quy tắc đã thống nhất trong Service: không tăng tồn khi chỉ duyệt.
4. **Admin lập phiếu nhập:** báo cáo đặc tả chức năng ghi rõ “Quản trị viên hoặc nhân viên” có thể tạo phiếu. Không giới hạn thao tác lập phiếu cho Staff.
5. **Giá vốn:** phương pháp bình quân gia quyền là quyết định bổ sung cho triển khai; xác minh cách tính và làm tròn trong code hiện có.
6. **Serial/IMEI khi nhập:** báo cáo chưa nêu đầy đủ quy trình tạo Serial/IMEI ở bước nhập hàng. Không tự thay đổi schema để hỗ trợ.
7. **Đóng phiếu nhận thiếu:** báo cáo chưa quy định cách đóng phiếu nếu NCC giao thiếu và không giao tiếp; mặc định giữ `Receiving`.
8. **Đổi trả/bù tiền:** báo cáo mô tả bù tiền nhưng chưa xác định công thức, phê duyệt và luồng thanh toán; chưa triển khai suy đoán.
9. **Thời hạn bảo hành:** cần xác định nguồn dữ liệu/ngày bắt đầu, ngày kết thúc và chính sách tính thời hạn nếu schema hiện tại không đủ.
10. **Xóa dữ liệu:** các mô tả “xóa” trong báo cáo phải được đối chiếu với FK/lịch sử và quy tắc soft delete của schema.

## 18. Thứ tự triển khai Service Layer

Triển khai theo phụ thuộc dữ liệu và các Service đã có; không viết lại nhóm đã hoàn thành nếu không có lỗi cụ thể:

1. Promotion/Coupon — đã triển khai; regression khi sửa logic dùng coupon.
2. Purchasing — đã triển khai; kiểm tra quy tắc quyền Admin lập phiếu, nhận hàng, giá vốn và serial theo các quyết định đã chốt.
3. Review.
4. Chat/Customer support.
5. Warranty/Return.
6. Content/Banner/News.
7. Statistics/reporting.
8. Hoàn thiện tích hợp giữa Order, Payment, Purchasing và các nghiệp vụ tồn kho.
9. Sau khi Service ổn định, xây Router/API, test tích hợp và frontend.

> Thứ tự trên là kế hoạch triển khai, không phải yêu cầu chức năng nguyên văn của báo cáo. Trước khi tiếp tục, kiểm tra trạng thái repo thực tế vì một số nhóm có thể đã được hoàn thành sau khi tài liệu này được tạo.

## 19. Checklist kiểm thử tối thiểu cho mỗi Service

- Luồng thành công.
- Dữ liệu thiếu/sai định dạng/vi phạm CHECK hoặc UNIQUE.
- Bản ghi không tồn tại hoặc đã bị xóa/ẩn.
- Sai role, sai chủ sở hữu hoặc không có quyền thực hiện.
- Trạng thái hiện tại không cho phép thao tác.
- Hai yêu cầu cạnh tranh trên cùng tài nguyên (tồn kho, coupon, phiếu nhập, thanh toán).
- Gọi cùng thao tác nhiều lần không gây nhân đôi dữ liệu, trừ khi nghiệp vụ cho phép.
- Lỗi giữa transaction rollback toàn bộ thay đổi.
- Không làm hỏng nhóm Service phụ thuộc; chạy regression test.
- `alembic check` không có thay đổi ngoài dự kiến; không tạo/apply migration nếu không được yêu cầu.

## 20. Nguồn sự thật

1. `docs/business-requirements.md`: diễn giải nghiệp vụ phục vụ triển khai Service Layer, dựa trên quy trình và đặc tả trong báo cáo.
2. `docs/database-schema.md`: nguồn chuẩn cho cấu trúc database và constraint.
3. SQLAlchemy Models, Pydantic Schemas, Repositories và migrations: hiện trạng kỹ thuật thực tế.
4. `Quy trình nghiệp vụ.docx`: nguồn gốc nghiệp vụ/báo cáo. Khi trích dẫn trong trao đổi, chỉ khẳng định điều được tài liệu hỗ trợ; mọi quyết định bổ sung phải được gắn nhãn là quyết định triển khai.


---

## Bổ sung hiện hành cho phần admin — 18/10/2026

Phần bổ sung này ghi các quyết định mới và hợp đồng đã đối chiếu với mã nguồn ngày 18/10/2026. Giữ nguyên nội dung gốc để lưu lịch sử; khi có khác biệt ở đúng chủ đề bên dưới, áp dụng phần bổ sung thay cho quy tắc cũ tương ứng. Đây là cập nhật tài liệu, không phải lệnh thay đổi source code, chạy migration hoặc sửa CSDL thật.

[2026-10-18-admin.md](updates/2026-10-18-admin.md) | [README.md](README.md)

### Phiếu nhập, người tạo và người duyệt

- Staff lập phiếu ở Pending, chờ Admin duyệt hoặc từ chối. Admin lập thì phiếu ở Approved ngay và có thể nhận hàng, không cần bước quyết định tự duyệt riêng.
- Phiếu chỉ sửa khi Pending/Rejected. Sửa đầu phiếu và toàn bộ dòng hàng gửi trong một PATCH tới `/admin/purchase-orders/{id}` với `SupplierId`, `Note`, `Items`.
- Backend khóa phiếu, kiểm tra lại trạng thái và lưu tất cả trong một transaction. Lỗi kiểm tra/ghi/commit thì hoàn tác toàn bộ. Giữ ID của dòng còn cùng ProductVariantId; thêm dòng mới, xóa dòng bị bỏ, tính lại tổng tiền ở backend. Gửi lại cùng bộ dòng không thêm trùng SKU.
- Bỏ `Items` trong PATCH là giữ nguyên dòng hiện có; `Items=[]` hoặc null bị từ chối. Trường ngày lập, người lập, thành tiền và thực nhận không phải đầu vào được phép sửa tùy ý.

### Bảo hành, đổi trả và các luồng tạm dừng

**Đổi trả hiện hành:** Staff/Admin tiếp nhận hoặc từ chối, sau đó chỉ chuyển tiến độ theo thứ tự `Pending → Approved → Receiving → Processing → Completed`. Customer hủy theo điều kiện của API khách. Rejected/Cancelled/Completed là phiếu đóng; không có chuyển lùi. Từ chối cần lý do. Backend kiểm tra trạng thái đang quan sát để bấm lặp hoặc form cũ không làm nhảy nhiều giai đoạn.

Luồng đổi trả hiện hành không bắt kiểm tra thiệt hại, duyệt tiền hoặc hoàn tiền để tiến bước; không tự cộng/trừ kho hay chuyển serial theo việc bấm chuyển trạng thái. Completed tại đây chỉ là hoàn tất tiến độ phiếu, không chứng nhận tiền đã được hoàn hoặc hàng đã nhập lại kho. Luồng tài chính cũ được giữ nhưng endpoint ghi theo luồng đó đang trả lỗi `service_workflow_paused`.

### Lưu tin tức và banner theo trạng thái

- Tạo/sửa tin tức gửi nội dung cùng Status trong một POST/PATCH tới `/admin/news` hoặc `/admin/news/{id}`. Mặc định tạo Draft; chọn Published thì đăng ngay khi lần lưu thành công. Backend tự ghi PublishedAt lần đầu, giữ khi ẩn rồi đăng lại; không nhận PublishedAt hoặc người tạo tùy ý từ client.
- Chuyển trạng thái tin tức vẫn theo quy tắc: Draft giữ Draft hoặc sang Published; Published giữ Published hoặc sang Hidden; Hidden giữ Hidden hoặc sang Published. Không đưa bài đã đăng về Draft. Bỏ Status trong PATCH thì giữ trạng thái đang có.
- Tạo/sửa banner gửi nội dung, khoảng hiển thị và IsActive cùng một POST/PATCH tới `/admin/banners` hoặc `/admin/banners/{id}`. Mặc định tạo true; nếu chọn ngừng thì bản ghi được tạo false ngay, không có bước tạo hoạt động rồi gửi lệnh tắt sau. Bỏ IsActive trong PATCH thì giữ cờ đang có.
- Mỗi lần lưu thuộc một transaction: lỗi kiểm tra, ghi hoặc commit hoàn tác nội dung và trạng thái cùng nhau. Form giữ dữ liệu nhập để thử lại, không dùng cơ chế lưu một phần rồi tiếp tục đổi trạng thái.
- Các nút đổi trạng thái riêng ở danh sách/chi tiết vẫn dùng publish/hide hoặc activate/deactivate. Form không cần gọi thêm các endpoint này sau lần lưu nội dung.
- API công khai chỉ trả bài Published; banner phải IsActive=true và đang trong [StartDate, EndDate], mốc null là không giới hạn. Trạng thái trong CSDL quyết định khả năng hiển thị, không phải việc trình duyệt đã từng bấm một nút Đăng.

### Promotion và Coupon

- Promotion là chương trình mẹ giữ điều kiện giảm, phạm vi Product/Category và thời gian. Coupon giữ Code, Name, PromotionId, UsageLimit, UsedCount và các dấu vết tạo; không tách điều kiện giảm độc lập khỏi mẹ.
- Sửa thông tin và phạm vi chương trình dùng cùng PATCH, một transaction. Lỗi ở bất kỳ phần nào hoàn tác cả thông tin lẫn phạm vi. Endpoint targets cũ vẫn có thể tồn tại cho tương thích, không phải hai bước form bắt buộc.
- Promotion ở Scheduled/Active được đánh giá theo giờ server; Draft/Cancelled vẫn là quyết định quản trị. Tại EndDate còn trong khoảng, sau EndDate là hết hạn.
- Coupon có bốn trạng thái API: Active (Đang áp dụng), Upcoming (Chưa bắt đầu), Exhausted (Hết lượt), Ended (Hết chương trình). Hết/hủy chương trình mẹ được ưu tiên trước hết lượt. IsActive chỉ true khi Active; không còn công tắc tạm ngừng riêng mã.

### Báo cáo và lịch sử thanh toán

- API báo cáo hiện có `/admin/statistics/report-options`, `/admin/statistics/reports/revenue` và `/admin/statistics/reports/orders`, dùng cho Staff/Admin theo quyền. Chúng bổ sung cho các API thống kê cũ, không xóa API cũ.
- Hai màn hình báo cáo có lựa chọn từng tháng trong 12 tháng của năm hoặc 6 tháng gần nhất. Từng tháng hiển thị một cột, 6 tháng hiển thị 6 cột; nhãn là tháng cụ thể. Bộ lọc tác động đồng thời biểu đồ và bảng; kỳ bảng là tháng/năm, không chia tuần.
- Cập nhật 21/10/2026: tab Đơn nhập hàng dùng `/admin/statistics/reports/purchases`, bổ sung lọc nhà cung cấp kết hợp thời gian/danh mục/thương hiệu/sản phẩm. Xem cách tính hiện hành trong [admin-reporting-redesign.md](admin-reporting-redesign.md). Chưa có lọc tài khoản và xuất báo cáo; không suy ra giá trị bằng 0 khi API báo lỗi.
- Báo cáo doanh số theo sản phẩm dùng OrderItems.LineTotal của đơn Delivered/Completed theo DeliveredAt, có giao dịch Payment Success; không tính lặp doanh số khi một đơn có nhiều giao dịch. Báo cáo này không đồng nghĩa mọi chỉ số doanh thu thuần của StatisticsService: phí giao, hoàn tiền và giá vốn cần phân biệt theo từng API.
