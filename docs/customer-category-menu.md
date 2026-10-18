# Menu danh mục cạnh banner trang chủ

Các danh mục con được bổ sung ngày 18/10/2026 có thể chọn trong trang danh mục và khối danh mục hiện có; xem [danh sách và cách hoạt động](catalog-child-categories.md). Menu cạnh banner vẫn giữ phạm vi thương hiệu và khoảng giá dưới đây.

Tham chiếu [Figma Category Sidebar, node 5:29](https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=5-29). Phần mở rộng tham khảo cách tổ chức danh mục/hãng của [CellphoneS](https://cellphones.com.vn/), dùng màu sắc và component sẵn có của VieTech.

- Desktop: rê chuột hoặc bấm danh mục để mở bảng bên phải. Điện thoại/tablet: bấm mở bảng ngay dưới hàng danh mục.
- Bảng gồm bộ lọc thương hiệu có sản phẩm đang bán trong danh mục và “Chọn theo giá”. Không hiển thị danh mục con, gợi ý sản phẩm hay liên kết “Xem tất cả”. Không thêm hãng/sản phẩm mẫu hoặc biến thương hiệu thành danh mục con.
- Chọn hãng đi tới `/danh-muc/<slug>?brand=<BrandId>`; API lọc đồng thời danh mục và thương hiệu. Phạm vi tìm sản phẩm vẫn gồm các danh mục con để không bỏ sót hàng trong danh mục đã chọn.
- Có trạng thái tải, rỗng, lỗi và thử lại cho danh sách thương hiệu. Chỉ đọc danh sách sản phẩm tóm tắt khi mở menu để xác định hãng phù hợp; không tải danh mục con hoặc chi tiết sản phẩm trong menu. Chuyển danh mục/đóng menu hủy yêu cầu cũ.
- Dùng Tab/Enter để mở, mũi tên phải để vào bảng, Escape để đóng và trả focus. Bấm ngoài hoặc nút đóng để thu lại.
- SVG nền tròn danh mục lấy nguyên bản từ Figma, kích thước 24×24; icon loại sản phẩm dùng bộ icon hiện có. Dữ liệu danh mục, hãng và banner tiếp tục lấy từ API.
- Menu mở rộng gọn theo nội dung, các ô thương hiệu bo góc và dùng `LogoUrl` do Admin lưu; thiếu ảnh hoặc tải lỗi thì hiển thị tên thương hiệu.
- Chọn mức giá đi tới `/danh-muc/<slug>?price=<mức>`; trang danh sách cho phép kết hợp với thương hiệu hoặc bỏ lọc giá. Các mức dùng chung: dưới 5 triệu, 5–10 triệu, 10–15 triệu, 15–20 triệu, từ 20 triệu. Mốc trên của các khoảng giữa không bao gồm trong khoảng (10 triệu thuộc mức 10–15 triệu).
- API công khai `/products` nhận `min_price`/`max_price` không âm, tối đa 15 chữ số và 2 chữ số thập phân. Lọc theo giá thấp nhất của biến thể đang hoạt động/chưa xóa, khớp giá trên thẻ sản phẩm; lọc trước khi đếm và phân trang. Khoảng đảo ngược trả 400 `invalid_price_range`. Không đổi database hay quyền.
- Ảnh danh mục là tùy chọn: Admin tải ảnh từ máy hoặc dán URL trong form thêm/sửa danh mục, giống thương hiệu; có thể bỏ ảnh và lưu lại. API dùng `ImageUrl` (tối đa 500 ký tự, cho phép `null`); bỏ qua trường này khi PATCH giữ nguyên ảnh đang lưu. Migration `6f8a2c4d9b10` thêm cột nullable vào `Categories`, danh mục cũ không cần bổ sung ảnh.
- Menu danh mục gốc và bộ lọc nhóm sản phẩm ở các khối sản phẩm dùng ảnh Admin đã lưu; thiếu ảnh hoặc tải lỗi thì dùng icon hiện có. Không thay đổi quyền hay ảnh banner.
