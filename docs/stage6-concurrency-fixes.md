# Sửa ba lỗi sau rà soát giai đoạn 6

Ngày thực hiện: 11/10/2026. Phạm vi gồm checkout trùng giỏ, bảo vệ database khi chạy integration test PostgreSQL và ghi địa chỉ mặc định đồng thời.

## 1. Checkout cùng giỏ hàng

Trước khi sửa, hai request có thể cùng đọc các dòng giỏ đã chọn trước khi khóa tồn kho. Nếu còn đủ hàng, cả hai đều tạo đơn từ cùng một giỏ.

`OrderService.create_order()` hiện khóa dòng `Carts` bằng `SELECT ... FOR UPDATE` trước khi đọc `CartItems`. Các thao tác đọc/thêm/sửa/chọn/xóa của `CartService` dùng cùng khóa. Sau khi chờ khóa, repository nạp lại dữ liệu để tránh dùng số lượng, trạng thái chọn hoặc thông tin sản phẩm cũ trong identity map của SQLAlchemy.

Thứ tự khóa là **Cart → ProductVariant → Coupon**. Request checkout thứ hai đọc giỏ sau khi request đầu commit; nếu request đầu đã đặt hết các dòng được chọn thì request thứ hai bị từ chối với `cart_empty`. Hai khách mua từ hai giỏ riêng vẫn dùng khóa biến thể để bảo vệ tồn kho.

Các thay đổi chính nằm trong `backend/app/services/order.py`, `backend/app/services/wishlist_cart.py`, `backend/app/repositories/wishlist_cart.py` và `backend/app/repositories/catalog.py`.

## 2. Guard cho integration test PostgreSQL

Guard cũ có thể coi cùng database là khác nhau khi đổi SQL username hoặc viết port mặc định khác cách. Bộ test này có `TRUNCATE`, nên việc kiểm tra đích test phải hoàn tất trước khi tạo engine.

`backend/tests/postgres_safety.py` hiện:

- Chuẩn hóa host và port mặc định; nhận diện các alias loopback.
- So sánh database độc lập với password, driver và SSL. Với PostgreSQL thông thường, đổi username không chứng minh database khác nhau.
- Nhận diện project ref của Supabase qua host trực tiếp hoặc username của shared pooler. Cùng project và cùng database bị từ chối dù khác role, host trực tiếp/pooler hay port 5432/6543.
- Cho phép database có tên khác được ghi rõ trong URL hợp lệ, hoặc hai project Supabase đã nhận diện có ref khác nhau.
- Từ chối URL thiếu/sai, query parameter có thể ghi đè đích kết nối, và trường hợp cùng tên database nhưng alias host/port chưa thể xác định là tách biệt.
- Chỉ trả thông báo lỗi đã lược bỏ thông tin kết nối; không tạo engine, phân giải DNS hoặc kết nối database để kiểm tra.

Tên database trong URL phải là tên database thực. Custom proxy ánh xạ nhiều tên database về cùng một database không nằm trong các cấu hình được hỗ trợ.

Định dạng Supabase được đối chiếu với [tài liệu kết nối PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres). [Supavisor FAQ](https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI) xác nhận pooler hỗ trợ database khác nhau và tạo pool theo tổ hợp user/database/mode.

`backend/tests/conftest.py` ghi nhận `RUN_POSTGRES_TESTS=1` từ môi trường process trước khi collection import ứng dụng và load `.env`. Giá trị được load muộn từ `.env` không tự bật bộ test. Fixture cũng kiểm tra cờ này và guard trước mọi thao tác database. Cleanup dùng tên bảng đã escape và chỉ rõ schema `public`.

## 3. Địa chỉ mặc định

`UserService.save_default_address()` và các thao tác tạo/sửa/xóa trong `AddressService` hiện khóa cùng dòng `Users` của chủ địa chỉ trong suốt transaction. Khóa này bảo vệ cả trường hợp người dùng chưa có địa chỉ nào.

Sau khi chờ khóa, service kiểm tra lại trạng thái tài khoản và quyền Customer, rồi nạp lại địa chỉ từ database. Khi đổi mặc định, các cờ mặc định cũ được flush trước khi ghi địa chỉ thay thế. Hai request từ API hồ sơ và sổ địa chỉ vì vậy không thể cùng tạo hai mặc định từ cùng trạng thái ban đầu.

Không thêm migration hoặc sửa Models cho ba bản sửa này. Các thao tác ứng dụng duy trì tối đa một địa chỉ mặc định đang hoạt động khi dữ liệu đầu vào đã hợp lệ; chúng không tự sửa dữ liệu trùng có từ trước hoặc thay thế việc kiểm tra các tác vụ ghi SQL ngoài ứng dụng.

## Kiểm thử

Chạy bộ test backend mặc định từ thư mục `backend`:

```powershell
$env:RUN_POSTGRES_TESTS = '0'
..\.venv\Scripts\python.exe -m pytest -q
```

Các ca hồi quy mới gồm:

- `test_checkout_cart_locking.py`: checkout trùng khi còn nhiều tồn kho, sửa giỏ sau checkout, cộng số lượng đồng thời, thứ tự khóa và dữ liệu ORM đã cũ.
- `test_address_concurrency.py` và `test_address_service.py`: hai session ghi địa chỉ, phối hợp hai API, xóa/đổi mặc định, kiểm tra lại tài khoản sau khi chờ khóa và thứ tự flush.
- `test_postgres_safety.py`: URL alias/credentials/port/Supabase, cấu hình không rõ đích, cờ opt-in trước dotenv và guard chạy trước engine/cleanup.
- `test_postgres_concurrency.py`: ba ca opt-in dùng PostgreSQL thật cho hai checkout cùng giỏ và hai cặp thao tác địa chỉ đồng thời.

Kết quả bộ test mặc định ngày 11/10/2026: **938 test đạt, 633 subtest đạt, 8 ca PostgreSQL bỏ qua** trong 29,27 giây. Có một cảnh báo deprecation từ Starlette TestClient/httpx.

Sau đó đã chạy riêng **8/8 ca PostgreSQL đạt** trong 101,80 giây trên database test tách biệt, PostgreSQL **17.11**, migration head `3d9f987f3c6f`. Các ca gồm năm luồng API hiện có, hai checkout cùng giỏ khi còn nhiều hàng và hai cặp ghi địa chỉ đồng thời (sổ địa chỉ/sổ địa chỉ, sổ địa chỉ/hồ sơ). Guard bảo vệ database đã được kiểm thử offline; kiểm tra đích thực tế hoàn tất trước khi chạy các ca có ghi/xóa dữ liệu.

Kiểm tra chỉ đọc sau test xác nhận **44 bảng nghiệp vụ không còn dòng dữ liệu test**, còn revision migration được giữ nguyên. Không chạy migration mới và chưa commit.

Chạy lại PostgreSQL chỉ với `TEST_DATABASE_URL` trỏ tới database test riêng đã migrate; bộ test xóa dữ liệu trong database này trước và sau khi chạy:

```powershell
$env:RUN_POSTGRES_TESTS = '1'
..\.venv\Scripts\python.exe -m pytest tests/test_postgres_integration.py tests/test_postgres_concurrency.py tests/test_postgres_warranty.py tests/test_postgres_coupon.py tests/test_postgres_engagement.py -v --tb=short
$env:RUN_POSTGRES_TESTS = '0'
```

## Cập nhật: giới hạn ngày thống kê

Đã sửa `backend/app/services/statistics.py`: khi đổi ngày Việt Nam sang UTC vượt giới hạn `datetime`, service trả `BusinessRuleError` với mã `invalid_statistics_period`. Với `date_from=0001-01-01`, bốn API orders/revenue/cogs/top-products hiện trả **400**, thay vì phát sinh `OverflowError` và trả 500. Không truy vấn dữ liệu với khoảng ngày không hợp lệ.

Các ngày sát biên hợp lệ `0001-01-02` và `9999-12-30` vẫn được hỗ trợ; giữ cách tính ngày Việt Nam và kiểm tra `date_to=date.max`. Regression được thêm vào `test_statistics_service.py` và `test_router_flows.py`, gồm cả Staff/Admin.

Lượt kiểm thử sau sửa thống kê: **949 test đạt, 657 subtest đạt, 8 ca PostgreSQL bỏ qua**, trong 30,24 giây. Tám ca PostgreSQL thật nêu ở trên đã chạy trước bản sửa thống kê; lượt này chạy bộ test mặc định.

## Đối chiếu test PostgreSQL cho bốn mảng nghiệp vụ

Rà ban đầu xác nhận test cho bốn mảng dùng `InMemoryDB`/`FakeSession`. Ngày **12/10/2026**, đã bổ sung workflow PostgreSQL thật và chạy đạt toàn bộ **17/17 ca**; xem [kết quả và phạm vi hiện tại](stage6-postgres-validation.md).

| Mảng | Test hiện có | Workflow PostgreSQL thật |
|---|---|---|
| Bảo hành | `backend/tests/test_warranty_service.py` | `backend/tests/test_postgres_warranty.py` (3 ca) |
| Coupon | `backend/tests/test_stock_and_coupon.py` | `backend/tests/test_postgres_coupon.py` (2 ca) |
| Chat | `backend/tests/test_chat.py`, `backend/tests/test_chat_rules.py`, `backend/tests/test_router_flows.py` | `backend/tests/test_postgres_engagement.py` (1 ca) |
| Nội dung | `backend/tests/test_content_service.py`, luồng banner trong `backend/tests/test_router_flows.py` | `backend/tests/test_postgres_engagement.py` (2 ca) |

Bộ PostgreSQL gồm năm file với 17 ca: các luồng đăng ký OTP, nhập hàng, đơn COD/đổi trả/hoàn tiền/thống kê, ngày thống kê vượt giới hạn, tranh mua tồn cuối, hết hạn QR, checkout/địa chỉ đồng thời và bốn mảng bổ sung. Lượt kiểm thử mặc định mới nhất đạt **952 test, 657 subtest; 17 ca PostgreSQL bỏ qua**. Đã đồng bộ mô tả quyền/xác thực theo code hiện tại; SePay và cron thực tế để sau, không đổi cấu hình hoặc logic Auth/RBAC.
