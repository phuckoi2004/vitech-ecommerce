# Đối chiếu admin: đơn hàng, thông báo và quyền nội dung — 21/10/2026

Đây là bản bổ sung, giữ nguyên các tài liệu trước để lưu lịch sử. Người dùng cho phép sửa backend/API và kiểm thử đúng phạm vi bên dưới; không sửa cấu trúc CSDL, không chạy ghi thử lên database thật, không sửa frontend khách hàng. Tài liệu không khẳng định báo cáo Word gốc đã được sửa.

## 3.26 — Tìm đơn trên trang admin

- Một ô tìm kiếm nhận mã đơn, họ tên tài khoản khách (`Users.FullName`) hoặc số điện thoại tài khoản (`Users.PhoneNumber`). Không nhầm tài khoản đặt với thông tin người nhận có thể khác trên đơn.
- Từ một ký tự đã tự tìm, không cần Enter/nút tìm. `098` tìm đúng chuỗi `098` liền nhau ở bất kỳ vị trí nào, không tìm theo từng chữ số rời. Tên tìm theo chuỗi, không phân biệt hoa/thường; không tự bỏ dấu tiếng Việt.
- Frontend gửi `keyword` tới `GET /admin/orders`; backend kết hợp OR giữa mã đơn/tên/SĐT, AND với bộ lọc trạng thái và các bộ lọc cũ. Danh sách và tổng số dùng cùng điều kiện, phân trang ở server. `%`, `_`, `\` được xử lý như ký tự tìm thông thường.
- Nhập tiếng Việt bằng IME chờ kết thúc tổ hợp ký tự; khi đổi truy vấn, yêu cầu cũ bị hủy/bỏ qua để không ghi đè kết quả mới. Không sửa tìm kiếm phía khách. Chưa thêm bộ chọn ngày vào giao diện đơn hàng trong lần này.

## 3.29 — Luồng đơn và người phụ trách

- Chốt lại ngày 21/10: khôi phục bước Đã xác nhận. Luồng hiện hành là `Pending → Confirmed → Processing → Shipping → Delivered`, tương ứng **Chờ xác nhận → Đã xác nhận → Đang xử lý → Đang giao → Đã giao (đóng đơn)**.
- Nút lần lượt: **Xác nhận → Bắt đầu xử lý → Giao hàng → Giao hoàn tất**. Đã xác nhận có bộ lọc và một bước riêng trong tiến trình; bỏ chữ “(cũ)” khỏi nhãn trạng thái. Không yêu cầu bấm Completed ở cuối.
- Xác nhận đầu tiên ghi người thao tác vào `AssignedStaffId` và thời gian `ConfirmedAt`. Khóa dòng đơn trước khi kiểm tra/ghi để hai lần xác nhận không lấy quyền phụ trách của nhau.
- Sau đó chỉ nhân viên đã xác nhận được chuyển bước/hủy và xử lý ghi chú, gán/gỡ Serial của đơn đó; nhân viên khác vẫn xem được. Admin được can thiệp, không tự thay người phụ trách khi làm thay.
- Không cho dùng PATCH thông tin đơn để tự thay/xóa `AssignedStaffId` và lách quyền. Nhân viên không được tự chiếm đơn cũ chưa có người phụ trách; Admin có thể xử lý các đơn này.
- Khi Đã giao: trong cùng transaction ghi thời điểm giao/đóng, bán các Serial đã gán, bắt đầu bảo hành và cộng bộ đếm doanh số/số đơn/số lượng bán đúng một lần. Gọi lặp không ghi thêm giao dịch COD hoặc cộng doanh số lần nữa. Không ghi lại hàng lịch sử.
- Giữ điều kiện thanh toán và Serial trước giao: QR phải đã thanh toán; COD phải xác nhận thu đủ tiền khi giao hoàn tất; biến thể có quản lý Serial phải gán đủ mã trước giao.
- `Confirmed` là bước hoạt động bình thường, tiếp tục sang Processing theo quyền. `Completed` vẫn đọc được cho các bản ghi đã có; Delivered/Completed đều không có bước chuyển mới trên admin. Không sửa dữ liệu thật hoặc cấu trúc CSDL.

### Nhánh hủy và giới hạn phạm vi

- Admin hoặc nhân viên phụ trách được hủy trước Đã giao; đơn đang giao bị hủy tạo hồ sơ chờ hàng quay về, không tự cộng tồn khi hàng còn ở bên vận chuyển. Hủy không đồng nghĩa đã hoàn tiền.
- Phía khách hiện chỉ tự hủy ở Pending và chưa thanh toán, hẹp hơn mô tả gốc cho hủy tới Đang xử lý. **Giữ nguyên** vì người dùng loại phần khách khỏi đợt sửa này; chưa coi điểm này đã khớp báo cáo.

## Thông báo đơn mới

- Khi tạo đơn Pending thành công, cùng transaction tạo một thông báo `NewOrder` cho mỗi tài khoản Staff/Admin chưa xóa, gồm cả tài khoản hiện đang khóa để có lịch sử khi mở lại. Không gửi thông báo quản trị cho khách.
- `ReferenceType=Order`, `ReferenceId=OrderId`, đường dẫn thẳng `/admin/orders/{id}`. Bộ điều hướng kiểm tra quyền `orders:view` và định dạng ID; mở đúng trang chi tiết cùng sidebar.
- Người bấm đọc chỉ đánh dấu bản thông báo của chính mình. Người khác chưa đọc vẫn còn cảnh báo.
- Bất kỳ người hợp lệ xác nhận đơn thành công: đánh dấu đã đọc mọi thông báo `NewOrder` của đúng đơn đó trong cùng transaction. Hủy đơn cũng giải quyết cảnh báo đang chờ xác nhận. Không xóa lịch sử, không đánh dấu thông báo khách hoặc đơn khác.
- Chốt lại khi ghép incoming: chuông dùng chấm đỏ đứng yên, không nhấp nháy; bấm chuông mở trang thông báo riêng, có lọc tất cả/chưa đọc. Đọc thông báo thì hết chấm cho thông báo đó; xác nhận/hủy đơn tự đánh dấu đã đọc cảnh báo `NewOrder` của đúng đơn cho mọi người. Chấm đỏ vẫn còn nếu người dùng còn thông báo khác chưa đọc. Phiên vừa thao tác làm mới ngay; các phiên khác kiểm tra lại mỗi 60 giây và khi cửa sổ được focus. Đây không phải WebSocket, nên thao tác từ máy khác không được đẩy tức thời. Nội dung thông báo đơn mới bổ sung tổng tiền và phương thức thanh toán, không tạo thêm một thông báo `Order` trùng sự kiện.

## 3.33–3.36 — Đánh giá, tin tức và banner

- Staff và Admin đều được xem/lọc/xóa mềm đánh giá; **bắt buộc lý do** cho cả hai vai trò. Frontend khóa xác nhận khi trắng; schema/service backend cũng từ chối thiếu, null, rỗng hoặc chỉ khoảng trắng. Giới hạn lý do 2.000 ký tự.
- Xóa đánh giá vẫn ghi người, thời điểm, lý do và tính lại số sao; không xóa vật lý.
- Staff và Admin đều được xem/thêm/sửa/xóa tin tức và banner; nội dung + trạng thái vẫn lưu nguyên tử theo lần sửa trước. Không liên kết banner với tin tức.
- API danh sách/chi tiết tin tức trả thêm tên người tạo (`CreatedByName`) từ liên kết tài khoản hiện có, để nhân viên xem được tên người tạo bài khác mà không cần quyền tra cứu/quản lý tài khoản.
- Cho phép Staff dùng API tải ảnh chung hiện có để thêm ảnh local cho tin tức/banner. Việc tải ảnh chỉ đưa file lên kho ảnh, không cấp quyền sửa sản phẩm/danh mục/thương hiệu cho nhân viên.
- Phiên đăng nhập cũ có thể cần đăng nhập lại để nhận danh sách quyền mới. Khởi động lại backend nếu không chạy tự reload.

## Những phần giữ lại để đối chiếu tiếp

- Bảo hành 3.27 và đổi trả 3.28 giữ luồng hiện hành, chờ trao đổi tiếp; không bật lại hoàn tiền/trung tâm bảo hành/đổi máy.
- Quyết định trước khi pull là chỉ giữ số đơn giao thành công, số đơn hủy và tỷ lệ hủy, không thêm tỷ lệ hoàn thành. Khi xử lý merge ngày 21/10, người dùng chốt **lấy nguyên bản incoming cho phần báo cáo/thống kê**, không trộn với bản local; quyết định này thay giới hạn tỷ lệ trước đó. Riêng trang chi tiết đơn hàng (phần 5) bỏ toàn bộ giá nhập, cột lãi, tổng hợp lãi/biên lãi và các nhãn dự kiến/thiếu giá nhập; giữ thông tin mua hàng, thanh toán và luồng xử lý đơn của bản local. Giữ điều hướng quay lại đúng nơi mở đơn: từ báo cáo thì về báo cáo với bộ lọc trước đó, từ danh sách đơn thì về danh sách đơn. Phần form sản phẩm/biến thể (phần 3) giữ nguyên bản local, không lấy ô giá niêm yết tham khảo và xử lý lưu ô đó của incoming. Chưa sửa bản Word.
- Không thay đổi dữ liệu CSDL thật, migration, thông tin SePay, cron, hoặc frontend khách hàng.

## Kiểm thử

- Backend: chạy toàn bộ `backend/tests`, **1.352 passed, 137 skipped, 717 subtests passed**. Các bài PostgreSQL/API cần môi trường riêng vẫn bỏ qua; không dùng database thật để thử ghi hoặc tự bật chế độ integration.
- Frontend: **132 kiểm thử liên quan đạt** ở bảy file đơn hàng/chi tiết/đánh giá/tin tức/banner/thông báo/điều hướng; gồm lần chạy bảy file 130 bài và hai bài bổ sung kiểm tra quyền Staff ở tin tức/banner đã chạy lại đạt.
- Build frontend thành công. Scoped lint không có lỗi, còn cảnh báo `react(set-state-in-effect)` ở hook tải dữ liệu `useAdminQuery.js` đã có kiểu cập nhật state trong effect từ trước. Build còn cảnh báo kích thước chunk lớn hơn 500 kB.
- SQL thật trên SQLite kiểm tra tìm chuỗi liên tiếp, escape `%`/`_`, cùng điều kiện đếm/phân trang và giải quyết đúng nhóm thông báo. Kiểm thử fake kiểm tra quyền người xác nhận, Admin can thiệp, đọc riêng/đọc chung, rollback, COD và bộ đếm chỉ tăng một lần.
- Fake/SQLite không chứng minh khóa đồng thời PostgreSQL. Không kiểm tra giao diện màn hình nhỏ theo yêu cầu trước của người dùng. Không commit, không thay migration hoặc file `test_migration_graph.py`.

## Bổ sung tiếp: sửa trực tiếp số lượng tồn kho, không lưu lịch sử

- Người dùng yêu cầu QTV được tăng/giảm số tồn ngay trong chi tiết sản phẩm, không âm; sau đó chốt **sửa chay, không cần lịch sử thao tác**. Đã được phép sửa backend/API đúng phạm vi này, không đổi cấu trúc CSDL.
- Nút **Điều chỉnh tồn kho** nằm cạnh số tồn trong chi tiết biến thể. QTV nhập thẳng số tồn mới, số nguyên từ 0 đến 2.147.483.647; không nhập lý do, không dùng luồng phiếu điều chỉnh hoặc khai báo đầu kỳ. Nhân viên không thấy nút và backend cũng từ chối quyền.
- `PATCH /admin/variants/{variant_id}/stock` nhận `StockQuantity` và `ExpectedStockQuantity` (số đang hiển thị). Service khóa biến thể rồi so sánh số cũ: nếu vừa có bán/nhập hoặc QTV khác sửa thì trả 409 để tải lại, tránh ghi đè âm thầm. Số âm, số lẻ, boolean, chuỗi hoặc vượt giới hạn bị từ chối.
- Chỉ đổi `ProductVariants.StockQuantity`, không tạo `StockAdjustments`/lịch sử thao tác, không tự đổi giá vốn, không sửa phiếu nhập/bán. Cảnh báo tồn thấp vẫn được cập nhật theo cơ chế có sẵn; thông báo tồn thấp không phải lịch sử điều chỉnh kho.
- Sau lưu, vẫn ở trang chi tiết, tải lại số tồn/trạng thái và danh sách phía sau. Hủy không ghi dữ liệu; khóa gửi lặp khi đang lưu. Lỗi kết nối/5xx hoặc số cũ thay đổi thì yêu cầu tải lại trước lần sửa tiếp.
- Người dùng yêu cầu **chưa sửa Serial/IMEI và giải thích trước**. Vì vậy lần bổ sung này chỉ mở sửa trực tiếp cho biến thể `IsSerialTracked=false`; nhóm đang quản lý Serial vẫn giữ cơ chế nhập/gán mã hiện có, không tự bật/tắt cờ, không thêm/xóa mã và không cho sửa chay số tồn làm lệch số máy đã ghi mã. Quyết định cuối cho nhóm Serial đang chờ người dùng.
- Chưa thay đổi quy tắc giá vốn của các nghiệp vụ nhập hàng khác. Sửa trực tiếp số lượng không xác lập giá vốn đầu kỳ hoặc tạo số liệu nhận hàng.
- Xác minh riêng đợt bổ sung: **79 kiểm thử backend, 45 kiểm thử frontend đạt**, scoped lint không lỗi/cảnh báo, build thành công (còn cảnh báo chunk lớn). Kiểm thử HTTP dùng service thật với repository giả lập, không thử ghi lên CSDL thật. Giữ nguyên các thay đổi trước đó.

## Bổ sung tiếp: tự gán Serial khi xác nhận đơn và chỉnh tồn kho có Serial

Quyết định mới này thay phần đang chờ thống nhất Serial ở mục trước; giữ nguyên nội dung cũ để theo dõi quyết định. Người dùng đã cho phép sửa backend/API và kiểm thử trong phạm vi này, không đổi cấu trúc CSDL, không tự bật `IsSerialTracked` cho dữ liệu cũ.

- `IsSerialTracked` thuộc `ProductVariants`; tạo biến thể mới qua giao diện/API mặc định bật quản lý Serial, vẫn cho phép bỏ tick. Khi đang bật, số lượng nhận/tăng mới yêu cầu đủ mã, không được để trống/chỉ khoảng trắng; tồn cũ không bắt nhập bù. Các cờ đã lưu của biến thể hiện có chưa được đổi hàng loạt; không sinh Serial giả hoặc chạy thao tác ghi dữ liệu thật. Luồng sau áp dụng khi biến thể đã bật quản lý Serial và đã có mã thực tế.
- Khi NV/QTV xác nhận `Pending → Confirmed`, hệ thống khóa đơn, khóa các biến thể theo thứ tự ID, tự chọn mã `Available` chưa gắn đơn cho từng dòng rồi chuyển `Reserved`, gắn `ProductSerials.OrderItemId`. Bước sang Processing giữ các mã đã gán; dữ liệu Confirmed chưa được gán từ trước vẫn được xử lý tại bước này. Phần máy cũ không mã được áp dụng theo quyết định cuối tài liệu. Lỗi khóa/lưu hoặc lỗi dòng tiếp theo thì hoàn tác toàn bộ: trạng thái, người phụ trách, Serial và thông báo đã đọc.
- `GET /admin/orders/{id}/serials` tiếp tục dùng để xem. Cả trang chi tiết và cửa sổ thao tác nhanh đều chỉ đọc Serial, bỏ ô nhập/nút gán/nút gỡ. Hai endpoint POST gán và DELETE gỡ cũ bị chặn tại service với `order_serials_read_only`, kể cả Admin; ẩn nút không phải biện pháp phân quyền duy nhất.
- Tồn khả dụng `StockQuantity` đã được trừ khi đặt đơn. Xác nhận chỉ giữ Serial, không trừ lại. Giao hoàn tất giữ liên kết mã với dòng đơn, chuyển Reserved sang Sold và ghi bảo hành theo cơ chế hiện có; không xóa mã và không trừ tồn lần nữa. Hủy trước khi giao hoàn tồn và nhả mã theo luồng cũ; hủy khi đang giao vẫn giữ máy chờ nhận lại.
- Nút chỉnh tồn chỉ QTV: biến thể không quản lý Serial tiếp tục đặt trực tiếp số lượng. Biến thể quản lý Serial tăng thêm N thì sau bước nhập số tồn xuất hiện form chỉ có một ô nhập Serial nhiều dòng cho N máy. Chưa gửi API khi mới mở bước này. Hủy không lưu; sai số lượng, mã trùng trong yêu cầu/trong CSDL, mã rỗng hoặc dài quá 100 ký tự thì không tăng số tồn hay lưu dở mã mới. Quy tắc trim, phân biệt hoa thường và giới hạn độ dài dùng lại như nhập hàng.
- Giảm tồn N: server chọn ngẫu nhiên N mã Available chưa gắn đơn của đúng biến thể, đổi sang WrittenOff; không đụng mã Reserved/Sold/thuộc biến thể khác, không xóa bản ghi. Thiếu mã khả dụng hoặc đang bị khóa thì không lưu số lượng. Cả tăng/giảm vẫn không tạo StockAdjustments/lịch sử thao tác và không đổi giá vốn.
- Kiểm tra đồng bộ phải tính cả đơn đã giữ số lượng nhưng chưa được gán mã: `Available chưa gắn đơn = StockQuantity + số máy của các đơn còn xử lý chưa có Serial Reserved`. Vì vậy số mã Available có thể cao hơn StockQuantity khi có đơn Pending. Dữ liệu đang lệch bị chặn 409 `serial_stock_mismatch`, không tự bù mã hoặc sửa số tồn để che sai lệch. Vẫn kiểm tra ExpectedStockQuantity dưới khóa biến thể, tránh ghi đè số vừa bán/nhập.
- Không sửa giao diện khách hàng, dữ liệu cũ hay schema/migration. Các đơn Processing cũ chưa đủ Serial vẫn bị chặn giao hàng, không bổ sung nút sửa tay để lách quy tắc mới.

Xác minh: bộ backend hiện có **1.369 passed, 137 skipped, 720 subtests passed**; bổ sung sau đó hai ca HTTP kiểm tra Serial, chạy lại hai file liên quan **27 passed, 21 subtests passed**. Frontend liên quan **102 passed** ở bốn file (chi tiết/danh sách đơn và chi tiết/sửa tồn sản phẩm). Scoped lint đạt, build thành công (còn cảnh báo chunk lớn hiện có). Test service/HTTP dùng kho giả lập, test truy vấn khóa biên dịch SQL PostgreSQL; chưa chạy kiểm thử ghi/đồng thời trên PostgreSQL thật.

### Chốt lại cách giảm tồn: giữ ngẫu nhiên, không sửa CSDL

- Người dùng yêu cầu QTV chỉ sửa số lượng, không chọn mã để loại và không có thông báo riêng về Serial. Kiểm tra frontend admin xác nhận đã đúng: giảm tồn không hiển thị ô nhập/danh sách chọn mã; frontend chỉ gửi StockQuantity và ExpectedStockQuantity, server tự chọn ngẫu nhiên mã khả dụng. Ô nhập Serial chỉ dành cho tăng tồn. Giữ thông báo lưu số lượng thông thường, không hiện danh sách mã bị loại.
- Đã giải thích việc ưu tiên mã nhập mới nhất cần thời điểm tạo riêng, trong khi ProductSerials chưa có trường này. Người dùng chọn **“Giữ ngẫu nhiên, không sửa CSDL”**. Vì vậy không thêm CreatedAt, không tạo/chạy migration và không đổi cách chọn mã ở backend.
- Bổ sung kiểm thử trường hợp đang nhập mã để tăng tồn, quay lại rồi chuyển sang giảm: không còn ô chọn/nhập mã và không gửi mã đã nhập ở bước trước. Toàn bộ **16 kiểm thử ProductStockDialog đạt**.

### Bổ sung nút mũi tên trong ô số tồn

- Theo yêu cầu tiếp theo, ô số lượng tồn kho khi QTV điều chỉnh có hai mũi tên đen ▲/▼ xếp dọc ngay trong khung nhập. Mỗi lần bấm tăng/giảm 1, vẫn nhập số trực tiếp được; không cho giảm dưới 0 hoặc tăng quá giới hạn số nguyên của trường. Bấm mũi tên chưa lưu dữ liệu, chỉ nút lưu mới gửi yêu cầu.
- Giữ nguyên so sánh với số tồn ban đầu: tăng trên biến thể quản lý Serial mới mở form nhập mã, giảm để server tự loại mã ngẫu nhiên. Chỉ sửa frontend admin, không đổi API/backend hoặc CSDL. Kiểm thử ProductStockDialog 16 bài đạt, lint đạt.

### Sửa lại đúng vị trí ô tồn kho trong Sửa biến thể

- Người dùng phản ánh ô “Số lượng tồn kho” trong trang cập nhật biến thể vẫn khóa. Nguyên nhân: nút/mũi tên trước đó được đặt ở cửa sổ riêng mở từ trang xem chi tiết, còn ô ở form biến thể vẫn readOnly.
- Đã gỡ nút “Điều chỉnh tồn kho” đặt ở trang xem chi tiết và đường mở cửa sổ chỉnh số lượng từ đó. Ô tồn kho ngay phần “Giá và tồn kho” của Sửa biến thể cho QTV nhập trực tiếp, có hai mũi tên đen ▲/▼ tăng/giảm 1. Nhân viên, trang tạo mới và chế độ sửa thông tin chung không được dùng ô này để sửa số tồn.
- “Lưu tồn kho” nằm ngay dưới ô số lượng, gọi API tồn kho hiện có. Tăng trên biến thể quản lý Serial mới mở cửa sổ nhập mã; giảm lưu số lượng và server tự chọn mã. Không tạo form lồng nhau, không vô tình gửi form cập nhật sản phẩm khi bấm lưu Serial.
- Giữ nguyên thông tin sản phẩm đang nhập dở khi lưu tồn kho, cập nhật số tồn làm mốc cho lần sửa tiếp theo và làm mới danh sách phía sau. Phải lưu hoặc hủy phần số tồn đang sửa trước khi lưu thông tin biến thể hoặc chuyển sang sửa thông tin chung, tránh bỏ qua số tồn người dùng vừa nhập. Lưu số tồn là thao tác riêng được ghi rõ trên giao diện.
- Chỉ sửa frontend admin và tài liệu, không đổi backend/API/CSDL. Hai file kiểm thử liên quan đạt **49 bài**, scoped lint đạt.

### Chốt lại tồn cũ không mã, checkbox có hiệu lực khi Lưu tồn kho và ưu tiên mã khi bán

Quyết định mới sau phản hồi của người dùng: **không bắt nhập bù Serial cho tồn đã có**, chỉ yêu cầu mã cho phần tăng mới khi đang bật quản lý Serial. Khi giảm thì lấy phần không mã trước, khi bán thì ngược lại: gán mã có sẵn trước, hết mã mới sử dụng phần hàng cũ không mã. Các kiểm tra bắt đủ mã bằng tổng tồn trong các mục cũ được thay bằng quy tắc này; giữ các mục cũ làm lịch sử trao đổi.

- Lỗi UI đã xác định: checkbox lưu vào form.IsSerialTracked nhưng bộ lưu tồn đọc item.IsSerialTracked của lần tải trước. Đã nối giá trị checkbox đang chỉnh vào bộ lưu tồn, giữ riêng cờ đã lưu. Tick rồi tăng số lượng và bấm **Lưu tồn kho** mở form Serial ngay, không cần **Lưu thay đổi**. Giảm/hủy không mở form nhập mã. Hủy form khôi phục checkbox về thiết lập đã lưu.
- API PATCH tồn kho nhận thêm IsSerialTracked và ExpectedIsSerialTracked tùy chọn, boolean thực sự. Khi checkbox thay đổi, frontend gửi cờ mới cùng số tồn, số cũ và các mã mới trong một yêu cầu. Backend khóa biến thể, kiểm tra trạng thái cũ, kiểm tra đủ đúng số mã tăng thêm và trùng mã rồi mới lưu số tồn/cờ/các mã trong cùng transaction. Sai dữ liệu, lỗi lưu hoặc xung đột thì hoàn tác tất cả. Không thay cờ cho các biến thể khác, không chạy cập nhật dữ liệu thật.
- Ví dụ có 10 máy cũ không mã, tick quản lý Serial rồi tăng thành 13: chỉ nhập 3 mã mới. Sau lưu còn 10 máy không mã + 3 máy có mã. Giảm xuống 8 không loại mã nào; giảm tiếp xuống 2 thì bỏ hết 5 máy không mã còn lại và loại ngẫu nhiên 1 mã. Bản ghi mã bị loại chuyển WrittenOff, không xóa, không lấy mã Reserved/Sold.
- Không dùng giả định StockQuantity luôn bằng số Serial Available. Nhóm máy chưa được gán cho đơn = StockQuantity + số lượng đơn Pending chưa có Serial Reserved; phần không mã trong nhóm này = tổng nhóm trừ số mã Available chưa gắn đơn. Đơn Confirmed/Processing/Shipping không được cộng phần máy thiếu mã vào nhóm tồn khả dụng nữa. Nếu số mã vượt số máy trong nhóm thì chặn dữ liệu lệch; không tự sửa tồn hoặc sinh mã giả.
- Xác nhận đơn tự lấy các mã Available chưa gắn đơn trước, tới số lượng khách mua. Nếu mã ít hơn số lượng mua, phần còn lại được hiểu là tồn cũ không mã. Mã đã tồn tại vẫn được ưu tiên kể cả biến thể đang tắt yêu cầu nhập mã cho hàng mới. Các mã đang khóa không được bỏ qua để âm thầm bán hàng không mã: báo xung đột và hoàn tác, cho phép thử lại. Không cho NV/QTV gán/gỡ tay.
- Trang chi tiết và cửa sổ thao tác đơn hiển thị Serial/IMEI: kèm mã thực tế; với phần không mã, vẫn có nhãn và để trống sau dấu hai chấm, không ghi mã giả hoặc “Chưa gán”. Đơn có phần máy cũ không mã vẫn chuyển giao hàng và hoàn tất được; chỉ bán các mã Reserved thực sự có, không trừ tồn lần nữa.
- Hủy đơn đang giao tạo dòng hàng chờ về cho từng máy có Serial và một dòng số lượng cho phần không mã còn lại. Nhận lại hàng cộng đúng cả hai phần, tránh bỏ sót máy cũ. Không thay nghiệp vụ ReturnRequests/WarrantyRequests hay giao diện khách hàng.
- Lưu tồn không tạo StockAdjustments/lịch sử thao tác và không đổi giá vốn. Quy tắc tắt quản lý Serial vẫn giữ chặn tồn còn hàng hoặc lịch sử đang sử dụng; không dùng checkbox để bỏ qua dữ liệu Serial đã có. Mã trùng trong CSDL có thể sửa ngay tại form nhập mã, không phải lưu lại biến thể trước.

**Phần cần theo dõi riêng:** API tạo yêu cầu bảo hành/đổi trả của khách hiện vẫn xét cờ IsSerialTracked để bắt ProductSerialId. Với dòng mua từ tồn cũ không mã của biến thể đã bật cờ, hai API này còn cần điều chỉnh chính sách riêng. Chưa sửa vì phạm vi lần này là lưu tồn và xử lý đơn admin; các phần bảo hành/đổi trả đã được yêu cầu giữ lại xử lý sau.

Xác minh sau thay đổi: **1.378 kiểm thử backend đạt, 137 skipped, 722 subtests đạt**; **106 kiểm thử frontend đạt** ở bốn file liên quan. Scoped lint đạt, build đạt (cảnh báo chunk lớn có sẵn). Các test HTTP/service dùng kho dữ liệu cô lập, không ghi database thật; chưa kiểm thử concurrency thực tế trên PostgreSQL. Không thay model/migration/CSDL, không sửa frontend khách hàng.
