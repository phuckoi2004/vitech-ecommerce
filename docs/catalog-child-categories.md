# Danh mục con và mô tả sản phẩm

Phần mô tả được biên tập lại trong đợt [rà màu và nội dung ngày 18/10/2026](catalog-color-review.md), gồm cả bài S26 theo yêu cầu mới. Danh mục và việc phân nhóm dưới đây được giữ nguyên.

Đã áp dụng vào database đang cấu hình ngày 18/10/2026. Theo lựa chọn của người dùng, giữ cấu trúc `Products.CategoryId`: **mỗi sản phẩm có một danh mục con chính**, không nhân bản sản phẩm để đưa vào nhiều nhóm.

## Kết quả

| Danh mục cha | Danh mục con | Sản phẩm được phân nhóm |
|---|---:|---:|
| Điện thoại | 10 | 36 |
| Laptop | 10 | 35 |
| Máy tính bảng | 10 | 20 |
| Tai nghe | 10 | 30 |
| **Tổng** | **40** | **121** |

- Tạo 39 danh mục con và dùng lại “Điện thoại pin trâu” đã có. Tổng catalog hiện có 49 danh mục, gồm 9 danh mục gốc và 40 danh mục con.
- Tổng số sản phẩm vẫn là 201; giữ nguyên ID, slug sản phẩm, SKU, giá, tồn, ảnh thư viện, thương hiệu và lịch sử kho.
- 80 sản phẩm ở các nhóm khác giữ danh mục cũ. 200 sản phẩm mẫu được cập nhật mô tả; bài Samsung Galaxy S26 do người dùng viết giữ nội dung và chỉ được chuyển vào “Điện thoại cao cấp”.
- Một sản phẩm có thể phù hợp nhiều nhu cầu, nhưng chỉ nằm trong nhóm chính đã chọn. Ví dụ máy có pin lớn vẫn có thể được xếp vào nhóm chơi game. Các nhóm không phải những bộ lọc đặc tính bao phủ lẫn nhau.

## Các nhóm

- **Điện thoại:** Pin trâu, Chơi game, Chụp ảnh, Màn hình gập, Mỏng nhẹ, Phổ thông, Tầm trung, Cao cấp, Nhỏ gọn, Màn hình lớn.
- **Laptop:** Gaming, Học tập, Văn phòng, Đồ họa, Mỏng nhẹ, 2 trong 1, AI, Màn hình lớn, Lập trình, Cao cấp.
- **Máy tính bảng:** Học tập, Văn phòng, Chơi game, Sáng tạo, Giải trí, Nhỏ gọn, Màn hình lớn, Kèm bút, Kèm bàn phím, Phổ thông.
- **Tai nghe:** Chống ồn chủ động, Chụp tai, Thể thao, Có dây, Đeo cổ, Hi-Res, Đàm thoại, Pin lâu, Hệ sinh thái Apple, Hệ sinh thái Galaxy.

Danh mục “Điện thoại pin trâu” dùng lại ID và slug `samsung` đã được lưu trước đó để giữ đường dẫn cũ; đây vẫn là danh mục nhu cầu, không phải thương hiệu Samsung. Các sản phẩm được xếp vào nhóm này có pin công bố từ 6.000 mAh.

Danh sách để kiểm tra bằng Excel:

- [40 danh mục, tiêu chí và đường dẫn](data/catalog-child-categories-2026-10-17.csv).
- [121 sản phẩm và danh mục con tương ứng](data/catalog-product-categories-2026-10-17.csv).

## Hiển thị phía khách

Trang `/danh-muc/<slug>` có các ô nhóm bo góc, ảnh đại diện tùy chọn và liên kết vào nhóm. Nhóm đang xem được đánh dấu; có thể chuyển sang nhóm khác hoặc trở lại danh mục cha. Chuyển nhóm xóa phân trang và bộ lọc cũ để không làm danh sách trống do điều kiện từ trang trước.

Trang danh mục cha vẫn tìm cả sản phẩm của các danh mục con bằng `include_descendants=true`. Các ô nhóm trên màn hình nhỏ cuộn ngang trong khung. Menu cạnh banner trang chủ tiếp tục hiển thị thương hiệu và khoảng giá theo yêu cầu trước; không thêm danh mục con vào menu đó.

## Mô tả và nguồn

200 mô tả được viết lại bằng tiếng Việt, dùng tiêu đề `<h2>`, thông số in đậm, đoạn giải thích theo từng đặc điểm và ảnh thật từ thư viện của đúng mẫu sản phẩm. Số mục tùy dữ liệu công bố, không điền thông số chưa có để ép đủ một số mục cố định. Có tổng cộng 557 URL ảnh minh họa đã trả HTTP 200 và Content-Type ảnh. Không thêm các ảnh này thành SKU hay bản ghi `ProductImages` mới.

Bố cục tham chiếu bài Samsung S26 có sẵn. Nội dung viết mới từ dữ kiện, không sao chép nguyên bài mô tả của nhà bán lẻ hoặc áp chính sách của họ thành cam kết của VieTech. Thông số nguồn riêng của từng sản phẩm được ghi trong [manifest bộ mẫu](../backend/data/sample-catalog-2026-10-17.json).

Tham khảo cách tổ chức nhu cầu tại [Điện thoại CellphoneS](https://cellphones.com.vn/mobile.html), [Laptop CellphoneS](https://cellphones.com.vn/laptop.html), [Máy tính bảng CellphoneS](https://cellphones.com.vn/tablet.html), [Tai nghe CellphoneS](https://cellphones.com.vn/thiet-bi-am-thanh/tai-nghe.html) và [GearVN](https://gearvn.com/).

## Nhập lại và kiểm tra

Sau khi nhập bộ mẫu ban đầu, chạy tại thư mục gốc:

```powershell
# Kiểm tra kế hoạch; không sửa dữ liệu
.venv\Scripts\python.exe -X utf8 backend\scripts\enrich_sample_catalog.py

# Áp dụng các manifest đã chuẩn bị
.venv\Scripts\python.exe -X utf8 backend\scripts\enrich_sample_catalog.py --apply
```

Script dùng `CategoryService`/`ProductService` trong một transaction, lưu bản sao catalog vào `output/catalog-enrichment-20261017/` trước khi ghi, kiểm tra nguyên trạng giá/tồn/lịch sử kho rồi mới commit. Nếu một mô tả đã được sửa thủ công khác cả bản cũ lẫn bản chuẩn bị, script dừng để tránh ghi đè. Một lượt chạy lại sau cập nhật ghi nhận 0 thay đổi trên 201 sản phẩm.

Kết quả kiểm tra:

- Đối chiếu đủ 40 API danh mục con: không nhóm rỗng, danh sách đúng sản phẩm đã phân; bốn danh mục cha trả đủ 36/35/20/30 sản phẩm và không trùng ID.
- Đối chiếu 200 mô tả đã lưu, nội dung S26 cũ, toàn bộ SKU, giá, tồn, ảnh, thương hiệu và lịch sử kho.
- Chrome desktop/mobile: cả bốn danh mục có 10 liên kết nhóm; bấm vào nhóm đúng danh sách, không tràn ngang. Mô tả có đề mục, ảnh tải được và xem thêm/thu gọn hoạt động.
- 54 kiểm thử frontend liên quan đạt; build đạt. Lint còn hai cảnh báo có sẵn trong các component Admin, không có lỗi mới.
- Một lượt kiểm tra API chạy cùng Chrome có phản hồi 503 tạm thời. Lượt kiểm tra lại toàn bộ 40 nhóm sau đó đạt; chưa xác định nguyên nhân của phản hồi tạm thời này.
