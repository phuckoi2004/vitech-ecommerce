# VieTech – Chạy backend Giai đoạn 5

Backend cung cấp Auth, hồ sơ cá nhân, avatar, địa chỉ mặc định và quản lý tài khoản theo [auth-spec.md](auth-spec.md), [auth-rbac.md](auth-rbac.md). Nội dung chỉnh báo cáo nằm ở [requirements-revision.md](requirements-revision.md). Frontend hiện có Auth riêng cho khách hàng và khu vực nội bộ, cùng các trang hồ sơ và quản lý tài khoản nội bộ. Các trang mua bán và thao tác nghiệp vụ đầy đủ tiếp tục được triển khai ở giai đoạn tương ứng.

## Giao diện đăng nhập nội bộ Admin / Staff

Frontend có đăng nhập tại `/admin/login`, khôi phục mật khẩu tại `/admin/forgot-password`, trang chính nội bộ, hồ sơ cá nhân và quản lý Customer/Staff theo quyền. Giao diện nội bộ dành cho Staff và Admin, không có đăng ký công khai. Khách hàng dùng các trang riêng `/dang-nhap`, `/dang-ky`, `/quen-mat-khau` và `/tai-khoan`.

Khởi động backend theo mục 1, rồi mở một PowerShell khác tại `E:\vitech-ecommerce\frontend`:

```powershell
npm ci
npm run dev
```

Mở <http://127.0.0.1:5173/admin/login>. Ô đăng nhập nhận số điện thoại Việt Nam hoặc email; mật khẩu là mật khẩu tài khoản VieTech. Tài khoản nội bộ do Admin tạo (mục 5) đăng nhập được ngay. Không dùng luồng đăng ký Customer để tạo Admin.

Frontend chuyển các request `/api` đến backend `http://127.0.0.1:8000`. Proxy Vite đổi path cookie refresh từ `/auth` thành `/api/auth`; cookie CSRF giữ path `/`. Access token và dữ liệu khôi phục chỉ ở bộ nhớ, refresh token nằm trong cookie HttpOnly. Khi reload, frontend khôi phục phiên từ cookie và kiểm tra vai trò nội bộ.

Luồng quên mật khẩu gồm ba bước: nhập email đã đăng ký để nhận OTP, xác minh mã 6 số, rồi nhập mật khẩu mới và xác nhận. Form chỉ nhận email theo quyết định 10/10/2026; frontend gửi email qua trường `Identifier` của API. Bộ đếm dùng `expires_in`, là thời gian còn lại khi API trả response, đã trừ thời gian gửi SMTP. OTP reset mặc định 60 giây, gửi lại sau 60 giây, quyền đặt lại mật khẩu sau xác minh mặc định 300 giây (cấu hình `AUTH_RESET_GRANT_TTL` trong backend, đơn vị giây). Đổi mật khẩu thành công quay lại trang đăng nhập.

Chạy `npm run lint`, `npm test` và `npm run build` tại frontend để kiểm tra. Các kiểm thử tự động dùng response giả, không gửi SMTP hay sửa tài khoản thật. Khi triển khai, cấu hình reverse proxy `/api` và cookie tương ứng; nếu dùng cổng frontend khác 5173, thêm đúng origin vào `CORS_ORIGINS` backend trước khi thử refresh/logout.

## 1. Cài và chạy tại máy phát triển

Mở PowerShell trong `E:\vitech-ecommerce\backend`. Dùng Python của `.venv` ở thư mục gốc dự án:

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Mở Swagger: <http://localhost:8000/docs>. Endpoint `/health/db` kiểm tra kết nối database; kết quả này không kiểm tra SMTP hoặc toàn bộ luồng Auth.

Sao chép [auth.env.example](../backend/auth.env.example) thành `backend/.env` (hoặc thêm các biến còn thiếu vào `.env` đang có) rồi điền giá trị thật, gồm cả `DATABASE_URL`. Các giá trị phát triển:

```dotenv
APP_ENV=development
AUTH_STATE_BACKEND=memory
AUTH_JWT_SECRET=<chuoi-bi-mat-ngau-nhien-it-nhat-32-byte>
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Nếu chưa có secret, tạo tại máy rồi điền vào `.env`:

```powershell
..\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Memory dành cho phát triển/kiểm thử một tiến trình. Khởi động lại hoặc reload làm mất challenge OTP và phiên; nhiều worker không chia sẻ dữ liệu memory. Các cấu hình thời hạn trong mẫu dùng đơn vị giây.

## 2. Cấu hình SMTP dịch vụ email bên ngoài

Điền thông tin SMTP của nhà cung cấp bạn chọn vào `backend/.env`. `SMTP_SENDER` cần là địa chỉ được dịch vụ cho phép gửi; dữ liệu xác thực nằm trong `.env` tại máy.

Ví dụ kết nối qua cổng 587:

```dotenv
SMTP_HOST=<smtp-host-cua-dich-vu>
SMTP_PORT=587
SMTP_USERNAME=<smtp-username>
SMTP_PASSWORD=<smtp-password>
SMTP_SENDER=<dia-chi-email-gui>
SMTP_STARTTLS=true
SMTP_SSL=false
```

Nếu dịch vụ yêu cầu SSL cổng 465, đổi thành `SMTP_PORT=465`, `SMTP_SSL=true`, `SMTP_STARTTLS=false`. Chọn cấu hình kết nối theo thông tin dịch vụ, rồi khởi động lại backend.

### Dùng Gmail để thử email thật

Bật xác minh hai bước trên Gmail, rồi tạo mật khẩu ứng dụng tại <https://myaccount.google.com/apppasswords>. Dùng đúng tài khoản tạo mật khẩu ứng dụng làm `SMTP_USERNAME` và `SMTP_SENDER`; không dùng mật khẩu đăng nhập Gmail thông thường. Xem [hướng dẫn của Google](https://support.google.com/accounts/answer/185833?hl=vi).

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<gmail-cua-ban>
SMTP_SENDER=<gmail-cua-ban>
SMTP_PASSWORD=<mat-khau-ung-dung>
SMTP_STARTTLS=true
SMTP_SSL=false
```

Lưu mật khẩu ứng dụng vào `.env` ở máy, bỏ khoảng trắng giữa các nhóm ký tự. Không gửi mã vào chat hoặc commit `.env`. Nếu mã đã bị chia sẻ, thu hồi và tạo mã khác. Lỗi SMTP `535` cho biết Gmail từ chối xác thực: kiểm tra tài khoản tạo mã và thay mã mới nếu mã đã bị thu hồi. Đổi mật khẩu tài khoản Google cũng thu hồi các mật khẩu ứng dụng cũ.

Để thử OTP với state memory, chạy một tiến trình không dùng `--reload` trong lúc đăng ký; khởi động lại sẽ làm mất challenge đang chờ xác minh:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Khi chưa cấu hình SMTP hợp lệ, thao tác gửi OTP trả lỗi dịch vụ, thường là HTTP 503. Mã OTP chỉ gửi qua email, không trả trong response và không in log. SMTP thực tế cần được kiểm tra bằng email nhận thành công; bộ kiểm thử tự động dùng adapter giả.

## 3. Thử đăng ký và đăng nhập

Trong Swagger, gọi `POST /auth/register` với email/số điện thoại của bạn. Ví dụ cấu trúc request:

```json
{
  "Email": "ban@example.com",
  "PhoneNumber": "0912345678",
  "FullName": "Nguyễn Văn A",
  "Password": "MatKhau@2026",
  "ConfirmPassword": "MatKhau@2026"
}
```

Response chứa `challenge_id`, `expires_in`, `resend_after`. Nhập mã 6 số trong email vào `POST /auth/register/verify`:

```json
{
  "ChallengeId": "challenge_id-vua-nhan",
  "Code": "ma-6-so-trong-email"
}
```

Tài khoản chỉ được lưu sau xác minh thành công. OTP đăng ký có hạn 90 giây; `POST /auth/otp/resend` nhận `ChallengeId` để gửi lại sau cooldown. OTP cũ không còn dùng được sau gửi lại.

Đăng nhập qua `POST /auth/login`:

```json
{
  "Identifier": "ban@example.com",
  "Password": "MatKhau@2026",
  "Portal": "customer"
}
```

`Identifier` có thể là số điện thoại. Customer dùng `Portal=customer`; Staff/Admin dùng `Portal=admin`. Response trả `access_token`, `csrf_token`, dữ liệu người dùng và quyền; server đồng thời đặt cookie refresh HttpOnly và cookie CSRF.

Gọi `/auth/me` hoặc `/users/me` với `Authorization: Bearer <access_token>`. Trong Swagger có thể nhập token bằng nút Authorize. Request nghiệp vụ dùng PascalCase; trường token/challenge trong response dùng snake_case.

## 4. Refresh và đăng xuất bằng PowerShell

Để giữ cookie khi thử API, đăng nhập với `SessionVariable`. Thay định danh/mật khẩu trong ví dụ bằng tài khoản đã xác minh:

```powershell
$vieLogin = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/auth/login' -ContentType 'application/json' -Body '{"Identifier":"ban@example.com","Password":"MatKhau@2026","Portal":"customer"}' -SessionVariable vieAuthSession
Invoke-RestMethod -Method Get -Uri 'http://localhost:8000/auth/me' -Headers @{ Authorization = 'Bearer ' + $vieLogin.access_token }
$vieLogin = Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/auth/refresh' -WebSession $vieAuthSession -Headers @{ 'X-CSRF-Token' = $vieLogin.csrf_token }
Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/auth/logout' -WebSession $vieAuthSession -Headers @{ Authorization = 'Bearer ' + $vieLogin.access_token; 'X-CSRF-Token' = $vieLogin.csrf_token }
```

Refresh cần cookie và header `X-CSRF-Token`, xoay refresh token mỗi lần; dùng `csrf_token` mới sau refresh. Logout cần access token; nếu có cookie refresh thì phải kèm CSRF. Khi frontend gọi API, dùng `credentials: 'include'` để nhận/gửi cookie.

Access token có hạn 15 phút. Phiên Customer tối đa 7 ngày; phiên nội bộ tối đa 8 giờ và hết hiệu lực sau 30 phút không hoạt động. Đổi/reset mật khẩu, đổi email, khóa hoặc xóa mềm tài khoản thu hồi toàn bộ phiên; đăng xuất thu hồi phiên hiện tại. API quản trị không cho thay role.

## 5. Tài khoản nội bộ và Admin đầu tiên

Khởi tạo Admin đầu tiên bằng CLI khi bạn chủ động chạy lệnh này; lệnh ghi tài khoản vào database đang được cấu hình:

```powershell
..\.venv\Scripts\python.exe -m app.cli.create_admin
```

CLI hỏi email, số điện thoại, họ tên và mật khẩu hai lần; mật khẩu được nhập ẩn. Admin này được đánh dấu email đã xác minh trong quy trình khởi tạo tin cậy. Lệnh dừng nếu đã có Admin; không có API đăng ký hoặc tạo thêm Admin. Nếu database đã có Admin, dùng tài khoản đó để đăng nhập hoặc khôi phục mật khẩu.

Sau khởi tạo, mở `/admin/login` hoặc gọi `POST /auth/login` với `Portal=admin`. Admin chỉ xem/quản lý Customer/Staff. Để cấp tài khoản nhân viên, đăng nhập Admin trong Swagger, Authorize bằng `access_token`, rồi gọi `POST /admin/users` với `Role: "Staff"` cùng thông tin theo schema. Admin không quản lý Admin khác hoặc nâng/hạ role; đăng ký công khai chỉ tạo Customer.

Staff được Admin tạo đăng nhập được ngay bằng email hoặc số điện thoại và mật khẩu ban đầu; không cần OTP. Nhân viên quên mật khẩu thì dùng luồng Quên mật khẩu (OTP gửi tới email của tài khoản).

## 6. Cấu hình kho avatar

Điền cấu hình Supabase Storage vào `backend/.env`. `SUPABASE_URL` phải là URL project đang dùng, dạng `https://<project-ref>.supabase.co`. Dùng khóa backend `sb_secret_...` từ Supabase Dashboard → Project Settings → API Keys cho `SUPABASE_SECRET_KEY`; nếu project dùng khóa JWT cũ, điền `service_role` vào `SUPABASE_SERVICE_ROLE_KEY` thay thế. Khi có cả hai, backend ưu tiên `SUPABASE_SECRET_KEY`. Xem [hướng dẫn API key của Supabase](https://supabase.com/docs/guides/getting-started/api-keys).

```dotenv
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SECRET_KEY=<khoa-backend-cua-project>
SUPABASE_AVATAR_BUCKET=avatars
```

Các khóa này chỉ nằm ở backend; không đưa vào biến `VITE_*`, frontend, Git hoặc chat. Từ thư mục `backend`, chạy:

```powershell
..\.venv\Scripts\python.exe -m app.cli.setup_avatar_storage
..\.venv\Scripts\python.exe -m app.cli.setup_avatar_storage --check
```

Lệnh đầu kiểm tra bucket và chỉ tạo nếu chưa tồn tại: public, chỉ nhận `image/jpeg`, `image/png`, `image/webp`, tối đa 2 MiB. `--check` chỉ đọc cấu hình bucket. CLI không tự sửa hoặc xóa bucket đã có; nếu cấu hình hiện tại không phù hợp, lệnh báo lỗi để bạn kiểm tra trong Storage Dashboard hoặc chọn một bucket avatar mới. Xem [hướng dẫn tạo bucket](https://supabase.com/docs/guides/storage/buckets/creating-buckets).

Khởi động lại backend sau khi thay `.env`, rồi thử thay avatar trong hồ sơ. Bộ kiểm thử dùng storage giả; CLI xác nhận cấu hình bucket nhưng chưa chứng minh luồng upload ảnh thật từ giao diện. Nếu thiếu URL/khóa, API upload trả HTTP 503; khóa không hợp lệ hoặc lỗi dịch vụ cần được xử lý trước khi nghiệm thu.

## 7. Production và kiểm thử

Production đặt `APP_ENV=production`, `AUTH_STATE_BACKEND=redis`, `REDIS_URL` của Redis được bảo vệ phù hợp (dùng `rediss://` khi kết nối qua TLS), secret ngẫu nhiên đủ mạnh và `CORS_ORIGINS` là danh sách origin HTTPS cụ thể. Chạy API qua HTTPS để cookie Secure hoạt động; triển khai frontend và API theo cấu hình SameSite=Lax hiện tại, hoặc thiết kế chính sách cookie phù hợp trước khi dùng hai site khác nhau.

Chạy bộ kiểm thử từ thư mục backend:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
```

Các kiểm thử Auth dùng database/state/email giả cho tình huống cần cô lập; không tạo tài khoản thử, chạy migration hoặc gửi email lên production. Kết quả kiểm thử không thay cho xác nhận Redis/SMTP thật và kiểm tra triển khai HTTPS.
