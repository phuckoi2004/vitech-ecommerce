# Bước 10.3 — AI đọc catalog, giá và ưu đãi

Mã nguồn ngày 22/10/2026 mở rộng API chat ở bước 10.2. Giao diện “Sắp ra mắt” thuộc bước 10.4 và chưa thay đổi trong bước này.

## Luồng xử lý

1. Customer gửi câu hỏi qua `POST /conversations/{conversation_id}/ai-messages` như bước 10.2.
2. Gemini chọn công cụ chỉ đọc; backend kiểm tra tên/tham số, quyền hội thoại, trạng thái và lease.
3. Công cụ lấy dữ liệu qua ProductService/CategoryService/BrandService/PricingService trong transaction ngắn. Session được đóng/reset trước mỗi lần gọi model.
4. Gemini kết thúc bằng `present_answer`: ý định, ID sản phẩm/phiên bản và tên thông số cần đối chiếu.
5. Backend đọc lại dữ liệu quan trọng và dựng nội dung/thẻ, rồi lưu cùng trạng thái Completed trong một transaction.

`present_answer` không phải công cụ ghi dữ liệu kinh doanh. Model không được sửa giỏ hàng, đơn hàng, giá, tồn kho hoặc quyền. Phần văn bản về sản phẩm/giá/thông số/ưu đãi được dựng từ dữ liệu chuẩn; model không được cung cấp giá hoặc thông số bằng lời tự do.

## Công cụ và giới hạn

| Công cụ | Nguồn dữ liệu / kiểm tra |
|---|---|
| `search_products` | ProductService.search_products; danh mục/hãng map từ dữ liệu công khai đang hoạt động |
| `get_product` | ProductService.get_product_detail/by_slug; hỗ trợ `rank=2` từ thẻ trong hội thoại này |
| `list_offers` | PricingService.public_coupons; tùy chọn scope product_id |
| `present_answer` | Schema ý định/lựa chọn; chỉ nhận ID đã được công cụ trả trong lượt hiện tại |

`AI_MAX_TOOL_ROUNDS=4`, tối đa 6 lượt thực thi công cụ, tối đa hai call trong một phản hồi (thực thi tuần tự), tối đa 5 lần gọi model theo số vòng. Phản hồi cuối sau công cụ vòng thứ tư vẫn được nhận. Một lần sửa schema kết quả cuối được phép trong giới hạn vòng/thời gian hiện có. SDK dùng `tool_choice=required`, `parallel_tool_calls=False`, `max_retries=0`.

`AI_TIMEOUT_SECONDS` làm deadline cho chu trình: truyền thời gian còn lại cho SDK và kiểm tra lại sau mỗi lần gọi/công cụ. Thời gian HTTP còn phụ thuộc các pha kết nối/đọc của SDK; phản hồi về sau deadline không được lưu thành công.

Mỗi tool result tối đa 14.000 ký tự, tổng 24.000 ký tự. Lịch sử tối đa 12 cặp hỏi–đáp và 10.000 ký tự, gồm tham chiếu sản phẩm. Mỗi câu hỏi có thể tiêu thụ nhiều request/token Gemini; quota và cooldown ở bước 10.2 tiếp tục áp dụng.

Search lấy tối đa 20 ứng viên qua service. Từ bước 10.6, ứng viên hợp lệ được chấm điểm và chỉ 5 lựa chọn đầu được trả cho model (trước đây 8, chưa xếp hạng); xem [xếp hạng gợi ý](stage10-ai-recommendation.md). Các cụm nhu cầu thông dụng như “học lập trình”, “pin tốt” không được dùng riêng làm từ khóa bắt buộc khớp tên.

## Ngân sách, phiên bản và tính đúng đắn

- Backend nhận diện các dạng trần ngân sách phổ biến: “dưới 20 triệu”, “không quá 20,5 triệu”, “20tr500”, “ngân sách 20.000.000 đồng”. Giá từ tool phải nằm trong trần này; model không được tự tăng trần. Các câu mơ hồ vẫn cần làm rõ, không coi parser là bộ hiểu đầy đủ mọi cách diễn đạt.
- Hãng bắt buộc và danh mục được đối chiếu với dữ liệu thật. “Ưu tiên ASUS nhưng Lenovo cũng được” không bị ép thành chỉ ASUS; “chỉ ASUS” vẫn được giữ khi có ưu tiên mềm khác.
- Kiểm tra giá và tồn trên **cùng biến thể**. Sản phẩm có bản 15 triệu đã hết hàng và bản còn hàng 25 triệu không tạo thẻ phù hợp ngân sách 20 triệu.
- Dùng SalePrice của ProductService/PricingService, gồm ưu đãi tự động hợp lệ. Không cộng coupon vào giá thẻ khi chưa có quote giỏ hàng.
- ProductId/variant ID lạ hoặc thông số không thuộc dữ liệu tool bị từ chối. Thông số công khai dạng lồng nhau được làm phẳng có giới hạn, giữ nguyên giá trị, không tự suy ra FPS/chất lượng camera/thời lượng pin.
- Đọc lại giá/tồn/trạng thái trước khi lưu đáp án. Nếu thay đổi khiến lựa chọn không còn hợp lệ thì bỏ thẻ và thông báo theo dữ liệu hiện tại.
- Có thể so sánh từ hai đến ba sản phẩm; giới hạn số thẻ không làm mất thông tin đối chiếu. Mỗi sản phẩm hiển thị tối đa bốn thông số được chọn từ dữ liệu chuẩn và số tháng bảo hành.
- Coupon được tra cứu lại khi dựng kết quả: hiển thị mức giảm, đơn tối thiểu, mức giảm tối đa nếu có, hạn và giới hạn lượt. Việc thực sự áp dụng theo khách/giỏ hàng được kiểm tra ở checkout.

## Response và lưu lịch sử

`AiMessages` bắt đầu bằng một tin Text, sau đó tối đa `AI_MAX_PRODUCTS` (1–3) tin Product. Metadata thẻ gồm ProductId, ProductVariantId, ProductName, Slug, VariantName, Price (giá hiệu lực), OriginalPrice, ImageUrl, InStock, Rank, SnapshotAt và AiAnswerMessageId.

Tin khách lưu AiCardMessageIds/AiConstraints nội bộ; tin Text AI lưu ProductReferences có thứ tự. Tham chiếu “máy thứ hai” lấy theo danh sách đã lưu trong hội thoại, sau đó đọc lại ProductService. Không dò tên trong văn bản và không đọc hội thoại của người khác.

Giá trong lịch sử/replay là snapshot lúc tạo đáp án, không phải báo giá mới. Trang sản phẩm/giỏ hàng cung cấp dữ liệu mới nhất. Unique index AiReply của bước 10.2 áp dụng liên kết question → tin Text; thẻ liên kết về tin Text bằng AiAnswerMessageId để không vi phạm ràng buộc.

Không thêm bảng/cột hoặc migration mới ở bước 10.3. Migration chống trùng `d7a1e5c9b304` của 10.2 vẫn chưa được tự áp dụng lên database dùng chung.

## Thử trên Swagger

Khởi động lại backend, đăng nhập Customer và Authorize. Tạo/lấy hội thoại AI bằng `POST /conversations` với `{"Mode":"AI"}`. Gửi mỗi câu dưới đây qua endpoint ai-messages, mỗi câu hỏi mới dùng ClientRequestId mới:

```json
{
  "ClientRequestId": "a6e9c282-e9bc-45c7-9868-3f65a20cf91a",
  "Content": "Laptop ASUS dưới 20 triệu để học lập trình"
}
```

Sau khi có thẻ, thử “Máy thứ hai có RAM bao nhiêu?” nếu lượt trước có ít nhất hai sản phẩm. Các câu khác: “So sánh hai mẫu vừa nói”, “Có mã giảm giá nào hôm nay?”. Kết quả phụ thuộc catalog hiện có; không có sản phẩm phù hợp thì không tạo thẻ giả.

Nếu đang có hội thoại Staff Open, đóng phiên hiện tại qua API nghiệp vụ trước khi chuyển AI. Retry cùng câu hỏi giữ nguyên ClientRequestId và nội dung; đọc trạng thái qua endpoint GET ở bước 10.2.

## Kiểm thử

Test mới: `backend/tests/test_ai_grounded.py`, cùng test adapter/schema/lịch sử ở bước 10.2. Dùng SQLite cô lập, real catalog/pricing services, ScriptedModel và HTTP MockTransport. Có kiểm tra thẻ qua HTTP, retry cùng ID, rollback toàn bộ Text/thẻ khi lỗi, ngân sách/hãng/giá/tồn/khuyến mãi thay đổi, so sánh và tham chiếu thứ tự, công cụ lạ, UUID/variant/spec giả, giới hạn vòng và deadline.

## Kiểm soát tương thích Gemini

Adapter sử dụng `store=false`. `AiChatService` chuyển nguyên các bước Gemini và chữ ký suy luận qua các vòng gọi hàm; dữ liệu đó chỉ tồn tại trong lượt xử lý, không vào database hoặc response Customer. Tối đa bốn vòng tra cứu rồi chỉ cho `present_answer`; backend tiếp tục xác thực JSON, ID, biến thể và thông số.

Các ca hồi quy kiểm tra danh mục tiếng Anh, phân biệt hãng bắt buộc/ưu tiên mềm, tham chiếu theo thứ tự thẻ, đọc nhiều sản phẩm trong một lần, output sai schema được sửa một lần, giới hạn tool/deadline và rollback Text/thẻ. `test_ai_gemini.py` bổ sung kiểm tra SDK thật qua HTTP giả lập và cả luồng SDK → orchestrator → catalog SQLite → thẻ đã xác nhận.

Kết nối thật với Gemini 3.5 Flash-Lite đã thành công qua adapter; model chính 3.8 Flash có lần trả 503 hoặc timeout. Chưa có kiểm thử xuyên suốt trình duyệt → backend → Gemini trên database thật. Xem [kiểm thử 10.7](stage10-ai-evaluation.md).

## Sửa bộ lọc sau khi chuyển Gemini

- Hãng bị loại được giữ qua câu hỏi nối tiếp. Khi khách nêu rõ muốn dùng lại hãng đó, yêu cầu mới thay thế điều kiện cũ.
- Nhận diện cả giá tối thiểu và tối đa, ví dụ “từ 18 đến 20 triệu”, “18–20 triệu”, “ít nhất 18tr500”. Chuỗi số sai định dạng không làm lỗi server.
- Trước khi lấy tối đa 20 ứng viên, truy vấn AI yêu cầu **cùng một biến thể** đang bán, còn hàng và có giá sau khuyến mãi nằm trong khoảng yêu cầu; hãng bị loại cũng được lọc trước giới hạn. Không dùng giá thấp nhất của một biến thể rẻ hơn nhưng không phù hợp để loại bỏ cả sản phẩm.
- Bộ lọc của `search_products` được giữ khi `get_product` đọc lại chi tiết trong cùng lượt; không tự đổi sang phiên bản rẻ hơn nằm ngoài khoảng giá.
- Lượt nối tiếp giữ khoảng giá. Khách nêu ngân sách mới thấp hơn hoặc bỏ giới hạn thì điều kiện mới được áp dụng.

Tùy chọn `match_variant_price` của service/repository chỉ dùng nội bộ cho AI. Trang danh sách sản phẩm tiếp tục lọc theo giá “từ” như contract hiện có. Các tình huống trên có test hồi quy trong `test_ai_grounded.py`.
