# Kiểm kê và chuẩn hóa catalog — chỉ đề xuất

Giai đoạn A ngày 29/10/2026 giữ nguyên schema, cột, ID, SKU, slug và toàn bộ khóa/cấu trúc JSONB. Chỉ tạo file đề xuất thay giá trị kỹ thuật hiện có, chưa cập nhật Supabase.

Báo cáo, CSV trước/sau và JSON đề xuất nằm tại `output/catalog-standardization/` (thư mục ignored). Mở `catalog-validation-report.md` trước, sau đó xem từng dòng `catalog-changes.csv`. Không dùng `catalog-cleaned.json` để import đè database.

## Công cụ

- `backend/scripts/audit_catalog_specs.py`: dùng kết nối backend hiện có, SELECT catalog trong transaction `REPEATABLE READ, READ ONLY`; kiểm tra chế độ server và rollback. Tái sử dụng serializer kiểm kê `fingerprint` của `enrich_sample_catalog.py`, không chạy phần import/cập nhật.
- `backend/scripts/catalog_standardization.py`: xử lý snapshot offline, chuẩn hóa scalar, kiểm tra nguồn, bảo toàn mọi khóa/kiểu/media, thử các bộ đọc AI và xuất CSV/JSON.
- `backend/data/catalog-standardization-evidence-2026-10-29.json`: từng giá trị đã rà soát, định danh chính xác, trước/sau, nguồn, ngày và phạm vi model/khu vực. Các dòng manual không cho phép sửa nội dung.
- `backend/tests/test_catalog_standardization.py`: bảo toàn dữ liệu, từ chối bằng chứng sai snapshot/model, chặn sửa trá hình dưới nhãn định dạng và xác nhận không có chế độ apply.

Giá vốn không được xuất chi tiết; chỉ lưu fingerprint để đối chiếu. Không truy vấn tài khoản, đơn hàng hoặc giao dịch.

## Chạy lại trên bản chụp đã có

Từ root:

```powershell
.\.venv\Scripts\python.exe -X utf8 backend\scripts\audit_catalog_specs.py --input output\catalog-standardization\catalog-original.json --evidence backend\data\catalog-standardization-evidence-2026-10-29.json --validate-consumers
```

Lệnh trên chạy offline. Thêm `--verify-live` để SELECT lại và kiểm tra fingerprint với database; vẫn không ghi dữ liệu. Các báo cáo CSV/JSON được tạo lại. Báo cáo Markdown bàn giao ghi nhận kết quả đã chạy và cần cập nhật nếu làm một đợt kiểm kê mới.

Để chụp một đợt mới, dùng thư mục kết quả mới:

```powershell
.\.venv\Scripts\python.exe -X utf8 backend\scripts\audit_catalog_specs.py --capture --output output\catalog-standardization-next --validate-consumers
```

Không cung cấp evidence cũ cho snapshot khác. Mỗi thay đổi nội dung cần rà soát nguồn và giá trị gốc mới; công cụ từ chối snapshot/evidence không khớp. Manifest nhập mẫu chỉ được tham khảo URL khi slug và SKU đều khớp, không cung cấp thông số thay thế.

## Kiểm thử

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_catalog_standardization.py tests/test_catalog_standardization_artifacts.py -q
Pop-Location
```

`test_catalog_standardization_artifacts.py` kiểm tra bộ đề xuất thật trong `output/catalog-standardization/` bằng bộ so sánh riêng và được bỏ qua khi chưa có artifact. Chuẩn hóa định dạng bị chặn (`format_shifts_ai_window`) nếu khoảng trắng thêm vào đẩy nội dung ra ngoài phần chat đọc (160 ký tự) hoặc Smart Compare đọc (200 ký tự). Kết quả kiểm định độc lập xem trong `CLAUDE_DATA_AUDIT_REPORT.md`.

Không chạy migration, không bật test PostgreSQL ghi dữ liệu và không chạy các script import/enrichment với `--apply` để kiểm tra nhiệm vụ này. Công cụ giai đoạn A không ghi database. Giai đoạn B đã được thực hiện theo yêu cầu ngày 29/10/2026 bằng lệnh riêng cho danh sách 468 thay đổi sau kiểm định; xem [kết quả, backup và cách hoàn tác](catalog-standardization-phase-b.md).
