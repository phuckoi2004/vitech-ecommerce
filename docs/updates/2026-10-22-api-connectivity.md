# Kiểm tra và sửa kết nối API VieTech — 22/10/2026

Đã kiểm tra tiến trình thực, HTTP trực tiếp, HTTP qua Vite, PostgreSQL Supabase và HTTP client frontend gọi Gemini thật. Nhà cung cấp/model vẫn là **Gemini 3.5 Flash-Lite**. Không chạy migration hoặc sửa cấu trúc database.

## Nguyên nhân và bằng chứng

| Hạng mục | Kết luận |
|---|---|
| Backend | FastAPI đã khởi động và lắng nghe `127.0.0.1:8000`. Tiến trình ban đầu không có reload, chạy từ 17:28 và chưa nạp các thay đổi mới; OpenAPI thực tế chưa có `/ai-messages/{request_id}/cancel` hoặc trạng thái `Cancelled`. Đã khởi động lại bằng launcher phát triển có reload. |
| Vite/URL | Frontend lắng nghe `127.0.0.1:5173`. `VITE_API_URL` không ghi đè `/api`. Proxy chuyển tới `127.0.0.1:8000`, bỏ tiền tố `/api`, đổi cookie refresh từ `/auth` thành `/api/auth` đúng. Không cần sửa `vite.config.js` hoặc đổi URL database. |
| 503 đã tái hiện | HTTP 503 của chatbot có `code=ai_unavailable`, header `server=uvicorn` và log `provider_error_type=APITimeoutError`. Đây là response của FastAPI khi chờ Google quá hạn, không phải Vite tự tạo lỗi. |
| 503 của API cửa hàng | Chưa tái hiện được trong lần điều tra. `/banners`, `/products`, `/brands`, `/categories`, `/pricing/category-offers` đều trả 200 khi gọi thẳng hoặc qua proxy. Hai lượt 30 GET, mỗi lượt tối đa 6 request đồng thời, đều 30/30 HTTP 200. Không có log SQL của thời điểm các lỗi lịch sử này, nên chưa thể quy toàn bộ 503 trước đó cho một nguyên nhân cụ thể. |
| Supabase/dependency | `SELECT 1` và `/health/db` thành công. Revision `d7a1e5c9b304`; không thiếu bảng/cột so với ORM; đủ ba index AI. `pip check` không báo dependency hỏng. Không có bằng chứng cần sửa schema, đổi Supabase URL hoặc đổi driver. |
| Refresh | Tái hiện một lỗi riêng bằng test: sau khi đổi refresh secret, `AuthService.refresh` còn đọc User từ database lần nữa. Nếu database lỗi tại bước này, response là 503 nhưng trình duyệt chưa nhận cookie mới; lần refresh sau có thể thất bại vì vẫn dùng secret cũ. Đã bỏ lần đọc sau rotation, sử dụng đúng User đã kiểm tra trước đó. |
| Thời gian chờ AI | Ngân sách cũ 20 giây không đủ cho tải Google đang quan sát. Một request công cụ mất 24,289 giây; log thực tế có vòng đầu 25,718 giây. Lượt 45 giây timeout ở vòng tiếp theo. Đã đặt ngân sách toàn vòng backend 60 giây và HTTP frontend 75 giây; giữ nguyên model, mức suy luận, `store=false`, không tự retry/fallback. |

Đã đối chiếu kết nối Google trực tiếp và thử mức suy luận khác ở script chẩn đoán; các thử này không loại được timeout 20 giây. Không áp dụng thay đổi proxy Internet/mức suy luận vào website.

## File thay đổi

- `backend/app/services/auth.py`: hoàn tất đọc/kiểm tra User trước khi rotation refresh, tránh lỗi database sau khi credential đã đổi.
- `backend/app/main.py`: lỗi SQLAlchemy có `code=database_unavailable`; lỗi health database được ghi log với loại exception/SQLSTATE đã kiểm soát.
- `backend/app/services/ai_chat.py`: ghi model ngay khi Pending; log mã lỗi, loại lỗi gốc, HTTP status nhà cung cấp, thời gian từng vòng và token. Không ghi câu hỏi, prompt, tham số SQL, API key hoặc token đăng nhập.
- `backend/app/core/ai_config.py`, `backend/.env.example`, cấu hình local `backend/.env`: deadline AI 60 giây. Không đổi khóa, model hoặc datasource.
- `frontend/src/customer/components/AiChatThread.jsx`: HTTP timeout 75 giây, sau đó vẫn kiểm tra trạng thái thay vì tự POST lại.
- `backend/scripts/run_dev.py`: launcher từ bất kỳ thư mục nào, cổng 8000, một worker, reload `backend/app`.
- Test: `backend/tests/test_auth_http.py`, `test_ai_chat.py`, `test_ai_grounded.py`, `test_ai_connection_check.py`; `frontend/src/auth/AuthProvider.test.jsx`, `frontend/src/customer/components/AiChat.test.jsx`.
- Tài liệu: hướng dẫn auth, cấu hình Gemini, chat/ frontend và báo cáo này.

Fixture AI dùng deadline 20 giây riêng để tiếp tục kiểm tra chặt việc hết hạn/lease. Test lệnh kết nối xác nhận default thật là 60 giây. Không nới các điều kiện validation, quyền truy cập, số thẻ, retry hoặc chống gửi trùng.

## Kết quả kiểm thử

| Kiểm tra | Kết quả |
|---|---|
| API cơ bản trực tiếp và `/api` qua Vite | Health/database, banners, products, brands, categories, category-offers đều 200 |
| Đọc API đồng thời | Trước sửa: 30/30 HTTP 200; sau sửa: 30/30 HTTP 200; tối đa 6 request đồng thời |
| Refresh không có cookie/CSRF | 403 đúng chính sách; không tính đây là lỗi kết nối |
| Login/refresh/me/logout qua frontend HTTP client thật | 200; refresh secret đổi, cookie refresh có path `/api/auth`, HttpOnly, CSRF hợp lệ |
| Backend auth + AI/chat | **272 test, 45 subtest đạt**, 7 PostgreSQL opt-in bỏ qua; 57,23 giây |
| Frontend HTTP/auth/AI và trang mua hàng | **154/154 test đạt** trong 6 tệp; 52,36 giây |
| Lint/build | Không có lỗi lint; hai cảnh báo admin có sẵn. Production build đạt, còn cảnh báo bundle lớn hơn 500 kB |

Hai regression refresh mô phỏng database lỗi trước/sau rotation. Bản cũ thất bại ở trường hợp database lỗi sau rotation (503); bản sửa trả 200 vì không còn truy vấn sau rotation. Trường hợp database lỗi trước rotation vẫn trả 503 đúng, giữ nguyên cookie và có thể thử lại sau khi database phục hồi. React không xóa phiên hoặc tự lặp request khi nhận 503.

## Lượt chatbot thực qua Vite và Supabase

Đã chạy module `frontend/src/services/api/client.js` và `frontend/src/lib/auth-api.js` thật từ Node, với cookie jar mô phỏng trình duyệt, gọi Vite 5173 → FastAPI 8000 → Gemini → Supabase. Đây là kiểm tra HTTP client thực; không phải điều khiển giao diện React trong trình duyệt. Component React được kiểm tra riêng bằng jsdom/HTTP giả lập.

Một tài khoản kiểm thử duy nhất được tạo riêng cho mỗi lượt; đăng nhập và refresh bằng API thật. Lượt thành công lấy trước một sản phẩm còn hàng từ `/products` rồi hỏi giá/thông số của đúng sản phẩm đó.

- `POST /conversations`: **201**.
- `POST .../ai-messages`: **200 Completed**, khoảng **62,443 giây** tính cả chuẩn bị/lưu database.
- Có văn bản AI và một thẻ đúng **OPPO A7 Pro 5G 6GB 256GB**, giá **12.990.000 đồng**, còn hàng.
- Đọc trực tiếp metadata của chính lượt thử trong Supabase xác nhận `Completed`, model `gemini-3.5-flash-lite`, usage **5.016 input + 201 output token**.
- GET trạng thái và lịch sử đều **200**, MessageId trùng với response ban đầu. POST lại cùng UUID trả **200** với chính các ID đã lưu, không tạo câu trả lời mới.
- Đã logout **200**, xóa chính xác **1 khách thử, 1 hội thoại thử, 3 tin nhắn thử**. File mật khẩu thử đã bị xóa. Không sửa tài khoản, sản phẩm hoặc tin nhắn của người dùng khác.

Các lượt thăm dò trước đó vẫn được giữ riêng: timeout ở 20/45 giây và một lượt ASUS dưới 20 triệu còn timeout ở ngân sách 60 giây. Đọc catalog trực tiếp cho bộ lọc này trả 0 sản phẩm thỏa điều kiện còn hàng. Khi timeout, API trạng thái vẫn đọc được `Failed`, đã lưu câu hỏi và không có câu trả lời AI; việc giao diện hiển thị “Chưa nhận được câu trả lời” tương ứng đúng trạng thái đó. Không biến các lượt thất bại này thành kết quả đạt.

Chưa khẳng định chatbot hết mọi timeout/quota hoặc đạt mục tiêu latency. Lượt thành công thực vẫn chậm; cần đánh giá tải/độ trễ riêng nếu dùng nhiều người đồng thời. Không tăng thời gian chờ thêm sau mức 60/75 giây trong lần sửa này.

## Vận hành sau sửa

Backend đã chạy lại ở cổng 8000 bằng `backend/scripts/run_dev.py`. Với auth memory, restart/reload làm mất phiên; đăng nhập lại trước khi thử chatbot.

```powershell
# Từ gốc dự án, khi cần tự khởi động backend (không chạy chồng lên cổng đang dùng)
.\.venv\Scripts\python.exe backend/scripts/run_dev.py

# Kiểm tra trực tiếp và qua Vite
Invoke-RestMethod http://127.0.0.1:8000/health/db
Invoke-RestMethod http://127.0.0.1:5173/api/health/db
```

Log local: `output/backend-api-fix.stdout.log` (HTTP) và `output/backend-api-fix.stderr.log` (startup, SQLSTATE, vòng Gemini). Chỉ dùng request ID để đối chiếu, không dán khóa/cookie vào log. Gemini greeting thành công không xác nhận Supabase, cookie refresh hoặc toàn bộ vòng công cụ.

Bằng chứng local trong `output/gemini-migration/`: `api-burst-before.json`, `api-burst-after.json`, `frontend-api-flow-report.json`, `frontend-api-flow-timeout.json`, `frontend-api-flow-timeout-45s.json`, `frontend-api-flow-no-stock-timeout-60s.json`. Các tệp này được Git bỏ qua.
