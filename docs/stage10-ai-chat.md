# Bước 10.2 — API chat AI

Cập nhật ngày 22/10/2026: dùng Gemini Interactions API, model trong `GEMINI_MODEL` (mặc định `gemini-3.5-flash-lite`, đã thử kết nối thành công). `GEMINI_FALLBACK_MODEL` chỉ được khai báo, chưa tự chuyển model khi lỗi. Xem [cấu hình và kiểm tra kết nối](stage10-gemini-integration-guide.md).

Cập nhật tiếp theo: [bước 10.3](stage10-ai-tools.md) đã mở rộng pipeline với công cụ catalog/giá/ưu đãi và thẻ sản phẩm. Các mô tả phạm vi 10.2 bên dưới ghi nhận mốc trước khi thêm công cụ.

## Cấu hình

Xem `backend/.env.example`. SDK `google-genai==2.31.0` gọi `/v1beta/interactions` trên `generativelanguage.googleapis.com`. Adapter cố định `store=false`, gửi lại đầy đủ các bước trong lượt và không dùng `previous_interaction_id`.

Giới hạn mặc định: input 1.000 ký tự, tối đa 12 cặp hỏi–đáp đã hoàn thành (thêm ngân sách lịch sử 10.000 ký tự), 2.048 token đầu ra mỗi lần gọi, deadline 60 giây cho cả vòng suy luận/công cụ, 10 yêu cầu/phút/khách, tối đa 3 lần xử lý cho một request ID. Các lần đọc lại kết quả/Pending không tiêu thụ thêm lượt gọi model.

Rate limit/cooldown dùng StateStore đang cấu hình của Auth: memory cho development/test, Redis cho production. HTTP 429 từ Gemini được chuyển thành 503 `ai_quota_exceeded` và `Retry-After`; yêu cầu mới cũng tôn trọng cooldown của model. Không retry tự động trong SDK.

## Migration

Đã tạo `d7a1e5c9b304`, sau head `c3a9f5e7d206`, thêm 3 chỉ mục chống trùng trên `Messages.Metadata`. **Đã áp dụng lên database phát triển ngày 22/10/2026** bằng `backend/scripts/migrate_stage10.py`: preflight chỉ đọc (0 bản ghi trùng) và thử trong schema tạm có rollback, sau đó một transaction nâng `93e7a2b0c518` → `a6d2e8f4b190` → `b2f8c6d4e901` → `c3a9f5e7d206` → `d7a1e5c9b304`. Ba chỉ mục đã có, số dòng các bảng được kiểm tra không đổi. Báo cáo: `output/stage10-migration-preflight-applied.json`. Với database khác, vẫn đối chiếu revision và kiểm tra dữ liệu trùng trước; không stamp hoặc xóa lịch sử để vượt lỗi unique index.

Lệnh kiểm tra graph offline, chạy trong `backend`:

```powershell
..\.venv\Scripts\python.exe -m alembic heads
```

Sau khi đã chọn đúng database và đối chiếu lịch sử migration, áp dụng bằng Alembic theo quy trình dự án (`alembic upgrade head`). Không chạy lệnh đó trên database dùng chung khi chưa kiểm tra đích/revision.

## Thử bằng Swagger

1. Chạy backend và mở `http://127.0.0.1:8000/docs`.
2. Đăng nhập tài khoản Customer; đưa access token vào nút Authorize.
3. Gọi `POST /conversations` với `{"Mode":"AI"}` và lấy ConversationId. Nếu đang có Staff Open, dùng API close trước khi chuyển kênh.
4. Gọi `POST /conversations/{conversation_id}/ai-messages` với body:

```json
{
  "ClientRequestId": "e8609ad1-3a5c-4d63-89e0-2adbc88a1f1e",
  "MessageType": "Text",
  "Content": "Tôi cần laptop học lập trình, hãy hỏi thêm để hiểu nhu cầu của tôi"
}
```

Mỗi câu hỏi mới dùng UUID mới. Retry cùng câu hỏi giữ nguyên UUID và nội dung. Completed trả 200 cùng tin khách và `AiMessages`; duplicate đang xử lý trả 202 Pending. Đọc trạng thái qua `GET /conversations/{conversation_id}/ai-messages/{request_id}`; Failed được retry theo giới hạn cấu hình. Retry Completed vẫn đọc lại được sau khi hội thoại đóng.

Khách có thể dừng bằng `POST /conversations/{conversation_id}/ai-messages/{request_id}/cancel`, body `{"Content":"nội dung câu hỏi gốc"}`. Trạng thái `Cancelled` là kết thúc: gửi lại cùng UUID chỉ đọc trạng thái, không khởi động model. Câu hỏi vẫn được giữ trong lịch sử, không thêm tin AI/thẻ. Lệnh dừng dùng cùng khóa hội thoại với gửi/hoàn tất, có thể đến trước POST gốc; trường hợp này vẫn lưu câu hỏi đã dừng để POST đến muộn không khởi động lại. Nếu câu trả lời đã được lưu trước khi dừng, endpoint trả lại `Completed` và kết quả đó. Dừng không bị khóa bởi cooldown nhà cung cấp.

## Cách lưu và phục hồi

Chuẩn bị lượt: kiểm tra quyền/chế độ, khóa hội thoại, lưu Pending + lease bằng transaction ngắn. Sau commit, đóng/reset Session (kể cả transaction đọc từ xác thực) trước khi gọi Gemini. Lưu kết quả: mở transaction mới, kiểm tra lại tài khoản/hội thoại và lease, ghi tin AI + trạng thái Completed nguyên tử. Lỗi tích hợp chuyển Pending sang Failed. Lease tối thiểu 120 giây; khi worker chết, request sau có thể thu hồi lease hết hạn. Worker cũ không thể hoàn tất sau khi lease được thay thế.

Kiểm tra trạng thái/lease trước mỗi vòng model, mỗi lần đọc công cụ và khi hoàn tất. Khi `Cancelled`, worker cũ không được gọi vòng sửa/tra cứu kế tiếp hoặc lưu câu trả lời. Khách có thể gửi câu hỏi mới ngay sau khi server xác nhận dừng. Không cần migration mới vì trạng thái được lưu trong metadata JSON và index đang xử lý chỉ áp dụng cho `Pending`.

Endpoint chat nhân viên giữ nguyên. API AI dùng schema riêng để client không tự gán SenderType/lease/metadata. Customer không đọc được lịch sử/trạng thái hội thoại của người khác.

## Giới hạn hiện tại

Pipeline hiện đã có [công cụ catalog và thẻ sản phẩm](stage10-ai-tools.md), [giao diện khách hàng](stage10-ai-frontend.md), cá nhân hóa tự động và ranking. Chưa có bằng chứng chạy xuyên suốt với Gemini thật nếu chưa cấu hình khóa hợp lệ.

Prompt chỉ nhận hội thoại cần thiết, không nhận hồ sơ/email/địa chỉ từ bảng User. Có che email/số điện thoại nhận diện được trong văn bản; đây không phải công cụ nhận diện đầy đủ mọi dữ liệu cá nhân trong nội dung tự do.

Hiện API trả câu trả lời hoàn chỉnh, chưa streaming từng phần. Nút dừng hủy lượt ở ứng dụng và chặn việc lưu/hiển thị kết quả đến muộn; yêu cầu đã phát đi tới Google có thể vẫn xử lý xong ở phía nhà cung cấp. Không cam kết hủy được việc tính token của yêu cầu đó.

## Kiểm thử

```powershell
Set-Location E:\vitech-ecommerce\backend
..\.venv\Scripts\python.exe -m pytest tests/test_ai_chat.py tests/test_ai_gemini.py tests/test_ai_chat_http.py tests/test_ai_migration.py -q
```

Các test dùng SQLite riêng, FakeChatModel, HTTP MockTransport và JWT đăng nhập thật trong môi trường test. Kiểm tra quyền, lịch sử, không giữ connection khi đợi AI, retry/lease, unique index, lỗi quota và đường dẫn SDK. Migration được biên dịch bằng PostgreSQL dialect offline. Những kiểm tra này không thay thế thử nghiệm cạnh tranh khóa dòng trên PostgreSQL thật.

Kết quả kiểm thử sau khi chuyển Gemini được tổng hợp tại [10.7](stage10-ai-evaluation.md). Các số kiểm thử lịch sử không phải bằng chứng kết nối Gemini thật.
