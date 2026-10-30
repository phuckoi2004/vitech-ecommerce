# Chuẩn hóa catalog — giai đoạn B

Ngày 29/10/2026 đã áp dụng danh sách sau kiểm định độc lập: **468 giá trị Specifications trên 163 sản phẩm**, gồm 457 thay đổi định dạng và 11 sửa/diễn giải thông số có evidence. Không sử dụng bản 488 thay đổi đã được thay thế.

Run đã commit lúc **09:00:40 +07:00**, được xác nhận bằng SELECT lúc **09:00:58 +07:00**:

`output/catalog-standardization/phase-b/20261029-085813-018ceabb/`

Xem `phase-b-report.md`, `receipt.json` và `verification.json` trong thư mục trên. Artifact chứa dữ liệu catalog nên nằm trong thư mục ignored, không được commit. Các file và báo cáo giai đoạn A được giữ nguyên.

## Phạm vi dữ liệu

Lệnh chỉ SET `Products.Specifications`, giữ nguyên khóa, cấu trúc, kiểu dữ liệu và `_vietech_variant_media`. Trigger `UpdatedAt` sẵn có chạy bình thường cho 163 sản phẩm. Không có DDL/migration, thêm bảng/cột/thuộc tính, thêm/xóa bản ghi, sửa SKU/slug/ID/danh mục/hãng, tên, bảo hành, giá, giá vốn hoặc tồn kho.

Giá trị chưa xác minh không được tự điền. Các thay đổi bị loại trong kiểm định độc lập, bao gồm Xiaomi Pad 8 Pro và 19 chuỗi có nguy cơ bị cắt nội dung trong cửa sổ đọc AI, được giữ nguyên. Trạng thái unknown của Compatibility vẫn tuân theo dữ liệu có bằng chứng.

## Cách lệnh bảo vệ dữ liệu

`backend/scripts/apply_catalog_standardization.py` là lệnh riêng; công cụ giai đoạn A vẫn chỉ đọc. `--prepare` kiểm tra đề xuất, evidence, các bộ đọc AI và dữ liệu live, đóng băng input với SHA-256, lưu bản sao trước ghi trong một thư mục mới. Bắt buộc truyền số thay đổi và sản phẩm được duyệt.

`--apply` kiểm tra lại hash và đúng đích database. Trong transaction REPEATABLE READ, lệnh khóa sản phẩm theo thứ tự ID, từ chối mọi chỉnh sửa mới trên sản phẩm mục tiêu, lưu backup bền vững, rồi chạy một batch UPDATE có điều kiện khớp toàn bộ Specifications gốc và UpdatedAt. Đối chiếu mọi trường của năm bảng catalog, schema và fingerprint giá vốn trước khi commit. Nếu một dòng không khớp hoặc một kiểm tra thất bại, toàn bộ transaction rollback.

Lệnh chỉ ghi Specifications đã được kiểm tra từ các dòng vừa khóa. Không import toàn bộ `catalog-cleaned.json`. Giá và tồn kho thay đổi độc lập kể từ giai đoạn A được giữ theo giá trị live trước transaction.

Nếu mất phản hồi COMMIT, receipt mang trạng thái `commit_unknown`; chỉ dùng `--verify` để đọc lại, không chạy lại UPDATE. Lệnh apply từ chối một run đã thực hiện. `--verify` và `--prepare` đều chỉ đọc database.

## Xác nhận kết quả đã áp dụng

Từ root, lệnh sau chỉ SELECT:

```powershell
.\.venv\Scripts\python.exe -X utf8 backend\scripts\apply_catalog_standardization.py --verify output\catalog-standardization\phase-b\20261029-085813-018ceabb
```

Receipt `committed_verified` cùng `MatchesCommittedTargetRows: true` xác nhận các dòng mục tiêu khớp trạng thái sau commit. Nếu dữ liệu sau đó được sửa hợp lệ, lần verify tiếp theo có thể báo khác; không dùng artifact cũ để ghi đè.

## Hoàn tác khi được yêu cầu

**Không thực hiện hoàn tác trong đợt này.** Lệnh sau sẽ ghi database và chỉ dùng khi cần hủy thay đổi của run:

```powershell
.\.venv\Scripts\python.exe -X utf8 backend\scripts\apply_catalog_standardization.py --rollback output\catalog-standardization\phase-b\20261029-085813-018ceabb
```

Rollback kiểm tra hash backup và trạng thái đã commit, khóa lại cùng các dòng, yêu cầu mọi trường và UpdatedAt trên sản phẩm mục tiêu còn khớp bản sau apply. Chỉ khôi phục Specifications gốc trong một transaction; giá, tồn kho và dữ liệu bảng khác lấy theo trạng thái hiện tại. Nếu có chỉnh sửa mới, rollback dừng toàn bộ. UpdatedAt tiếp tục được trigger cập nhật, không khôi phục timestamp cũ.

Sau rollback, dùng `--verify <thư mục run> --verify-rollback`. Backup và receipt hoàn tác dùng tên riêng, không ghi đè backup apply.

## Kiểm thử

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_apply_catalog_standardization.py tests/test_catalog_standardization.py tests/test_catalog_standardization_artifacts.py -q
Pop-Location
```

Kết quả trước khi ghi: **114 passed**. Test giao dịch dùng mô phỏng offline, bao gồm lỗi giữa chừng, CAS không khớp, chỉnh sửa mới, COMMIT mất phản hồi, bảo toàn giá/tồn kho/media và rollback không ghi đè dữ liệu mới. Không chạy test ghi lên PostgreSQL dùng chung. Giao dịch thực tế và SELECT xác nhận được ghi riêng trong receipt.

## Bổ sung dữ liệu sau giai đoạn B

Đợt 4 ngày 30/10/2026 đã áp dụng thêm **6 chuỗi cổng kết nối trên 6 sản phẩm**, trạng thái `committed_verified`. Đợt này dùng cùng quy trình backup/CAS/đối chiếu; 145 kiểm thử dữ liệu đạt trước ghi. Xem [chi tiết dữ liệu cổng đợt 4](catalog-port-data-round4.md). Các số liệu 468/163 ở đầu tài liệu là lần chuẩn hóa ban đầu, không phải tổng cộng dồn các lần bổ sung.

Theo yêu cầu bổ sung mô tả và thông số, lúc 17:06 ngày 30/10/2026 đã mở rộng **203 mô tả** và cập nhật **30 giá trị kỹ thuật trên 14 sản phẩm**. Đợt này cho phép sửa `Description`, giữ nguyên toàn bộ tên khóa Specifications và schema. Đã đọc xác nhận với trạng thái `committed_verified`, xem [bản bổ sung và bằng chứng kiểm tra](catalog-details-enrichment-20261030.md).

Lúc 18:49 cùng ngày, theo yêu cầu tránh lặp bảng thông số, đã gỡ mục `Thông số kỹ thuật chi tiết` khỏi **203 mô tả**, giữ phần giới thiệu, ảnh và toàn bộ thông số vừa bổ sung. Lần ghi này chỉ sửa `Description`, đã xác nhận `committed_verified`, 70 kiểm thử đạt và 4 trang sản phẩm được kiểm tra trên trình duyệt thật. Công cụ bổ sung mô tả cũng không còn tự chèn danh sách thông số.

Lúc 19:34 cùng ngày, đã bổ sung hoặc làm rõ **49 giá trị trong thuộc tính hiện có của 32 sản phẩm**, chỉ sửa `Specifications`. Đọc lại xác nhận `committed_verified` lúc 19:36, schema, khóa JSON và toàn bộ mô tả giữ nguyên. Xem [đợt bổ sung các thông số còn thiếu](catalog-completion-20261030.md), gồm 150 kiểm thử đạt, API của 32 sản phẩm, 4 trang trên trình duyệt và kiểm kê còn 278 cờ cần rà soát.

Lúc 20:22 cùng ngày, đã bổ sung **38 mô tả và 4 giá trị thông số hiện có**, giữ nguyên bảng, cột và mọi khóa thuộc tính. Trọng lượng, RAM, camera trước, hệ điều hành và switch chưa có ô riêng được đặt ở đúng phần mô tả, không ghép vào ô khác nghĩa và không thêm bảng thông số lặp. Đã đọc lại xác nhận `committed_verified`, 181 kiểm thử đạt, API của 38 sản phẩm và 6 trang trình duyệt đều đạt. Xem [chi tiết cập nhật nội dung và run xác nhận mới nhất](catalog-narrative-completion-20261030.md).

Lúc 20:53 cùng ngày, đã cập nhật **7 mô tả**, gồm bổ sung RAM cho 5 mẫu và thu gọn chi tiết chưa xác nhận riêng tại Việt Nam của HONOR, Huawei. Toàn bộ 8 sản phẩm có cờ thiếu khóa RAM đều đã có dung lượng trong mô tả. Đã đối chiếu 10 sản phẩm, 201 kiểm thử đạt, API của 10 sản phẩm và 7 trang trình duyệt đều đạt. Giữ nguyên toàn bộ Specifications, bảng và cột. Xem [bằng chứng Việt Nam và run xác nhận mới nhất](catalog-vietnam-verification-20261030.md).
