# VIETECH — Mục lục tài liệu

Bổ sung ngày 18/10/2026. Thư mục này chứa tài liệu dùng chung cho frontend, backend, dữ liệu và kiểm thử. Việc bổ sung mục lục không di chuyển, xóa hoặc viết lại các tài liệu đã có.

## Đọc phần nào trước?

1. Đọc [bản bổ sung hiện hành ngày 18/10/2026](updates/2026-10-18-admin.md), nhất là khi làm phần admin.
2. Đọc tài liệu nghiệp vụ, phân quyền, CSDL và API tương ứng trong bảng dưới. Những file có nội dung cũ được nối thêm ghi chú ở cuối, giữ nguyên phần gốc để đối chiếu.
3. Đối chiếu với schema request/response, service, model và migration trong source. Bản mô tả kỹ thuật không tự chứng minh cấu trúc hoặc dữ liệu của CSDL thật đang chạy.
4. Các quyết định mới được người dùng chốt và ghi trong phần bổ sung thay thế quy tắc cũ tương ứng. Với phần chưa được đề cập, tiếp tục dùng tài liệu gốc. Nếu có khác biệt chưa được giải thích, ghi rõ để chốt, không tự sửa nghiệp vụ hay chạy migration.

## Nghiệp vụ, dữ liệu và API

| Tài liệu | Mục đích |
|---|---|
| [business-requirements.md](business-requirements.md) | Nghiệp vụ và kiến trúc Service Layer; đọc thêm phụ lục cho quyết định mới |
| [requirements-revision.md](requirements-revision.md) | Các nội dung từng chỉnh so với báo cáo; giữ lại lịch sử quyết định |
| [database-schema.md](database-schema.md) | Cột, kiểu, quan hệ và ràng buộc; phần nghiệp vụ/constraint đã thay đổi được bổ sung ở cuối |
| [api-endpoints.md](api-endpoints.md) | Danh sách endpoint; phụ lục bổ sung hợp đồng API và endpoint mới/đang tạm dừng |
| [auth-rbac.md](auth-rbac.md) | Vai trò, quyền cố định và phạm vi tài khoản; đọc thêm phụ lục bảo hành/đổi trả |
| [auth-spec.md](auth-spec.md) | Đặc tả xác thực, phiên, OTP và tài khoản |
| [auth-setup.md](auth-setup.md) | Chạy backend/frontend, cấu hình xác thực và Storage; thay đường dẫn ví dụ bằng thư mục thực tế |
| [internal-endpoints.md](internal-endpoints.md) | Webhook và tác vụ nội bộ; không phải API để frontend tự gọi |

## Các trang frontend

| Tài liệu | Mục đích |
|---|---|
| [admin-dashboard.md](admin-dashboard.md) | Tổng quan và nền tảng admin ở giai đoạn đầu; có phụ lục về các trang đã làm tiếp |
| [admin-products.md](admin-products.md) | Product/Variant, SKU và thao tác admin; có phụ lục lựa chọn ảnh theo biến thể |
| [customer-product-detail.md](customer-product-detail.md) | Trang sản phẩm phía khách; phụ lục phân biệt dữ liệu ảnh API đã có với việc UI đã sử dụng |
| [customer-product-reviews.md](customer-product-reviews.md) | Gửi/sửa/đọc đánh giá phía khách và giới hạn hiện có |
| [customer-wishlist.md](customer-wishlist.md) | Yêu thích và chọn biến thể khi thêm giỏ |

Tài liệu bàn giao admin chi tiết đã có tại [admin-implementation.md](../frontend/src/admin/docs/admin-implementation.md) và [bản Word](../frontend/src/admin/docs/admin-implementation.docx). Hai file vẫn được giữ nguyên vị trí. Ghi chú riêng khuyến mãi nằm ở [promotion-coupon-notes.md](../frontend/src/admin/docs/promotion-coupon-notes.md); các ghi chú lịch sử trong đó cần đọc cùng quyết định hiện hành.

## Biên bản triển khai và kiểm thử theo thời điểm

| Tài liệu | Cách đọc |
|---|---|
| [stage4-stage5-integration.md](stage4-stage5-integration.md) | Lịch sử ghép giai đoạn và migration tại thời điểm ghi nhận |
| [stage6-concurrency-fixes.md](stage6-concurrency-fixes.md) | Các lỗi đồng thời đã xử lý và kiểm thử lúc đó |
| [stage6-postgres-validation.md](stage6-postgres-validation.md) | Kết quả các ca PostgreSQL tại ngày xác minh được ghi trong file |
| [stage7-api-testing.md](stage7-api-testing.md) | Cách tổ chức và phạm vi kiểm thử API của giai đoạn 7 |

Giữ nguyên các biên bản này. Số test đạt, head migration và mô tả workflow trong biên bản là thông tin theo thời điểm, không phải kết quả kiểm thử lại ngày 18/10/2026 hoặc cam kết cho toàn bộ bản hiện tại.

## Phạm vi chưa chốt hoặc để sau

- Cách tổ chức menu/trang lịch sử thanh toán đang chờ người dùng cân nhắc; không thay đổi trong lần cập nhật tài liệu này.
- Luồng hoàn tiền gắn với đổi trả và luồng trung tâm bảo hành/duyệt kết quả độc lập đang tạm dừng theo quyết định hiện hành; giữ code, trường dữ liệu và ghi chú để xem xét sau.
- Xuất báo cáo và các bộ lọc tài khoản/nhà cung cấp của báo cáo đã được yêu cầu bỏ khỏi giao diện hiện tại. Không tự mở lại chỉ vì tài liệu giai đoạn trước có đề cập.

## Bổ sung ngày 20/10/2026

- [Xóa mềm danh mục/thương hiệu, quyền và xóa chứng từ phiếu nhập](updates/2026-10-20-catalog-purchases.md): quyết định mới, cách frontend gọi backend, thay đổi CSDL đã áp dụng và lưu ý revision CSDL khác source. Đọc phần này để cập nhật các mô tả hủy/xóa phiếu cũ; giữ nguyên nội dung lịch sử phía trên.

- Đề xuất bổ sung nhận hàng nhiều đợt vào báo cáo: [bản Word](updates/2026-10-20-purchase-receiving-spec.docx) và [bản Markdown](updates/2026-10-20-purchase-receiving-spec.md). Đây là tài liệu đề xuất riêng, chưa thay nội dung báo cáo gốc.

## Bổ sung ngày 21/10/2026

- [Tìm đơn, luồng trạng thái, quyền người phụ trách, thông báo đơn mới và quyền đánh giá/tin tức/banner](updates/2026-10-21-admin-orders-content.md). Bổ sung hiện hành cho 3.26, 3.29 và 3.33–3.36; ghi rõ phần bảo hành/đổi trả giữ lại và giới hạn phía khách.

