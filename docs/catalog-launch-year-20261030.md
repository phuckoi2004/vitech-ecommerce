# Bổ sung năm ra mắt vào thông số sản phẩm

Đã ghi **119 sản phẩm** vào database VieTech `stkvyiqosljeehbkqteb`, giữ nguyên **42 sản phẩm** đã có `Thời điểm ra mắt`. Hiện **161/203 sản phẩm** có năm hoặc thời điểm ra mắt. **42 sản phẩm còn thiếu**, chưa điền khi chưa xác nhận được đúng mẫu hoặc phiên bản.

Không thêm bảng hoặc cột database. Thông tin mới là mục `Năm ra mắt` dạng chuỗi bốn chữ số trong JSON `Products.Specifications` hiện có. Không lặp lại năm trong mô tả, không tạo thêm mục năm khi đã có tháng và năm ra mắt.

## Các giao dịch đã hoàn thành

| Đợt | Sản phẩm bổ sung | Thời điểm commit, giờ Việt Nam | Run |
| --- | ---: | --- | --- |
| 1 | 97 | 30/10/2026 22:40:14 | `20261030-223931-4875bc69` |
| 2 | 18 | 31/10/2026 00:04:42 | `20261031-000415-8a6dea8e` |
| 3 | 4 | 31/10/2026 00:11:57 | `20261031-001114-7f9019cd` |

Cả ba receipt đều có trạng thái `committed_verified`. Đợt 3 đọc lại xác nhận lúc **00:12:01 ngày 31/10/2026**. SELECT độc lập qua Supabase xác nhận **119 mục năm**, **42 mục thời điểm ra mắt**, **0 sản phẩm bị trùng hai mục**.

Các run nằm trong `output/catalog-launch-year-20261030/runs/`, mỗi run có snapshot trước ghi, evidence đã đóng băng, plan, manifest checksum, backup trước và sau giao dịch, receipt và kết quả đọc lại. Không áp dụng lại các run đã commit.

## Cách đối chiếu

Ưu tiên thông báo của hãng, trang hỗ trợ có trường thời điểm giới thiệu, hồ sơ sản phẩm do nhà sản xuất cung cấp và bảng thông số của niêm yết Việt Nam đúng mẫu. Thông cáo hãng được đăng trên dịch vụ phát hành thông cáo hoặc bài tường thuật trực tiếp sự kiện được lưu theo URL cụ thể đã xem xét.

Không lấy năm sản xuất từng lô, năm CPU, bản quyền, ngày cập nhật bài viết, ngày đăng driver, ngày chứng nhận hoặc bình luận làm năm ra mắt. Năm của thế hệ sản phẩm, năm bắt đầu bán và mốc riêng tại Việt Nam được ghi rõ trong `Scope` của từng evidence. Không coi ngày ra mắt một SKU nước ngoài là ngày mở bán riêng SKU Việt Nam.

Một số trường hợp cần phân biệt:

| Sản phẩm | Năm bổ sung | Cơ sở và phạm vi |
| --- | --- | --- |
| MacBook Air M2 có hậu tố bán hàng 2024 | 2022 | [Apple xác định dòng M2 là đời 2022](https://support.apple.com/en-us/111867), năm đổi RAM tiêu chuẩn không phải năm giới thiệu thiết kế |
| Acer Swift Air 14 SFA14-I31 | 2026 | [Thông báo Acer cho bản Intel Core Series 3](https://news.acer.com/acer-launches-new-swift-air-14-powered-by-latest-intel-core-series-3-processors), không dùng mốc SFA14-61M |
| Lenovo IdeaPad 14AHP10 83K9004RVN, Ryzen 7 155 | 2026 | [Niêm yết Việt Nam đúng MTM ghi 08/2026](https://www.thegioididong.com/laptop/lenovo-ideapad-slim-3-14ahp10-r7-155-83k9004rvn), không lấy năm của cấu hình 14AHP10 khác |
| ROG Azoth 96 HE | 2025 | [Thông cáo ASUS ngày 02/12/2025](https://www.mynewsdesk.com/de/asus-dach/pressreleases/asus-republic-of-gamers-announces-azoth-96-he-3422906) |
| Aura Studio 5 Bluetooth | 2025 | [Thông cáo Harman International Japan](https://prtimes.jp/main/html/rd/p/000000504.000012767.html), phân biệt bản Wi-Fi 2026 |
| Baseus EnerCore CR11 20000 mAh 67W | 2025 | [Thông cáo Baseus ngày 01/07/2025](https://www.hartware.de/2025/07/01/baseus-produktstart-drei-neue-produkte-kommen-auf-den-markt/), không dùng bản 100W |
| Targus Energy Harvesting EcoSmart AKB868 | 2023 | [Thông báo mở bán đầu 2023](https://us.targus.com/blogs/press-room/targus-launches-premium-collection-of-sustainable-ecosmart-tech-accessories), phân biệt thông báo giải thưởng trước đó tháng 11/2022 |
| Huawei MatePad 11.5 S 2026 | 2026 | [Phiếu sản phẩm Huawei, model SLG-W09](https://consumer.huawei.com/dam/content/dam/huawei-cbg-site/weu/de/v4/mkt/v5-ana/2026/new-products/tablets/MatePad-11,5-S-2026/Fiche_matepad11_5_S_2026_de.pdf), năm bắt đầu đưa ra thị trường, phân biệt công bố sớm tháng 12/2025 |
| Logitech Alto Keys K98M | 2024 | [Bài giới thiệu trực tiếp sự kiện của lãnh đạo Logitech](https://www.linkedin.com/posts/delphinedonne_innovation-china-logitech-activity-7234852926488211458-fy-e), đối chiếu dấu thời gian bài đăng tháng 8/2024 và lịch sử firmware tháng 9/2024, không lấy đợt mở rộng Bắc Mỹ 2025 |
| Soundcore C50i | 2025 | [Tường thuật và ảnh sự kiện Việt Nam](https://thanhnien.vn/soundcore-ra-mat-dong-tai-nghe-open-ear-wireless-stereo-185251103181907391.htm), không dùng mốc Nhật Bản 2026 |

Evidence đầy đủ của **119 sản phẩm** có ProductId, tên, model đối chiếu, năm, phạm vi, lý do và URL trong [catalog-launch-year-evidence-2026-10-30.json](../backend/data/catalog-launch-year-evidence-2026-10-30.json). Tên file là ngày bắt đầu đợt công việc, lần rà soát cuối ghi ngày 31/10/2026.

## 42 sản phẩm chưa điền năm

Danh sách đầy đủ và lý do riêng nằm ở `Unresolved` trong evidence, đồng thời xuất ra `output/catalog-launch-year-20261030/launch-year-unresolved.csv` với tên, ID, slug và trang niêm yết.

- Một số mẫu có nhiều đời trùng tên hoặc biến thể chưa rõ mã, như AULA AG60, F75 có dây, AKKO AG ONE Joy of Life, Asus MD100 Lite và Lenovo ThinkPad Essential.
- Một số laptop là bản cập nhật cấu hình hoặc SKU Việt Nam khác nguồn đã tìm được, như ASUS X1404VA-EB355W, Acer A715-59G-59RD, MSI Cyborg A13UC-2082VN và Modern F1MG-1225VN.
- Hồ sơ Dell P185G dùng chung DC14250 và Inspiron 5440, không lấy ngày của hồ sơ chung làm năm giới thiệu tên máy mới. Hồ sơ Modern 15 cũng có ngày thị trường dùng chung nhiều dòng, cần tiếp tục đối chiếu đúng cấu hình.
- Một số màn hình, chuột, pin dự phòng và tai nghe chưa có mốc rõ trong nguồn đã đối chiếu. Các mốc chứng nhận, tài liệu hoặc mở bán tại một thị trường khác chưa đủ để chốt cho mẫu đang bán.

Đây là phần còn thiếu năm ra mắt, không phải kết luận các thông số khác của 42 sản phẩm đều thiếu. Không thêm giá trị phỏng đoán hoặc chữ giữ chỗ vào database để làm đầy danh sách.

## Bảo toàn và kiểm tra

Đối chiếu xuyên suốt snapshot ban đầu với kết quả sau cả ba giao dịch xác nhận chỉ **119 mục `Năm ra mắt`** được thêm và `UpdatedAt` được trigger hiện có cập nhật. Toàn bộ mô tả, thông số cũ, thông tin ảnh riêng từng phiên bản, ID, slug, giá, giá vốn và tồn kho giữ nguyên.

Số lượng không đổi: **203 sản phẩm, 464 biến thể, 50 danh mục, 46 thương hiệu, 656 ảnh**. Dấu kiểm tra schema và giá vốn không đổi.

- **112 kiểm thử đạt** sau đợt 2, gồm bảo toàn thông số, chuẩn hóa, đối chiếu nội dung Việt Nam và phần so sánh chi tiết.
- **28 kiểm thử bảo toàn năm ra mắt đạt** sau khi bổ sung evidence đợt 3. Kiểm tra đúng toàn bộ nguồn thực tế, kiểu năm, trùng ngày, xung đột năm, giữ nguyên thông số và thông tin ảnh riêng.
- **203/203 API sản phẩm** trả đúng năm hoặc thời điểm ra mắt, gồm cả các sản phẩm chưa có năm. Không cần sửa frontend để đọc mục thông số mới.
- **6 lượt kiểm tra trình duyệt**, ba trang sản phẩm trên máy tính và điện thoại, xác nhận có đúng dòng năm hoặc thời điểm, không lặp mục, không lỗi JavaScript và không tràn ngang.
- Công cụ ghi khóa các sản phẩm được duyệt, đối chiếu bản ghi chưa bị sửa, cập nhật theo điều kiện CAS và kiểm tra bất biến trước commit. Nếu một bản ghi không khớp thì rollback toàn giao dịch.

## File bàn giao

- Evidence có thể commit: `backend/data/catalog-launch-year-evidence-2026-10-30.json`.
- Công cụ chỉ bổ sung năm: `backend/scripts/add_catalog_launch_year.py`.
- Kiểm thử: `backend/tests/test_catalog_launch_year.py`.
- Kết quả tổng hợp: `output/catalog-launch-year-20261030/final-verification.json`.
- Danh sách đã ghi và còn thiếu: `launch-year-applied.csv`, `launch-year-unresolved.csv` trong cùng thư mục output.
- Đối chiếu database độc lập: `independent-database-verification.json`.
- API và trình duyệt: `api-verification.json`, `browser-verification.json`, các ảnh `launch-specs-*.png`.
- Trang nguồn, checksum và các lượt đọc qua web nằm trong `sources/`, `reviewed-source-capture.json`, `reviewed-web-capture.json`, `continued-web-captures.json`. Một số website chặn tải HTML hoặc PDF trực tiếp, kết quả đọc qua web được lưu riêng, không coi lần tải bị chặn là đã có bản HTML đầy đủ.

`output/` được gitignore, không đưa backup toàn database vào commit. Chưa tạo commit hoặc push.
