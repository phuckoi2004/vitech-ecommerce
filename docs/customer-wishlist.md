# Trang sản phẩm yêu thích

Tham chiếu: [Figma — VieTech Wishlist Desktop, node 743:333](https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=743-333). Đã đọc design context và screenshot theo skill `figma-design-to-code`; dùng `figma-use` để tìm đúng màn hình, không sửa file Figma.

## Giao diện và thao tác

- Trang `/yeu-thich` có breadcrumb, tiêu đề, số lượng thực tế và lưới 5 cột trên desktop; tablet 3 cột, mobile 2 cột.
- Giữ cấu trúc thẻ trong Figma: khung ảnh/thông tin, dòng “Đã thêm vào yêu thích”, trái tim và nút “Thêm vào giỏ hàng”. Bỏ hai nút riêng “Xem chi tiết” và “Xóa khỏi yêu thích”. Bấm ảnh/tên/thông tin sản phẩm để mở chi tiết; bấm trái tim để bỏ yêu thích.
- Trái tim đang thích dùng đúng SVG 26×26 từ Figma, lưu tại `frontend/src/assets/storefront/wishlist-heart-active.svg`. Sau khi bỏ thích, trái tim ở trang chủ rỗng bên trong và vẫn có viền xanh; không chuyển thành màu xám.
- Khi danh sách thật sự trống, hiển thị trạng thái trống và hướng dẫn bấm trái tim. Khung trạng thái mẫu trong Figma không hiển thị cùng danh sách có sản phẩm.
- Giữ cơ chế đồng bộ trạng thái giữa các thẻ/trang, làm mới cache khi quay lại và ngăn GET cũ ghi đè thao tác thêm/bỏ vừa thành công.

## Lỗi “Hết hàng” và cách sửa

`GET /wishlist` chỉ nhúng `ProductSummary`, không có `Variants`, `Images`, giá hay tồn kho. Trước đây trang đưa thẳng summary vào `toProductCard`, nên danh sách biến thể trống bị tính thành hết hàng và không có giá/ảnh.

Trang hiện đọc thêm `GET /products/{product_id}` cho từng sản phẩm trước khi dựng thẻ. Giá, ảnh và tồn lấy từ response chi tiết thật. Chỉ hiện “Hết hàng” khi không có phiên bản còn tồn; lỗi mạng/500 hiển thị lỗi có thử lại, không giả thành tồn bằng 0. Sản phẩm không còn công khai (404) vẫn giữ trong danh sách để khách bỏ yêu thích, hiển thị “Ngừng bán” và khóa thêm giỏ.

## Thêm vào giỏ

- Một phiên bản hợp lệ: gửi `POST /cart/items` với `ProductVariantId` và `Quantity: 1`.
- Nhiều phiên bản: mở cửa sổ chọn màu/cấu hình và giá trước khi gửi; phiên bản hết hàng không chọn được. Không tự chọn SKU thay cho khách trong trường hợp này.
- Backend kiểm tra giá/tồn và gộp dòng giỏ theo nghiệp vụ hiện có. Thêm giỏ không tạo đơn hàng hoặc trừ tồn.
- Khóa thao tác đang gửi; thành công cập nhật icon giỏ qua sự kiện hiện có. Lỗi nghiệp vụ được hiển thị và giữ sản phẩm trong wishlist.

## Phạm vi dữ liệu

Không thêm sản phẩm/ảnh mẫu, tồn kho giả, giá gạch ngang hoặc phần trăm giảm giả vào frontend chạy thật. Giá gốc/phần trăm giảm trong Figma chưa có trường tương ứng trong API catalog; giữ cách hiển thị giá hiện tại. Backend, database, migration, quyền, Admin/Staff không thay đổi.

## Kiểm chứng

- 59 test thẻ sản phẩm, trang chủ và các trang mua sắm đạt. Sau sửa lỗi callback đo mô tả lúc rời trang chi tiết, 46 test liên quan mô tả, thẻ và trang sản phẩm đạt; hai lượt có phần kiểm tra thẻ chung.
- Build đạt; lint các file sửa không có lỗi/cảnh báo.
- Browser đạt ở 1440/1024/768/390/320px: không tràn ngang; icon SVG tải được và đúng 26×26; thêm giỏ theo phiên bản đã chọn, bỏ thích/cập nhật số lượng, mở chi tiết và quay lại, trạng thái trống và viền xanh hoạt động; không có lỗi JavaScript.
- API thật của Samsung Galaxy S26 tại thời điểm kiểm tra trả tồn 5 máy màu đen và 10 máy màu xanh. Kiểm tra giao diện dùng wishlist giả lập chứa summary công khai của sản phẩm này và GET chi tiết thật; thẻ hiển thị giá thật và nút thêm giỏ khả dụng, không còn nhãn “Hết hàng” sai. Không xác nhận đây là wishlist thật của người dùng và không ghi database thật.
- Ảnh/báo cáo trong `output/wishlist-figma/`. Ảnh điện thoại/laptop từ Figma chỉ dùng trong fixture trình duyệt tại thư mục output; không được import vào giao diện chạy thật.

Các file chính: `CustomerLists.jsx`, `ShoppingPages.css`, `ProductCard.jsx`, `ProductCard.css`, `WishlistProductCard.jsx`, `useWishlistProduct.js`. Sửa thêm guard đo chiều cao trong `ProductInformation.jsx` để tránh lỗi khi điều hướng rời trang. Chưa commit/push.
