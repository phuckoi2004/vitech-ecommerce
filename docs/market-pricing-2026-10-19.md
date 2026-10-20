# Đối chiếu giá thị trường và bố cục giá — 19/10/2026

**Đã có cập nhật tiếp theo:** người dùng yêu cầu cặp giá gạch ngang/giá bán khớp nhà bán lẻ và giảm từ giá vốn hiện tại. Bảng đang áp dụng được mô tả ở [giá niêm yết, giá bán và giá vốn mẫu mới](retail-list-and-sample-cost-2026-10-19.md). Tài liệu này lưu bằng chứng của bước rà giá trước đó.

Đã đọc lại trang sản phẩm công khai của CellphoneS/GearVN cho **201 sản phẩm**, đối chiếu **459 biến thể** đang bán theo đúng mẫu, cấu hình và màu. Đã cập nhật **45 biến thể thuộc 21 sản phẩm**; 413 biến thể đã khớp giá nên giữ nguyên. Một biến thể Anker Soundcore C50i màu Tím chưa có giá công khai đúng màu, giữ giá hiện tại để rà tiếp.

## Nguồn và cách tính

- Giá tham khảo là giá bán công khai của sản phẩm mới trên trang chi tiết, không cộng ưu đãi thành viên, thu cũ, trả góp, ngân hàng hoặc mã riêng. Với CellphoneS, giá chính trên HTML được kiểm tra khớp JSON-LD; giá từng màu lấy từ liên kết màu tương ứng. Với GearVN dùng Offer VND của đúng sản phẩm.
- Đối chiếu tên mẫu/cấu hình với tên trong catalog sau khi bỏ hậu tố tiếp thị `| Chính hãng...`; không lấy giá bản RAM/bộ nhớ khác. Bốn nhãn màu tương đương được rà rõ: S26 Đen ↔ Đen Classic, Redmi Note 14 Pro+ Vàng ↔ Vàng chỉ tại CPS, Lenovo Legion Tab Gen 5 Trắng/Đen ↔ mã máy kèm màu tương ứng.
- Chỉ cập nhật `ProductVariants.Price`. Đây là cơ sở **trước chương trình Automatic đang cấu hình ở VieTech**; giá khách thấy vẫn là `SalePrice` sau chương trình hợp lệ. Không lấy giá gạch ngang cao hơn từ nhà bán lẻ để tạo mức giảm mới trong hệ thống. Các chương trình và coupon hiện có không bị chỉnh sửa.
- Giữ nguyên `CostPrice` và tồn kho. Từ chối giá cơ sở dưới vốn/chưa có vốn. Bộ tính giá tiếp tục bỏ qua chương trình Automatic khiến giá sau giảm dưới vốn; phần trăm hiển thị tính từ cặp giá thực tế của cùng SKU.
- Ví dụ Samsung Galaxy S26 256GB: tham khảo [CellphoneS](https://cellphones.com.vn/dien-thoai-samsung-galaxy-s26.html) tại 22.090.000đ; kiểm tra thêm [FPT Shop](https://fptshop.com.vn/dien-thoai/samsung-galaxy-s26) tại 21.990.000đ. Chọn nguồn CellphoneS trong batch nhất quán theo từng màu. Bản Xanh ở VieTech có giá 20.090.000đ sau Automatic 2 triệu; bản Đen giữ 22.090.000đ sau kiểm tra vốn, không hiển thị mức giảm không áp dụng được.
- Nguồn thiết bị khác: [GearVN — Logitech G304 X Superlight Black](https://gearvn.com/products/chuot-gaming-khong-day-logitech-g304-x-superlight-black), [CellphoneS — iPhone 16 Pro Max 256GB](https://cellphones.com.vn/iphone-16-pro-max.html). Có kiểm tra chéo cấu hình [MacBook Air M4 13 16GB/256GB ở FPT Shop](https://fptshop.com.vn/may-tinh-xach-tay/macbook-air-13-m4-2025-10cpu-8gpu-16gb-256gb).
- Nguồn [Anker C50i ở CellphoneS](https://cellphones.com.vn/tai-nghe-bluetooth-anker-soundcore-c50i.html) ghi “Giá liên hệ” cho bản Tím; không áp giá bản Trắng/Đen sang bản này.

Giá chỉ phản ánh thời điểm đối chiếu và khu vực mặc định của trang nguồn, không phải đồng bộ tự động hằng ngày.

## File để kiểm tra

- [Bảng trước/sau của 459 SKU](data/market-prices-2026-10-19.csv): giá cũ, giá tham khảo, giá sau Automatic, phần trăm giảm, trạng thái và đường dẫn nguồn của biến thể.
- [Manifest](../backend/data/market-pricing-2026-10-19.json): 201 trang tham khảo, thời điểm đọc, SHA-256 HTML và phép ghép 459 SKU.
- [Script cập nhật](../backend/scripts/reprice_catalog_from_market.py): mặc định dry-run, kiểm tra toàn bộ danh tính/cấu hình/giá trước khi ghi, phát hiện kế hoạch cũ, khóa SKU và ghi trong một transaction qua service hiện có. Script chỉ chấp nhận bằng chứng mới tối đa 3 ngày; sau đó phải thu thập/rà lại nguồn.

```powershell
.venv\Scripts\python.exe backend\scripts\reprice_catalog_from_market.py
.venv\Scripts\python.exe backend\scripts\reprice_catalog_from_market.py --apply
```

Bản chụp trước cập nhật và báo cáo có trong `output/market-pricing-20261019/`: `before-*.json`, `applied.json`, `applied.csv`, `preview.json`. Đã chạy lại chế độ xem trước: **0 giá cần đổi**, 458 biến thể khớp và 1 màu chưa có giá.

## Giao diện và kiểm chứng

- Các ô danh mục ở trang chủ dùng cùng nền xanh nhạt, gồm ô Tai nghe.
- Thẻ sản phẩm: giá bán đỏ ở hàng chính; giá trước giảm gạch ngang và nhãn `-x%` nằm cạnh nhau ở hàng dưới, không phủ nhãn giảm lên ảnh. Các trang dùng chung ProductCard (trang chủ, danh sách, liên quan, yêu thích) cùng nhận bố cục này.
- Chi tiết sản phẩm: khối giá nền hồng nhạt, giá bán nổi bật, giá gạch ngang và phần trăm liền nhau, phía dưới là số tiền tiết kiệm và hạn áp dụng.
- Backend: **4 kiểm thử đạt**, gồm dry-run không ghi giá/tồn, cập nhật chỉ Price/chạy lại không đổi, phát hiện giá đã bị sửa và không áp giá thị trường dưới vốn. Kiểm thử dùng SQLite cô lập.
- Frontend: **75 kiểm thử đạt** ở ProductCard, ProductPage, HomePage và catalog-api; lint JS liên quan không có lỗi/cảnh báo; Vite production build thành công.
- Batch thật xác nhận không thay đổi các cột khác của catalog hoặc phiếu tồn đầu kỳ so với snapshot. Không tạo/sửa giỏ, thanh toán hoặc đơn hàng.
- Chrome desktop/mobile kiểm tra hàng giá ở 1440/390/320 px, các ô danh mục cùng màu, chọn màu S26 đổi đúng giá và bỏ nhãn giảm khi không đủ điều kiện vốn. Báo cáo/ảnh nằm trong `output/market-pricing-20261019/`.
