# Chính sách bảo hành và đổi sản phẩm

Cập nhật 30/10/2026. Nội dung này mô tả chức năng hiện đang triển khai; không đặt thêm điều kiện kinh doanh hoặc cam kết ngoài quy trình có sẵn.

## Nguồn nội dung dùng chung

- `backend/app/services/after_sales_policy.py`: nội dung công khai của bảo hành và đổi sản phẩm.
- `GET /store-policies`: không yêu cầu đăng nhập, không đọc đơn hàng hoặc dữ liệu khách; trả `Warranty`, `Returns`, `ReturnWindowDays` với `Cache-Control: no-store`.
- Thời hạn đổi lấy từ cùng dependency `get_return_policy()` được dùng để tạo yêu cầu: `RETURN_WINDOW_DAYS`, mặc định 7 ngày. Ngày giao là ngày thứ nhất, theo lịch Việt Nam. Không có thời hạn hợp lệ thì không tự công bố một con số.
- Hai trang `/chinh-sach-bao-hanh`, `/chinh-sach-doi-tra` và mục đổi sản phẩm trên trang chủ đọc API này. Khi tải lỗi, trang chính sách có nút thử lại; trang chủ dùng “Xem điều kiện”, không tự mặc định 7 ngày.
- Chatbot dùng cùng nội dung, đồng thời lấy thời hạn bảo hành của đúng mẫu đang hỏi từ catalog. Đơn đã mua giữ thời hạn đã chụp vào dòng đơn lúc đặt hàng.

## Bảo hành

Thời hạn tùy từng sản phẩm, tính từ ngày giao hàng thành công; 0 tháng là không bảo hành. Khách chọn sản phẩm thuộc đơn đã giao của mình, chọn Serial/IMEI nếu có, mô tả lỗi và có thể đính kèm tối đa 5 ảnh JPG/PNG/WEBP, mỗi ảnh tối đa 2 MiB.

Luồng hiện hành: tiếp nhận → kiểm tra → xử lý → công bố kết quả → trả sản phẩm và đóng phiếu. Kết quả được phép là sửa chữa, thay linh kiện hoặc không thể bảo hành. Đổi máy trong phiếu bảo hành đang tạm dừng; không cam kết chuyển trung tâm hoặc tự động cấp máy mới.

Rơi vỡ, vào nước, tự ý can thiệp và các tình trạng khác cần nhân viên kiểm tra theo điều kiện của từng sản phẩm. Chưa có bộ điều khoản loại trừ chi tiết áp dụng chung cho toàn cửa hàng. Phí gửi/nhận và thời gian xử lý cần nhân viên xác nhận theo từng trường hợp; không mặc định miễn phí hoặc đặt thời hạn sửa chữa.

Khi khách hỏi chung “Tôi mua laptop tại VIETECH thì được bảo hành bao lâu?”, chatbot giải thích thời hạn theo từng mẫu và hỏi tên/mã máy nếu chưa biết mẫu. Không mặc định 12/24 tháng, không lấy thời hạn của điện thoại vừa tư vấn để trả lời cho laptop.

## Đổi sản phẩm

Yêu cầu mới chỉ có hình thức `Exchange`, mỗi phiếu đúng 1 sản phẩm, trong thời hạn cấu hình. Sản phẩm phải thuộc đơn đã giao của khách, đúng Serial/IMEI nếu có, không trùng yêu cầu bảo hành/đổi đang mở.

Còn hàng thì đổi đúng phiên bản đã mua. Nếu phiên bản đó hết hàng, khách có thể chọn sản phẩm khác cùng danh mục: giá cao hơn thì thanh toán phần bù, phần dư không hoàn lại. Đơn sản phẩm đổi miễn phí giao hàng tiêu chuẩn; không suy rộng thành miễn phí gửi sản phẩm cũ hoặc miễn phí bảo hành. Khách có thể hủy trước khi chốt đơn đổi.

Chưa hỗ trợ yêu cầu trả hàng hoàn tiền mới. Các phiếu trả hàng cũ vẫn được đọc/theo dõi; liên hệ nhân viên để kiểm tra trường hợp cụ thể.

## Kiểm chứng

`tests/test_after_sales_policies.py` kiểm tra API công khai, cấu hình khác 7 ngày, nội dung đúng workflow, câu hỏi bảo hành laptop chưa có mẫu và việc loại bỏ cam kết sai của mô hình. `InfoPage.test.jsx` kiểm tra trang chính sách đọc API, thử lại khi tải lỗi, liên kết tạo yêu cầu và thời hạn trên trang chủ.
