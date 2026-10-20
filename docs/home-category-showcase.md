# Khối sản phẩm theo danh mục ở trang chủ

Từ 18/10/2026, trang chủ hiển thị **mọi danh mục gốc đang hoạt động** thành các khối sản phẩm, thay cho giới hạn cũ chỉ 4 danh mục đầu (khiến Màn hình, Bàn phím, Chuột, Loa, Pin sạc dự phòng không xuất hiện).

## Cách ghép khối

- Hai danh mục liên quan dùng chung một khối, mỗi danh mục là một tab. Danh mục không còn danh mục phù hợp để ghép thì có khối riêng, tiêu đề là tên danh mục.
- Thứ tự các khối và thứ tự tab trong khối theo **Thứ tự hiển thị** Admin đặt cho danh mục.
- Nhận diện danh mục theo slug hoặc tên (không phân biệt dấu, hoa thường), trong `frontend/src/customer/components/home/categories.js`.
- Cặp ưu tiên từ mạnh đến yếu; cặp sau chỉ áp dụng khi danh mục ở cặp trước không có hoặc đã được ghép:

| Thứ tự | Cặp |
|---:|---|
| 1 | Điện thoại – Laptop |
| 2 | Máy tính bảng – Tai nghe |
| 3 | Bàn phím – Chuột |
| 4 | Máy tính để bàn – Linh kiện máy tính |
| 5 | Màn hình – Máy tính để bàn |
| 6 | Loa – Tai nghe |
| 7 | Điện thoại – Máy tính bảng |
| 8 | Laptop – Máy tính để bàn |
| 9 | Màn hình – Linh kiện máy tính |
| 10 | Đồng hồ thông minh – Điện thoại |
| 11 | Loa – Tivi |
| 12 | Pin sạc dự phòng – Phụ kiện |

Danh mục mới không thuộc bảng trên (ví dụ “Máy in”) hiển thị thành khối riêng. Muốn ghép thêm loại mới, bổ sung tên/slug vào `aliases` và cặp vào `SHOWCASE_PAIRS`.

## Với dữ liệu hiện tại

1. Điện thoại | Laptop
2. Máy tính bảng | Tai nghe
3. Màn hình
4. Bàn phím | Chuột
5. Loa (Tai nghe đã ghép với Máy tính bảng)
6. Pin sạc dự phòng

Mỗi khối vẫn chỉ tải sản phẩm khi người xem cuộn tới gần. Không đổi backend, database hay quyền.
