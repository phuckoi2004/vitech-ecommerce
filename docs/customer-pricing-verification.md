# Kết quả kiểm tra giá ưu đãi — 19/10/2026

- Backend: **1.185 passed, 109 skipped, 655 subtests passed**. Các kiểm thử PostgreSQL opt-in không được bật; bộ suite dùng SQLite cô lập/fake và kiểm tra biên dịch SQL PostgreSQL. Pytest chạy với thư mục tạm mới trong workspace vì quyền thư mục tạm của sandbox Windows.
- Frontend liên quan trực tiếp: **150 passed** (sản phẩm, trang chủ, coupon công khai, quản trị khuyến mãi/coupon, bộ định dạng giá).
- Chạy rộng toàn frontend: **913 passed, 1 failed** trong 78 file. Trường hợp lỗi là kiểm thử thời gian của bộ lọc bảo hành `WarrantiesPage.test.jsx` (không sửa file này); chạy lại riêng cả file **9/9 passed**. Không báo toàn bộ frontend là xanh tuyệt đối từ lần chạy rộng đó.
- Vite production build thành công; lint không có lỗi, còn hai cảnh báo có sẵn ở `useAdminQuery.js` và `AdminTable.jsx`.
- Migration thật: CSDL ứng dụng đã lên `82d6f1a9b407`, thêm `Promotions.ApplyMode` và CHECK, mặc định Coupon.
- Dữ liệu thử thật: thêm **10 chương trình, 5 coupon**, gồm 5 nhóm giảm trực tiếp áp dụng **201 sản phẩm**. Chạy lại script tạo thêm **0 chương trình, 0 coupon**; không đặt lại lượt sử dụng.
- Kiểm tra chỉ đọc trên PostgreSQL ứng dụng: lọc công khai 28.500.000–29.000.000đ trả đúng 2 sản phẩm và giá sau giảm thấp nhất của mỗi sản phẩm nằm trong khoảng lọc.
- Chrome headless ở kích thước desktop: trang chủ có mã công khai; trang chi tiết có giá gốc/giá mới/phần trăm; xem thử `TEST300K` và sao chép không trừ lượt; danh sách có badge và giá gạch ngang. Không có JavaScript page error, không phát sinh request ghi `/cart`, `/orders`, `/payments`.
- Ví dụ đã xác nhận trên trang thật: iPhone 16 Pro Max 256GB, **30.990.000đ → 28.990.000đ (6,45%) → 28.690.000đ** sau xem thử `TEST300K`.

Báo cáo và ảnh nằm trong `output/pricing/`: `seed-applied.json`, `seed-rerun.json`, `browser-report.json`, `home-offers.png`, `product-top.png`, `product-offer.png`, `catalog-discounts.png`.

Phần giỏ hàng/thanh toán/tạo đơn được giữ nguyên theo phạm vi yêu cầu. Xem hợp đồng tích hợp ở [customer-pricing-promotions.md](customer-pricing-promotions.md).

## Bổ sung bốn ô ưu đãi theo Figma

- Đọc design context và screenshot của `Category Promos` node `917:1708`; dùng lại bố cục, token và CTA có sẵn. Thay số lượng sản phẩm bằng mức giảm tự động thực tế, không gán các mức mẫu 30%/50%/5 triệu.
- Kiểm thử liên quan sau bổ sung: backend **22 passed** (`test_category_offers.py`, `test_automatic_pricing.py`), frontend **36 passed** (`HomePage.test.jsx`, `catalog-api.test.js`). Lint các file JS liên quan không có lỗi/cảnh báo; production build thành công.
- PostgreSQL thật: kết quả tổng hợp khớp cách tính độc lập bằng `variant_price` cho cả **9 danh mục gốc**, gồm số sản phẩm còn hàng, mức giảm tiền và phần trăm tối đa. Không ghi CSDL trong lần đối chiếu này.
- Chrome headless: kiểm tra ở **1440, 1024, 390, 320 px**, không tràn ngang trang, chữ ưu đãi và nút nằm trong thẻ. Nút Laptop mở `/danh-muc/laptop`; không có JS page error hoặc request ghi giỏ/đơn/thanh toán.
- Dữ liệu hiện tại: Điện thoại **8,69%**, Laptop **2 triệu**, Máy tính bảng **8,51%**, Tai nghe **17,54%**. Hai danh mục mẫu Phụ kiện/Gia dụng thông minh chưa tồn tại nên dùng các danh mục thật kế tiếp.
- Ảnh và báo cáo: `output/pricing/category-promos-{1440,1024,390,320}.png`, `category-promos-report.json`, script `verify-category-promos.mjs`.
