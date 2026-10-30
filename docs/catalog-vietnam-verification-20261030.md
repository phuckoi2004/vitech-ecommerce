# Hoàn thiện RAM và đối chiếu phiên bản Việt Nam

Đã ghi **7 mô tả sản phẩm** vào VieTech `stkvyiqosljeehbkqteb` lúc **20:53:14 +07:00 ngày 30/10/2026**, đọc lại xác nhận lúc **20:54:50 +07:00**. Receipt `committed_verified`. Chỉ cập nhật `Description` và `UpdatedAt` do trigger hiện có, câu UPDATE không ghi `Specifications` trong đợt này.

## RAM đã hoàn thiện

| Sản phẩm | RAM | Kết quả |
| --- | --- | --- |
| iPhone 17 256GB | 8 GB | Bổ sung trong phần hiệu năng |
| iPhone 17 Pro Max 512GB | 12 GB | Bổ sung trong phần hiệu năng |
| iPhone 18 Pro 1TB | 12 GB | Bổ sung trong phần hiệu năng |
| iPhone 18 Pro Max 1TB | 12 GB | Bổ sung trong phần hiệu năng |
| iPad A16 Wi-Fi 256GB 2025 | 6 GB | Bổ sung trong phần hiệu năng |
| iPhone Air 256GB | 12 GB | Đối chiếu Việt Nam, giữ nội dung đã đúng |
| iPhone 16e 128GB | 8 GB | Đối chiếu Việt Nam, giữ nội dung đã đúng |
| iPhone 17 Pro 256GB | 12 GB | Đối chiếu Việt Nam, giữ nội dung đã đúng |

Toàn bộ **8 sản phẩm có cờ thiếu khóa RAM** trong bản kiểm kê trước đợt này đều đã có giá trị RAM trong mô tả. Không thêm khóa RAM mới để xóa cờ kiểm kê. Số cờ `missing_key` của công cụ chỉ kiểm tra JSON có thể vẫn giữ nguyên, thông tin mới nằm trong phần hiệu năng theo yêu cầu.

## Cơ sở đối chiếu Việt Nam

Đối chiếu theo tên máy, chip, dung lượng lưu trữ và niêm yết bản chính hãng Việt Nam. Không dùng màu sắc hoặc tên SKU nội bộ VieTech làm bằng chứng về phần cứng, không chép cấu hình SIM, pin hoặc phụ kiện của bản Mỹ sang bản Việt Nam.

- **iPhone 17, Air, 17 Pro và 17 Pro Max** có ô RAM trong niêm yết FPT Shop đúng cấu hình, lần lượt 8, 12, 12 và 12 GB. SKU FPT tương ứng là 00921654, 00921698, 00921741 và 00921804. Đối chiếu [17 256 GB](https://fptshop.com.vn/dien-thoai/iphone-17), [Air 256 GB](https://fptshop.com.vn/dien-thoai/iphone-air), [17 Pro 256 GB](https://fptshop.com.vn/dien-thoai/iphone-17-pro) và [17 Pro Max 512 GB](https://fptshop.com.vn/dien-thoai/iphone-17-pro-max-512gb).
- **iPhone 16e 128 GB** được đối chiếu với [niêm yết VN/A của Di Động Việt](https://didongviet.vn/dien-thoai/iphone-16e.html), No.0042793, RAM 8 GB khớp bản nhận diện chip đã dùng trước đó. Không dùng ô RAM đang rỗng ở trang FPT làm bằng chứng.
- **iPad A16 Wi-Fi 256 GB** được đối chiếu [đúng cấu hình tại Thế Giới Di Động](https://www.thegioididong.com/may-tinh-bang/ipad-11-wifi-256gb), SKU 210283, có RAM 6 GB. Không lấy thông số của bản 5G, iPad Air hoặc iPad Pro.
- **Hai mẫu iPhone 18 Pro 1 TB** được xác nhận đúng cấu hình bán tại Việt Nam qua [Pro SKU 00930916](https://fptshop.com.vn/dien-thoai/iphone-18-pro?sku=00930916) và [Pro Max SKU 00930838](https://fptshop.com.vn/dien-thoai/iphone-18-pro-max?sku=00930838), cùng [trang Apple Việt Nam](https://www.apple.com/vn/iphone-18-pro/specs/). Dung lượng 12 GB lấy từ [bản kiểm tra trực tiếp Xcode 27 của MacRumors](https://www.macrumors.com/2026/09/09/iphone-18-pro-and-pro-max-ram/), nơi người thực hiện xác nhận riêng cả Pro và Pro Max. Ô RAM trong phần thông số có cấu trúc của hai trang FPT đang rỗng, không diễn giải ô rỗng thành 12 GB.

Apple không công bố dung lượng RAM iPhone trên các trang thông số Việt Nam đã đối chiếu. Đây là đối chiếu niêm yết bản Việt Nam với bằng chứng phần cứng hoặc phần mềm, **không phải phép đo trên một máy VN/A do dự án trực tiếp thực hiện**, không ghi thành xác nhận RAM do Apple công bố. Không suy diễn thông số của iPhone Duo từ chip chung.

## Hai phần mô tả được thu gọn

- **HONOR Pad V9 Wi-Fi 8 GB, 256 GB**, giữ camera trước 8 MP được đối chiếu với [bài đánh giá tại Việt Nam](https://fptshop.com.vn/tin-tuc/danh-gia/danh-gia-honor-pad-v9-213467). [Trang HONOR Việt Nam](https://www.honor.com/vn/tablets/honor-pad-v9/spec/) trỏ tới [đúng cấu hình bán tại CellphoneS](https://cellphones.com.vn/may-tinh-bang-honor-pad-v9-wifi.html), có RAM 8 GB và ROM 256 GB. Bỏ riêng khẩu độ f/2.0 và lấy nét cố định của camera trước vì chưa có xác nhận riêng đủ rõ ở nguồn Việt Nam. Giữ nguyên khẩu độ f/2.0 của camera sau đã có trong thông số, không sửa nhầm hai camera và không chép RAM Turbo của Malaysia.
- **Huawei MatePad 11.5 S 2026**, giữ RAM 12 GB, ROM 256 GB và HarmonyOS 4.3 từ [Huawei Việt Nam](https://consumer.huawei.com/vn/tablets/matepad-11-5-s-2026/specs/) và [niêm yết đúng bản kèm bàn phím](https://cellphones.com.vn/may-tinh-bang-huawei-matepad-11-5-s-2026.html). Tên Kirin T92C được đối chiếu với [bài kiểm tra tại Việt Nam](https://didongviet.vn/dchannel/cau-hinh-huawei-matepad-11-5-s-2026/), không chuyển sang Kirin 9000WL từ các nội dung thiếu rõ ràng về thế hệ máy. Bỏ số “6 nhân” trong mô tả vì trang Huawei Việt Nam không công bố riêng bộ xử lý, không tiếp tục khẳng định số lõi cho mã đang bán chỉ từ nguồn Hà Lan.

Hai thay đổi này thu gọn chi tiết chưa đối chiếu riêng, không kết luận phần cứng Việt Nam khác phần cứng quốc tế.

## Bảo toàn và kiểm tra

Không thêm bảng, cột, khóa JSON, kiểu giá trị hoặc bản ghi sản phẩm. Toàn bộ `Specifications` của **203 sản phẩm** giữ nguyên, cùng **464 biến thể, 50 danh mục, 46 thương hiệu và 656 ảnh**. ID, SKU, slug, giá, giá vốn, tồn kho, danh mục, thương hiệu và ảnh trong mô tả không đổi. Giữ nguyên thứ tự tiêu đề, không thêm bảng hoặc danh sách thông số lặp vào mô tả. Nội dung mới không có dấu chấm phẩy.

- **201 kiểm thử đạt**, gồm đối chiếu nguồn Việt Nam, nguồn giả mạo, dung lượng đúng phiên bản, ô RAM nguồn bị rỗng, bảo toàn camera sau, cấu trúc JSON, CAS và giao dịch.
- Schema phản hồi của **203 sản phẩm và 464 biến thể** hợp lệ trước ghi, cả 8 mục RAM có trong mô tả đề xuất.
- Một transaction ghi đúng 7 mô tả sau khi khóa và kiểm tra bản ghi chưa bị sửa, có backup trước UPDATE và chặn áp dụng lặp.
- Đọc lại toàn bộ catalog khớp bản sau giao dịch, schema và dấu kiểm tra giá vốn không đổi.
- SELECT độc lập qua Supabase xác nhận **10/10 mô tả**, **10/10 tập khóa thông số**, **8/8 giá trị RAM** và không có phần thông số chi tiết lặp.
- API thật của **10 sản phẩm** trả đúng nội dung, thông số và ảnh giữ nguyên. Kiểm tra **7 trang** trên Chrome ở kích thước máy tính và điện thoại, thấy các đoạn mới, không lỗi JavaScript và không tràn ngang.

## Bàn giao

- Evidence có thể commit: `backend/data/catalog-vietnam-evidence-2026-10-30.json`, gồm 7 cập nhật và 10 bản đối chiếu Việt Nam.
- Công cụ: `backend/scripts/enrich_catalog_details.py`, chỉ cho phép các nguồn Việt Nam đã duyệt và đúng bản báo cáo Xcode được dẫn, giữ nguyên xác minh plan lịch sử.
- Kiểm thử: `backend/tests/test_catalog_vietnam_content.py` và phần bổ sung trong `backend/tests/test_enrich_catalog_details.py`.
- Backup, plan, receipt và xác nhận: `output/catalog-vietnam-verification-20261030/runs/20261030-204820-9cf05ecf/`.
- Nguồn công khai đã lưu và checksum: `output/catalog-vietnam-verification-20261030/sources/`.
- RAM của cả 8 sản phẩm: `output/catalog-vietnam-verification-20261030/ram-completeness.json`.
- Website: `output/catalog-vietnam-verification-20261030/browser-verification.json`.
- SELECT độc lập: `output/catalog-vietnam-verification-20261030/independent-database-verification.json`.

`output/` được gitignore, không đưa backup toàn catalog vào commit. Chưa commit hoặc push.

Lệnh chỉ đọc để xác nhận run mới nhất:

```powershell
.\.venv\Scripts\python.exe -X utf8 backend\scripts\enrich_catalog_details.py --verify output\catalog-vietnam-verification-20261030\runs\20261030-204820-9cf05ecf
```

Run đã commit, không chạy lại `--apply`. Các run trước là lịch sử, dùng run này để xác nhận hiện trạng mới nhất. Bảng so sánh có cấu trúc chưa được đổi cách đọc RAM từ mô tả, đợt này chỉ bổ sung nội dung và không thêm thuộc tính so sánh.
