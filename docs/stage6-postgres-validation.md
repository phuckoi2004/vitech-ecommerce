# Kiểm thử PostgreSQL giai đoạn 6

Ngày xác minh: **12/10/2026**. Các ca gọi API qua HTTP với JWT thật và dùng Service/Repository thật để ghi, đọc lại dữ liệu trên database test riêng.

## Kết quả

- Backend mặc định: **952 test đạt, 657 subtest đạt, 17 ca PostgreSQL bỏ qua**, trong 27,52 giây.
- Chạy riêng PostgreSQL: **17/17 ca đạt**, trong 280,12 giây (4 phút 40 giây).
- Database: PostgreSQL **17.11**, head Alembic `3d9f987f3c6f`, **44 bảng nghiệp vụ**.
- Kiểm tra chỉ đọc sau cleanup: cả 44 bảng nghiệp vụ không còn dòng dữ liệu test; revision migration giữ nguyên.
- Có một cảnh báo deprecation Starlette TestClient/httpx; không có test thất bại.

Các bản sửa và test chưa được commit. Không thêm hoặc chạy migration mới.

## Phạm vi kiểm thử

| File | Số ca | Nội dung chính |
|---|---:|---|
| `backend/tests/test_postgres_integration.py` | 6 | OTP/đăng nhập, nhập hàng và tồn/giá vốn, đơn COD/đổi trả/hoàn tiền/thống kê, ngày thống kê vượt giới hạn, tranh mua tồn cuối, hết hạn đơn QR |
| `backend/tests/test_postgres_concurrency.py` | 3 | Hai checkout cùng giỏ; ghi địa chỉ mặc định đồng thời qua sổ địa chỉ và hồ sơ |
| `backend/tests/test_postgres_warranty.py` | 3 | Sửa chữa bảo hành đầy đủ; đổi máy có serial và trừ kho đúng một lần; người đề xuất không tự duyệt và có thể đề xuất lại sau bị từ chối |
| `backend/tests/test_postgres_coupon.py` | 2 | Điều kiện đơn tối thiểu, giá server sau thay đổi giá, phạm vi sản phẩm/mức giảm tối đa; giới hạn lượt dùng toàn hệ thống; hủy đơn hoàn lượt và tồn kho đúng một lần |
| `backend/tests/test_postgres_engagement.py` | 3 | Chat: quyền sở hữu, nhận hội thoại, ẩn thông tin Staff, lưu transcript và đóng/mở lại; tin tức: đăng/ẩn/đăng lại; banner: thời gian hiển thị, bật/tắt và quyền Admin |

Các ca xác nhận kết quả API bằng truy vấn SQL độc lập, gồm số lượng đơn/dòng giỏ, tồn kho, lượt dùng coupon, serial và ngày bảo hành, lịch sử/thông báo bảo hành, hội thoại/tin nhắn, trạng thái bài viết/banner. Dữ liệu được tạo phục vụ kiểm thử trên PostgreSQL thật; không dùng `InMemoryDB` hoặc `FakeSession` cho các workflow này.

Giới hạn coupon hiện tại là `UsageLimit`/`UsedCount` tổng. Lịch sử theo khách được đối chiếu qua `Orders.CustomerId`/`CouponId`; hệ thống chưa có quota độc lập cho từng khách và các test không thêm chính sách đó.

## Mô tả quyền và xác thực đã đồng bộ

- Đổi/trả: Staff/Admin tiếp nhận yêu cầu (`Pending → Approved`) và xử lý hàng; `Approved` tại bước tiếp nhận chưa phải duyệt tiền hoàn. Staff/Admin từ chối trước khi nhận hàng; Admin duyệt số tiền hoàn hoặc từ chối sau khi nhận hàng.
- Bảo hành: Staff/Admin tiếp nhận/kiểm tra/xử lý và đề xuất kết quả; Admin duyệt/từ chối kết quả. Người đề xuất không tự duyệt/từ chối đề xuất của mình.
- API có xác thực tùy chọn: thiếu Authorization, Basic hoặc Bearer rỗng là khách chưa đăng nhập; Bearer token có giá trị nhưng sai/hết hạn/bị thu hồi trả 401. API bắt buộc đăng nhập luôn cần Bearer token hợp lệ.

Đã chỉnh `docs/auth-rbac.md`, `docs/api-endpoints.md` và docstring `get_optional_actor`. Logic Auth/RBAC được giữ nguyên; thêm ba regression HTTP cho Basic/Bearer rỗng để kiểm tra mô tả tương ứng.

## Chạy lại

Chỉ dùng `TEST_DATABASE_URL` trỏ đến database test riêng đã migrate. Fixture kiểm tra đích tách biệt trước khi tạo test engine và xóa dữ liệu trong database test trước/sau mỗi module. Chạy theo thứ tự, không chạy nhiều worker hoặc nhiều bộ test đồng thời trên cùng database test.

Từ thư mục `backend`:

```powershell
$env:RUN_POSTGRES_TESTS = '1'
..\.venv\Scripts\python.exe -m pytest tests/test_postgres_integration.py tests/test_postgres_concurrency.py tests/test_postgres_warranty.py tests/test_postgres_coupon.py tests/test_postgres_engagement.py -v --tb=short
$env:RUN_POSTGRES_TESTS = '0'
```

`RUN_POSTGRES_TESTS` phải được bật trong môi trường process trước collection; giá trị load muộn từ `.env` không tự bật test. Các test dùng mailer thu OTP trong bộ nhớ và tắt payment gateway bên ngoài, còn truy vấn/transaction/constraint/row lock dùng PostgreSQL thật.

## Trạng thái giai đoạn 6

Đã hoàn thành phần API nghiệp vụ, các bản sửa đã yêu cầu, đồng bộ mô tả và kiểm thử các workflow PostgreSQL nêu trên. Frontend nghiệp vụ là phần tiếp theo.

SePay và cron vận hành để sau theo yêu cầu người dùng: chưa cấu hình/đăng ký webhook, chưa thiết lập lịch cron hoặc kiểm thử giao dịch SePay thật. Ca hết hạn QR trong bộ test chỉ kiểm tra logic endpoint với bí mật test, không xác nhận cron đã triển khai. SMTP, Redis và Supabase Storage thực tế vẫn thuộc các tích hợp cần xác minh khi triển khai.
