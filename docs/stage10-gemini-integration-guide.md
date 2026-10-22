# Giai đoạn 10 — Tích hợp Google Gemini

Đối chiếu ngày 22/10/2026 với `VieTech_AI_GiaiDoan10.docx` và mã nguồn của VieTech. Tài liệu Word là bản thiết kế tham khảo; trạng thái thực tế được ghi bên dưới.

## Cấu hình đang triển khai

- SDK: `google-genai==2.31.0`.
- Model đang dùng: `gemini-3.5-flash-lite` theo lựa chọn vận hành của dự án, sau khi đã thử kết nối thành công. `gemini-3.8-flash` vẫn được giữ để lựa chọn thủ công/thử nghiệm.
- API: Gemini Interactions, `store=false` cố định trong adapter, không sử dụng `previous_interaction_id`. Đây là phương án B trong tài liệu Word.
- Backend lưu lịch sử trong database VieTech. Trong một lượt nhiều vòng, adapter gửi lại đầy đủ bước gọi hàm, kết quả hàm và chữ ký suy luận. Các bước tạm này không được lưu vào tin nhắn hoặc trả cho khách.
- Mỗi bước `function_result` gửi cả `name` của hàm và `call_id` tương ứng. Đã kiểm tra thật chuỗi tìm kiếm bằng dữ liệu tổng hợp → nhận kết quả → `present_answer` trên Flash-Lite, ngoài kiểm tra câu chào.
- Không tự retry hoặc tự chuyển model trong adapter. Model dự phòng chỉ là cấu hình dành cho thử nghiệm có chủ đích.

Thiết lập khóa tại [Google AI Studio](https://aistudio.google.com/apikey). Chỉ điền khóa vào `backend/.env`; cấu hình mẫu trong `backend/.env.example` không chứa khóa:

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_FALLBACK_MODEL=gemini-3.8-flash
AI_TIMEOUT_SECONDS=60
AI_INPUT_MAX_CHARS=1000
AI_CONTEXT_MAX_TURNS=12
AI_MAX_OUTPUT_TOKENS=2048
AI_REQUESTS_PER_MINUTE=10
AI_MAX_ATTEMPTS=3
AI_MAX_TOOL_ROUNDS=4
AI_MAX_PRODUCTS=3
AI_RANKING_ENABLED=true
AI_BENCHMARK_TOKENS_PER_MINUTE=0
```

`AI_MAX_OUTPUT_TOKENS` dành cho đầu ra của model, bao gồm ngân sách suy luận theo API. Backend tiếp tục giới hạn câu trả lời công khai ở 5.000 ký tự và tối đa ba thẻ. `AI_BENCHMARK_TOKENS_PER_MINUTE=0` tắt ước lượng pacing; nếu cần, điền hạn mức TPM thực tế của dự án trong AI Studio. Không có một hạn mức Free cố định dùng chung cho mọi tài khoản.

Deadline website đã cập nhật lên 60 giây sau khi chẩn đoán được một lượt gọi công cụ trả kết quả sau 24,3 giây, vượt cấu hình cũ 20 giây. Lượt thử với ngân sách 45 giây có vòng đầu mất 25,7 giây và vòng trả lời cuối timeout với phần thời gian còn lại; luồng tư vấn cần ít nhất hai vòng model. Frontend chờ tối đa 75 giây cho mỗi HTTP request rồi kiểm tra trạng thái, không tự POST lại câu hỏi. Việc tăng ngân sách chờ không bảo đảm Google luôn phản hồi trong hạn hoặc tránh quota. Model, mức suy luận, cơ chế không retry và `store=false` giữ nguyên. Xem [báo cáo kết nối API](updates/2026-10-22-api-connectivity.md).

Biến môi trường tiến trình được ưu tiên, sau đó `backend/.env.local`, rồi `backend/.env`. Không tạo `.env.local` chỉ để thêm khóa AI vì file này có quy tắc database riêng. Khởi động lại backend sau khi sửa cấu hình. Không dùng biến `VITE_*` để chứa khóa.

## Cài và kiểm tra kết nối

Từ thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -X utf8 backend/scripts/check_gemini_connection.py
```

Hoặc từ thư mục `backend`:

```powershell
..\.venv\Scripts\python.exe -X utf8 -m app.cli.check_gemini
```

Có thể thử model khác và timeout riêng cho script mà không sửa cấu hình website:

```powershell
..\.venv\Scripts\python.exe -X utf8 -m app.cli.check_gemini --model gemini-3.8-flash --timeout 10
```

Script in mã HTTP khi Google từ chối yêu cầu, không in API key hoặc nội dung lỗi gốc. Đã xác nhận ngày 22/10/2026: khóa/model có thể đọc qua endpoint Google (HTTP 200), Flash-Lite trả lời thật thành công; Flash 3.8 có lần trả 503 hoặc timeout. Đây là kiểm tra kết nối, chưa phải benchmark 40 câu.

Script dùng cùng adapter với website, không import database. Thiếu khóa sẽ trả `ai_not_configured`, không gọi mạng. Chỉ xác nhận kết nối thành công khi thực sự nhận được câu chào từ Gemini; kiểm thử giả lập không thay cho bước này.

## Luồng xử lý và kiểm soát

`AiChatService` kiểm tra role Customer, quyền sở hữu hội thoại, chế độ AI, trạng thái Open và giới hạn gửi. Request được lưu Pending với UUID và lease trước khi gọi model; connection/transaction được trả về pool trong lúc chờ mạng. Cùng UUID đã hoàn thành được replay; request mới không chạy chồng lên lượt Pending khác.

Gemini đề nghị gọi một trong bốn hàm được khai báo: `search_products`, `get_product`, `list_offers`, `present_answer`. Backend kiểm tra schema và chỉ gọi các service công khai được cho phép. Không cung cấp SQL, công cụ sửa giá, đơn hàng hoặc thanh toán. Giá, biến thể, tồn kho và thẻ được kiểm tra lại trước khi hoàn tất lượt nguyên tử.

Từ [nâng cấp tư vấn theo catalog](stage10-ai-advisor-upgrade.md):

- System instruction gồm ba phần: persona `app/prompts/vietech_ai.py`, quy ước backend `app/prompts/vietech_ai_protocol.py`, và dữ liệu của lượt (phân tích ý định/ngữ cảnh, kết quả tìm kiếm đã xếp hạng chạy sẵn, sản phẩm được tham chiếu).
- `present_answer` có thêm `message`. Backend chỉ hiển thị `message` khi mọi số liệu có căn cứ; nếu không thì dùng văn bản của backend.
- Adapter Interactions và `store=false` không đổi.

Adapter chuyển 429 thành 503 `ai_quota_exceeded`, đọc `Retry-After` hoặc `google.rpc.RetryInfo`. Timeout/mất kết nối trả `ai_unavailable`; sai quyền/key/model trả lỗi cấu hình đã ẩn chi tiết nhà cung cấp. Thiếu khóa không ngăn API bán hàng khởi động.

## Phạm vi so với tài liệu Word

Việc chuyển nhà cung cấp sử dụng lại API chat, UUID chống trùng, công cụ catalog, ranking và giao diện hiện tại. Theo lựa chọn đã có của dự án, AI không có nút chuyển sang nhân viên; chat nhân viên là kênh riêng. Cá nhân hóa hiện tự lấy hãng/danh mục từ wishlist và đơn đã giao, chưa có hồ sơ sở thích và UI opt-in như bản thiết kế Word. Hai phần khác biệt này chưa được xem là đã triển khai theo tài liệu Word.

Không cần migration đổi nhà cung cấp: tái sử dụng migration chống trùng `d7a1e5c9b304`. Database mới vẫn phải áp dụng migration theo [hướng dẫn AI chat](stage10-ai-chat.md).

## Kiểm thử và nghiệm thu

Chạy test SDK, service và HTTP từ `backend`:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_ai_gemini.py tests/test_ai_chat.py tests/test_ai_chat_http.py tests/test_ai_grounded.py tests/test_ai_recommendation.py tests/test_ai_personalization.py tests/test_ai_advisor.py tests/test_ai_migration.py tests/test_ai_benchmark.py -q
```

Benchmark [10.7](stage10-ai-evaluation.md) dùng bộ kết quả riêng `output/stage10-gemini-benchmark/`. Chưa có kết quả Gemini thật thì phải ghi “chưa đo”, không chuyển số liệu của một hệ thống khác thành kết quả Gemini. Khóa và luồng công cụ đã được kiểm tra thật; vẫn cần kiểm thử luồng trình duyệt → backend → Gemini trên database đã migrate.

Đã kiểm tra thêm 10 ca tư vấn qua HTTP/JWT → service/catalog → Gemini thật trên SQLite riêng: sáu ca chính đạt, bốn ca còn lại đạt sau khi chờ hạn mức Google. Có quan sát timeout/quota trong các lượt thử, nên chưa xác nhận độ ổn định khi gọi liên tục. Kết quả chi tiết và phạm vi kiểm tra ở [báo cáo luồng tư vấn](stage10-ai-evaluation.md#kiểm-tra-luồng-tư-vấn-qua-http-với-gemini-thật). Script kết nối phía trên vẫn chỉ kiểm tra câu chào.

Tham khảo chính thức: [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview), [model](https://ai.google.dev/gemini-api/docs/models), [function calling](https://ai.google.dev/gemini-api/docs/function-calling), [quota](https://ai.google.dev/gemini-api/docs/rate-limits), [SDK 2.31.0](https://pypi.org/project/google-genai/2.31.0/).
