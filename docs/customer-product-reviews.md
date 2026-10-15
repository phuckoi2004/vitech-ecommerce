# Đánh giá sản phẩm phía khách

Phần đánh giá nằm trong trang `/san-pham/:slug`, sau mô tả/thông số và trước sản phẩm tương tự. Bấm số đánh giá dưới tên sản phẩm để đi đến phần này.

## Quy tắc sử dụng

- Bất kỳ ai cũng được đọc đánh giá công khai, lọc theo 1–5 sao và chuyển trang. Không tự tạo đánh giá mẫu khi API rỗng hoặc lỗi.
- Customer đăng nhập mới viết đánh giá. Khách chưa đăng nhập dùng hộp chọn đăng nhập/đăng ký hiện có, giữ URL sản phẩm để quay lại; không thêm form xác thực mới.
- Form đọc đơn của chính Customer với `order_status=Delivered`, có phân trang. Sau khi chọn đơn, đọc chi tiết để chọn đúng phiên bản của sản phẩm đang xem. Không suy đoán theo tên, SKU hoặc tự nhập mã dòng đơn.
- Chỉ đơn đang `Delivered` hợp lệ; `Completed`, `Shipping`, `Cancelled` không hợp lệ theo `ReviewService` hiện tại. Backend luôn kiểm tra lại sở hữu, trạng thái và trùng đánh giá.
- Tạo đánh giá chỉ gửi `OrderItemId`, `Rating`, `Content`. `UserId` lấy từ phiên đăng nhập và `ProductId` do backend suy ra từ dòng đơn.
- Mỗi dòng đơn tối đa một đánh giá, kể cả đánh giá đã bị Admin ẩn. Rating 1–5; nội dung phải có ký tự ngoài khoảng trắng.
- Chủ đánh giá được sửa số sao/nội dung trước `CreatedAt + 7 ngày`; đúng tại hạn không được sửa. Form kiểm tra lại hạn ngay trước khi gửi. Không có nút xóa hoặc sửa ảnh cho Customer.
- Khóa gửi/sửa và đóng cửa sổ khi đang gửi, tránh thao tác lặp. Lỗi nghiệp vụ/HTTP giữ nội dung đang soạn, không báo thành công giả.
- Danh sách, phân bố sao và số đánh giá dưới tên sản phẩm cập nhật sau gửi/sửa. Phân bố dùng `Total` của từng bộ lọc, không đếm riêng trang đang hiển thị; trung bình làm tròn hai chữ số theo backend rồi định dạng tiếng Việt.
- Nội dung đánh giá hiển thị dạng văn bản, không thực thi HTML. Ảnh đánh giá sẵn có được hiển thị/phóng to; URL không hợp lệ bị bỏ và ảnh hỏng có trạng thái riêng.

## API sử dụng

| Mục đích | API |
|---|---|
| Danh sách công khai | `GET /products/{product_id}/reviews?rating=…&page=…&page_size=5` |
| Phân bố 5 mức sao | Cùng API, mỗi mức `page_size=1`, đọc `Total` |
| Đơn đã giao của khách | `GET /orders?order_status=Delivered&page=…&page_size=10` |
| Dòng sản phẩm trong đơn | `GET /orders/{order_id}` |
| Tạo đánh giá | `POST /reviews` |
| Sửa số sao/nội dung | `PATCH /reviews/{review_id}` |

Các yêu cầu riêng tư dùng `useCustomerRequest` để tái sử dụng refresh token và kiểm tra phiên. API công khai không gửi access token.

## Giới hạn API hiện tại

- Không có endpoint tải ảnh đánh giá dành cho Customer. API tạo nhận URL ảnh, nhưng chưa có luồng upload phù hợp. Lần này form gửi số sao/nội dung; vẫn đọc được ảnh đã có. Không dùng upload ảnh Admin hoặc avatar để thay thế.
- Theo lựa chọn của người dùng, giữ nguyên backend: trước mắt Customer chỉ chọn đánh giá phiên bản còn xuất hiện trong dữ liệu trang sản phẩm. `OrderItemResponse` chưa có `ProductId`; frontend đối chiếu `ProductVariantId` với danh sách biến thể mà API sản phẩm trả về. Phiên bản đã mua nhưng nay đã ngừng bán và không còn trong response chưa chọn được ở form này. Không bổ sung trường API, sửa bảng hoặc đổi quyền.
- `ReviewResponse`, kể cả `/reviews/mine`, không trả `OrderItemId`. Vì vậy không thể xác định trước dòng đơn nào đã được đánh giá ở phiên cũ hoặc đã bị ẩn. Backend trả `409 review_exists`; form báo rõ và khóa dòng đó trong lần mở hiện tại. Các dòng vừa tạo thành công được ghi nhớ trên trang để tránh chọn lại. Không đối chiếu theo tên hay gán nhầm một review cho một đơn.
- Không thêm trả lời đánh giá, lượt hữu ích, đánh giá ẩn danh hoặc ảnh mới khi chưa có nghiệp vụ/API tương ứng.

## File

| File | Vai trò |
|---|---|
| `frontend/src/customer/components/product/ProductReviews.jsx`, `ProductReviews.css` | Danh sách, thống kê, lọc, phân trang, sửa và xem ảnh |
| `frontend/src/customer/components/product/ReviewComposer.jsx` | Chọn đơn/phiên bản đã mua và gửi/sửa |
| `frontend/src/customer/components/product/ReviewStars.jsx` | Sao nguyên/lẻ và nhãn trợ năng |
| `frontend/src/lib/review-api.js` | Đọc công khai, thống kê, điều kiện sửa và đối chiếu dòng đơn |
| `frontend/src/customer/pages/ProductPage.jsx` | Tích hợp vào trang sản phẩm, cập nhật số sao và hộp đăng nhập cũ |
| `frontend/src/customer/components/product/ProductReviews.test.jsx` | 24 ca kiểm thử giao diện, quyền, lỗi và nghiệp vụ |

## Kiểm chứng

- 88 test liên quan đạt, gồm 24 ca mới và ca tích hợp khách chưa đăng nhập. Bộ kiểm tra gồm quyền Customer/Staff/Admin, lọc và phân trang thật, API lỗi/tải lại, POST/PATCH đúng trường, đơn sai trạng thái, không có đơn, trùng đánh giá, hạn sửa đúng tại 7 ngày và gửi lặp.
- Build đạt; lint không có lỗi mới, còn 3 cảnh báo Admin có sẵn.
- Browser đạt ở 1440/768/390/320px; danh sách/form không tràn ngang, gửi/sửa/lọc/cập nhật thống kê và đóng bằng Escape hoạt động, không có lỗi JavaScript.
- Đọc API localhost thật với Samsung Galaxy S26: phần đánh giá hoạt động, dữ liệu hiện có 0 đánh giá. Lượt này chỉ GET, không tạo đơn, đánh giá mẫu hoặc ghi database thật.
- Ảnh chụp/báo cáo: `output/product-reviews/`. Lượt gửi/sửa trong browser dùng API fixture được chặn riêng trong context, không đến backend thật.

Backend, bảng dữ liệu, migration, quyền và giao diện Admin/Staff không thay đổi trong nhiệm vụ này. Chưa commit/push.
