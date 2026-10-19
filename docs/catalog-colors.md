# Màu sắc cho bộ sản phẩm mẫu

Sau bước nhập màu bên dưới, đã có đợt [rà lại màu/ảnh và mô tả](catalog-color-review.md) ngày 18/10/2026 để sửa ảnh chung của phiên bản gốc, màu Lenovo và ảnh S26 bị lẫn Ultra. Các con số bên dưới ghi nhận lần thêm SKU màu ban đầu.

Áp dụng vào database đang cấu hình ngày 18/10/2026. Màu và giá theo màu lấy từ trang nguồn của từng sản phẩm mẫu ([CellphoneS](https://cellphones.com.vn/), [GearVN](https://gearvn.com/)) cùng ngày.

## Kết quả

- 161 sản phẩm được gán màu cho SKU đang có. SKU này giữ nguyên ID, giá, tồn, giá vốn và lịch sử kho; chỉ đổi `Color` và `VariantName` (`Màu · Dung lượng`).
- 257 SKU màu mới trên 107 sản phẩm. Mỗi SKU mới có:
  - giá theo màu trên trang nguồn, nguồn không ghi giá thì lấy giá sản phẩm;
  - ảnh riêng của màu đó (ảnh CDN CellphoneS 358×358, đã kiểm tra tải được). Ảnh được thêm vào thư viện sản phẩm và chỉ hiện khi chọn màu đó;
  - phiếu `Opening` 10 đơn vị, giá vốn mẫu bằng 80% giá tham khảo, giống bộ mẫu ban đầu.
- SKU mới có dạng `<SKU gốc>-<MÃ MÀU>`, ví dụ `VT-DEMO-20261017-C5C5AAE68AEE-XANH-LA`.
- Sau khi nhập: 201 sản phẩm, 459 SKU, 461 ảnh, 457 phiếu kho. Chạy lại script không tạo thêm gì.

## Không thay đổi

- 21 màn hình và 3 bàn phím GearVN: trang nguồn không có lựa chọn màu.
- 8 bàn phím: trang nguồn liệt kê loại switch, không phải màu.
- Laptop Lenovo IdeaPad Slim 3 14AHP10: SKU đang lưu màu Đen, nguồn ghi Xám; giữ nguyên để không ghi đè.
- 6 chuột GearVN đã có màu từ trước (GearVN tách mỗi màu thành sản phẩm riêng). Samsung Galaxy S26 do người dùng nhập giữ nguyên.

Giá, tồn và màu là dữ liệu tham khảo để thử mua hàng; cần rà lại trước khi bán thật.

## Trang chi tiết

Sản phẩm không có dung lượng (tai nghe, loa, chuột…) trước đây lấy tên biến thể làm “Phiên bản”, nên mỗi màu thành một phiên bản riêng. Nay phần màu trong tên được bỏ khi tạo nhãn phiên bản, nên các màu cùng một mẫu nằm chung một phiên bản.

## Nhập lại

```powershell
# Kiểm tra, không ghi database
.venv\Scripts\python.exe -X utf8 backend\scripts\add_sample_colors.py

# Ghi dữ liệu
.venv\Scripts\python.exe -X utf8 backend\scripts\add_sample_colors.py --apply
```

Manifest: [`backend/data/catalog-colors-2026-10-18.json`](../backend/data/catalog-colors-2026-10-18.json). Script dùng các service Admin trong một transaction và lưu bản chụp dữ liệu vào `output/catalog-colors-2026-10-18/` trước khi ghi. Nếu SKU, màu hoặc danh sách biến thể của sản phẩm đã đổi sau khi chuẩn bị, sản phẩm đó được bỏ qua.
