# Rà lại màu, ảnh và mô tả catalog — 18/10/2026

## Phạm vi

Rà catalog 201 sản phẩm/459 SKU hiện có. Chỉ sửa nhãn màu, liên kết ảnh theo màu, ảnh mặc định và nội dung mô tả; không tạo thêm sản phẩm/SKU, không thay giá, tồn, giá vốn, danh mục, thông số kỹ thuật hay lịch sử kho.

## Các lỗi được xử lý

- 167 phiên bản chưa có bộ ảnh riêng trong metadata. Chúng dùng lại ảnh chung nên có thể mang nhãn Trắng nhưng hiện máy Đen; ví dụ iPhone 13.
- Lenovo IdeaPad Slim 3 14AHP10 83K9004RVN đang ghi Đen, trong khi lựa chọn màu của đúng mã máy tại nguồn là Xám.
- S26 thường có hai ảnh mang tên/model S26 Ultra. Thay bộ ảnh được chọn bằng ảnh S26 thường từ FPT Shop, bỏ hai bản ghi ảnh Ultra gắn nhầm. Các tệp người dùng đã tải lên kho lưu trữ không bị xóa.
- Chuẩn hóa nhãn `Xanh Blue Sky` của S26 thành `Xanh Sky Blue`, tương ứng cách ghi tại Samsung Việt Nam.
- Thẻ sản phẩm trước đây lấy ảnh chung dù Admin đã chọn ảnh riêng cho màu mặc định. Thẻ trên trang chủ, danh sách tìm kiếm và yêu thích nay dùng ảnh của `DefaultVariantId`.
- Một lựa chọn ảnh rỗng được tôn trọng; frontend không lấy ảnh của màu khác để lấp chỗ trống.
- Nút màu hỗ trợ thêm các nhãn rõ nghĩa, có viền cho màu sáng. Các tên chưa rõ như `Xanh`, `Đặc biệt` không được tự đoán thành một mã màu; hình ảnh của SKU là căn cứ xem hoàn thiện. Nếu chưa lưu màu thì hiển thị đang cập nhật, không tạo lựa chọn màu “Tiêu chuẩn”.

Đã áp dụng 170 sửa đổi ảnh/metadata theo màu (gồm 167 lựa chọn thiếu, Lenovo và hai màu của S26), 2 sửa nhãn màu; thêm 164 ảnh vào thư viện và bỏ 2 ảnh sai mẫu. Các SKU màu đã được gắn đúng trước đó được giữ nguyên. Sau cập nhật có 201 sản phẩm, 459 SKU, 623 ảnh và 457 phiếu kho.

Danh sách đối chiếu từng SKU: [CSV màu và ảnh đúng](data/catalog-color-review-2026-10-18.csv).

## Mô tả sản phẩm

Viết lại mô tả cho cả 201 sản phẩm, gồm S26 cũ, theo bố cục đề mục rõ, đoạn văn ngắn, thông số quan trọng in đậm và ảnh minh họa. Mỗi nhóm dùng các đặc điểm phù hợp:

- Điện thoại/máy tính bảng: màn hình và tần số quét, chip/RAM, camera, pin, bộ nhớ.
- Laptop: CPU/RAM, màn hình, GPU, lưu trữ/hệ điều hành, cổng kết nối và pin.
- Tai nghe/loa: thiết kế, âm thanh và chế độ nghe, pin, đàm thoại/điều khiển, kết nối.
- Màn hình: kích thước/tấm nền, tần số quét/phản hồi, cổng và lắp đặt; giá treo được viết riêng theo ngàm/tải trọng.
- Bàn phím/chuột: bố cục/cảm biến, hoàn thiện, kết nối và nguồn điện.
- Pin dự phòng: dung lượng lõi, công suất, cổng/cáp và cách nạp lại.

S26 được viết lại riêng, loại bỏ đoạn ghi chú soạn thảo và thuộc tính ảnh sai cú pháp. Mô tả không dùng kết quả benchmark, thời lượng thực đo hoặc chính sách của nhà bán lẻ làm cam kết của VieTech. Không sao chép nguyên bài mô tả của nguồn.

## Mở rộng nguồn tham khảo

Ngoài nguồn gốc CellphoneS/GearVN của từng SKU, đã đọc và đối chiếu thêm:

- [FPT Shop — iPhone 13](https://fptshop.com.vn/dien-thoai/iphone-13), [OPPO Find X8](https://fptshop.com.vn/dien-thoai/oppo-find-x8), [MacBook Air M4](https://fptshop.com.vn/may-tinh-xach-tay/macbook-air-13-m4-2025-10cpu-8gpu-16gb-256gb), [iPad Air M3](https://fptshop.com.vn/may-tinh-bang/ipad-air-11-inch-m3-2025-wifi), [Galaxy S26](https://fptshop.com.vn/dien-thoai/samsung-galaxy-s26).
- [Thế Giới Di Động — Sony WF-C510](https://www.thegioididong.com/tai-nghe/tai-nghe-bluetooth-true-wireless-sony-wf-c510), [ASUS VG27AQ5F](https://www.thegioididong.com/man-hinh-may-tinh/man-hinh-asus-27-inch-2k-ips-220hz-0-3ms-vg27aq5f).
- [Viettel Store — Galaxy S26](https://viettelstore.vn/dien-thoai/samsung-galaxy-s26-12gb-512gb-pid362292.html), tham khảo bố cục giới thiệu; không lấy dung lượng 512GB áp vào SKU 256GB.
- [Phong Vũ — Logitech G502 HERO](https://phongvu.vn/chuot-gaming-logitech-g502-hero--s1810470), tham khảo cách trình bày đặc điểm chuột.
- [HACOM — bàn phím ASUS](https://hacom.vn/ban-phim-co?brand=asus), đối chiếu mã và hoàn thiện, phân biệt V2 với V2X.
- [Hoàng Hà Mobile — Harman Kardon Go + Play 3](https://core.hoanghamobile.com/loa/loa-harman-kardon-go-play-3-chinh-hang).
- Hãng: [Samsung S26](https://www.samsung.com/vn/smartphones/galaxy-s26/specs/), [OPPO Find X8](https://www.oppo.com/vn/smartphones/series-find-x/find-x8/specs/), [Sony WF-C510](https://www.sony.com.vn/headphones/products/wf-c510), [ASUS Falchion Ace 75 HE](https://rog.asus.com/vn/keyboards/keyboards/pbt-keycaps/rog-falchion-ace-75-he/).

Các nguồn này bổ sung đối chiếu cho những mẫu tương ứng và cách biên tập. Thông số của những mẫu khác vẫn phải dựa trên nguồn riêng đã lưu trong manifest bộ mẫu, không lấy thông số của một máy áp hàng loạt cho máy khác.

## Áp dụng và bảo vệ dữ liệu

```powershell
# Kiểm tra, không ghi dữ liệu
.venv\Scripts\python.exe -X utf8 backend\scripts\review_catalog_colors.py

# Áp dụng bản đã chuẩn bị
.venv\Scripts\python.exe -X utf8 backend\scripts\review_catalog_colors.py --apply
```

Manifest: [catalog-review-2026-10-18.json](../backend/data/catalog-review-2026-10-18.json). Script lưu bản sao trước ghi vào `output/catalog-review-20261018/`, kiểm tra thay đổi đồng thời và áp dụng trong một transaction. Màu chỉ cập nhật `Color`/`VariantName`; ảnh dùng helper media hiện có trong service. Không gửi lại toàn bộ form biến thể để tránh chuẩn hóa ngoài ý muốn cấu hình lưu trữ cũ. Nếu một mô tả hoặc bộ ảnh đã được sửa sau lúc chuẩn bị, script dừng để không ghi đè.

## Kết quả kiểm tra

- Đối chiếu 201 mô tả, 170 lựa chọn ảnh/màu và toàn bộ giá, tồn, giá vốn, cấu hình SKU, danh mục, thông số kỹ thuật, lịch sử kho với bản sao trước ghi: đạt.
- 8 trang chi tiết đại diện được kiểm tra qua API; S26 không còn ảnh Ultra trong thư viện.
- Chrome desktop/mobile: 20 lượt đổi màu trên iPhone 13, S26, Lenovo và Sony đều khớp ảnh đúng màu; ảnh thẻ sản phẩm dùng đúng màu mặc định. Đề mục, ảnh mô tả, xem thêm/thu gọn hoạt động và không phát sinh lỗi JavaScript.
- 97 kiểm thử frontend liên quan đạt; build đạt. Lint chỉ còn hai cảnh báo Admin có sẵn.
- Chạy lại chế độ kiểm tra: 0 thay đổi, không thêm SKU/ảnh hay đặt lại tồn.
