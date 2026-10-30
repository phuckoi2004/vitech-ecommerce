# Bổ sung thông số cổng đợt 4 — 30/10/2026

Đã ghi **6 giá trị `Products.Specifications` trên 6 sản phẩm** vào database VieTech, commit giao dịch lúc **08:35:23 +07:00**, đọc xác nhận lúc **08:37:15 +07:00**. Receipt có trạng thái `committed_verified`.

Không thêm bảng, cột, migration hoặc khóa Specifications. Chỉ sửa chuỗi của thuộc tính `Cổng kết nối` đã có. Giá, giá vốn, tồn kho, SKU, tên sản phẩm, ảnh và media riêng giữ nguyên; trigger cập nhật `UpdatedAt` của đúng 6 sản phẩm.

| Sản phẩm | Dữ liệu đã bổ sung | Nguồn hãng |
|---|---|---|
| LG 27G610A-B | HDMI 2.0 nhận tối đa 2560×1440 @ 144 Hz; DP 1.4 nhận tối đa 2560×1440 @ 200 Hz | [LG: bảng tín hiệu đầu vào](https://www.lge.co.kr/monitors/27g610a) |
| LG 24U631A-B | HDMI 2.0 và USB-C nhận tối đa 2560×1440 @ 100 Hz; giữ PD 15 W | [LG: bảng tín hiệu đầu vào](https://www.lge.co.kr/monitors/24u631a) |
| LG 24U411A-B | D-Sub tối đa 1920×1080 @ 75 Hz; HDMI 2.0 tối đa 1920×1080 @ 120 Hz | [LG: bảng tín hiệu đầu vào](https://www.lge.co.kr/monitors/24u411a) |
| Dell U2424H | DP 1.4 đầu vào tối đa 1920×1080 @ 120 Hz; giữ nguyên DP Out/MST và USB chỉ dữ liệu | [Dell U2424H: thông số cổng](https://www.dell.com/en-us/shop/dell-ultrasharp-24-monitor-u2424h-without-stand/apd/210-bkzb/monitors-monitor-accessories) |
| ASUS ZenScreen MB169CK | Bổ sung 2 USB-C DP Alt Mode bị thiếu; cả USB-C và Mini HDMI nhận 1920×1080 @ 60 Hz | [ASUS: hướng dẫn, trang PDF 23 và 26](https://dlcdnets.asus.com/pub/ASUS/LCD%20Monitors/MB169CK/ASUS_MB169CK_English.pdf?model=MB169CK) |
| ViewSonic VA2708-2K-MHD | HDMI 2.0 và DP 1.4 nhận tối đa 2560×1440 @ 100 Hz | [ViewSonic: hướng dẫn, trang PDF 27–28](https://www.viewsonicglobal.com/public/products_download/user_guide/display/VA2708-2K-HD_VA2708-2K-MHD/VA2708-2K-HD_VA2708-2K-MHD_UG_ENG.pdf) |

Đúng model LG có hậu tố `-B` được đối chiếu thêm với trang sản phẩm/support LG quốc tế. Chỉ sử dụng số liệu cổng của cùng nền tảng phần cứng; không chép bảo hành hoặc phụ kiện theo thị trường. Manual ViewSonic ghi HDMI 2.0 còn trang giới thiệu hiện ghi 2.1: đợt này giữ 2.0 theo manual/cấu hình catalog, không tự nâng phiên bản. Không gán tần số tối đa của panel cho mọi cổng.

## Kết quả Compatibility

Đối chiếu cùng 35 laptop và 23 màn hình thực, tổng 805 cặp. Hai giá treo cơ khí không nằm trong thống kê kết nối video. Quy tắc R4b và giới hạn cáp vẫn giữ nguyên; đây là kết quả từ catalog/rule engine, không phải thử phần cứng.

| Yêu cầu | Chạy trực tiếp trước → sau | Cần chuyển đổi trước → sau | Không đạt trước → sau | Chưa đủ dữ liệu trước → sau |
|---|---:|---:|---:|---:|
| Kết nối cơ bản | 595 → 605 | 210 → 200 | 0 → 0 | 0 → 0 |
| 1080p60 | 70 → 130 | 70 → 110 | 0 → 0 | 665 → 565 |
| 1440p144 | 0 → 0 | 10 → 15 | 85 → 255 | 710 → 535 |
| 4K60 | 8 → 8 | 10 → 10 | 120 → 325 | 667 → 462 |
| 4K144 | 0 → 0 | 5 → 5 | 200 → 381 | 600 → 419 |

Số cặp 4K chạy được không tăng trong đợt này vì các màn hình được bổ sung có giới hạn FHD/QHD. Các cặp trước đây chưa đủ dữ liệu nay có thể kết luận không đạt 4K từ giới hạn đầu vào đã xác minh.

## Chứng cứ và kiểm tra

- Evidence có thể commit: `backend/data/catalog-port-evidence-round4-2026-10-30.json`.
- Test mới: `backend/tests/test_catalog_port_round4.py`, 15 ca, gồm phân biệt HDMI/DP, DP Out, USB dữ liệu, Mini HDMI/USB-C, nguồn hãng và các URL giả mạo.
- 145 kiểm thử dữ liệu đạt trước khi ghi, gồm kiểm tra quy trình transaction/CAS/rollback và bảo toàn trường khác.
- Snapshot, backup, receipt, manifest và SELECT sau ghi: `output/catalog-port-data-4/phase-b/20261030-082208-71c45b7f/`.
- `verification.json`: `MatchesCommittedTargetRows`, `SchemaUnchanged`, `WholeCatalogMatchesTransactionAfter` và `CostFingerprintMatchesTransactionAfter` đều `true`.
- Đọc lại độc lập qua Supabase connector xác nhận 6 chuỗi cổng đúng database VieTech.
- `output/catalog-port-data-4/compatibility-before-after.json`: kết quả ma trận trước/sau.

Kiểm tra toàn bộ workspace sau cập nhật:

- Backend: **2.417 passed, 138 skipped**, 728 subtests passed; các test PostgreSQL có điều kiện vẫn không ghi lên database dùng chung.
- Frontend: **1.370/1.370 passed**, 104 file test, chạy với tối đa 2 worker.
- Vite production build đạt. Lint trả mã 0; còn hai cảnh báo có sẵn ở `useAdminQuery.js` và `AdminTable.jsx`.
- `git diff --check` đạt. Không tạo commit hoặc push trong phiên này.

Khi commit cần thêm cả các file mới đang untracked của AI/Compatibility, bộ dữ liệu evidence, script và test; `git commit -am` đơn lẻ sẽ bỏ sót các file đó. Những chỉnh sửa có sẵn trong workspace được giữ nguyên.

`output/` tiếp tục được gitignore; không đưa snapshot toàn catalog, backup hoặc tài liệu hãng tải xuống vào commit. Dữ liệu thật đã được ghi riêng, không cần chạy migration khi commit mã nguồn. Các artifact giai đoạn A trước đó giữ nguyên làm lịch sử.

Lệnh xác nhận sau này, chỉ SELECT:

```powershell
.\.venv\Scripts\python.exe -X utf8 backend\scripts\apply_catalog_standardization.py --verify output\catalog-port-data-4\phase-b\20261030-082208-71c45b7f
```

Không chạy lại `--apply` cho run đã commit. Nếu sau này có chỉnh sửa hợp lệ, verify có thể báo khác; không dùng snapshot cũ để ghi đè.

## Các giới hạn giữ lại

Acer Swift Air 14 đã có bằng chứng DisplayPort qua USB-C nhưng manual đúng model chưa nêu độ phân giải/Hz tối đa. LG 25G523-B chưa có tài liệu tín hiệu đúng model đọc được. Các trang ASUS VG27AQ5F, VU249CFE-P và Xiaomi A27I/QI 2026 đã đọc chỉ có độ phân giải panel và dải tần số riêng, chưa đủ xác nhận một tổ hợp hình ảnh cho từng cổng. Apple M4 có số liệu không thống nhất giữa trang tech specs và một số bản địa hóa bài 122212; giữ dữ liệu trước đó thay vì chọn số cao hơn.

Các mục này tiếp tục trả kết quả chưa đủ dữ liệu khi yêu cầu vượt chứng cứ hiện có. Không điền số đoán để tăng tỷ lệ tương thích.
