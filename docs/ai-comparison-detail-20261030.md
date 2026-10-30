# So sánh sản phẩm chi tiết, 30/10/2026

Đợt này sửa câu trả lời và giao diện so sánh. Không ghi vào database, không thêm bảng, cột hoặc thuộc tính thông số sản phẩm.

## Hành vi sau chỉnh sửa

- Bảng dùng tên sản phẩm ở từng cột. Phần nhận xét trình bày xong từng sản phẩm rồi chuyển sang sản phẩm tiếp theo, không dùng nhãn “mẫu 1”, “mẫu 2”.
- Camera sau xuống dòng theo từng ống kính, giữ khẩu độ, FOV và thông tin lấy nét cùng ống kính tương ứng. Camera nhiều thông tin không còn bị cắt ở giới hạn 200 ký tự dùng cho thông số ngắn.
- Màu sắc không xuất hiện như tiêu chí mặc định. Chỉ so sánh khi khách yêu cầu, yêu cầu bỏ qua màu sắc vẫn được tôn trọng. Tên phiên bản được giữ để nhận diện đúng sản phẩm.
- Nhận xét giải thích vai trò của CPU, GPU, RAM, màn hình, pin và camera. Các khác biệt có thể định lượng được nêu cụ thể, kèm gợi ý theo nhu cầu.
- MariSilicon X được tách thành bộ xử lý hình ảnh, không ghép với Snapdragon thành tên CPU. Đây là cách trình bày trong kết quả so sánh, không tạo thuộc tính trong database.
- Khi RAM chưa có trong thông số nhưng đã được xác minh và ghi rõ trong đoạn RAM của mục Hiệu năng trong mô tả, bộ so sánh có thể đọc thông tin đó. Thông số RAM hiện có và RAM của SKU được chọn vẫn được ưu tiên. Không lấy dung lượng nâng cấp, thông tin mơ hồ hoặc dung lượng ở mục khác.
- Câu trả lời có bảng so sánh hợp lệ không lặp lại toàn bộ phần text bên trên. Nếu bảng không hợp lệ hoặc không có, phần text vẫn trình bày đủ thông tin theo tên từng sản phẩm.

Ví dụ với OPPO Reno16 F 5G 8GB 256GB và OPPO Find X5 Pro 5G 12GB 256GB, phần phân tích nêu chênh lệch RAM 4 GB, dung lượng pin 2.000 mAh, hai độ phân giải màn hình, các ống kính góc rộng và tele, cùng công dụng OIS. Mỗi thông số gắn với tên sản phẩm trên dòng riêng. Không lấy MHz giữa hai kiến trúc GPU để xếp hạng, không lấy số MP để khẳng định chất lượng ảnh, không đổi mAh thành số giờ sử dụng.

## Phạm vi nhận xét hiệu năng

Nhận xét CPU cụ thể hiện có cho Dimensity 7300, 7300-Energy và Snapdragon 8 Gen 1. Các CPU khác vẫn được hiển thị đúng tên và giải thích vai trò theo loại sản phẩm. Không có kết quả đo FPS, nhiệt độ, thời gian chạy ứng dụng hay thử ảnh thực tế trong đợt này. Điểm và quy tắc chọn sản phẩm của bộ tư vấn hiện có được giữ, các gợi ý theo nhu cầu bổ sung không tạo cơ chế chấm điểm thứ hai.

Nguồn kiến trúc và chức năng dùng để đối chiếu:

- [MediaTek, Dimensity 7300-Energy trên OPPO Reno12](https://www.mediatek.com/tek-talk-blogs/oppo-reno12-series-powered-by-mediatek-dimensity-7300-energy), cấu trúc bốn Cortex-A78 và bốn Cortex-A55.
- [Qualcomm, Snapdragon 8 Gen 1 product brief](https://www.qualcomm.com/content/dam/qcomm-martech/dm-assets/documents/snapdragon-8-gen-1-mobile-platform-product-brief.pdf), nhân hiệu năng Cortex-X2.
- [OPPO Find X5 Pro](https://www.oppo.com/en/smartphones/series-find-x/find-x5-pro/), vai trò xử lý hình ảnh của MariSilicon X.
- [OPPO Việt Nam, thông số Reno16 F](https://www.oppo.com/vn/smartphones/series-reno/reno16-f/specs/), đối chiếu phiên bản Việt Nam cho ví dụ trên.

## Kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Backend, so sánh, chọn sản phẩm, câu chữ, chuẩn hóa và hồi quy chat | 250 passed |
| Frontend, AiComparison, AiChatText, AiChat | 55 passed |
| Lint các file giao diện sửa trong đợt này | Thành công |
| Frontend build | Thành công, có cảnh báo kích thước bundle hiện có |
| Chrome, hai sản phẩm ở 1440 px và 390 px, ba sản phẩm ở 390 px | 3/3 trường hợp đạt, không lỗi JavaScript, không tràn ngang trang |

Kiểm tra trình duyệt dùng component thật, lấy thông tin sản phẩm qua API công khai đang chạy và dựng kết quả bằng bộ so sánh vừa sửa. Không tạo hội thoại hay ghi vào database. Các kiểm thử backend dùng cơ sở dữ liệu thử nghiệm riêng, không gọi Gemini thật. Chưa kiểm tra một lượt hội thoại đăng nhập qua Gemini trong đợt này.

Ảnh và báo cáo trình duyệt nằm tại `output/ai-comparison-detail-20261030/`. Các câu trả lời lịch sử không được phân tích lại, giao diện vẫn xuống dòng camera, bỏ tiêu chí màu mặc định và ẩn đoạn khác biệt cũ dùng nhãn “mẫu 1”, “mẫu 2”. Gửi lại câu hỏi so sánh để nhận phân tích mới.
