# Tìm kiếm sản phẩm (thanh tìm kiếm đầu trang)

Thanh tìm kiếm ở header làm như CellphoneS: gõ thì mở bảng gợi ý ngay dưới ô (không tự chuyển trang), nhấn Enter hoặc “Xem tất cả kết quả” thì mở `/tim-kiem?q=<từ khóa>`. Trang kết quả gọi `GET /products?keyword=…`. Từ ngày 20/10/2026 từ khóa được so khớp như sau ([app/core/search_text.py](../backend/app/core/search_text.py), `ProductRepository._filters`):

- **Tách từ, thứ tự bất kỳ:** mọi từ đều phải có, không cần liền nhau. “samsung s25” tìm được “Samsung Galaxy S25 Ultra”.
- **Tìm cả hãng và danh mục:** từ có thể nằm trong tên sản phẩm, tên hãng, tên danh mục hoặc danh mục cha. “loa jbl”, “điện thoại samsung”, “dien thoai cao cap” đều có kết quả.
- **Dấu tiếng Việt:** từ gõ không dấu khớp mọi dấu (“chuot” → “Chuột”, “sac du phong” → “Pin sạc dự phòng”); từ gõ có dấu phải đúng dấu (“bàn phím cơ” không lấy “bàn phím có dây”). Không phân biệt hoa thường.
- **Khoảng trắng:** khoảng trắng thừa được bỏ; từ viết liền vẫn khớp (“iphone17” → “iPhone 17”).
- **Thứ tự kết quả:** không chọn kiểu sắp xếp thì xếp theo độ liên quan: tên chứa nguyên cụm từ khóa trước, rồi tên chứa đủ các từ, cuối cùng là sản phẩm khớp qua hãng/danh mục; cùng mức thì mới nhất trước. Truyền `sort` (ví dụ `newest`) thì theo kiểu đó.
- Ký tự `%` và `_` trong từ khóa được tìm đúng nghĩa đen; tối đa 10 từ đầu tiên được dùng.

So khớp chạy trong SQL bằng `lower()` và `translate()` có sẵn của PostgreSQL (không cần extension `unaccent`, không thêm cột hay migration). Dữ liệu tên được lưu dạng Unicode dựng sẵn (NFC) như hiện tại.

Đối chiếu trên dữ liệu thật trước/sau khi sửa: “samsung s25” 0 → 2, “dien thoai” 0 → 36, “chuot” 0 → 15, “loa jbl” 0 → 3, “iphone17” 0 → 3, “màn hình 27 inch” 0 → 9; “bàn phím cơ” giữ 9 kết quả đúng.

## Bảng gợi ý khi gõ (giống CellphoneS)

Gõ xong 0,25 giây (chờ bộ gõ tiếng Việt ghép xong chữ), ô gọi `GET /products/suggestions?keyword=…` một lần và hiện:

- **Có phải bạn muốn tìm:** tối đa 6 trang danh mục, kèm ảnh: danh mục con khi các từ đã gõ chỉ đúng danh mục con đó (“laptop gaming” → Laptop gaming), danh mục gốc khi một từ đã gõ nằm trong tên danh mục (“điện thoại” → Điện thoại), rồi danh mục + hãng của các kết quả liên quan nhất (“Điện thoại SAMSUNG” → `/danh-muc/dien-thoai?brand=<BrandId>`). Gõ tên hãng (“samsung”) chỉ gợi ý các cặp danh mục + hãng.
- **Sản phẩm gợi ý:** 5 sản phẩm liên quan nhất, với ảnh, giá bán đỏ và giá gạch như trên thẻ sản phẩm.
- Liên kết “Xem tất cả kết quả cho “…””; không có gì khớp thì báo “Không có sản phẩm nào khớp với …”.

Mũi tên lên/xuống đi qua các liên kết trong bảng; Escape, bấm ra ngoài hoặc chuyển trang thì đóng bảng (Escape lần nữa xóa chữ như ô tìm kiếm thường). Bấm lại vào ô còn chữ thì bảng mở lại. Trong lúc tải gợi ý mới, gợi ý cũ vẫn hiện để bảng không nháy. Nhấn Enter với đúng từ khóa đang xem thì giữ nguyên danh mục và sắp xếp đã chọn.

## Trang kết quả

Bố cục theo CellphoneS:

- Đường dẫn “Trang chủ / Kết quả tìm kiếm cho: '…'”, dòng “Tìm thấy N sản phẩm cho từ khoá '…'”.
- Các nút danh mục “Tất cả · Điện thoại · Tai nghe…”: danh mục gốc có trong kết quả (`GET /products/filters`), chỉ hiện khi kết quả thuộc từ 2 danh mục trở lên hoặc khách đã chọn một; chọn để thu hẹp kết quả (gồm danh mục con).
- “Sắp xếp theo”: Liên quan (mặc định khi có từ khóa; không có từ khóa là Mới nhất), Giá cao, Giá thấp.
- Lưới sản phẩm dùng chung thẻ với trang danh mục, 20 sản phẩm mỗi lần; nút “Xem thêm N sản phẩm ↓” nối thêm trang sau thay cho nút Trước/Sau.
- Cột phải “Bài viết liên quan”: tối đa 6 tin có đủ mọi từ đã gõ trong tiêu đề hoặc tóm tắt, cùng “Xem tất cả bài viết”; ẩn khi không có bài.

Trang không còn ô lọc thương hiệu, khoảng giá hay còn hàng; liên kết cũ có `brand`, `price`, `stock` hay `page` chỉ giữ từ khóa, danh mục và sắp xếp. URL lưu `q`, `category=<CategoryId>` và `sort` (bỏ khi là mặc định). Không tìm thấy thì có liên kết “Xem tất cả sản phẩm”; lỗi tải có nút thử lại và không bị trình bày như kết quả rỗng. Trang thương hiệu `/thuong-hieu/<slug>` dùng cùng bố cục, cố định hãng, sắp xếp mặc định Mới nhất.

Mã nguồn: [CatalogPage.jsx](../frontend/src/customer/pages/CatalogPage.jsx), [CatalogPage.css](../frontend/src/customer/pages/CatalogPage.css), thanh tìm kiếm và bảng gợi ý [SearchBox.jsx](../frontend/src/customer/components/SearchBox.jsx), so khớp bài viết trong [search-text.js](../frontend/src/lib/search-text.js), `ProductService.search_suggestions`/`search_filters` ([services/catalog.py](../backend/app/services/catalog.py)).

## API

`GET /products/suggestions?keyword=` trả `Searches[Label, CategorySlug, BrandId, ImageUrl]` và `Products[ProductId, Name, Slug, ImageUrl, Price, OriginalPrice]` (OriginalPrice chỉ có khi cao hơn Price). Gợi ý lấy từ 40 sản phẩm đang bán liên quan nhất; ảnh và giá tính như trang chi tiết (ảnh chính của biến thể mặc định, giá thấp nhất sau khuyến mãi tự động). Từ khóa rỗng trả hai danh sách rỗng.

`GET /products/filters` nhận `keyword`, `category_id` (gồm các danh mục con đang hiện), `brand_id`, `min_price`, `max_price`, `in_stock` như `GET /products`. Trả `Categories[CategoryId, Name, Slug, ProductCount]` (danh mục gốc đang hiện; sản phẩm trong danh mục bị ẩn không được tính) và `Brands[BrandId, Name, Slug, ProductCount]` (hãng đang hoạt động), nhiều sản phẩm trước. Số của danh mục bỏ qua `category_id`, số của hãng bỏ qua `brand_id`. Giá tối thiểu lớn hơn giá tối đa trả 400 `invalid_price_range`.

Kiểm thử: [tests/test_product_search.py](../backend/tests/test_product_search.py), [search-text.test.js](../frontend/src/lib/search-text.test.js), [CatalogPage.test.jsx](../frontend/src/customer/pages/CatalogPage.test.jsx), các tình huống header trong [HomePage.test.jsx](../frontend/src/customer/pages/HomePage.test.jsx).
