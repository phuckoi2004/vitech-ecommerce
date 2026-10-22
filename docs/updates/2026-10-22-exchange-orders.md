# Luồng đổi sản phẩm theo phiếu — cập nhật 22/10/2026

Tài liệu này ghi lại quyết định mới và phần triển khai của lần làm việc ngày 22/10/2026. Nội dung cũ trong thư mục `docs` được giữ nguyên làm lịch sử; những mô tả đổi/trả hoặc hoàn tiền cũ không tự động trở thành quy tắc đang áp dụng.

## 1. Quyết định nghiệp vụ

- Yêu cầu mới chỉ có một hình thức: đổi một sản phẩm lấy một sản phẩm mới. Khách không còn chọn giữa hai phương án “Đổi” và “Trả”. Mỗi phiếu có số lượng đúng 1.
- Nếu đúng SKU khách đã mua vẫn còn hàng và đang bán: hệ thống tự chọn SKU đó để đổi mới. Khách không chọn máy khác.
- Nếu SKU cũ hết hàng hoặc đã ngừng bán: khách chọn một SKU khác trong **đúng danh mục của sản phẩm cũ**. Không chọn danh mục khác. Nếu cả danh mục hết hàng thì chờ; phiếu chưa được hoàn tất.
- Khách được thực hiện việc đổi trong giai đoạn 2–4. Nhân viên vẫn cập nhật tiến trình xử lý trên phiếu.
- Máy mới được tính khuyến mãi sản phẩm đang áp dụng. Không tạo coupon riêng cho việc đổi máy.
- Giao hàng tiêu chuẩn, phí giao hàng bằng 0.
- Máy mới rẻ hơn: không hoàn tiền chênh lệch, không giữ giá trị dư cho lần mua sau. Máy mới đắt hơn: khách thanh toán phần bù bằng QR theo luồng thanh toán hiện có.

## 2. CSDL đã thay đổi chính xác những gì?

**Chỉ bảng `Orders` có thêm cột: 2 cột, 1 khóa ngoại, không thêm bảng.** Không bỏ cột `RequestType`, không thay đổi hàng loạt các phiếu hoặc đơn lịch sử.

| Cột mới | Kiểu / giá trị mặc định | Ý nghĩa cho người dùng hệ thống |
| --- | --- | --- |
| `SourceReturnRequestId` | UUID, có thể để trống | Đơn mua bình thường để trống. Đơn đổi trả lưu ID phiếu đã sinh ra đơn này. |
| `ExchangeCreditAmount` | Số tiền `NUMERIC(15,2)`, bắt buộc, mặc định 0 | Phần giá trị máy cũ thực sự đã dùng giảm cho đơn đổi. Hệ thống tự tính; người dùng không nhập. Đơn cũ/mua bình thường có giá trị 0. |

Khóa ngoại mới: `Orders.SourceReturnRequestId` → `ReturnRequests.ReturnRequestId`, tên `FK_Orders_SourceReturnRequestId`. Không được xóa phiếu đang được đơn đổi tham chiếu.

Một phiếu có thể có nhiều lần thử tạo đơn, nhưng **chỉ được có một đơn chưa hủy**. Chỉ mục duy nhất `UX_Orders_SourceReturn_Active` áp dụng riêng cho các đơn có phiếu nguồn và chưa ở trạng thái `Cancelled`. Nhờ vậy, đơn QR hết hạn vẫn được giữ làm lịch sử và khách có thể thử lại; hai cửa sổ bấm đồng thời không thể tạo hai đơn đang hiệu lực cho một phiếu.

Hai kiểm tra mới trên bảng `Orders`:

- `CK_Orders_ExchangeCredit_Valid`: giá trị dùng đổi không âm, không lớn hơn tổng tiền giảm của đơn.
- `CK_Orders_ExchangeCredit_Source`: đơn không liên kết phiếu đổi trả thì giá trị dùng đổi phải bằng 0.

Sản phẩm mới lưu trong `OrderItems` của đơn mới. Máy cũ vẫn truy được qua phiếu → dòng đơn mua cũ → đơn cũ. Serial sử dụng bảng `ProductSerials` hiện có. Không thêm bảng voucher, coupon hay bảng serial phụ.

### Tình trạng áp dụng lên CSDL thật

**Đã áp dụng thành công ngày 22/10/2026**, sau khi người dùng và các thành viên đóng các kết nối đang giữ khóa bảng `Orders`. Đã đọc lại và xác nhận có đủ hai cột; ngay trong giao dịch áp dụng cũng đã xác nhận khóa ngoại, chỉ mục và các kiểm tra tồn tại đúng.

Hai lần trước đó gặp `lock timeout`: kết nối đang “idle in transaction” vẫn giữ khóa đọc bảng, khiến lệnh thay đổi cấu trúc không lấy được khóa. Các lần lỗi đã hoàn tác toàn bộ. Không tự ngắt kết nối của thành viên khác.

**Lưu ý lịch sử migration của nhóm:** database hiện mang revision `d7a1e5c9b304`, nhưng revision đó chưa có trong checkout này. Source có migration mới `e6a2c9d4b810`, nối sau head cũ `c3a9f5e7d206`. Vì vậy lần này chỉ chạy đúng phần DDL của migration đổi trả trong một giao dịch, **không sửa/stamp `alembic_version`** và không chạy các migration khác. Revision trên database vẫn là `d7a1e5c9b304`.

Migration có kiểm tra cấu trúc đã cài để có thể nhận lại phần bổ sung này khi lịch sử migration chung được đồng bộ sau. Việc khôi phục file revision bị thiếu/ghép lịch sử của nhóm là việc riêng; chưa tự làm trong phạm vi này. Không chạy `alembic stamp head` để che mất sự khác nhau.

File migration: `backend/alembic/versions/e6a2c9d4b810_exchange_orders.py`.

Công cụ kiểm tra an toàn: `backend/scripts/check_exchange_database.py`. Chạy bình thường chỉ đọc; `--locks` đọc thêm khóa bảng; `--apply` chỉ áp dụng phần đổi trả cho revision đã biết. Công cụ không in chuỗi kết nối, mật khẩu, dữ liệu khách hay nội dung câu SQL của phiên khác.

## 3. Hệ thống tự tính giá như thế nào?

Lấy `OrderItems.UnitPrice` của máy mua ban đầu làm mức giá trị được dùng đổi. Đây là giá gốc tại thời điểm mua, trước các khoản giảm của đơn cũ; không lấy giá bán hiện tại trong danh mục.

Gọi giá máy mới **sau khuyến mãi sản phẩm** là P, giá gốc máy cũ là C:

- Giá trị dùng đổi thực tế: `min(C, P)` → lưu `ExchangeCreditAmount`.
- Tiền khách bù: `max(P − C, 0)` → lưu `TotalAmount` của đơn mới.
- Phí giao hàng: 0.

Ví dụ máy cũ giá gốc 12 triệu, máy mới sau khuyến mãi 11 triệu: dùng đổi 11 triệu, đơn mới 0đ, 1 triệu dư không giữ lại. Máy mới sau khuyến mãi 14 triệu: dùng đổi 12 triệu, khách trả thêm 2 triệu.

`DiscountAmount` của đơn/dòng đơn đã bao gồm cả giảm khuyến mãi sản phẩm và giá trị dùng đổi. `ExchangeCreditAmount` là phần tách riêng để biết trong tổng giảm đó có bao nhiêu thuộc đổi máy; **không trừ thêm lần thứ hai**. Giá gốc của máy mới vẫn lưu trong `OrderItems.UnitPrice`, không thay giá gốc thành 0.

Frontend chỉ gửi SKU và thông tin nhận hàng (nếu đổi địa chỉ). Backend từ chối các trường khách tự gửi như tiền giảm, tổng tiền, số lượng, người sở hữu hoặc phương thức giao/thanh toán tùy ý.

## 4. Luồng khách hàng

1. Tạo phiếu từ một máy đã mua, trong thời hạn đổi trả đang cấu hình. Số lượng khóa là 1. Không có nút chọn hai hình thức Đổi/Trả.
2. Khi SKU cũ hết hàng: dòng thông tin đỏ nằm **ngay trên, bên ngoài khung xác nhận ở cuối form**. Còn hàng thì không hiện dòng này. Tồn kho vẫn được kiểm tra lại khi tạo đơn đổi.
3. Sau khi phiếu được tiếp nhận, trong chi tiết phiếu có nút **Chọn sản phẩm đổi**. Bấm vào sẽ vào luồng đổi gắn với chính phiếu đó.
4. SKU cũ còn hàng: tự chọn đúng SKU cũ. Nếu không còn: dùng trang tìm sản phẩm và trang chi tiết sản phẩm thông thường nhưng khóa danh mục theo phiếu, ngắt tìm kiếm chung, không thêm vào giỏ, số lượng 1.
5. Trang xác nhận hiển thị giá mới sau khuyến mãi, giá trị dùng đổi, tiền bù và giao hàng miễn phí. Mặc định lấy thông tin giao hàng của đơn mua cũ; khách có thể nhập địa chỉ nhận mới.
6. Đơn 0đ được chốt ngay và không mở QR. Đơn có tiền bù mở trang đơn hàng để thanh toán QR theo cơ chế SePay hiện có.
7. Khi đã có đơn đang chờ QR: tiếp tục đúng đơn đó, không tạo đơn khác. Đơn QR hết hạn được hủy, nhả tồn/serial, phiếu vẫn mở để chọn lại. Việc hết hạn được xử lý bởi tác vụ hết hạn hiện có, khi trang thanh toán đọc lại đơn hoặc khi khách mở lại ngữ cảnh đổi sản phẩm; trang đang mở không cần chờ riêng cron mới nhả hàng.
8. Bấm logo/trang chủ hoặc rời các liên kết đổi sẽ thoát ngữ cảnh mua đổi. Phiếu vẫn được giữ; quay lại từ nút trong phiếu thì tiếp tục luồng đổi. Giỏ mua thông thường không bị xóa hay trộn vào đơn đổi.

Chỉ kiểm tra danh mục trên trình duyệt là chưa đủ: backend cũng so sánh danh mục, quyền sở hữu, giai đoạn phiếu, số tồn và việc máy gốc còn hàng khi chốt đơn.

## 5. Trạng thái, quyền và điều kiện đóng phiếu

| Mốc | Mã lưu | Hành vi |
| --- | --- | --- |
| 1 | `Pending` | Đang chờ. NV/QTV được tiếp nhận hoặc từ chối có lý do. |
| 2 | `Approved` | Đã tiếp nhận. Khách được chọn máy đổi; NV/QTV không được từ chối nữa. |
| 3 | `Receiving` | Đang điều phối. Được đi tiếp; khách vẫn có thể đổi/chốt đơn. |
| 4 | `Processing` | Đang đánh giá hư hại. Chỉ đi tiếp khi đơn đổi đã chốt, phần bù đã được xác nhận thanh toán nếu có. |
| 5 | `Completed` | **Hoàn tất**. Đóng phiếu và nhập lại đúng một máy cũ vào tồn. Không dùng nhãn “Đã trả máy”. |
| Đóng sớm | `Rejected` / `Cancelled` | Từ chối trước tiếp nhận hoặc khách hủy trước khi chốt. Không nhập lại máy cũ. |

Khách được hủy ở các giai đoạn chưa đóng, miễn chưa chốt đơn đổi. Đơn 0đ khóa hủy ngay khi xác nhận; đơn có tiền bù khóa hủy khi backend nhận được xác nhận thanh toán. Hủy phiếu khi đơn đổi chưa trả tiền sẽ hủy luôn đơn đó và nhả hàng trong cùng một giao dịch.

NV/QTV không có nhánh hủy phiếu thay khách. Không được dùng chức năng hủy đơn của admin để hủy đơn đổi. Các đơn đã chốt không được hủy qua API đơn hàng chung.

Đơn 0đ dùng `PaymentStatus = Paid` với ý nghĩa đã giải quyết đủ nghĩa vụ thanh toán. **Không tạo giao dịch nhận tiền 0đ giả.** Giao diện ghi “Không cần thanh toán / Đã chốt đơn đổi”, không báo đã nhận chuyển khoản cho đơn này.

## 6. Tồn kho, Serial và bảo hành

- Tạo đơn đổi giữ/trừ một máy mới ngay, dùng quy tắc tồn kho hiện có. Có Serial khả dụng thì lấy ngẫu nhiên một mã, gắn với dòng đơn mới ở trạng thái `Reserved`. Tồn cũ chưa có Serial vẫn bán được, ô mã để trống.
- Hủy/hết hạn đơn chưa trả tiền: trả lại một tồn máy mới, nhả mã đã giữ. Không nhập máy cũ vào kho tại bước này.
- **Chỉ khi chuyển phiếu từ giai đoạn 4 sang Hoàn tất:** cộng 1 tồn SKU cũ; có mã cũ thì đặt lại chính bản ghi Serial đó thành `Available` và bỏ gắn dòng đơn cũ. Không chèn trùng chuỗi Serial. Không có mã thì chỉ cộng tồn.
- Việc tăng tồn, đổi trạng thái Serial, đóng phiếu và ghi lịch sử cùng một giao dịch; lỗi một phần thì hoàn tác hết. Bấm lặp hoặc trạng thái cũ bị chặn, không cộng tồn lần hai.
- Số Serial trên đơn mua cũ vẫn truy được qua liên kết phiếu sau khi máy được nhập lại kho. Phần hiển thị đơn không cung cấp thao tác sửa Serial.
- Máy mới có bảo hành mới theo dòng đơn mới và bắt đầu khi **giao thành công**, giống đơn mua thường; không bắt đầu từ lúc tạo đơn 0đ.

## 7. API và những phần mã nguồn chính

| Điểm giao tiếp | Công việc |
| --- | --- |
| `POST /return-requests` | Yêu cầu mới chỉ nhận `Exchange`, số lượng 1; các giá trị lịch sử vẫn giữ để đọc. |
| `GET /orders/{id}/return-items` | Trả các thiết bị đủ điều kiện, thông tin tồn của SKU gốc và mức giá trị dùng đổi; hỗ trợ phần tồn cũ không Serial. |
| `GET /return-requests/{id}/exchange` | Chỉ chủ phiếu được xem; lấy danh mục khóa, máy gốc, giá trị dùng đổi và đơn đổi đang hiệu lực; dọn đơn QR đã hết hạn của phiếu nếu cần. |
| `POST /return-requests/{id}/exchange-order` | Tính giá, kiểm tra lại tồn, tạo hoặc trả lại đơn đang có; không nhận số tiền do khách tính. |
| API chuyển giai đoạn/từ chối/hủy phiếu hiện có | Áp dụng các quy tắc chốt đơn, quyền hủy và nhập lại tồn mới. |
| API đơn hàng/QR/webhook hiện có | Xử lý đơn đổi, tiền bù, giao hàng, Serial và bảo hành mới. |

Backend: model/schema/repository đơn hàng, `services/exchange.py`, `services/returns.py`, `services/order.py` và router phiếu dịch vụ. Frontend khách: form gửi phiếu, chi tiết phiếu, tìm sản phẩm, chi tiết máy, xác nhận đơn đổi và hiển thị đơn. Frontend admin: nút từ chối chỉ ở chờ tiếp nhận, chặn hoàn tất khi khách chưa chốt, liên kết qua lại phiếu–đơn và hiển thị giá trị dùng đổi.

Các endpoint hoàn tiền/kiểm tra tài chính cũ vẫn tạm dừng. Các helper và kiểm thử tài chính lịch sử vẫn giữ để đọc/xử lý quyết định sau; không nối chúng trở lại luồng đổi mới.

## 8. Kiểm thử và cách vận hành

Kiểm thử mới kiểm tra: đổi đúng SKU; máy rẻ/bằng/đắt hơn; khuyến mãi máy mới; không tự nhập tiền giảm; danh mục và chủ phiếu; tồn thay đổi lúc khách chọn; đơn trùng; QR hết hạn và thử lại; quyền hủy; chặn từ chối sau tiếp nhận; chặn hoàn tất khi chưa chốt; nhập lại tồn/Serial đúng một lần; hoàn tác khi lỗi; tồn cũ không mã; thời điểm bắt đầu bảo hành mới; giao tiếp HTTP và các bước giao diện khách.

Không tạo đơn hay ghi dữ liệu thử vào CSDL kinh doanh thật. Kiểm thử nghiệp vụ dùng kho dữ liệu giả hoặc SQLite riêng; không chứng minh khóa đồng thời thật của PostgreSQL. Các kiểm thử PostgreSQL phá dữ liệu vẫn cần database thử riêng và cơ chế opt-in hiện có.

Kết quả kiểm thử:

- Backend toàn bộ: **1.567 passed, 137 skipped, 728 subtests passed**. Những bài cần PostgreSQL thử riêng được skip theo cơ chế bảo vệ hiện có; không bật chúng trên CSDL kinh doanh. Có cảnh báo thư viện Starlette/httpx của môi trường hiện tại.
- Sau các bổ sung cuối: chạy lại nhóm backend liên quan, **98 passed** (gồm API/SQLite, luồng đổi mới, đơn hàng, eligibility, chuyển giai đoạn và graph migration).
- Chạy thêm nhóm đơn hàng/thanh toán/đổi trả sau khi bổ sung nhả hàng ngay khi trang đơn đọc lại QR hết hạn: **71 passed**. Toàn bộ 22 bài nghiệp vụ/HTTP của luồng đổi nằm trong nhóm này đều đạt.
- Frontend toàn bộ với giới hạn 2 worker: **1.281 passed, 1 failed** trong 98 file. Bài còn lỗi là `PurchasesPage.test.jsx` — “actual receiving requires real serials and records a partial receipt without changing the ordered quantity”: kiểm thử chờ thông báo `role="alert"` khi nhận hàng nhưng không tìm thấy. Chạy riêng file vẫn có 24 đạt/1 lỗi. Luồng/file nhập hàng này không được sửa trong lần đổi trả; lưu lại để rà riêng, không tự chỉnh kiểm thử để che lỗi.
- Nhóm frontend liên quan chạy lại: **151 passed** trong 9 file, bao gồm chọn máy, xác nhận đổi, form/chi tiết phiếu, sản phẩm, checkout, hiển thị đơn admin và nhãn trạng thái. Hai bài mới kiểm tra dòng đỏ nằm ngoài và ngay trên footer, chỉ hiện khi máy cũ hết hàng.
- Build frontend thành công. Lint không có lỗi; còn 2 cảnh báo ở `useAdminQuery.js` và `AdminTable.jsx` đã có trong các phần không sửa của lần này. Build có cảnh báo kích thước bundle hiện có.

`backend/tests/test_migration_graph.py` có cập nhật để nhận head mới và kiểm tra migration chỉ thêm đúng hai cột/một khóa ngoại, không tạo bảng hoặc viết lại dữ liệu nghiệp vụ. Các kiểm thử finance lịch sử tạo dữ liệu qua helper cũ được giữ riêng; API công khai chỉ cho phiếu mới Exchange/1 máy.

Vận hành: đã có phương thức `STANDARD` và `QR` hoạt động trong database nên không thêm dữ liệu phương thức mới, không đổi `.env`. Khởi động lại backend để nạp code mới; mở frontend như thường. Muốn áp dụng cùng tính năng trên database khác cần áp dụng migration phù hợp lịch sử của database đó.

Tiền khách chuyển sau khi đơn QR đã bị hủy vẫn đi vào cơ chế đối soát khoản đến muộn hiện có; không tự khôi phục đơn cũ, không tự tạo quyền đổi thứ hai và không tự hoàn tiền. Không triển khai luồng hoàn tiền mới trong lần này.

## 10. Bổ sung ngày 22/10/2026 — tự tạo đơn khi còn đúng biến thể

Phần này cập nhật hành vi đã mô tả ở trên: **còn đúng biến thể thì hệ thống tự tạo đơn, không chỉ chọn sẵn sản phẩm rồi yêu cầu khách bấm xác nhận**.

- Ngay khi NV/QTV tiếp nhận phiếu từ Đang chờ sang Đã tiếp nhận, backend khóa phiếu và kiểm tra tồn của đúng biến thể khách đã mua. Nếu còn hàng được phép bán, hệ thống tự tạo một đơn đổi, số lượng 1, đứng tên khách gửi phiếu. Địa chỉ nhận lấy từ đơn gốc; giao tiêu chuẩn miễn phí.
- Đơn mới liên kết về phiếu bằng `Orders.SourceReturnRequestId` đã có. Chi tiết phiếu của khách/admin nhận được mã đơn và liên kết xem đơn. Lịch sử ghi rõ “Hệ thống tự động tạo đơn đổi trả”; không ghi giả rằng khách đã bấm tạo đơn. Người tiếp nhận vẫn được ghi ở lịch sử chuyển giai đoạn.
- Đơn giữ một tồn và một Serial khả dụng nếu có. Không có Serial thì dùng tồn không mã theo quy tắc đã chốt. Tiếp nhận, tạo đơn, giữ hàng, gán Serial và ghi lịch sử cùng giao dịch: bất kỳ phần nào lỗi thì hoàn tác toàn bộ, phiếu vẫn chờ tiếp nhận.
- Khi hết đúng biến thể và chưa có đơn đổi, khách mới thấy nút “Chọn sản phẩm đổi”. Trang tìm kiếm vẫn khóa đúng danh mục. Khi đã có đơn đổi, không hiện nút chọn nữa, kể cả việc giữ máy cuối cùng khiến tồn còn lại bằng 0.
- Bấm tiếp nhận lặp bị chặn bằng kiểm tra trạng thái. Các lần chuyển bước tiếp theo hoặc tải lại không tạo thêm đơn khi đã có đơn đang hiệu lực.
- Với phiếu đã được tiếp nhận từ trước nhưng chưa có đơn, backend kiểm tra lại ở lần chuyển giai đoạn hoặc tải chi tiết/ngữ cảnh đổi. Nếu đúng biến thể có hàng thì cũng tự tạo đơn; phiếu Đang chờ/Đã hủy/Từ chối/Hoàn tất không được tự tạo đơn. Phiếu lịch sử đã nhập lại hàng hoặc đã duyệt tiền không bị tự cấp thêm máy đổi.
- Khi QR hết hạn, lần tải lại chi tiết/ngữ cảnh phiếu sẽ giải phóng đơn hết hạn. Nếu đúng biến thể có hàng thì tự tạo lại đơn; nếu không có thì cho chọn sản phẩm cùng danh mục. Backend không tự tạo đơn thứ hai khi QR cũ vẫn hiệu lực.
- Quy tắc tiền giữ nguyên: tính giá bán hiện tại sau khuyến mãi rồi trừ giá trị dùng đổi. Đơn 0đ chốt ngay, khách không cần thao tác. Nếu giá hiện tại cao hơn giá trị máy cũ, đơn vẫn tự tạo nhưng chờ khách thanh toán phần bù qua QR; tự tạo đơn không có nghĩa tự xác nhận khách đã trả tiền.

Phạm vi sửa: service đổi trả và tạo đơn đổi; giao diện chi tiết phiếu/tìm sản phẩm của khách; kiểm thử liên quan. Không thêm cột, bảng, khóa ngoại hay migration; không ghi đơn thử vào CSDL thật.

Kiểm chứng riêng cho bổ sung này: 129 kiểm thử backend cùng 46 subtest đạt; 36 kiểm thử frontend (chi tiết phiếu, luồng chọn sản phẩm, tạo yêu cầu và quản lý đổi trả admin) đạt. Build frontend thành công; lint không có lỗi, còn hai cảnh báo cũ ở `AdminTable` và `useAdminQuery`. Kiểm thử bao gồm tự tạo khi tiếp nhận qua cả API `accept` và `advance`, đúng chủ tài khoản, chống tạo trùng, hoàn tác khi lỗi, hết hàng mới cho chọn, xử lý QR hết hạn và không tự tạo ở trạng thái chờ.

## 11. Đính chính tiếp theo — đổi ngang bỏ thanh toán; hủy qua phiếu

Theo xác nhận tiếp theo của người dùng ngày 22/10/2026, quy tắc ở mục 10 về giá tăng **không áp dụng khi đổi đúng biến thể cũ**:

- Đổi đúng SKU của máy cũ luôn là đổi ngang, số tiền phải trả bằng 0, kể cả giá niêm yết đã tăng. Hệ thống tạo đơn dưới tài khoản khách và ghi `PaymentStatus = Paid` để thể hiện đã chốt nghĩa vụ thanh toán, không tạo giao dịch thu tiền và không gọi SePay tạo QR. Đơn ở Chờ xác nhận để NV/QTV xử lý theo luồng đơn thông thường, không bị chặn bởi điều kiện chờ chuyển khoản.
- Dòng hàng vẫn ghi nhận giá hiện tại. `ExchangeCreditAmount` bù toàn bộ giá sau khuyến mãi của chính biến thể đó; `DiscountAmount` gồm giảm khuyến mãi và giá trị đổi, nên tổng đơn bằng 0. Đây là đổi ngang, không phát tiền dư/voucher cho khách. Khi chọn **biến thể khác**, vẫn dùng giá gốc đã mua làm hạn mức và chỉ thanh toán chênh lệch dương; bằng hoặc thấp hơn thì cũng 0đ.
- Trang đơn khách không yêu cầu hoặc tải QR cho đơn đổi 0đ. Trang chi tiết admin hiển thị “Không cần thanh toán”, không để tên phương thức QR khiến người vận hành hiểu nhầm là khách cần chuyển khoản.
- Trong đơn đổi trả, nút “Hủy đơn” được thay bằng “Hủy phiếu”. Xác nhận gọi API hủy phiếu, hủy cả đơn đổi chưa chốt và nhả hàng/Serial trong cùng giao dịch, rồi đưa khách về phiếu. Không gọi API hủy đơn độc lập. Backend cũng chặn việc gọi trực tiếp API hủy đơn đối với đơn đổi (`exchange_cancel_via_request`).
- Điều kiện hủy đã thống nhất vẫn giữ: không được hủy phiếu sau khi đơn 0đ đã chốt hoặc đơn bù tiền đã thanh toán. Khi đó nút Hủy phiếu bị khóa. Nếu thanh toán hoàn tất cùng lúc khách xác nhận hủy, backend chặn hủy và giao diện tải lại trạng thái.
- Không đổi bảng/cột hay migration. Đã chạy script `backend/scripts/inspect_even_exchange_orders.py` chỉ đọc trên CSDL cấu hình: tại thời điểm kiểm tra không có đơn đổi cùng SKU ở trạng thái Pending và chưa thanh toán cần đính chính. Không sửa dữ liệu thật trong lần đính chính này.

Kiểm chứng đính chính: 109 kiểm thử backend và 110 kiểm thử frontend liên quan đạt; build thành công, lint không có lỗi (hai cảnh báo cũ vẫn giữ). Đã kiểm tra giá cùng SKU tăng gấp đôi vẫn tạo đơn 0đ/Paid qua API tiếp nhận, NV xử lý được đơn không cần thanh toán, frontend không gọi API QR, nút Hủy phiếu gọi đúng API phiếu, chặn hủy khi thanh toán đã chốt và không làm thay đổi chức năng hủy của đơn mua thông thường.
