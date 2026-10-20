# Trang chi tiết sản phẩm khách hàng

Thiết kế tham chiếu: [Figma — Product Detail Content, node 139:361](https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=139-361).
Đã đọc design context và screenshot bằng Figma MCP, theo skill `figma-design-to-code`.

## Phạm vi và quyết định

- Sửa trang khách tại `/san-pham/:slug`, dùng Header/Footer, AuthProvider và API client hiện có.
- Không có ưu đãi thu cũ hay trả góp: dự án chỉ thanh toán COD và chuyển khoản QR, nên khung ưu đãi demo trong Figma không được đưa lên trang. Theo yêu cầu cập nhật, đã xóa nhóm cam kết đổi trả 30 ngày/bảo hành chính hãng/hỗ trợ kỹ thuật, ghi chú phía dưới nhóm này, nút Yêu thích trên trang sản phẩm và ghi chú VN/A/giao nhanh bên dưới ảnh. Không sửa chính sách backend, giá hay đơn hàng.
- Bảo hành bao nhiêu tháng lấy từ `WarrantyMonths` của sản phẩm. Backend đổi trả hiện có mặc định 7 ngày và có thể cấu hình; nội dung demo 30 ngày không đổi thiết lập đó.
- **Mua ngay** thêm 1 sản phẩm theo SKU đã chọn rồi mở `/gio-hang`. Chưa thêm checkout, chưa gọi `POST /orders` hay tạo giao dịch thanh toán.
- Backend, database, migration, quyền, `.env`, trang Admin và Staff giữ nguyên. Các thay đổi trang chủ/banner đã có trước nhiệm vụ được giữ.

## Chức năng

- Breadcrumb điều hướng về trang chủ, danh mục và thương hiệu theo slug thực tế. Không tự thêm “iPhone 18 Series” khi API không có dữ liệu dòng sản phẩm.
- Tiêu đề, điểm/số đánh giá, đã bán, giá và tồn kho lấy từ `ProductDetailResponse`. Theo yêu cầu mới, mã sản phẩm/SKU không hiển thị ở tiêu đề, bộ chọn cấu hình, modal thông số và giỏ hàng phía khách; dữ liệu định danh biến thể vẫn dùng nội bộ khi mua hàng.
- Gallery ảnh lớn và thumbnail; mở ảnh bằng modal, đóng bằng ESC, nút đóng hoặc nền ngoài. Ảnh thiếu/hỏng hiện thông báo. Không dùng ảnh iPhone mẫu thay thế ảnh sản phẩm thật.
- Chọn phiên bản và màu theo các biến thể `IsActive`. Tổ hợp không tồn tại bị vô hiệu hóa. Nếu cùng màu/dung lượng có nhiều cấu hình, có bộ chọn cấu hình để xác định đúng SKU.
- Đổi lựa chọn cập nhật biến thể, giá, tồn và thông số dung lượng/màu. Không tự bịa giá biến thể. Phiên bản hết hàng/thiếu giá không đặt mua được.
- Thêm giỏ gọi API hiện có; backend gộp cùng SKU và kiểm tra tồn. Frontend không xóa giỏ hay sản phẩm khác. Khóa thao tác đang gửi để tránh bấm lặp và đổi SKU giữa yêu cầu.
- Số lượng trên icon giỏ đọc từ `Items[].Quantity`, cập nhật sau thêm/sửa/xóa giỏ và khi quay lại cửa sổ.
- Khách chưa đăng nhập được đưa tới đăng nhập khi thêm giỏ/mua ngay, giữ URL sản phẩm để quay lại.
- Tư vấn mở dialog chọn chat với nhân viên hoặc AI giống trang tin tức. Chọn nhân viên mở khung chat hiện có; khách chưa đăng nhập được hỏi đăng nhập/đăng ký và giữ URL sản phẩm để quay lại. Chọn AI mở khung “Sắp ra mắt”. Không thay luồng hội thoại/lịch sử hay gửi tin nhắn sản phẩm tự động.
- Đặc điểm nổi bật nhóm dữ liệu `Specifications` theo thứ tự màn hình → chip/RAM → camera → bộ nhớ → pin/sạc, không phụ thuộc thứ tự khóa JSON. Ghép thông số liên quan vào một ý, chỉ hiện nhóm có dữ liệu, dung lượng lấy theo biến thể đang chọn. Các ô thông tin nhanh hiện toàn bộ tối đa 5 nhóm, desktop 5 cột; mobile 2 cột và ô cuối lẻ chiếm cả hàng. Mô tả và modal thông số dùng dữ liệu của sản phẩm đang xem, thiếu thì hiện đang cập nhật.
- Mô tả dài mặc định thu gọn khoảng 320px ở desktop và 260px trên mobile, có lớp chuyển màu cuối đoạn và nút “Xem thêm”/“Thu gọn”. Mô tả ngắn hiển thị đầy đủ, không thêm nút. Đo chiều cao nội dung đã render để hỗ trợ HTML, cỡ chữ, ảnh và thay đổi kích thước màn hình; giữ nguyên định dạng mô tả Admin đã nhập.
- Sản phẩm tương tự lấy sản phẩm đang bán cùng danh mục, loại chính sản phẩm đang xem, đọc chi tiết và dùng `ProductCard` hiện có. Desktop từ 1280px hiển thị 5 cột; tablet/mobile giảm cột.
- Loading, 404, lỗi tải có thử lại, thiếu dữ liệu, biến thể hết hàng và lỗi nghiệp vụ từ API đều có trạng thái riêng.
- Đánh giá công khai, lọc sao/phân trang và gửi/sửa từ đơn đã giao đã được tích hợp; xem [chi tiết và giới hạn API](customer-product-reviews.md).

## API và dữ liệu còn thiếu

| Chức năng | API hiện có |
|---|---|
| Sản phẩm | `GET /products/slug/{slug}` |
| Sản phẩm tương tự | `GET /products?category_id=…`, `GET /products/{product_id}` |
| Giỏ và số lượng | `GET /cart`, `POST /cart/items`, `PATCH/DELETE /cart/items/{id}` |
| Chat | Các endpoint hội thoại của khung chat đang có |

API ảnh chỉ liên kết `ProductId`, chưa liên kết màu/biến thể. Vì vậy đổi màu vẫn dùng bộ ảnh chung của sản phẩm; chưa thể đổi bộ ảnh theo màu bằng dữ liệu hiện tại.

API sản phẩm bổ sung `OriginalPrice`, `SalePrice`, `DiscountAmount`, `DiscountPercent` và chương trình áp dụng cho từng biến thể. Card lấy giá gốc và giá sau giảm của cùng biến thể có giá sau giảm thấp nhất; không tự tạo giá tham chiếu. Trang chi tiết đổi giá theo phiên bản/màu. Giá vốn không xuất hiện trong API khách. Xem [quy tắc giá ưu đãi](customer-pricing-promotions.md).

Không có mock sản phẩm trong giao diện chạy bình thường. Mục ưu đãi demo được thay bằng coupon công khai từ `GET /coupons`. Nút xem thử gọi `POST /pricing/quote`, chưa tạo đơn, không trừ lượt mã. Dữ liệu iPhone mẫu và ảnh Figma chỉ nằm ở runner kiểm thử trong `output/product-detail/`.

## Các file

| File | Vai trò |
|---|---|
| `frontend/src/customer/pages/ProductPage.jsx`, `ProductPage.css` | Trang, bố cục, state SKU, thao tác API, loading/lỗi |
| `frontend/src/customer/components/product/ProductGallery.jsx` | Ảnh, thumbnail, phóng to |
| `frontend/src/customer/components/product/ProductPurchasePanel.jsx` | Lựa chọn, ưu đãi demo, nút mua/giỏ/tư vấn |
| `frontend/src/customer/components/product/ProductInformation.jsx` | Đặc điểm, mô tả, bảng/modal thông số |
| `frontend/src/customer/components/product/ProductModal.jsx` | Native dialog, focus, ESC |
| `frontend/src/customer/components/product/RelatedProducts.jsx` | Danh sách sản phẩm tương tự |
| `frontend/src/lib/product-detail.js` | Chuẩn hóa dữ liệu hiện có, giá/tồn, thông số |
| `frontend/src/assets/storefront/product-detail/*.svg` | Bốn chấm màu 16×16 tải từ Figma; dùng khi tên màu khớp |
| `frontend/src/customer/components/CartLink.jsx` | Icon giỏ có số lượng thật |
| `frontend/src/customer/layouts/CustomerLayout.jsx`, `CustomerLayout.css` | Tái sử dụng header và hiển thị số lượng giỏ |
| `frontend/src/customer/pages/CustomerLists.jsx` | Báo cập nhật số lượng sau sửa/xóa giỏ |
| `frontend/src/customer/components/CustomerChat.jsx` | Nhận sự kiện mở chat từ nút tư vấn |
| `frontend/src/customer/pages/ProductPage.test.jsx` | 16 ca kiểm thử trang sản phẩm |
| `frontend/src/customer/components/product/ProductInformation.test.jsx` | Mô tả định dạng và nhóm đặc điểm: thứ tự JSON, thiếu dữ liệu, phiên bản dung lượng, thông số laptop, chống lặp thông số |

## Cách mở trang

Chạy backend và frontend như README. Từ trang chủ/danh sách, bấm sản phẩm có dữ liệu, hoặc mở `http://127.0.0.1:5173/san-pham/<slug-trong-API>`.

Các nút thêm giỏ/mua ngay yêu cầu tài khoản Customer. Không có sản phẩm thì Admin cần nhập dữ liệu bằng các chức năng quản trị đã có, không thêm sản phẩm mẫu vào database bằng frontend.

Kết quả test và ảnh chụp desktop/mobile nằm ở `output/product-detail/`. Bộ tương tác browser dùng API được chặn trong ngữ cảnh kiểm thử, không ghi database. Có một lượt kiểm tra riêng dùng API backend localhost thật, bằng phiên khách chưa đăng nhập, chỉ GET.

## Kết quả kiểm chứng

- Build production đạt; lint không có lỗi mới, còn 3 cảnh báo trong các file Admin có sẵn.
- 60 test trong `src/customer/` đạt, gồm 16 ca mới của trang chi tiết sản phẩm.
- Browser: 11 nhóm kiểm tra đạt, không có lỗi JavaScript. Sáu kích thước 1440, 1280, 1024, 768, 390 và 320px không tràn ngang. Desktop 5 cột; ảnh và thumbnail dùng object-contain; bốn SVG màu sắc không rỗng, tải được và hiển thị đúng 16×16. Giá chính 30px ở desktop, nút mua dùng màu #E11D2E.
- Đã kiểm tra thumbnail, phóng to/ESC, màu/phiên bản/giá/SKU/thông số, thêm giỏ, tư vấn nhân viên, mua ngay về giỏ và các trạng thái thiếu dữ liệu/ảnh lỗi/404/lỗi tải.
- Đọc API localhost thật và mở Samsung Galaxy S26: tên, giá 25.000.000đ, SKU và hai biến thể lấy từ backend, không tràn ngang desktop/mobile, không phát sinh yêu cầu ghi. Sản phẩm này chưa có `Specifications`, nên thông số hiển thị dung lượng/màu từ biến thể. URL ảnh mặc định hiện không tải được; ảnh thứ hai có dữ liệu. Cần cập nhật ảnh mặc định ở dữ liệu quản trị nếu muốn ảnh đầu hiển thị ngay.
- Lượt test toàn frontend cuối: 456/458 đạt. Hai ca không đạt thuộc `PurchaseDetailPage.test.jsx` (tìm nút chi tiết phiếu nhập) và `SuppliersPage.test.jsx` (đóng dialog sau tạo). Chạy lại riêng: toàn file phiếu nhập 17/17 đạt, ca nhà cung cấp đạt. Các file Admin liên quan không có diff so với HEAD; chưa sửa hoặc tuyên bố bộ test tổng hoàn toàn ổn định. Một test điều hướng đơn Admin cũng có log mock thiếu `getDashboardStock` dù test trả trạng thái đạt.

Ảnh đối chiếu Figma: `output/product-detail/product-content-1440.png`; ảnh mobile: `product-390.png` và `product-320.png`. Ảnh API thật: `live-product-desktop.png`, `live-product-mobile.png`. Báo cáo JSON: `browser-report.json`, `live-api-browser-report.json`, `frontend-tests-final.json`.

Cập nhật phần đặc điểm nổi bật: lint các file sửa và build đạt, 27 test liên quan đạt. Đọc lại Samsung Galaxy S26 qua API localhost thật cho năm nhóm: màn hình 6.3 inch/Dynamic AMOLED 2X/120 Hz; Exynos 2600/RAM 12GB; camera sau 50 MP/trước 12MP; bộ nhớ 256GB theo biến thể; pin 4300 mAh/sạc 25 W. Đây là dữ liệu Admin đã nhập, không bổ sung thông số mẫu hoặc sửa database. Báo cáo: `output/product-highlights/live-api-report.json`.
