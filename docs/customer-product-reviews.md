# Đánh giá sản phẩm phía khách

Phần đánh giá nằm trong trang `/san-pham/:slug`, sau mô tả/thông số và trước sản phẩm tương tự. Bấm số đánh giá dưới tên sản phẩm để đi đến phần này.

Giao diện đối chiếu [Figma — Product Reviews, node 821:371](https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=821-371): nền trắng, điểm trung bình màu đậm, sao vàng, thanh thống kê đỏ, bộ lọc dạng viên và từng đánh giá có khung bo góc. Hiện tối đa 3 đánh giá ban đầu; nút **Xem thêm đánh giá** tải nối tiếp 3 mục, giữ các mục đã đọc cả khi tải thêm bị lỗi. Đổi bộ lọc hoặc gửi/sửa thành công sẽ tải lại danh sách từ đầu. Số liệu lấy từ API, không dùng số điểm hoặc đánh giá mẫu của Figma.

Form dùng [Figma — Write Review Overlay, node 815:721](https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=815-721) và [Edit Review Overlay, node 815:750](https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=815-750): popup rộng 640px, padding 22px/24px, ảnh sản phẩm 62px, sao viền/vàng, ô “Nhận xét của bạn” cao 142px, thông báo điều kiện và nút Hủy/Gửi (hoặc Cập nhật) bên trái. Ảnh dùng dữ liệu sản phẩm theo phiên bản đã mua, có chữ “Ảnh” khi thiếu/hỏng; tên, mã đơn và phiên bản lấy từ dữ liệu thật. Form sửa không có mã đơn trong API công khai nên hiện “Đánh giá của bạn • Đã mua hàng”. Popup thu nhỏ theo màn hình và cuộn khi thiếu chiều cao; giữ chọn sao bằng bàn phím, nhãn trợ năng và cơ chế dialog có sẵn.

## Quy tắc sử dụng

- Bất kỳ ai cũng được đọc đánh giá công khai, lọc theo 1–5 sao và xem thêm. Không tự tạo đánh giá mẫu khi API rỗng hoặc lỗi.
- Customer đăng nhập mới viết đánh giá. Khách chưa đăng nhập dùng hộp chọn đăng nhập/đăng ký hiện có, giữ URL sản phẩm để quay lại; không thêm form xác thực mới.
- **Viết ở đâu:** nút **Viết đánh giá** trong phần đánh giá của trang sản phẩm, hoặc nút **Đánh giá sản phẩm** ở lịch sử mua hàng (`/tai-khoan?section=orders`) và trang chi tiết đơn (`/don-hang/:id`). Hai nút sau mở `/san-pham/:slug?review=<OrderId>#product-reviews`: form tự mở với đơn đó được chọn sẵn.
- **Khi nào:** sau khi nhận hàng, tức đơn `Delivered` hoặc `Completed` (Completed là bước sau khi giao). `Pending`, `Confirmed`, `Processing`, `Shipping`, `Cancelled` không hợp lệ. Backend luôn kiểm tra lại sở hữu, trạng thái và trùng đánh giá.
- Đánh giá viết ở sản phẩm nào là của sản phẩm đó: form **không có ô chọn đơn hay phiên bản**. API cần một dòng đơn (`OrderItemId`), nên form tự lấy lần mua mới nhất của sản phẩm chưa được đánh giá, từ các đơn đã nhận có sản phẩm này (`order_status=Delivered&order_status=Completed&product_id=…`, theo `ProductId` của dòng; mở bằng `?review=<OrderId>` thì ưu tiên đơn đó) và hiện tên sản phẩm, mã đơn, phiên bản đã mua. Mua nhiều lần thì mỗi lần mua được một đánh giá; đã đánh giá hết thì form báo "Bạn đã đánh giá sản phẩm này cho mọi lần mua."
- Tạo đánh giá chỉ gửi `OrderItemId`, `Rating`, `Content`. `UserId` lấy từ phiên đăng nhập và `ProductId` do backend suy ra từ dòng đơn.
- Mỗi dòng đơn tối đa một đánh giá, kể cả đánh giá đã bị Admin ẩn. Rating 1–5; nội dung phải có ký tự ngoài khoảng trắng.
- Chủ đánh giá được sửa số sao/nội dung trước `CreatedAt + 7 ngày`; đúng tại hạn không được sửa. Form kiểm tra lại hạn ngay trước khi gửi. Không có nút xóa hoặc sửa ảnh cho Customer.
- Khóa gửi/sửa và đóng cửa sổ khi đang gửi, tránh thao tác lặp. Lỗi nghiệp vụ/HTTP giữ nội dung đang soạn, không báo thành công giả.
- Danh sách, phân bố sao và số đánh giá dưới tên sản phẩm cập nhật sau gửi/sửa. Phân bố dùng `Total` của từng bộ lọc, không đếm riêng trang đang hiển thị; trung bình làm tròn hai chữ số theo backend rồi định dạng tiếng Việt.
- Thông báo gửi/cập nhật đánh giá thành công tự ẩn sau 3 giây; bộ đếm được dọn khi thông báo đổi hoặc rời trang.
- Nội dung đánh giá hiển thị dạng văn bản, không thực thi HTML. Ảnh đánh giá sẵn có được hiển thị/phóng to; URL không hợp lệ bị bỏ và ảnh hỏng có trạng thái riêng.

## API sử dụng

| Mục đích | API |
|---|---|
| Danh sách công khai | `GET /products/{product_id}/reviews?rating=…&page=…&page_size=3` |
| Phân bố 5 mức sao | Cùng API, mỗi mức `page_size=1`, đọc `Total` |
| Đơn đã nhận có sản phẩm này | `GET /orders?order_status=Delivered&order_status=Completed&product_id=…&page=…&page_size=10` |
| Tạo đánh giá | `POST /reviews` |
| Sửa số sao/nội dung | `PATCH /reviews/{review_id}` |

Các yêu cầu riêng tư dùng `useCustomerRequest` để tái sử dụng refresh token và kiểm tra phiên. API công khai không gửi access token.

## Giới hạn API hiện tại

- Không có endpoint tải ảnh đánh giá dành cho Customer. API tạo nhận URL ảnh, nhưng chưa có luồng upload phù hợp. Lần này form gửi số sao/nội dung; vẫn đọc được ảnh đã có. Không dùng upload ảnh Admin hoặc avatar để thay thế.
- Theo lựa chọn của người dùng, giữ nguyên backend: trước mắt Customer chỉ chọn đánh giá phiên bản còn xuất hiện trong dữ liệu trang sản phẩm. `OrderItemResponse` chưa có `ProductId`; frontend đối chiếu `ProductVariantId` với danh sách biến thể mà API sản phẩm trả về. Phiên bản đã mua nhưng nay đã ngừng bán và không còn trong response chưa chọn được ở form này. Không bổ sung trường API, sửa bảng hoặc đổi quyền.
- Dòng đơn đã được đánh giá (kể cả review đã bị ẩn) có `ReviewId` trong `GET /orders` và `GET /orders/{id}`: form bỏ qua dòng đó, lịch sử mua hàng không mời đánh giá lại và trang chi tiết đơn ghi "✓ Đã đánh giá". Nếu backend vẫn trả `409 review_exists` (gửi trùng cùng lúc), form báo rõ và chuyển sang lần mua kế tiếp chưa đánh giá.
- Không thêm trả lời đánh giá, lượt hữu ích, đánh giá ẩn danh hoặc ảnh mới khi chưa có nghiệp vụ/API tương ứng.

## File

| File | Vai trò |
|---|---|
| `frontend/src/customer/components/product/ProductReviews.jsx`, `ProductReviews.css` | Danh sách, thống kê, lọc, phân trang, sửa và xem ảnh |
| `frontend/src/customer/components/product/useProductReviewList.js` | Tải nối tiếp, giữ danh sách khi thử lại và bỏ phản hồi cũ khi đổi bộ lọc |
| `frontend/src/customer/components/product/ReviewComposer.jsx` | Hiển thị sản phẩm/lần mua và gửi/sửa theo popup Figma |
| `frontend/src/customer/components/product/ReviewStars.jsx` | Sao nguyên/lẻ và nhãn trợ năng |
| `frontend/src/lib/review-api.js` | Đọc công khai, thống kê, điều kiện sửa và đối chiếu dòng đơn |
| `frontend/src/customer/pages/ProductPage.jsx` | Tích hợp vào trang sản phẩm, cập nhật số sao và hộp đăng nhập cũ |
| `frontend/src/customer/components/product/ProductReviews.test.jsx` | 26 ca kiểm thử giao diện, quyền, lỗi và nghiệp vụ |

## Kiểm chứng

- Form Figma (21/10/2026): 54 test đánh giá/trang sản phẩm đạt; build và lint các file sửa đạt. Browser đối chiếu popup desktop đúng 640 × 517px, ảnh 62 × 62px và textarea 142px; kiểm tra ở 1440/768/390/320px và màn hình thấp 320 × 568px không tràn ngang. Chọn sao bằng hover/bàn phím, gửi/sửa, lỗi giữ nội dung, kiểm tra đơn/retry, ảnh theo phiên bản và ảnh hỏng đều đạt; không có lỗi JavaScript. Ảnh và báo cáo mới ở `output/review-composer-figma/`, dùng API fixture riêng trong browser, không ghi database thật.
- 47 test đánh giá và trang sản phẩm đạt, gồm 26 ca đánh giá và ca tích hợp khách chưa đăng nhập. Bộ kiểm tra gồm quyền Customer/Staff/Admin, lọc và tải thêm qua API, giữ danh sách khi tải thêm lỗi, bỏ phản hồi cũ khi đổi lọc, POST/PATCH đúng trường, đơn sai trạng thái, không có đơn, trùng đánh giá, hạn sửa đúng tại 7 ngày và gửi lặp.
- Build đạt; lint không có lỗi mới, còn 3 cảnh báo Admin có sẵn.
- Browser đạt ở 1440/768/390/320px; danh sách/form không tràn ngang, gửi/sửa/lọc/cập nhật thống kê và đóng bằng Escape hoạt động, không có lỗi JavaScript.
- Đọc API localhost thật với Samsung Galaxy S26: phần đánh giá hoạt động, dữ liệu hiện có 0 đánh giá. Lượt này chỉ GET, không tạo đơn, đánh giá mẫu hoặc ghi database thật.
- Ảnh chụp/báo cáo: `output/product-reviews/`. Lượt gửi/sửa trong browser dùng API fixture được chặn riêng trong context, không đến backend thật.

Backend, bảng dữ liệu, migration, quyền và giao diện Admin/Staff không thay đổi trong nhiệm vụ này. Chưa commit/push.
