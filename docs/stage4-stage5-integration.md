# Tích hợp giai đoạn 4 và 5

## Chính sách đã chọn

Giữ Auth/RBAC giai đoạn 5 theo quyết định trực tiếp của người dùng; đưa các service nghiệp vụ giai đoạn 4 vào. API tài khoản dùng `AuthService` và `UserService` giai đoạn 5; `AddressService` và `NotificationService` của giai đoạn 4 được giữ để các service nghiệp vụ sử dụng. Quyền (role) trong các service nghiệp vụ giai đoạn 4 giữ nguyên như giai đoạn 4; ngoại lệ duy nhất là Staff được xem thống kê. Ma trận `core/rbac.py` đã được đồng bộ theo các quyền này (11/10/2026).

## Phương án xử lý lịch sử migration đã được duyệt

Ngày 11/10/2026, người dùng xác nhận áp dụng phương án này trong project, kiểm thử offline. Ngày 11/10/2026 đã chạy `alembic upgrade head` lên database Supabase (từ `61f7b0a38d92` lên `c6a4e2b8d901`), sau đó đối chiếu bảng/cột với Models: không thiếu, không thừa.

Hai nhánh dùng chung revision ID nhưng có implementation hoặc parent khác nhau:

| Revision | Local giai đoạn 5 | GitHub giai đoạn 4 |
|---|---|---|
| `b5d3a7c912e4` | Chuyển SuperAdmin sang Admin rồi thay CHECK | Chỉ thay CHECK |
| `213feab4a632` | Parent `b5d3a7c912e4` | Parent `9b10f42fc70d` |

Thay đổi trong repository (đã chạy trên database ngày 11/10/2026):

1. Giữ một file `b5d3a7c912e4` với logic chuyển role local, bỏ file trùng ID.
2. Giữ `213feab4a632` với parent của giai đoạn 4; bỏ file local trùng ID. Giữ nguyên các dependency còn lại của giai đoạn 4.
3. Giữ nhánh local `61f7b0a38d92` từ `213feab4a632`; downgrade không xóa CHECK do ancestor `dd773e03e503` quản lý.
4. Cho `dd773e03e503` và `9b10f42fc70d` nhận CHECK đúng đang có, tạo nếu thiếu, validate nếu chưa validated. Dừng khi định nghĩa CHECK hoặc dữ liệu không hợp lệ; không tự sửa dữ liệu.
5. Thêm merge revision `c6a4e2b8d901` có hai parent `61f7b0a38d92` và `b81569bc34b0`. Upgrade kiểm tra/bổ sung lại CHECK AccountStatus và TransactionType: DB từng chạy revision `213` local có thể chưa chạy hai ancestor này. Downgrade giữ CHECK của ancestor.
6. Kiểm tra graph và SQL offline: 21 file, một root, một head, không ID trùng; không kết nối database.

SePay `b81569bc34b0` vẫn là migration cuối thêm nghiệp vụ trong nhánh giai đoạn 4; head Alembic sau ghép là `c6a4e2b8d901`. Người dùng đã xác nhận thay đổi này theo mục 5.4 README.

```text
... → 9b10f42fc70d → 213feab4a632 ┬→ 61f7b0a38d92 ─────────────┐
                                └→ ... → b81569bc34b0 ───────┴→ c6a4e2b8d901
```

File revision ghép và hai parent tuân theo cơ chế [merge branch của Alembic](https://alembic.sqlalchemy.org/en/latest/branches.html#merging-branches). Riêng việc trùng ID trước đây đòi hỏi guard bổ sung, vì graph mới không chứng minh DDL của ancestor đã chạy trong database local.

Trước khi chạy migration thật, phải đối chiếu revision và metadata DB, các điều kiện dữ liệu của migration giai đoạn 4, rồi thử trên staging. Guard/merge mới không viết lại dữ liệu; toàn bộ chuỗi cũ vẫn có chuyển role ở `b5d3` và xóa OTP đang chờ ở `a7c3`. API Auth giai đoạn 5 vẫn sử dụng cột OTP, nên cần dừng luồng OTP trong thời gian triển khai và yêu cầu gửi lại sau đó.

## Kết quả kiểm tra local

- Backend: `..\.venv\Scripts\python.exe -m pytest tests -q --tb=short` từ thư mục `backend`: 799 test và 628 subtest đạt (11/10/2026), gồm các test migration offline.
- Graph: 21 revision duy nhất, một root `2cb2e7418b06`, một head `c6a4e2b8d901`; đã kiểm tra đường nâng cấp từ `61f7b0a38d92`, `b81569bc34b0`, `213feab4a632` và base.
- Frontend: 37 test đạt, lint đạt, build đạt với `npm run build -- --configLoader native` trong môi trường Windows hiện tại.
- Migration đã chạy trên database Supabase ngày 11/10/2026 và cấu trúc đã được đối chiếu với Models. Bộ test tự động vẫn dùng SQLite/bộ nhớ; Redis/SMTP và các cổng tích hợp thật chưa được kiểm thử.
- Chưa stage/commit; các file đã xử lý conflict cần được đưa vào index trước khi tạo commit merge.
