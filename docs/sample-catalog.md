# Bộ dữ liệu mẫu 200 sản phẩm

Bộ `sample-catalog-2026-10-17` dùng để thử danh mục, tìm kiếm, lọc thương hiệu, chi tiết sản phẩm và giỏ hàng trên VieTech. Người dùng đã chọn thêm tồn mẫu để thử mua hàng.

Ngày 18/10/2026 đã có bước [bổ sung 40 danh mục con và viết lại mô tả](catalog-child-categories.md). Các số liệu bên dưới ghi nhận lần nhập mẫu ban đầu; tổng catalog hiện có 49 danh mục, vẫn 201 sản phẩm. CSV bộ mẫu giữ danh mục gốc để truy vết; danh mục con hiện tại được ghi trong các CSV ở tài liệu bổ sung.

## Nội dung

| Danh mục | Số sản phẩm mới |
|---|---:|
| Điện thoại | 35 |
| Laptop | 35 |
| Máy tính bảng | 20 |
| Tai nghe | 30 |
| Màn hình | 25 |
| Bàn phím | 15 |
| Chuột | 15 |
| Loa | 15 |
| Pin sạc dự phòng | 10 |
| **Tổng** | **200** |

Danh sách có nhiều thương hiệu như Apple, Samsung, ASUS, Acer, Dell, HP, Lenovo, MSI, OPPO, Xiaomi, Sony, JBL, Logitech và Anker. Thương hiệu/danh mục đang có được tái sử dụng, không đổi tên hoặc tạo lại; sản phẩm Samsung Galaxy S26 đang có được giữ nguyên.

## Nguồn và cách lưu

- Thông tin sản phẩm lấy từ trang công khai của [CellphoneS](https://cellphones.com.vn/) và [GearVN](https://gearvn.com/), ngày 17/10/2026.
- Tên, cấu hình, giá tham khảo và thời hạn bảo hành được đối chiếu trang chi tiết. Bằng chứng thời hạn bảo hành được lưu trong manifest; không lấy bảo hành của gói mua thêm để áp cho sản phẩm.
- Ảnh sử dụng URL của CDN nhà bán lẻ. Mỗi URL đã trả HTTP 200 với nội dung ảnh khi chuẩn bị dữ liệu. Không tải lại ảnh vào kho Supabase và không thay ảnh của sản phẩm cũ.
- Mô tả ngắn được viết từ tên và thông số; không sao chép bài đánh giá/mô tả dài của nhà bán lẻ. Điểm đánh giá, số đánh giá và số đã bán giữ mặc định 0.
- Manifest: [`backend/data/sample-catalog-2026-10-17.json`](../backend/data/sample-catalog-2026-10-17.json).
- Bảng tên, giá, URL ảnh, URL nguồn và URL trong project: [`docs/data/sample-products-2026-10-17.csv`](data/sample-products-2026-10-17.csv). CSV dùng UTF-8 BOM để mở tiếng Việt trong Excel.

## Tồn và giá vốn mẫu

- Mỗi sản phẩm có một SKU mẫu và **10 đơn vị** tồn đầu kỳ, tổng cộng **2.000 đơn vị mẫu**.
- Giá vốn mẫu bằng **80% giá tham khảo**, chỉ phục vụ kiểm thử, không phải giá nhập hàng thực tế.
- Mỗi SKU có phiếu `Opening` qua `InventoryService.declare_opening`; lý do ghi rõ batch và dữ liệu mẫu. Không cập nhật trực tiếp `StockQuantity`/`CostPrice` qua CRUD biến thể.
- SKU mẫu dùng mặc định không quản lý Serial/IMEI; không tạo Serial/IMEI giả. Quyền và quy tắc Serial/IMEI hiện có không thay đổi.
- Giá, tồn và thời hạn bảo hành trong bộ mẫu cần được cửa hàng rà lại trước khi dùng cho bán hàng thực tế; dữ liệu nguồn không tự trở thành chính sách của VieTech.

## Kiểm tra và nhập lại

Tại thư mục gốc project, PowerShell:

```powershell
# Chỉ kiểm tra, không ghi database
.venv\Scripts\python.exe -X utf8 backend\scripts\import_sample_catalog.py

# Nhập dữ liệu đã kiểm tra
.venv\Scripts\python.exe -X utf8 backend\scripts\import_sample_catalog.py --apply
```

Importer kiểm tra manifest đủ 200 dòng, SKU/slug/mẫu sản phẩm không trùng, URL đúng nguồn, cấu trúc schema hợp lệ và dữ liệu đang có trước khi ghi. Toàn bộ lần nhập nằm trong một transaction: có lỗi thì rollback. Chạy lại batch đã nhập chỉ bỏ qua SKU đã có; không đặt lại tồn, giá hoặc nội dung đã được sử dụng.

Kết quả chạy và bản chụp catalog trước khi nhập nằm trong `output/catalog-import-20261017/` trên máy phát triển. Không ghi tài khoản, mật khẩu hoặc khóa kết nối vào các file kết quả.

## Kết quả trên database đang cấu hình

- Đã thêm 200 sản phẩm, 200 SKU, 200 ảnh mặc định và 200 phiếu `Opening`; thêm 7 danh mục và 43 thương hiệu, tái sử dụng các mục đang có.
- Sau nhập: 201 sản phẩm, 202 SKU, 204 ảnh sản phẩm, 10 danh mục (gồm danh mục con cũ), 46 thương hiệu. Các sản phẩm mới thuộc 9 danh mục gốc.
- Đã đối chiếu 13 dòng catalog cũ với bản chụp trước nhập: không thay đổi. Các SKU mới có giá khớp manifest và tồn mẫu tổng 2.000 đơn vị; điểm/số đánh giá và số đã bán bằng 0.
- API quản trị và công khai đều đọc được đủ sản phẩm; kiểm tra lọc danh mục và chi tiết đại diện của cả 9 nhóm đạt.
- Chạy lại importer: bỏ qua 200 SKU đã có, không thêm sản phẩm/phiếu kho và không đặt lại tồn.
- Chrome trên máy tính và điện thoại: ảnh đại diện từ cả CellphoneS và GearVN tải được, nút mua khả dụng với tồn mẫu, trang chủ có sản phẩm; không có lỗi JavaScript hoặc tràn ngang trong các trang đã kiểm tra.
