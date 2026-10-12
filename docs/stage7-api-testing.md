# Giai đoạn 7 — Kiểm thử API backend

Bộ test API kiểm thử backend **qua HTTP** theo từng domain nghiệp vụ, đúng như người dùng và frontend gọi: FastAPI
`TestClient`, đăng nhập thật bằng JWT, dữ liệu thật trên PostgreSQL. Mỗi domain có đủ luồng thành công và các nhóm
lỗi 401, 403, 404, 409, 422 và lỗi nghiệp vụ.

## Cách tổ chức

| Thành phần | Vai trò |
|---|---|
| `backend/tests/api/test_<domain>_api.py` | 13 file, mỗi domain một file; tên test theo nhóm: `test_success_…`, `test_401_…`, `test_403_…`, `test_404_…`, `test_409_…`, `test_422_…`, `test_business_rule(s)_…` |
| `backend/tests/api/conftest.py` | Kết nối database test, mỗi test một transaction rồi rollback, runtime Auth riêng cho từng test, các vai trò `admin`, `staff`, `customer`, `other_customer` (đăng nhập thật qua `/auth/login`) |
| `backend/tests/api/support.py` | `expect(response, status, code)`, `expect_validation(response, *fields)`, `expect_unauthorized`, `expect_forbidden`; `Seed` tạo dữ liệu chuẩn bị (danh mục, biến thể, phương thức vận chuyển/thanh toán, nhà cung cấp, tài khoản) |
| `backend/tests/test_api_matrix.py` | Chạy **offline** trong bộ test mặc định, đọc cây cú pháp (AST) của `tests/api`: đủ 13 domain × 7 nhóm, mỗi nhóm có **lời gọi** helper kiểm tra đúng mã (docstring/comment không được tính), mọi file gán `pytestmark = requires_postgres`. Đây là kiểm tra cấu trúc, không thay cho việc chạy test API |
| `backend/tests/postgres_lock.py` + fixture `postgres_test_lock` (`tests/conftest.py`) | Khóa độc quyền database test cho cả lượt chạy (advisory lock PostgreSQL): lượt chạy thứ hai chờ lượt đầu xong thay vì xóa/ghi chồng dữ liệu của nhau |

### Database và transaction

- Dùng database PostgreSQL **riêng cho test** (`TEST_DATABASE_URL`, ví dụ project Supabase staging đã chạy
  `alembic upgrade head`). `tests/postgres_safety.py` từ chối chạy nếu trùng database của `DATABASE_URL`.
- Khi đã bật cờ mà database test chưa migrate đúng head, bộ test **fail** (không skip), để không báo thành công khi chưa
  chạy gì.
- Mỗi lượt chạy giữ **khóa độc quyền** database test (sau khi kiểm tra đích database, trước khi mở kết nối làm việc).
  Hai lượt chạy cùng lúc (hai terminal, hoặc một công cụ khác chạy lại bộ test) sẽ xếp hàng; trước khi có khóa, việc
  này gây deadlock ở `TRUNCATE` và lỗi trùng dữ liệu (`PaymentMethods.Code=COD`). Khóa phiên cần kết nối kiểu
  session (Supabase pooler cổng 5432 hoặc kết nối trực tiếp), đúng cấu hình đang dùng.
- Đầu phiên test xóa sạch dữ liệu database test một lần. Sau đó **mỗi test chạy trong một transaction và được
  rollback khi kết thúc**: mỗi request dùng một Session gắn vào cùng kết nối với
  `join_transaction_mode="create_savepoint"`, nên commit của Service chỉ chốt savepoint. Không test nào để lại dữ
  liệu, các test không phụ thuộc thứ tự, và ràng buộc/khóa dòng/giá trị mặc định/truy vấn tổng hợp vẫn là của
  PostgreSQL thật (ví dụ lỗi 409 đến từ ràng buộc UNIQUE thật).
- Email OTP được giữ trong bộ nhớ, cổng thanh toán bị tắt (test cần cổng thì gắn cổng giả không bao giờ được gọi),
  kho ảnh đại diện được thay bằng bản giả. Không có gì gửi ra ngoài ngoài truy vấn tới database test.
- Dữ liệu không phải đối tượng của test (danh mục, biến thể, tài khoản…) được tạo trực tiếp bằng ORM cho nhanh; mọi
  hành động được kiểm thử đều đi qua API.

## Chạy

Từ thư mục `backend` (PowerShell):

```powershell
$env:RUN_POSTGRES_TESTS = "1"
..\.venv\Scripts\python.exe -m pytest tests\api -v
Remove-Item Env:RUN_POSTGRES_TESTS
```

Không bật cờ thì các test API được bỏ qua; `tests/test_api_matrix.py` vẫn chạy trong bộ mặc định. Nếu một lượt khác
đang dùng database test, lượt sau in thông báo và chờ (tối đa 15 phút) rồi mới chạy.

## Ma trận domain × mã lỗi

Mỗi ô là một ví dụ tiêu biểu; mỗi test thường kiểm tra nhiều endpoint của cùng nhóm.

| Domain | Thành công | 401 | 403 | 404 | 409 | 422 | Lỗi nghiệp vụ |
|---|---|---|---|---|---|---|---|
| **Auth** | Đăng ký → OTP → đăng nhập → `/auth/me` → đăng xuất (thu hồi token) | Thiếu/sai token, sai mật khẩu | Staff vào cổng khách, khách vào cổng admin, tài khoản khóa | Quên mật khẩu với tài khoản không tồn tại | Đăng ký trùng email/SĐT (không gửi OTP) | Email sai, mật khẩu xác nhận khác, trường lạ `Role` | Sai OTP (không tạo tài khoản), mật khẩu mới trùng cũ |
| **User** | Hồ sơ, sổ địa chỉ (một mặc định), thông báo, Admin tạo Staff | Thiếu token | Staff/Admin dùng sổ địa chỉ, Staff quản lý tài khoản, Admin tự sửa mình | Địa chỉ của người khác, tài khoản Admin ngoài phạm vi | Trùng email/SĐT | Thiếu tỉnh, `Role=Admin`, khóa không lý do | Khóa tài khoản chặn ngay token cũ và đăng nhập; ảnh sai định dạng (415), quá lớn (413) |
| **Product** | Admin tạo danh mục → sản phẩm → biến thể; công khai xem/tìm | Thiếu token | Khách/Staff sửa danh mục | Sản phẩm không có, sản phẩm Draft không công khai | Trùng slug, SKU | `Status` sai, giá âm, trường lạ `StockQuantity` | Xóa danh mục/hãng còn sản phẩm; đổi theo dõi serial khi còn tồn |
| **Cart** | Thêm (gộp dòng), sửa, chọn, xóa; yêu thích | Thiếu token | Staff/Admin dùng giỏ | Biến thể không có/không bán, dòng giỏ của người khác | Sản phẩm đã có trong yêu thích | Số lượng 0, id sai | Vượt tồn kho |
| **Order** | Đặt COD → giao → thu tiền; giá vốn; khách hủy (hoàn tồn) | Thiếu token | Khách vào `/admin`, Staff xem giá vốn, Staff đặt hàng | Đơn của người khác, phương thức vận chuyển không có | Trùng mã phương thức vận chuyển | Thiếu `PaymentMethodId`, trạng thái sai, ngày giờ thiếu múi giờ | Giỏ trống, nhảy bước trạng thái, hủy khi đang giao, COD sang Delivered không thu tiền |
| **Payment** | Phương thức thanh toán; giao dịch COD hiện cho khách và nội bộ | Thiếu token | Staff tạo phương thức, Staff xác nhận hoàn tiền thủ công | Đơn của người khác, giao dịch hoàn tiền không có | Trùng mã phương thức | Số tiền âm, thiếu bằng chứng | QR cho đơn COD, chưa cấu hình cổng, hoàn tiền đơn chưa hủy, xóa phương thức đang dùng |
| **Promotion** | Xem trước mã → đặt hàng có giảm giá → tăng lượt dùng | Thiếu token | Staff/khách quản lý khuyến mãi | Khuyến mãi/mã không có | Trùng mã (không phân biệt hoa thường) | Loại giảm sai, giá trị âm, > 100% | Mã không hợp lệ, chưa đủ giá trị tối thiểu, hết hạn, hết lượt; sai khoảng ngày |
| **Purchase** | Admin tạo NCC → Staff lập phiếu → Admin duyệt → nhận 2 đợt → tồn kho; điều chỉnh kho | Thiếu token | Khách xem phiếu, Staff tạo NCC/duyệt/điều chỉnh kho | Phiếu/NCC không có | Trùng mã NCC | Phiếu không có dòng, số lượng 0, từ chối không lý do | Nhận khi chưa duyệt, nhận vượt số đặt, sửa phiếu đã duyệt, điều chỉnh làm âm kho |
| **Review** | Đánh giá → công khai → sửa → Admin ẩn | Thiếu token | Staff viết/ẩn đánh giá, khách ẩn | Dòng đơn/đánh giá của người khác | Đánh giá lần hai | Điểm 0 hoặc 6, thiếu nội dung | Đánh giá đơn chưa giao, ẩn lần hai |
| **Warranty** | Yêu cầu → nhận → kiểm tra → bàn giao → xử lý → đề xuất → Admin duyệt → hoàn tất | Thiếu token | Staff tạo yêu cầu, khách vào `/admin`, Staff duyệt kết quả | Dòng đơn/yêu cầu của người khác | Đã có yêu cầu đang mở | Thiếu mô tả lỗi, giá trị không hợp lệ | Đơn chưa giao, nhảy bước, hủy sau khi đã nhận máy, tự duyệt đề xuất của mình |
| **Return** | Yêu cầu → nhận → kiểm tra → Admin duyệt tiền → hoàn tiền → xác nhận → hoàn tất; hàng về kho | Thiếu token | Staff tạo yêu cầu, Staff duyệt tiền | Dòng đơn/yêu cầu của người khác | Sản phẩm đang có yêu cầu bảo hành | Loại yêu cầu sai, thiếu lý do | Đơn chưa giao, vượt số lượng, nhảy bước, sai số tiền duyệt, quá hạn đổi trả |
| **Chat** | Khách mở hội thoại → Staff nhận → trả lời (ẩn danh tính Staff) → đóng | Thiếu token | Khách vào `/admin`, Staff mở hội thoại | Hội thoại của người khác | Hội thoại đã có Staff khác nhận | Chế độ/loại tin sai, trường lạ | Dùng lại hội thoại đang mở, trả lời khi chưa nhận, nhắn khi đã đóng, tin rỗng |
| **Content** | Tin tức nháp → đăng → ẩn; banner hiện/tắt | Thiếu token | Staff/khách quản lý nội dung | Bài viết/banner không có | Trùng slug bài viết | Thiếu nội dung/ảnh, ngày sai, khoảng ngày banner sai | Đăng lần hai, slug sai định dạng, bật banner đang bật |

## Hành vi rút ra khi kiểm thử

Các điểm dưới đây là hành vi **đúng theo thiết kế** mà test giờ khóa lại, để frontend và người viết tài liệu dựa vào:

- **Thứ tự kiểm tra:** dữ liệu gửi lên được kiểm tra trước (422), rồi mới tới vai trò (403) ở Service. Thiếu token
  luôn là 401 trước mọi thứ. Mọi route `/admin/...` chặn Customer bằng 403 ngay từ router.
- **Không tiết lộ dữ liệu người khác:** đơn hàng, địa chỉ, dòng giỏ, đánh giá, yêu cầu bảo hành/đổi trả, hội thoại của
  khách khác trả **404**, không phải 403.
- **Mã giảm giá không tồn tại** khi khách xem trước trả **400 `coupon_invalid`**, không phải 404, để không dò được mã
  nào có thật. 404 `coupon_not_found` chỉ dành cho Admin tra theo id.
- **Một số quy tắc nằm ở schema (422)** thay vì Service (400): phần trăm giảm > 100, từ chối phiếu nhập không lý do,
  khoảng ngày banner, khóa tài khoản thiếu lý do/thời hạn.
- **Tài khoản bị khóa:** token cũ nhận **403 "Tài khoản đang bị khóa"** ngay ở request kế tiếp; đăng nhập lại cũng 403.
- **Đăng xuất** cần cả Bearer token và mã CSRF (`X-CSRF-Token`); thiếu mã CSRF trả 403.
- **Mở hội thoại khi đã có hội thoại đang mở** trả lại hội thoại đó (mỗi khách tối đa một hội thoại mở), không báo lỗi.

## Phạm vi và giới hạn

- Bộ test API bổ sung, không thay thế, các test nghiệp vụ ở tầng Service (chạy trên database giả) và các ca
  PostgreSQL theo luồng/đồng thời của giai đoạn 6 (`docs/stage6-postgres-validation.md`).
- Không kiểm thử tích hợp bên ngoài thật: SMTP, Redis, Supabase Storage, cổng SePay. Các ca cần chúng dùng bản giả.
- Tranh chấp đồng thời (hai request cùng lúc) không thuộc bộ này vì mỗi test dùng một kết nối; đã có ở
  `tests/test_postgres_concurrency.py` và `tests/test_postgres_integration.py`.
