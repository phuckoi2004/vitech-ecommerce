# Sửa lỗi chatbot từ kiểm thử nghiệm thu ngày 29/10/2026

Các sửa đổi xử lý sáu ca R09, N03, AR03, CT02, CT03 và CT04 của báo cáo
`output/ai-chat-acceptance/AI_CHAT_FINAL_REPORT.md`.

- “ASUS hoặc Lenovo” là tập hãng được phép. Chỉ các cụm như “ưu tiên” hoặc “không bắt buộc” mới tạo ưu tiên mềm. Tập hãng được lưu trong Metadata hội thoại hiện có, giữ qua câu hỏi nối tiếp và tải lại.
- Yêu cầu chống ồn phải có bằng chứng ANC trong catalog. Chống ồn micro/đàm thoại, cách âm thụ động và dòng thời lượng pin khi tắt ANC không tự xác nhận tính năng này. Thiếu bằng chứng thì sản phẩm không vượt bộ lọc.
- “Laptop gaming” yêu cầu nhóm gaming hoặc bằng chứng GPU rời; nhu cầu chung “chơi game” vẫn được chấm theo các tiêu chí sử dụng hiện có.
- Hỏi giá hoặc khả năng cung cấp Dell XPS 13 phải tra đúng tên/model trước. Không tìm thấy thì báo rõ và yêu cầu kiểm tra tên, thay vì gợi ý Dell khác như thể đó là XPS.
- “Chỉ lấy máy RAM từ 16GB” là cập nhật bộ lọc. Câu tiếp theo giữ hãng, ngân sách và mức RAM đã chọn.
- Câu hỏi chip mới hơn được trả lời bằng thế hệ Apple M ghi trong thông số CPU, kể cả khi trường CPU chứa thêm mô tả số lõi. Không suy hiệu năng tổng thể hoặc so thế hệ giữa các dòng chip khác nhau từ số model.
- “LG đang bán trong VieTech” được hiểu là phạm vi tìm màn hình LG. Khi có nhiều model, hỏi chọn model cụ thể. Câu tiếp “Nếu muốn xuất 4K144Hz thì sao?” cập nhật yêu cầu hình ảnh, không trở thành tên màn hình. Câu trả lời model sau đó giữ đúng laptop và chế độ 4K144Hz.

Không thêm bảng, cột, migration hoặc thay đổi giá, tồn kho và dữ liệu sản phẩm. Các slot mới chỉ là khóa trong Metadata JSON đã có của hội thoại.

Kiểm thử hồi quy tại `backend/tests/test_ai_chat_acceptance_regressions.py` sử dụng SQLite độc lập và provider giả lập. Các lần thử HTTP với catalog đã chụp và Gemini thật lưu riêng tại `output/ai-chat-fixes/`, giữ nguyên báo cáo nghiệm thu cũ. Timeout của Gemini và câu trả lời dự phòng được ghi riêng; không coi fallback là một lần sinh nội dung Gemini thành công.

Phần thông số 4K/Hz còn thiếu cần chứng cứ hãng cho từng cổng của đúng model. Dữ liệu LG 27G850A và khả năng DisplayPort của Acer Swift Air đã nằm trong đợt bổ sung trước. Sửa logic hội thoại không bổ sung các giới hạn Hz chưa được hãng công bố.

Ngày 30/10/2026 đã bổ sung thêm 6 thuộc tính cổng vào database thật sau khi hoàn thành đợt sửa logic này. Xem [dữ liệu cổng đợt 4](catalog-port-data-round4.md) để biết chính xác sản phẩm, bằng chứng, receipt và thay đổi kết quả Compatibility. Việc không ghi database trong báo cáo kiểm thử logic ban đầu vẫn được giữ đúng theo phạm vi của lần chạy đó.

## Cách trả lời khách hàng — 30/10/2026

Theo yêu cầu của chủ dự án, bỏ đoạn lưu ý tự động và câu kết lặp về giá, tồn kho, tiêu chí đánh giá; không thêm câu thay thế “Đánh giá dựa trên cấu hình được công bố…”. Bảng so sánh không tự nhắc thời lượng pin, số MP, kiểm thử phần mềm hoặc lý do chọn màu chỉ vì những trường đó xuất hiện trong thông số. Các đoạn lưu ý cố định của bảng so sánh đã lưu trước đây cũng được ẩn trên giao diện, không sửa nội dung hội thoại trong database.

Thông số thiếu vẫn hiện ở đúng ô và hạn chế của từng sản phẩm. Khi khách hỏi trực tiếp về chạy phần mềm cụ thể, số giờ dùng pin hoặc chất lượng ảnh thực tế, chỉ nêu giới hạn có liên quan. Kết quả tương thích tiếp tục giữ nguyên điều kiện cáp, chế độ tín hiệu và thông tin còn thiếu ảnh hưởng đến kết luận.

Hướng dẫn cho AI và các câu dự phòng dùng “thông tin sản phẩm”, “thông số”, “phiên bản”. Bộ kiểm tra câu trả lời chặn tên bảng và trường nội bộ như `catalog`, `Specifications`, `ProductVariants`, `CostPrice`; câu vi phạm được thay bằng nội dung dựng từ thông tin sản phẩm đã xác minh. Các công nghệ phục vụ nhu cầu lập trình của khách như PostgreSQL vẫn có thể được nhắc đúng ngữ cảnh.

Đợt sửa lời tư vấn này không có migration, không ghi database thật và không thay đổi quy tắc đánh giá tương thích. Kiểm thử lời tư vấn mới nằm ở `backend/tests/test_ai_customer_wording.py`; log kiểm thử và build lưu trong `output/ai-customer-wording/`.

Xác minh: 764 ca backend đạt, 7 ca bỏ qua, 45 subtest đạt; 67 ca giao diện chat đạt. Build frontend thành công; lint không có lỗi, còn 2 cảnh báo admin có sẵn. Không gọi Gemini thật trong đợt kiểm thử lời tư vấn này.

## Không đếm tiêu chí so sánh thành sản phẩm — 30/10/2026

Câu “So sánh iPhone 17 Pro và Samsung Galaxy S26 Ultra về camera, pin và hiệu năng.” từng bị tách thành 4 mục do kiểm tra số lượng trước khi bỏ phần tiêu chí. Bộ xử lý nay tách phần “về/theo …” và danh sách tiêu chí đứng trước “của/giữa …” trước khi đếm tên sản phẩm. Giới hạn 3 sản phẩm giữ nguyên; 2 hoặc 3 tên kèm nhiều tiêu chí không bị hỏi lại vì vượt giới hạn.

Đã tái hiện 6 trường hợp lỗi trước khi sửa và bổ sung 7 ca hồi quy trong `backend/tests/test_ai_comparison.py`, gồm câu gốc, dấu hai chấm, tiêu chí đứng trước tên mẫu, 3 mẫu và 4 mẫu thực sự. Tổng bộ kiểm thử liên quan: **334 passed**. Kiểm tra thêm đúng câu khách gửi bằng các dịch vụ sản phẩm hiện có trên bản chụp SQLite chỉ đọc: nhận đúng iPhone 17 Pro 256GB và Samsung Galaxy S26 Ultra 5G 12GB 256GB, có các hàng camera, pin, CPU, không hỏi lại. Bằng chứng tại `output/ai-comparison-criteria-fix/`; không ghi database thật hoặc gọi Gemini.

## Tự chọn sản phẩm rồi so sánh — 30/10/2026

Câu “Hãy chọn 3 laptop dưới 25 triệu rồi so sánh CPU, RAM, SSD, màn hình và giá.” cần tìm sản phẩm trước khi dựng bảng. Trước đây bộ xử lý coi danh sách tiêu chí là danh sách tên sản phẩm, đồng thời từ “màn hình” có thể ghi đè loại hàng laptop. Luồng mới giữ loại hàng theo phần yêu cầu lựa chọn và số lượng đã nêu; chỉ dùng các tiêu chí để so sánh.

Luồng này dùng tìm kiếm, lọc tồn kho, ngân sách, hãng, RAM/SSD và xếp hạng hiện có. Mỗi mẫu khóa một phiên bản đáp ứng điều kiện rồi dựng bảng bằng cơ chế so sánh hiện có, không cần một lượt sinh nội dung Gemini. Giá và tồn kho được kiểm tra lại trước khi trả kết quả; không áp dụng cách lọc này cho các mẫu khách đã chỉ định rõ trong một phép so sánh thông thường. Nếu chỉ có 2 mẫu trong số 3 mẫu yêu cầu thì so sánh 2 mẫu và nói rõ; có 0–1 mẫu thì báo thiếu lựa chọn, không nới điều kiện. Giới hạn 3 cột vẫn áp dụng khi thực sự yêu cầu 4 mẫu.

Kiểm thử mới: `backend/tests/test_ai_select_compare.py`. Đã kiểm tra đúng câu khách gửi trên bản chụp dữ liệu sản phẩm ở chế độ SQLite chỉ đọc: chọn đúng 3 laptop còn hàng, giá dưới 25 triệu, có CPU/RAM/SSD/màn hình và giá trong bảng. Bằng chứng ở `output/ai-select-compare-fix/frozen-catalog-proof.json`. Đợt này chỉ sửa code, không ghi database thật, không thêm bảng/cột hoặc migration; cờ phân luồng mới chỉ tồn tại trong bộ nhớ khi xử lý câu hỏi.

Xác minh cuối: **788 passed, 7 skipped, 45 subtests passed**, gồm 17 ca mới cho luồng tự chọn rồi so sánh; log và JUnit tại `output/ai-select-compare-fix/backend-verified-tests.*`. Câu so sánh iPhone–Samsung trước đó cũng được chạy lại thành công trên bản chụp chỉ đọc.

## Lời tư vấn đi thẳng vào sản phẩm — 30/10/2026

Theo yêu cầu mới, bỏ câu mở đầu “Mình đã đối chiếu các phiên bản sau bằng dữ liệu hiện tại của VieTech”. Phần trả lời nay bắt đầu bằng “So sánh các mẫu sau”, không kể nguồn hay quá trình tra cứu. Giao diện bỏ mức phần trăm hoàn thiện thông tin; các nhãn dùng “Nhận xét”, “Điểm mạnh”, “Điểm cần cân nhắc”, “Chưa rõ” hoặc “Chưa thể xác nhận” theo đúng trường hợp.

Quy tắc diễn đạt áp dụng tại ranh giới trả kết quả của `AiTools.finish`, gồm nội dung chữ và các trường giải thích trong bảng so sánh/tương thích. Bộ kiểm tra câu trả lời chặn lời kể quá trình xử lý do mô hình tự thêm. Phần hiển thị hội thoại cũ cũng áp dụng cách nói mới, không ghi lại lịch sử đã lưu.

Không đổi thuật toán xếp hạng, trạng thái tương thích, điều kiện cáp, phủ định khả năng xuất hình, giới hạn Hz/độ phân giải, ID, đường dẫn, giá hoặc lượng hàng. Chẳng hạn “USB-C chỉ truyền dữ liệu, không xuất hình” hiển thị thành “USB-C chỉ truyền tệp, không xuất hình”; kết quả chưa thể xác nhận vẫn giữ trạng thái `unknown`. Không có migration hoặc thao tác ghi vào database thật trong đợt sửa này. Log kiểm thử/build ở `output/ai-direct-wording/`.

Xác minh cuối: **798 ca backend đạt, 7 ca bỏ qua, 45 subtest đạt; 75 ca giao diện chat đạt**. Build thành công, lint không có lỗi (2 cảnh báo admin có sẵn). Kiểm thử bao gồm câu mở đầu cũ, bảng đã lưu, trường hợp thiếu thông số, giới hạn 4K/Hz, cổng chỉ truyền tệp và việc giữ nguyên cấu trúc Markdown.

## Bỏ câu kết chọn mẫu mặc định — 30/10/2026

Theo yêu cầu mới, khi chưa có đề xuất cụ thể thì để trống `Recommendation`, không thêm câu kết mặc định hoặc câu thay thế. Giao diện ẩn cả tiêu đề gợi ý nếu phần này trống. Các phiên bản của câu kết đã lưu trước đây cũng bị loại khỏi phần hiển thị. Gợi ý có lý do cụ thể, thứ tự sản phẩm, thông số và trạng thái tương thích được giữ nguyên. Kiểm thử/log đợt này ở `output/ai-remove-default-recommendation/`.

## Phân biệt câu hỏi về độ chính xác với yêu cầu lập bảng — 30/10/2026

Câu “Nếu hai sản phẩm thiếu thông số pin hoặc GPU, bạn có thể so sánh chính xác được không?” trước đây bị hiểu là yêu cầu chọn 2 sản phẩm từ danh sách 3 mẫu. Nhánh `comparison_guidance` nay nhận diện câu hỏi về cách so sánh khi thiếu thông số trước khi đọc số lượng hoặc chọn sản phẩm.

Trả lời trực tiếp bằng các mục có thể so sánh và cách ghi “Chưa rõ” cho mục còn thiếu. Không tạo bảng/thẻ mới, không hỏi chọn 2 hoặc 3 mẫu, không cần gọi mô hình. Các slot tìm kiếm trước đó được giữ nguyên để câu hỏi tiếp theo tiếp tục đúng danh sách, ngân sách, hãng và RAM đã chọn. Yêu cầu thực sự lập bảng vẫn dùng luồng so sánh thông thường, gồm cả giới hạn số cột và việc hỏi rõ mẫu khi cần.

Kiểm thử mới ở `backend/tests/test_ai_comparison_guidance.py`: 16 ca bao gồm danh sách 0/2/3/5 mẫu, các cách hỏi, yêu cầu so sánh thực sự, replay/recovery và giữ nguyên điều kiện tìm kiếm. Đã kiểm tra đúng câu trên sau bước chọn ba laptop từ bản chụp chỉ đọc; bằng chứng tại `output/ai-comparison-guidance-fix/frozen-catalog-proof.json`. Không thay đổi bảng/cột hoặc quy tắc tương thích.

Xác minh hồi quy cuối: **819 passed, 7 skipped, 45 subtests passed**; log và JUnit ở `output/ai-comparison-guidance-fix/backend-tests.*`.

## Dùng dấu phẩy trong nội dung hiển thị — 30/10/2026

Theo yêu cầu mới, các câu viết sẵn trên giao diện khách hàng, quản trị, chính sách, thông báo và lỗi nghiệp vụ dùng dấu phẩy thay dấu chấm phẩy. Những dấu thuộc cú pháp, cookie, MIME, CSS và biểu thức đọc thông số vẫn giữ chức năng ban đầu.

Lời tư vấn AI được chuẩn hóa khi trả kết quả và khi hiển thị hội thoại đã lưu, gồm phần giải thích của bảng so sánh và tương thích. Prompt cũng yêu cầu dùng dấu phẩy. Bộ nhận diện câu kết cũ chấp nhận cả hai cách viết để tiếp tục ẩn đúng nội dung không cần hiển thị. Đợt sửa này không ghi lại lịch sử hoặc thay đổi database. Bằng chứng rà soát và kiểm thử ở `output/comma-wording/`.
