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
| Bảo hành | Yêu cầu và theo dõi của mình | Tiếp nhận/kiểm tra/xử lý; đề xuất kết quả; hoàn tất sau duyệt | Như Staff; duyệt/từ chối kết quả và từ chối yêu cầu theo trạng thái |
| Đổi/trả | Yêu cầu và theo dõi của mình | Tiếp nhận/nhận hàng/kiểm tra; từ chối trước khi nhận hàng | Như Staff; duyệt số tiền hoàn; từ chối sau khi nhận hàng |
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

**Quyết định 11/10/2026:** quyền Staff trong bảng trên được đồng bộ theo kiểm tra quyền của các Service giai đoạn 4; ngoại lệ duy nhất là Staff được xem thống kê. Duyệt phiếu nhập, xác nhận hoàn tiền thủ công, duyệt/từ chối kết quả bảo hành, duyệt số tiền hoàn đổi/trả và đăng tin chỉ Admin trong Service. Với đổi/trả, Staff/Admin tiếp nhận yêu cầu (`Pending → Approved`) trước khi nhận hàng; trạng thái `Approved` ở bước này chưa phải quyết định về tiền. Staff/Admin được từ chối trước khi nhận hàng; chỉ Admin được từ chối sau khi nhận hàng.

**Quyền cố định (quyết định 09/10/2026):** quyền của cả ba vai trò được khai báo trong `backend/app/core/rbac.py` và không có giao diện hay API để thay đổi. Muốn đổi quyền phải sửa code, chạy lại test và triển khai lại.

## 3. Phạm vi và điều kiện bổ sung

- Role cho phép nhóm thao tác; backend vẫn kiểm tra chủ sở hữu, nhân viên phụ trách, trạng thái hiện tại và điều kiện nghiệp vụ. Quyền xem không tự cho quyền cập nhật.
- B3.25–3.26 cho Staff xem đơn toàn hệ thống. Phạm vi cập nhật đơn/bảo hành/đổi trả theo người phụ trách cần chốt với workflow trước khi triển khai các service đó.
- Staff sửa/gửi lại/hủy phiếu nhập theo trạng thái nhưng không duyệt/từ chối (B3.17); được xem/lọc lịch sử nhập (B3.18). Xuất báo cáo nhập hàng mặc định chỉ Admin.
- Chat người thật (B3.37): Staff và Admin đều nhận/trả lời; nhận chat phải tránh hai người cùng nhận một hội thoại.
- Không cấp Customer quyền kiểm duyệt hoặc quản lý banner từ các lỗi tác nhân trong B3.33, B3.34, B3.36.
- Danh mục/thương hiệu/nhà cung cấp đã ẩn vẫn hiện với Staff/Admin ở trạng thái ẩn (B3.12, 3.13, 3.16), khách hàng không thấy.
- Luồng hoàn tiền (COD hoàn theo cách nào, công thức số tiền) vẫn cần đặc tả trước khi làm service. Quyền điều chỉnh tồn trực tiếp, duyệt đăng nội dung và chuyển người phụ trách vẫn cần mô tả riêng; chưa mở mặc định.


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
