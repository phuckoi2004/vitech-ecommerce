# Giá niêm yết, giá bán và giảm giá vốn mẫu — 19/10/2026

> **Cập nhật 20/10/2026:** theo yêu cầu người dùng, giá niêm yết không còn hiện gạch ngang. Giá niêm yết của 438 biến thể được chuyển thành giá bán (`Price`) và `CompareAtPrice` được để trống; khi có khuyến mãi giảm trực tiếp, giá bán này mới bị gạch ngang cạnh giá sau giảm.

Đã cập nhật **459 biến thể của 201 sản phẩm** theo yêu cầu mới. Giá bán công khai khớp trang nguồn cho **458 biến thể**; **433 biến thể có giá niêm yết công khai** để lưu riêng và hiện gạch ngang. Những biến thể nguồn không niêm yết giá cũ sẽ không tự tạo giá gạch. Anker C50i màu Tím vẫn dùng giá bán đang có vì nguồn ghi “Giá liên hệ”; giá vốn của nó vẫn giảm theo nhóm đã chốt.

## Cặp giá đúng theo nguồn

- Dùng bằng chứng CellphoneS/GearVN đã đọc trong ngày 19/10. Đã đọc thêm **46 trang màu riêng** khi giá màu khác màu mặc định, kiểm tra đúng `product_id` và giá đang hiển thị để lấy giá niêm yết của màu đó. Một số trang CellphoneS vẫn để JSON-LD của màu mặc định; khi đó chỉ chấp nhận giá HTML nếu ID màu đang chọn, giá chính và giá của màu cùng khớp.
- Ví dụ [iPhone 16 Pro Max 256GB tại CellphoneS](https://cellphones.com.vn/iphone-16-pro-max.html): niêm yết **34.990.000đ**, bán **30.990.000đ**, tính ra **11,43%**. Các màu hiện có cùng cặp giá.
- Ví dụ [Logitech G304 X Superlight Black tại GearVN](https://gearvn.com/products/chuot-gaming-khong-day-logitech-g304-x-superlight-black): niêm yết **2.390.000đ**, bán **1.790.000đ**, tính ra **25,1%**.
- Giá là ở thời điểm kiểm tra và khu vực mặc định của nhà bán lẻ, không phải đồng bộ giá hằng ngày.

Migration **`93e7a2b0c518`** thêm một cột nullable `ProductVariants.CompareAtPrice`, không thêm bảng. Cột này lưu giá niêm yết; `Price` lưu giá bán cơ sở. Giá niêm yết không được thấp hơn giá bán. Phải lưu riêng vì hai màu của cùng sản phẩm có thể có mức giảm khác nhau.

Khách dùng `OriginalPrice`/`SalePrice` của cùng SKU; phần trăm nằm cạnh giá niêm yết gạch ngang. Form quản trị biến thể có ô Giá niêm yết để kiểm tra/chỉnh/bỏ giá này. Không lấy giá bán đã giảm làm giá gạch rồi giảm thử thêm một lần nữa.

Đã **hủy 5 Automatic thử** mang tiền tố `[TEST] public-pricing-test-v1`; giữ chương trình qua mã, giới hạn lượt và lịch sử coupon. Automatic mới vẫn dùng được như giảm bổ sung trên `Price`, tính đúng vốn và thời gian. Coupon tính trên `SalePrice`; báo giá tổng giảm trực tiếp từ `OriginalPrice` đến `SalePrice`, sau đó mới trừ coupon.

## Giảm từ giá vốn hiện tại

Người dùng đã xác nhận: **trừ trực tiếp từ giá vốn đang có**, không đặt vốn bằng giá bán trừ một mức lãi. Nhóm giá xét theo giá bán công khai:

| Giá bán | Trừ khỏi giá vốn cũ | Số biến thể |
|---|---:|---:|
| Dưới 500.000đ | 50.000đ | 63 |
| Từ 500.000đ đến dưới 2 triệu | 100.000đ | 70 |
| Từ 2 triệu đến dưới 5 triệu | 300.000đ | 92 |
| Từ 5 triệu đến dưới 10 triệu | 500.000đ | 51 |
| Từ 10 triệu đến dưới 20 triệu | 1.000.000đ | 75 |
| Từ 20 triệu trở lên | 1.500.000đ | 108 |

Tất cả giá vốn sau sửa đều **dương và thấp hơn giá bán**. Đây là hiệu chỉnh **giá vốn mẫu của bài/test**, không phải giá nhập được thu thập từ nhà cung cấp. Ví dụ vốn mẫu iPhone 16 Pro Max giảm **24.792.000đ → 23.292.000đ**; giá bán **30.990.000đ**, lãi gộp mẫu **7.698.000đ** trước coupon và các chi phí khác.

Chỉ sửa giá niêm yết, giá bán và vốn hiện tại của đúng SKU đã rà. Không sửa số lượng tồn, Serial/IMEI, phiếu tồn đầu kỳ/nhập hàng, `OrderItems.UnitCost`, thanh toán hoặc đơn hàng. Catalog CRUD vẫn từ chối ghi giá vốn. Script hiệu chỉnh riêng được phép ghi vốn mẫu theo yêu cầu cụ thể, lưu đầy đủ bản trước/sau; không bổ sung đường sửa vốn tự do trong app.

## Truy vết và chạy lại

- [Manifest dữ liệu](../backend/data/retail-list-and-sample-cost-2026-10-19.json): giá/vốn trước và sau, nguồn, thời điểm đọc, SHA-256 HTML.
- [Bảng đối chiếu SKU](data/retail-list-and-sample-cost-2026-10-19.csv): giá gạch, giá bán, vốn cũ/mới, phần trăm và lãi gộp mẫu. File dùng cho người quản trị dự án; API khách không trả giá vốn/lãi.
- [Script hiệu chỉnh](../backend/scripts/apply_retail_prices_and_sample_costs.py): mặc định chỉ xem trước; `--apply` khóa SKU, kiểm tra toàn bộ kế hoạch, chụp trước thay đổi và commit nguyên batch. Giá/cấu hình/vốn thay đổi ngoài kế hoạch sẽ dừng. Chỉ hủy đúng Automatic thử đã ghi trong manifest.
- Snapshot và báo cáo thật nằm trong `output/retail-list-cost-20261019/`: `before-*.json`, `applied.json`, `applied.csv`, `preview.json`, `color-references.json`.

Đã chạy lại chế độ xem trước: **0 thay đổi giá, 0 thay đổi giá niêm yết, 0 thay đổi vốn**, không trừ vốn lần nữa. Bằng chứng giá chỉ được dùng trong 3 ngày; sau đó cần rà lại trước khi chạy batch mới.

## Kiểm tra

- Backend đầy đủ: **1.215 passed, 109 skipped, 655 subtests passed**; gồm cặp giá theo SKU, tổng báo giá/coupon, bộ lọc theo giá bán, chặn niêm yết dưới giá bán, giới hạn vốn, hiệu chỉnh nguyên batch và chạy lại không giảm vốn lần hai.
- Frontend liên quan: 75 kiểm thử khách/catalog đạt. File quản trị ProductsPage có một lần timeout tải trang trong lần chạy chung; chạy lại riêng **31/31 đạt**. Lint các JS liên quan không lỗi/cảnh báo; production build thành công.
- Migration thật đã lên `93e7a2b0c518`. Batch thật sửa vốn 459 SKU, thêm giá niêm yết cho 433 SKU và hủy 5 Automatic thử. Đối chiếu snapshot xác nhận các cột catalog khác và toàn bộ phiếu tồn đầu kỳ giữ nguyên.
- Ảnh và báo cáo Chrome ở `output/retail-list-cost-20261019/`, kiểm tra desktop/mobile, giá gạch và phần trăm cùng hàng, coupon không trừ lượt khi xem thử, không có thao tác ghi giỏ/đơn/thanh toán.
