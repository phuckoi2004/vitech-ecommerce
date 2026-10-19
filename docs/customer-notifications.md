# Thông báo phía khách hàng

- Chuông và trang `/thong-bao` cập nhật mỗi 30 giây khi đang hiển thị, khi quay lại cửa sổ và sau thao tác đánh dấu đã đọc. Request không chạy chồng; dữ liệu cũ giữ nguyên khi cập nhật nền, lỗi có nút thử lại.
- Lỗi lấy số chưa đọc được thông báo riêng, giữ số đã biết thay vì giả định bằng 0. Request danh sách bị hủy khi rời trang hoặc đổi trang phân trang; đổi tài khoản hủy các request và không dùng lại dữ liệu của tài khoản cũ.
- Nhân viên hoặc Admin phụ trách trả lời chat tạo thông báo cho đúng Customer trong cùng transaction với tin nhắn; rollback hủy cả hai. Không thay đổi bảng hoặc quyền.
- Mở thông báo chưa đọc sẽ đánh dấu đã đọc rồi mở nội dung. Nếu thao tác lỗi, có nút thử lại thực hiện tiếp đúng thao tác; không tự chuyển trang khi người dùng đã rời đi.
- Tham chiếu đơn hàng, bảo hành và đổi trả hợp lệ mở khung xem thông tin qua API Customer hiện có: `/orders/{id}`, `/warranty-requests/{id}`, `/return-requests/{id}`. Khung chỉ hiển thị thông tin công khai và lịch sử; không bổ sung thao tác xử lý/hủy/hoàn tiền hay triển khai trang lịch sử mua hàng.
- Thông báo chat mở đúng `/tu-van?conversation=<id>`, kể cả lịch sử đã đóng. Truy cập không hợp lệ giữ kiểm tra quyền ở backend. Liên kết ngoài, khu vực Admin và trang chưa tồn tại bị bỏ qua.

Kiểm thử dùng API giả lập trên frontend và SQLite cô lập cho nghiệp vụ chat/thông báo. Không ghi dữ liệu vào database chính.
