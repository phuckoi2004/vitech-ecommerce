# Trang danh mục khách hàng (Danh sách sản phẩm)

Thiết kế tham chiếu: [Figma — Danh sách sản phẩm, node 981:2391](https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=981-2391) và các bảng “Filter Overlay/…” (node 157:374 → 157:592). Áp dụng cho mọi danh mục tại `/danh-muc/<slug>` từ ngày 19/10/2026; trang tìm kiếm và trang thương hiệu giữ giao diện cũ.

## Các khối và nguồn dữ liệu

| Khối (Figma) | Hiển thị | Dữ liệu |
|---|---|---|
| Breadcrumb | Trang chủ › (danh mục cha) › danh mục | `GET /categories` |
| Advertising Banner | 2 banner của danh mục, giữ nguyên tỉ lệ ảnh | `GET /banners?category_id=` — xét trang banner dẫn tới: đúng danh mục này, rồi danh mục con hoặc sản phẩm trong nó, rồi danh mục cha, cuối cùng banner chung (tin tức, mã giảm giá); không lấy banner của danh mục khác |
| Brands | Tên danh mục, “Chọn thương hiệu”: hãng có sản phẩm đang bán, nhiều sản phẩm trước | `GET /categories/{id}/filters` |
| Feature Categories | “Chọn theo nhu cầu”: các danh mục con (trang con hiện các nhóm cùng cấp) | `GET /categories` |
| Full Filters | “Chọn theo tiêu chí”: Bộ lọc, Sẵn hàng, Hàng mới về, Xem theo giá, Nhu cầu sử dụng và tiêu chí thông số | `GET /categories/{id}/filters` |
| Sort | 6 kiểu sắp xếp, mặc định “Phổ biến” | `GET /products?sort=` |
| Product Listing | “<Danh mục> nổi bật”, 20 sản phẩm mỗi lần, thẻ sản phẩm dùng chung | `GET /products` + chi tiết từng thẻ |
| See More Banner | “Xem thêm N sản phẩm ↓” nối trang tiếp theo, giữ các sản phẩm đã hiện | `GET /products?page=` |
| Introduction | “Thông tin về …”: mô tả danh mục, mỗi dòng một đoạn; **ẩn khi danh mục chưa có mô tả** | `Categories.Description` |
| News | “Tin tức …”: tối đa 4 bài có nhắc nguyên cụm tên danh mục (hoặc danh mục cha); ẩn khi không có bài | `GET /news` |

Chưa danh mục gốc nào có mô tả nên khối “Thông tin về …” chưa hiện; thêm mô tả trong trang quản trị danh mục là đủ. Banner hiện có là ảnh của trang chủ (tỉ lệ khoảng 2,3:1) nên khối banner cao hơn dải mỏng trong Figma; dùng ảnh ngang dài nếu muốn đúng dải đó.

## Tiêu chí lọc theo từng danh mục

`Products.Specifications` là văn bản tự do, mỗi danh mục một bộ khóa. Mỗi lựa chọn là một quy tắc khớp chữ/số trên thông số, tên sản phẩm và dung lượng của biến thể đang bán ([app/core/catalog_facets.py](../backend/app/core/catalog_facets.py)). Bộ tiêu chí chọn theo slug danh mục gốc; danh mục con dùng bộ của gốc. API chỉ trả về lựa chọn có ít nhất một sản phẩm đang bán, nên giao diện không có lựa chọn rỗng; danh mục gốc mới chưa có bộ riêng chỉ có hãng và khoảng giá.

| Danh mục gốc | Tiêu chí |
|---|---|
| Điện thoại (theo đúng Figma) | Chip xử lý, Loại điện thoại, Dung lượng RAM, Bộ nhớ trong, Tính năng đặc biệt, Tính năng camera, Tần số quét, Kiểu màn hình, Công nghệ NFC, Hỗ trợ mạng |
| Laptop | Chip xử lý, Dung lượng RAM, Ổ cứng, Card đồ họa, Kích thước màn hình, Laptop AI |
| Máy tính bảng | Chip xử lý, Hệ điều hành, Dung lượng RAM, Bộ nhớ trong, Kích thước màn hình, Kết nối mạng |
| Tai nghe | Chống ồn, Thời lượng pin, Tính năng, Điều khiển |
| Màn hình | Kích thước, Độ phân giải, Tần số quét, Tấm nền, Thời gian phản hồi |
| Bàn phím | Kết nối, Kích thước bàn phím, Loại bàn phím, Đèn nền |
| Chuột | Kết nối, Độ phân giải (DPI), Đèn LED, Nguồn điện |
| Loa | Kiểu loa, Chống nước, Công suất, Thời lượng pin, Cổng kết nối |
| Pin sạc dự phòng | Dung lượng pin, Công suất sạc, Tính năng, Cổng sạc ra |

Khoảng giá cũng theo danh mục (điện thoại theo Figma: dưới 2, 2–4, 4–7, 7–13, 13–20, trên 20 triệu; phụ kiện bắt đầu từ dưới 500 nghìn). Liên kết khoảng giá từ menu trang chủ (`?price=under-5`...) vẫn dùng được và hiện trong bảng “Xem theo giá” để bỏ chọn.

Một số lựa chọn trong Figma chưa có dữ liệu trong thông số mẫu (ví dụ Tai thỏ, Giọt nước, Video 4K, Điện thoại phổ thông) nên đang tự ẩn; chúng sẽ hiện khi thông số sản phẩm có ghi các đặc điểm đó.

## API

- `GET /categories/{id}/filters` → `Brands`, `PriceRanges` (`MinPrice`/`MaxPrice` gửi lại làm `min_price`/`max_price`), `Facets` (`Key`, `Label`, `Options[Value, Label, ProductCount]`). Đếm trên sản phẩm `Active`, chưa xóa, thuộc danh mục và các danh mục con đang hiện. Danh mục ẩn hoặc không tồn tại trả 404.
- `GET /products` thêm:
  - `sort`: `newest` (mặc định khi không có từ khóa), `relevance` (mặc định khi có từ khóa, xem [tìm kiếm](customer-search.md)), `popular` (lượt bán + lượt đánh giá, rồi điểm đánh giá), `best_selling`, `price_asc`/`price_desc` (giá “từ” khách thấy, đã tính khuyến mãi tự động), `discount` (tỉ lệ giảm lớn nhất so với giá gốc/giá so sánh). Mọi kiểu đều kết thúc bằng ngày tạo và ID để phân trang ổn định.
  - `in_stock=true`: có biến thể đang bán còn hàng. `new_arrivals=true`: sản phẩm tạo trong 30 ngày gần nhất.
  - `spec=<Key>:<Value>` (lặp lại, cần `category_id`): cùng tiêu chí là HOẶC, khác tiêu chí là VÀ. Tiêu chí/lựa chọn không có trong danh mục trả 400 `invalid_filter`; giao diện bỏ các lựa chọn cũ không còn trước khi gửi.

Lọc thông số đọc toàn bộ sản phẩm của danh mục bằng hai truy vấn (sản phẩm, rồi dung lượng biến thể) rồi khớp quy tắc trong Python; sắp xếp, phân trang, giá, còn hàng và hàng mới chạy trong SQL. Với vài trăm sản phẩm mỗi danh mục như hiện tại là đủ nhanh. Nếu một danh mục lên hàng nghìn sản phẩm nên lưu sẵn giá trị tiêu chí đã chuẩn hóa khi lưu sản phẩm.

Vì dữ liệu mẫu chưa có lượt bán và đánh giá, “Phổ biến” và “Bán chạy” hiện cho ra cùng thứ tự với “Mới nhất”.

## Trạng thái trên URL

`?brand=<BrandId>&price=<khoảng>&sort=<kiểu>&stock=1&new=1&spec=chip:snapdragon&spec=ram:8gb`. Kiểu sắp xếp mặc định không ghi lên URL. “Xóa bộ lọc” bỏ mọi bộ lọc nhưng giữ kiểu sắp xếp. Chuyển sang danh mục con xóa bộ lọc cũ.

Đổi bộ lọc hoặc kiểu sắp xếp luôn tải lại từ trang 1, kể cả khi quay về lựa chọn đã từng bấm “Xem thêm”. Kết quả từ yêu cầu đã hủy không được ghi đè danh sách hiện tại.

“Xem thêm N sản phẩm” tính số bản ghi chưa đọc từ trang API, không trừ theo số thẻ đang hiện: sản phẩm vừa bị ẩn có thể trả 404 khi tải chi tiết và không được tính là một trang còn thiếu. Nút biến mất khi đã đọc đủ `Total` hoặc API trả trang không đầy/trang rỗng, kể cả khi tổng số sản phẩm vừa thay đổi. Lỗi tải trang tiếp theo vẫn giữ các sản phẩm đã hiện và cho phép thử lại trang đó.

## Mã nguồn và kiểm thử

- Backend: [catalog_facets.py](../backend/app/core/catalog_facets.py), `ProductRepository.listing_facts`/`_order` ([repositories/catalog.py](../backend/app/repositories/catalog.py)), `ProductService.search_products`/`category_filters` ([services/catalog.py](../backend/app/services/catalog.py)), [schemas/catalog_filters.py](../backend/app/schemas/catalog_filters.py). Kiểm thử: [tests/test_category_listing.py](../backend/tests/test_category_listing.py).
- Frontend: [CategoryPage.jsx](../frontend/src/customer/pages/CategoryPage.jsx), [CategoryCriteria.jsx](../frontend/src/customer/components/category/CategoryCriteria.jsx), [useProductPages.js](../frontend/src/customer/hooks/useProductPages.js), [catalog-filters.js](../frontend/src/lib/catalog-filters.js). Kiểm thử: [CategoryPage.test.jsx](../frontend/src/customer/pages/CategoryPage.test.jsx), [catalog-filters.test.js](../frontend/src/lib/catalog-filters.test.js).
- Đã đối chiếu trên dữ liệu thật (Postgres) cả 9 danh mục gốc và chụp màn hình ở 1440px và 390px.
