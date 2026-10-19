# Ghi chú cần xử lý chung: Chương trình khuyến mãi và Mã giảm giá

## Quyết định hiện hành — cập nhật ngày 17/10/2026

Người dùng đã cho phép sửa backend/API và kiểm thử cho các mục dưới đây. Không sửa cấu trúc CSDL, không sửa frontend khách hàng, không ghi dữ liệu thử vào CSDL thật.

- Promotion Scheduled/Active tự theo giờ máy chủ: trước ngày bắt đầu là Scheduled, trong thời gian là Active, qua ngày kết thúc là Expired. Draft và Cancelled vẫn do admin quyết định.
- Coupon chỉ có Đang áp dụng, Chưa bắt đầu, Hết lượt, Hết chương trình. Bỏ tạm ngừng và ô tự chỉnh trạng thái. IsActive do backend tính: chỉ true khi Đang áp dụng. Mẹ bị hủy cũng khiến mã Hết chương trình; mẹ hết hạn ưu tiên cao hơn hết lượt.
- API trả Status và EvaluatedAt cho mã. Admin dùng trạng thái máy chủ, không dùng đồng hồ máy khách để quyết định mã có áp dụng được không. Form chỉ xem trước; backend kiểm tra lại khi lưu/đặt hàng.
- Đồng bộ cột Status/IsActive khi API quản lý được gọi; khi khách áp mã, kiểm tra lại hiệu lực bằng giờ máy chủ mà không cần admin mở trang trước. Không có cron chạy nền để ghi cột đúng thời điểm nếu hoàn toàn không có request.
- Dùng hết lượt: đặt IsActive=false ngay trong giao dịch tạo đơn. Hủy đơn hợp lệ trả lượt và mở lại mã nếu chương trình còn hiệu lực. Tăng giới hạn cũng tự tính lại trạng thái.
- PATCH Promotion nhận cả thông tin và ProductIds/CategoryIds trong một giao dịch. Bất kỳ bước nào lỗi đều rollback toàn bộ. Frontend gửi một request, giữ form khi lỗi để thử lại; Hủy trước khi gửi hoặc sau khi lưu lỗi không ghi dữ liệu. Trong lúc gửi, khóa đóng/bấm lặp; Hủy không phải thao tác hoàn tác một lần lưu đã thành công.
- Chi tiết cả hai loại hiển thị người tạo và ngày tạo từ API; không có ô tự nhập.
- Coupon đã có đơn tham chiếu vẫn không xóa được. Bỏ gợi ý tạm ngừng; có thể xử lý chương trình mẹ nếu muốn kết thúc cả chương trình.
- Danh sách/chi tiết tự đọc lại mỗi 30 giây và khi quay lại cửa sổ. Không tự đọc lại form đang nhập.
- Chưa xác minh PostgreSQL thật vì TEST_DATABASE_URL chưa được cấu hình. Kiểm thử HTTP/repository/giao dịch và luồng tạo chương trình → mã → đặt đơn → dùng lượt → hủy trả lượt chạy trên SQLite tạm cô lập.

## Lịch sử ghi chú trước khi xử lý

Giữ nguyên ghi chú cũ bên dưới để đối chiếu. Những mô tả về tạm ngừng, hai lần lưu và phải tự chuyển Scheduled đã được thay thế bằng quyết định hiện hành ở trên.

Ghi nhận ngày 17/10/2026. Giữ lại đúng các lưu ý đã rà soát; làm trang Mã giảm giá trước, sau đó xử lý chung hai trang. Các mục dưới đây chưa phải yêu cầu thay đổi backend/CSDL đã được duyệt.

1. **Chương trình đang `Active`** chỉ sửa được tên, mô tả và trạng thái. Mức giảm, thời gian, điều kiện và phạm vi bị khóa theo backend.
2. **Đã có Coupon liên kết thì không xóa được.** Giao diện sẽ cho chọn “Hủy chương trình”; việc này khiến các mã thuộc chương trình ngừng áp dụng.
3. **“Đã lên lịch” chưa tự chuyển sang “Đang diễn ra”.** Hiện admin phải đổi trạng thái; backend chỉ chấp nhận chương trình `Active` và trong thời hạn. Hết hạn thì mã bị từ chối dù nhãn trạng thái có thể chưa đổi.
4. **Tạo chương trình chưa đủ để khách được giảm:** vẫn cần Coupon đang bật thuộc chương trình đó, theo luồng đã chốt.
5. **Sửa phạm vi và sửa thông tin là hai lần gọi API.** Có thể phạm vi đã lưu nhưng thông tin lưu thất bại; giao diện có thông báo rõ trường hợp này và cho thử lại.

## Phạm vi đã chốt cho bước làm Mã giảm giá

- Giữ dropdown Khuyến mãi với hai mục Chương trình khuyến mãi và Mã giảm giá.
- Giữ nguyên quan hệ một Promotion có nhiều Coupon; không tự tạo mã mặc định hoặc đổi sang 1–1.
- Promotion lưu điều kiện/mức giảm/thời hạn/phạm vi. Coupon lưu mã, chương trình liên kết, giới hạn lượt, số lượt đã dùng và bật/tắt.
- Khách phải áp mã; chưa triển khai giảm tự động hay tự cấp mã theo điều kiện khách hàng.
- Chỉ sửa frontend admin. Mọi thay đổi backend, CSDL hoặc phần mã nguồn khác phải hỏi trước.

## Điểm nối cần nhớ khi rà soát cả hai trang

- Đổi điều kiện của một chương trình ảnh hưởng mọi mã thuộc chương trình đó.
- Coupon bật không đồng nghĩa mã đang đủ điều kiện dùng: còn phụ thuộc trạng thái/thời gian chương trình, lượt còn lại và điều kiện đơn.
- Coupon đã có đơn hàng tham chiếu không xóa cứng được; dùng tắt mã. Không tự chuyển xóa thành tắt khi chưa có hành động xác nhận của admin.

## Mẫu danh sách Mã giảm giá đã nhận ngày 17/10/2026

- Figma: https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=791-1141
- Thay cột Loại giảm bằng Lượt sử dụng: `UsedCount/UsageLimit` (ví dụ `0/100`). Nếu giới hạn NULL thì hiện `x/∞`; giới hạn 0 vẫn hiện `0/0`.
- Giá trị giảm, đơn tối thiểu và thời gian hiển thị từ Promotion mẹ; trạng thái bật/tắt dùng riêng `Coupon.IsActive`.
- Giữ dropdown sidebar Khuyến mãi đã chốt, không chuyển lại menu cũ trong Figma.
- Backend hiện tăng lượt khi tạo đơn có áp mã thành công, không tăng khi xem thử mã; hủy đơn hợp lệ trả lại lượt. Có khóa dòng và kiểm tra giới hạn ở backend.
- Bước này chỉnh trang danh sách theo mẫu; các mẫu chi tiết/thêm/sửa sẽ theo hướng dẫn tiếp theo của người dùng.

## Form và trạng thái Coupon đã chốt tiếp ngày 17/10/2026

- Mẫu chi tiết: node `894:1876`; mẫu form dùng chung thêm/sửa: node `894:1913`.
- Tên mã (`Name`) và mã khách nhập (`Code`) là hai ô riêng. Chọn Promotion có thật trong dropdown; nếu không có chương trình thì danh sách lựa chọn trống, không chèn mục “Không có gì”.
- Loại giảm, giá trị, đơn tối thiểu, giảm tối đa, ngày bắt đầu/kết thúc và mô tả hiển thị trực tiếp từ chương trình mẹ trong ô nền xám chỉ đọc. Không gửi các trường này vào API Coupon.
- Giới hạn lượt do admin nhập; lượt đã dùng do backend quản lý. Nút lưu chỉ bật khi có chương trình mẹ và các trường bắt buộc hợp lệ.
- “Điều chỉnh trạng thái” có Theo chương trình mẹ (`IsActive=true`) và Tạm ngừng (`IsActive=false`). Các nhãn trạng thái còn lại được tính khi hiển thị, không thêm cột/enum vào CSDL.
- Thứ tự hiển thị: Hết hạn (theo ngày kết thúc hoặc trạng thái mẹ) → Tạm ngừng → Hết lượt (UsedCount >= UsageLimit, kể cả 0/0) → Đã hủy (chương trình bị hủy) → Đang áp dụng/Chưa bắt đầu theo chương trình mẹ.
- Người dùng đã xác nhận: ngày bắt đầu/kết thúc đều theo chương trình mẹ. Mã đang Tạm ngừng KHÔNG tự trở lại Đang áp dụng khi mẹ bắt đầu. Khi mẹ hết hạn, mã PHẢI hiện Hết hạn kể cả đang Tạm ngừng. Admin vẫn có thể chủ động thay đổi điều chỉnh trạng thái.
- Không tự chuyển Promotion từ Scheduled sang Active. Việc giải quyết trạng thái chương trình mẹ vẫn thuộc 5 lưu ý cần xử lý chung ở đầu file.
- Nhãn theo thời gian cập nhật khi trang đang mở. Danh sách và chi tiết đọc lại dữ liệu mỗi 30 giây và khi quay lại cửa sổ; không tự đọc lại rồi làm mất dữ liệu của form đang nhập.

## Hoàn thiện đủ thao tác Coupon

- Đã nhận lại mẫu thêm `894:1913` và mẫu xác nhận xóa `894:2019`; chi tiết dùng `894:1876`. Thêm và sửa dùng chung form, khác tiêu đề/nút lưu và dữ liệu ban đầu.
- Popup thêm 680×850; popup chi tiết 650×690; popup xác nhận xóa 460×280. Đều hiện trên danh sách với nền sau tối và mờ.
- Sửa nhãn sai “Xóa khuyến mãi” của mẫu xóa thành “Xóa mã giảm giá”. Hiển thị mã được chọn để nhận biết đúng dữ liệu sắp xóa.
- Chỉ gọi DELETE sau khi xác nhận; chống bấm lặp và khóa đóng trong lúc đang gửi. Hủy giữ nguyên dữ liệu và bộ lọc danh sách.
- Khi API báo `coupon_in_use`, giữ nguyên mã; chỉ tạm ngừng nếu admin chủ động bấm “Tạm ngừng mã”. Mã đã tạm ngừng thì không hiện hành động này lần nữa.
- Đủ các thao tác thêm, sửa, xóa, xem chi tiết ở frontend. 5 lưu ý xử lý chung đầu file vẫn còn nguyên, chưa đánh dấu đã giải quyết.
