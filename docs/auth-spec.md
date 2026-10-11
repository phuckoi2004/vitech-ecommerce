# VieTech – Đặc tả Auth/RBAC, Giai đoạn 5

Ngày cập nhật: 10/10/2026.

Đặc tả này hợp nhất báo cáo chức năng mới nhất, các quyết định tài khoản đã chốt và yêu cầu bắt đầu Giai đoạn 5. Chính sách có nhãn **mặc định cấu hình** là phương án vận hành dùng cho lần triển khai này, có thể điều chỉnh bằng cấu hình; không phải số liệu suy ra từ báo cáo. Tài liệu mô tả hành vi cần thực hiện, không tự chứng minh chức năng đã hoàn thành hay email thật đã gửi thành công.

Schema tiếp tục theo [database-schema.md](database-schema.md) và các model hiện tại. Phạm vi Auth không thêm bảng, cột hoặc trạng thái tài khoản; quyền của từng vai trò cố định trong code; ràng buộc `Users.Role` được quản lý qua Alembic để chỉ nhận `Customer`, `Staff`, `Admin`. Bản chỉnh các bảng báo cáo ở [requirements-revision.md](requirements-revision.md); bảng quyền ở [auth-rbac.md](auth-rbac.md).

## 1. Phạm vi

- Backend FastAPI xác thực qua bảng `Users` trong Supabase PostgreSQL; frontend React/Vite đã có Auth riêng cho khách hàng và khu vực nội bộ, cùng trang hồ sơ và quản lý tài khoản nội bộ.
- Giai đoạn 5 gồm Auth, hồ sơ cá nhân, quản lý tài khoản, dependency xác thực và phân quyền, kiểm thử các luồng này. Source hiện có thêm API đọc/lưu địa chỉ mặc định phục vụ hồ sơ; CRUD địa chỉ đầy đủ thuộc AddressService của Giai đoạn 4. Các service thanh toán, nhập hàng, đổi trả hoặc chatbot thuộc giai đoạn tương ứng.
- Customer có giao diện riêng với Staff/Admin. Giai đoạn 8 tiếp tục hoàn thiện hai khu vực và các thao tác nghiệp vụ, gọi chung backend/database; khu vực nội bộ không có đăng ký công khai.
- Hạng thành viên, tích điểm và username không thuộc phạm vi. `FullName` là họ tên, không phải định danh đăng nhập.
- Router xử lý HTTP, Service áp dụng nghiệp vụ và transaction, Repository truy cập dữ liệu. Backend kiểm tra quyền và phạm vi bản ghi ở từng thao tác.

## 2. Quy tắc tài khoản

| Nội dung | Quy tắc |
|---|---|
| Role | `Customer`, `Staff`, `Admin`; không tự nhận role từ đăng ký công khai. Admin chỉ quản lý Customer/Staff. |
| Trạng thái | `Active`, `Locked`; xóa mềm dùng `IsDeleted`, tách khỏi khóa. Backend kiểm tra giá trị này; database có `CHECK AccountStatus IN (Active, Locked)`. |
| Khóa quản trị | Bắt buộc lý do và thời điểm kết thúc trong tương lai, lưu `LockReason`, `LockedUntil`; tài khoản bị khóa không được tiếp tục dùng API có xác thực. |
| Tự mở khóa | Khi `LockedUntil` đã qua, backend chuyển về `Active` và xóa thông tin khóa khi xác thực/truy cập; không phụ thuộc frontend hay tác vụ định kỳ. |
| Mật khẩu | Ít nhất 8 ký tự, có chữ hoa, số và ký tự đặc biệt; không bắt buộc thêm chữ thường. Không lưu mật khẩu rõ hoặc ô xác nhận. |
| Định danh | Email không phân biệt hoa/thường; số điện thoại Việt Nam được chuẩn hóa thống nhất trước kiểm tra trùng và tìm kiếm. |
| Đăng ký | Email, `PhoneNumber`, `FullName`, mật khẩu, xác nhận mật khẩu. Server gán `Customer`, `Active`, email đã xác minh sau OTP. |
| Tạo Users | Đăng ký công khai chỉ tạo Customer sau OTP hợp lệ; dữ liệu chờ và hash mật khẩu nằm trong kho trạng thái tạm thời. Admin tạo Staff qua API nội bộ; Admin đầu tiên được tạo bằng CLI riêng. |
| Đăng nhập | Nhập email **hoặc** số điện thoại. |
| Quên mật khẩu | Form chỉ nhận email đã đăng ký (quyết định 10/10/2026). OTP khôi phục gửi tới email gắn với tài khoản, không triển khai SMS. |
| Đổi email | Xác minh mật khẩu hiện tại và OTP gửi tới email mới trước khi thay `Users.Email`; kiểm tra lại trùng email khi cập nhật. |
| Hồ sơ | Cho đổi thông tin cá nhân được phép; không nhận `Role`, `AccountStatus`, `IsDeleted`, tổng chi tiêu hoặc OTP qua API sửa hồ sơ. |
| Địa chỉ | Theo Giai đoạn 4, chỉ Customer có sổ địa chỉ. API hiện có đọc/lưu địa chỉ mặc định của chính chủ (Customer); Staff/Admin nhận 403. CRUD đầy đủ thuộc AddressService của Giai đoạn 4; địa chỉ mặc định phải thuộc tài khoản đó. |

## 3. OTP và giới hạn thử sai

| Chính sách | Giá trị |
|---|---|
| OTP đăng ký | 6 chữ số, hiệu lực **90 giây**. |
| OTP quên mật khẩu | 6 chữ số, hiệu lực **60 giây**. |
| OTP đổi email | 6 chữ số, mặc định cấu hình **90 giây**. |
| Quyền reset sau xác minh OTP | Token ngẫu nhiên dùng một lần, mặc định **300 giây**, cấu hình bằng `AUTH_RESET_GRANT_TTL`. |
| Thử sai | Sau **5 lần sai**, chặn thử lại **3 phút**. |
| Phạm vi bộ đếm | Mặc định riêng cho đăng nhập và từng mục đích OTP; không dùng chung bộ đếm với khóa tài khoản quản trị. |
| Cửa sổ đếm | Mặc định cấu hình **15 phút**. |
| Gửi lại OTP | Mặc định tối thiểu **60 giây**; mã mới vô hiệu mã cũ, không xóa hạn chế thử sai đang còn hiệu lực. |

OTP gắn với một yêu cầu, tài khoản/định danh và mục đích cụ thể (đăng ký, reset mật khẩu, đổi email). Không được dùng OTP đăng ký để reset mật khẩu. Chỉ giữ digest có khóa bí mật; không ghi mã vào log hoặc trả mã trong API thật. Việc kiểm tra và tiêu thụ OTP phải bảo đảm một mã chỉ được dùng một lần, kể cả yêu cầu đồng thời.

Sau 3 phút chờ, OTP cũ thường đã hết hạn; người dùng cần xin mã mới. Không sửa `AccountStatus` thành `Locked` chỉ vì thử sai: hạn chế Auth nằm trong kho trạng thái tạm thời, còn khóa quản trị nằm trong `Users`.

## 4. Luồng chính

### Đăng ký và xác minh

1. Validate dữ liệu, chính sách mật khẩu và ô xác nhận; kiểm tra trùng email/số điện thoại.
2. Hash mật khẩu rồi lưu yêu cầu đăng ký tạm; chưa tạo `Users`.
3. Gửi OTP tới email và trả mã tham chiếu yêu cầu, thời hạn/cooldown để giao diện hiển thị.
4. Kiểm tra OTP đúng mục đích, còn hạn, chưa dùng và không đang bị chặn.
5. Tạo tài khoản Customer trong transaction. Kiểm tra lại xung đột UNIQUE nếu có đăng ký đồng thời; không tạo tài khoản hai lần khi gửi lại yêu cầu xác minh.

### Đăng nhập, đăng xuất và refresh

- Tìm theo email/số điện thoại; kiểm tra mật khẩu, xóa mềm, khóa và portal được phép. Đăng nhập không yêu cầu xác minh email.
- Sai định danh/mật khẩu trả thông báo chung; áp dụng bộ đếm thử sai, kể cả định danh chưa tồn tại.
- Đăng nhập tạo phiên phía server và access token. Đăng xuất thu hồi phiên hiện tại. Refresh hợp lệ xoay token; token cũ không được dùng lại.
- Customer dùng portal Customer; Staff/Admin dùng portal nội bộ. Backend từ chối role không phù hợp, dù giao diện đã ẩn menu.

### Đổi/quên mật khẩu

- Đổi mật khẩu yêu cầu mật khẩu hiện tại, mật khẩu mới và xác nhận; mật khẩu mới khác mật khẩu cũ và đạt chính sách.
- Form quên mật khẩu chỉ nhận email đã đăng ký và gửi email qua trường `Identifier` của API hiện có. OTP gửi tới email của tài khoản. Endpoint xác minh OTP cấp `reset_token` dùng một lần, có hiệu lực mặc định 300 giây; endpoint đặt lại mật khẩu nhận token này và mật khẩu mới/xác nhận.
- Sau đổi/reset, thu hồi tất cả phiên của tài khoản và yêu cầu đăng nhập lại.

### Đổi email

- Xác minh lại mật khẩu hiện tại, kiểm tra email mới và gửi OTP tới địa chỉ mới.
- Email cũ vẫn có hiệu lực đến khi OTP mới được xác minh và transaction thành công.
- Sau thay đổi, thu hồi tất cả phiên; không cho bỏ qua OTP bằng API sửa hồ sơ hoặc sửa tài khoản quản trị.

### Quản lý tài khoản

- Admin chỉ xem và quản lý Customer/Staff, tạo mới Staff; không tạo hoặc quản lý Admin khác, không nâng/hạ role. Staff không có API quản lý người khác.
- Không tự khóa/xóa chính mình qua API quản trị. Tài khoản giữ nguyên role; request gửi role khác bị từ chối, kể cả chuyển Customer ↔ Staff.
- Khóa hoặc xóa mềm thu hồi các phiên của tài khoản bị tác động. Mỗi request tiếp tục kiểm tra role hiện tại trong database, không tin riêng role cũ trong JWT.
- Xóa tài khoản là `IsDeleted=true`, giữ lịch sử đơn hàng và các liên kết nghiệp vụ; không gọi xóa vật lý `Users`.
- Admin đầu tiên được khởi tạo bằng `python -m app.cli.create_admin` qua quy trình quản trị riêng, được xác minh trong quy trình khởi tạo tin cậy; lệnh dừng khi đã có Admin. Không đăng ký công khai hoặc ghi mật khẩu mặc định vào source.
- Staff do Admin tạo được đánh dấu email đã xác minh và đăng nhập được ngay, không cần OTP (quyết định 09/10/2026). Nhân viên chỉ nhận OTP khi quên mật khẩu hoặc đổi email.
- Admin có quyền nghiệp vụ theo bảng RBAC, bao gồm mọi quyền của Staff (cả nhận/trả lời chat). Quyền còn thiếu quy tắc nghiệp vụ chưa được mở endpoint.

## 5. Chính sách phiên mặc định cấu hình

| Nội dung | Giá trị |
|---|---|
| Access token | JWT, hết hạn sau **15 phút**. |
| Duy trì phiên | Refresh token ngẫu nhiên, server chỉ lưu digest; xoay mỗi lần refresh. |
| Customer | Phiên tối đa **7 ngày**, cho nhiều thiết bị. |
| Staff/Admin | Phiên tối đa **8 giờ**, hết hiệu lực sau **30 phút** không hoạt động. |
| Thu hồi | Đăng xuất: phiên hiện tại. Đổi/reset mật khẩu, đổi email, khóa/xóa mềm: toàn bộ phiên. Backend từ chối phiên có role khác dữ liệu tài khoản hiện tại. |
| Cookie | Refresh trong cookie HttpOnly; Secure khi chạy HTTPS; SameSite=Lax mặc định, cấu hình CORS/Origin phù hợp hai khu vực giao diện. |
| CSRF | Refresh/logout kiểm tra cookie CSRF và header `X-CSRF-Token`, cùng Origin khi có. |

Backend kiểm tra phiên còn hiệu lực ở mỗi request có xác thực, bao gồm access token chưa hết hạn nhưng phiên đã thu hồi. Thời điểm kết thúc tối đa của phiên không được kéo dài vô hạn bởi refresh.

## 6. Kho trạng thái và gửi email

- Production dùng Redis cho yêu cầu chờ xác minh, digest OTP đăng ký, bộ đếm/cooldown và phiên; thao tác một lần/refresh xoay cần đồng bộ. Redis không thay thế các bảng nghiệp vụ.
- Kho memory chỉ dùng một tiến trình trong phát triển và kiểm thử; khởi động lại mất OTP/phiên, không phù hợp nhiều worker hoặc production.
- SMTP của dịch vụ email bên ngoài qua adapter chung, đọc cấu hình từ môi trường. Không giả định nhà cung cấp hoặc sử dụng lại mật khẩu Supabase. Thiếu cấu hình email phải báo rõ chưa sẵn sàng, không báo đã gửi email thành công.
- Kiểm thử dùng email adapter giả, không cần gửi thư thật. Kiểm thử này không xác nhận SMTP production hoạt động.
- OTP của tài khoản đã tồn tại (quên mật khẩu, đổi email) lưu trong `Users.OtpCode` dưới dạng 10 ký tự hex đầu của HMAC-SHA256 gắn mục đích (vừa cột `varchar(10)` sẵn có, không đổi schema), hạn dùng ở `Users.OtpExpiredAt`. Mỗi tài khoản chỉ có một OTP chờ: mã mới thay mã cũ; xác minh thành công đặt cả hai cột về NULL nên mã chỉ dùng một lần. Không lưu mã gốc.
- OTP đăng ký nằm trong kho trạng thái vì chưa có dòng `Users` trước khi xác minh. Bộ đếm sai, cooldown gửi lại và dữ liệu đi kèm yêu cầu (email mới, dấu trạng thái tài khoản) luôn ở kho trạng thái.

## 7. Contract API

Prefix URL theo cấu hình router; request dữ liệu nghiệp vụ dùng PascalCase theo schema hiện có. Các trường phản hồi token/challenge dùng snake_case; response người dùng công khai không bao gồm hash mật khẩu, OTP hoặc dữ liệu phiên.

| API | Mục đích |
|---|---|
| `POST /auth/register` | `Email`, `PhoneNumber`, `FullName`, `Password`, `ConfirmPassword`; tạo yêu cầu đăng ký chờ OTP. |
| `POST /auth/register/verify` | `ChallengeId`, `Code`; xác minh OTP và tạo Customer. |
| `POST /auth/otp/resend` | Gửi mã mới cho challenge, giữ giới hạn thử sai. |
| `POST /auth/login` | Đăng nhập bằng `Identifier`, `Password`, `Portal` (`customer` hoặc `admin`). |
| `POST /auth/refresh` | Cookie refresh + CSRF; xoay token và cấp access token mới. |
| `POST /auth/logout` | Access token; kèm CSRF nếu có cookie refresh. Thu hồi phiên hiện tại và xóa cookie. |
| `POST /auth/forgot-password` | `Identifier`; yêu cầu OTP khôi phục từ email/số điện thoại. |
| `POST /auth/reset-password/verify` | `ChallengeId`, `Code`; nhận `reset_token` dùng một lần, thời hạn mặc định 300 giây (`AUTH_RESET_GRANT_TTL`). |
| `POST /auth/reset-password` | `ResetToken`, `NewPassword`, `ConfirmPassword`; đặt mật khẩu mới và thu hồi phiên. |
| `POST /auth/change-password` | `CurrentPassword`, `NewPassword`, `ConfirmPassword`; cần xác thực. |
| `POST /auth/email-change` | `Email`, `CurrentPassword`; cần xác thực, yêu cầu OTP tới email mới. |
| `POST /auth/email-change/verify` | `ChallengeId`, `Code`; cần xác thực, xác minh và đổi email. |
| `GET /auth/me` | Người dùng công khai và danh sách quyền hiện tại. |
| `GET/PATCH /users/me` | Xem/sửa hồ sơ cá nhân. |
| `PUT /users/me/avatar` | Upload ảnh avatar; chỉ dọn ảnh cũ có đường dẫn chuẩn thuộc chính chủ. |
| `GET/PUT /users/me/default-address` | Customer đọc/lưu địa chỉ mặc định của chính mình; Staff/Admin nhận 403. |
| `GET/POST /admin/users` | Admin xem Customer/Staff (lọc `role`, `account_status`, `search` theo họ tên/email/số điện thoại, `deleted_only` cho tài khoản đã xóa mềm); tạo Staff với `Role=Staff`, không tạo Admin. |
| `GET /admin/users/{id}` | Admin xem chi tiết một Customer/Staff; tài khoản Admin hoặc đã xóa mềm trả 404 (xem tài khoản đã xóa với `include_deleted=true`). |
| `GET /admin/users/{id}/default-address` | Admin xem địa chỉ mặc định của một Customer (kể cả tài khoản đã xóa mềm); trả `null` khi chưa có hoặc khi là tài khoản Staff, tài khoản Admin trả 404. |
| `PATCH/DELETE /admin/users/{id}` | Admin sửa/khóa/mở khóa hoặc xóa mềm Customer/Staff; không đổi role hay thao tác tài khoản Admin. |

Action response dùng `message`, `challenge_id`, `expires_in`, `resend_after` khi phù hợp, không trả mã OTP. Schema OpenAPI thực tế là contract chi tiết để frontend tích hợp; tài liệu vận hành nằm ở [auth-setup.md](auth-setup.md).

## 8. Tiêu chí kiểm tra Giai đoạn 5

- Đăng ký chỉ tạo Customer sau OTP; mã sai, hết hạn, sai mục đích, đã dùng hoặc gửi lại không tạo tài khoản sai/đúp.
- Login và OTP bị chặn sau 5 lần sai, được thử lại sau 3 phút; không lẫn với khóa quản trị.
- Nhập sai mật khẩu hiện tại khi đổi mật khẩu/đổi email cũng chặn sau 5 lần trong 3 phút, bộ đếm riêng theo tài khoản.
- Khóa tài khoản luôn cần lý do và `LockedUntil` trong tương lai; không có khóa vĩnh viễn.
- Định danh email/số điện thoại chuẩn hóa nhất quán; xử lý xung đột UNIQUE khi tạo/sửa.
- Logout/refresh xoay/đổi mật khẩu thu hồi phiên đúng phạm vi; token cũ hoặc phiên đã thu hồi bị từ chối.
- Active/Locked/IsDeleted được kiểm tra trong request; khóa hết hạn tự mở.
- Customer/Staff không gọi được API quản trị; Admin chỉ xem/quản lý Customer/Staff, không tạo/sửa/xóa/khóa Admin hoặc thay role. Frontend nội bộ chỉ nhận Staff/Admin.
- API hồ sơ không sửa người khác và không nhận các trường quản trị; CRUD địa chỉ được kiểm tra ở giai đoạn UserService tương ứng.
- Không tự chạy migration hoặc ghi tài khoản thử lên Supabase thật khi chạy bộ kiểm thử.

## 9. Tài liệu kỹ thuật

- [FastAPI – JWT và hash mật khẩu](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
- [Redis – Python client](https://redis.io/docs/latest/develop/clients/redis-py/).

Các thời hạn phiên, OTP và quy tắc mật khẩu trong tài liệu này là quyết định/default của VieTech, không được trình bày thành số liệu mặc định bắt buộc của các nguồn kỹ thuật trên.
