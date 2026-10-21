# Tổng quan và báo cáo bán hàng — 21/10/2026

Tài liệu này mô tả báo cáo hiện hành với kỳ 6 tháng gần nhất, thay thế các mô tả giao diện cũ trong `admin-dashboard.md`.

## Dữ liệu và cấu trúc database

Không thay đổi ORM, không chạy migration, không thêm bảng/cột và không cập nhật dữ liệu nghiệp vụ. Các trường mới trong response API là kết quả SELECT/tổng hợp từ bảng, cột hiện có.

- Doanh số bán hàng: tổng `OrderItems.LineTotal` sau mọi giảm giá, không gồm phí vận chuyển. Chỉ đơn Delivered/Completed có Payment Success, lọc theo DeliveredAt; EXISTS bảo đảm nhiều giao dịch thanh toán không làm nhân doanh số.
- Tổng giá nhập: tổng `OrderItems.UnitCost × Quantity`, dùng giá đã lưu trên đơn. Giá nhập hiện tại trong danh mục thay đổi không sửa số liệu lịch sử.
- Lãi gộp: doanh số trừ tổng giá nhập; biên lãi bằng tổng lãi chia tổng doanh số. Doanh số bằng 0 thì biên lãi chưa xác định. `UnitCost <= 0` được coi là chưa có giá nhập theo quy tắc hiện hành; `Cost`, `Profit`, `Margin` trả null cho tập dữ liệu có dòng thiếu, kèm `LinesMissingCost`. Không tạo lãi giả bằng cách tính giá nhập thiếu là 0.
- Bán hàng và lãi gộp chưa điều chỉnh trả hàng. Không gọi là lợi nhuận ròng. Phí ship, hoàn tiền, thu dư tiếp tục thuộc phần đối soát thanh toán; API `/statistics/revenue` cũ giữ nguyên cách tính và không còn dùng làm doanh số trên Dashboard.
- Đơn đặt và tỷ lệ hủy xét theo OrderedAt, trạng thái tại thời điểm xem. Đã giao gồm Delivered/Completed, kể cả chưa có Payment Success; vì vậy khác tập đơn ghi nhận bán hàng.
- Lý do hủy: tối đa 10 nội dung đã ghi, gộp chuỗi giống nhau sau bỏ khoảng trắng hai đầu. Không suy diễn nhóm lý do, không thêm cột mã lý do.

## Giao diện

Tổng quan ưu tiên công việc hiện tại: đơn Pending, hội thoại Staff/Open chưa phân công, đổi trả Pending và bảo hành New chưa tiếp nhận. Các ô mở đúng danh sách đã lọc, theo quyền của người đăng nhập. Bốn thẻ kết quả là doanh số, lãi gộp, số đơn đã giao và số đơn hủy. Hai thẻ đơn hàng hiển thị số lượng lớn ở trên, số lượng / tổng số đơn ở dòng phụ bên dưới, ví dụ `4` và `4 / 10`, `6` và `6 / 10`. Dữ liệu lấy từ báo cáo Đơn hàng (theo ngày đặt trong kỳ, trạng thái tại thời điểm xem); số đã giao gồm cả đơn hoàn thành và không phụ thuộc điều kiện thanh toán của báo cáo bán hàng. Cảnh báo tồn kho nằm trong phần riêng bên dưới.

SKU lấy từ danh sách biến thể sản phẩm hiện có, không tạo bảng SKU riêng. Chỉ tính biến thể đang bán của sản phẩm đang hoạt động, loại các bản ghi đã xóa. Bộ lọc tồn kho dùng ba mục hiện có: “Hết hàng” là tồn bằng 0; “Còn hàng” là tồn dương; “Sắp hết” là tồn dương không vượt mức tối thiểu đã đặt. Tổng quan hiển thị riêng số hết hàng và sắp hết trong phần cảnh báo, mỗi số mở danh sách tương ứng. Các số và liên kết cùng dùng bộ lọc `/admin/variants` như Danh sách sản phẩm, tránh bấm vào thấy số lượng khác.

Công việc, đơn mới và cảnh báo tồn kho tự tải lại mỗi phút khi tab đang hiển thị; quay lại cửa sổ cũng tải lại. Dữ liệu tài chính tải lại khi quay lại hoặc bấm “Làm mới”. Yêu cầu không chồng nhau, bị hủy khi chuyển trang; dữ liệu cũ được giữ trong lúc tải lại hoặc khi gặp lỗi. Thời điểm hiển thị cho biết lần cập nhật mới nhất trong các phần đã tải thành công.

Thời gian dùng ngày lịch Việt Nam, tự cập nhật khi sang ngày hoặc quay lại tab. Kỳ hiện tại từ đầu tháng đến hôm nay; kỳ so sánh từ đầu tháng trước đến cùng ngày, chặn tại ngày cuối của tháng ngắn hơn và ghi rõ cả hai khoảng. Biểu đồ 6 tháng lấy cùng API báo cáo bán hàng; bấm tháng mở báo cáo của tháng đó. Tháng đang chạy có dấu hiệu chưa hết tháng.

Báo cáo có ba tab: Bán hàng & lãi gộp, Đơn hàng và Đơn nhập hàng. Bộ lọc gồm tháng bất kỳ, quý, năm, sáu tháng gần nhất, khoảng ngày tự chọn tối đa 366 ngày; hỗ trợ năm trước. Kỳ đang chạy kết thúc hôm nay. Danh mục, thương hiệu, sản phẩm được áp dụng đồng thời lên toàn bộ báo cáo. Tab Đơn nhập hàng bổ sung nhà cung cấp; danh sách có cả nhà cung cấp ngừng hoạt động để tra cứu lịch sử.

Trong tab Đơn hàng, bấm thẻ “Đã hủy” để mở bảng đơn hủy ngay dưới các thẻ. Bảng giữ nguyên kỳ, danh mục, thương hiệu và sản phẩm đang lọc; gồm mã đơn, ngày đặt, khách hàng, giá trị đơn và lý do hủy. Đây là các đơn đặt trong kỳ và hiện đã hủy, cùng phạm vi với số trên thẻ. Một đơn có nhiều SKU khớp bộ lọc vẫn chỉ hiện một dòng. Giá trị đơn là tổng tiền đã lưu trên đơn, gồm phí vận chuyển nếu có, không phải doanh số của các sản phẩm đang lọc.

Danh sách đơn hủy có phân trang riêng trong URL (`cancelled=1`, `cancelled_page`), vẫn mở khi áp dụng bộ lọc mới và về trang đầu. Đổi tab sẽ đóng danh sách; Back khôi phục đúng trạng thái. Bấm mã đơn mở chi tiết nếu có quyền xem đơn, sau đó “Quay lại báo cáo” giữ nguyên kỳ, bộ lọc và trang danh sách. Phần lý do hủy phổ biến vẫn hiển thị. Thẻ số đơn hủy trên Tổng quan tiếp tục chỉ hiển thị số liệu.

Bấm thẻ “Đã giao” trong tab Đơn hàng để xem danh sách tương tự, gồm mã đơn, ngày đặt, ngày giao, khách hàng, giá trị đơn và trạng thái tiếng Việt. Gồm các đơn hiện ở trạng thái Đã giao hoặc Hoàn tất, kể cả khi chưa thanh toán; vẫn lọc kỳ theo ngày đặt, không theo ngày giao. Ngày giao chưa có thì hiển thị “—”. Danh sách dùng `delivered=1`, `delivered_page`, giữ kỳ/bộ lọc và trang khi mở đơn rồi quay lại. Áp dụng bộ lọc mới giữ danh sách mở và về trang đầu; đổi tab đóng danh sách. Mỗi lần chỉ mở một trong hai danh sách đã giao/đã hủy; bấm thẻ còn lại sẽ chuyển danh sách. Các thẻ đơn hàng trên Tổng quan chỉ hiển thị số liệu.

Biểu đồ tối đa 31 ngày hiển thị từng ngày, khoảng dài hơn hiển thị từng tháng. Doanh số dùng cột, lãi gộp dùng đường; hỗ trợ lãi âm và ngắt đường khi thiếu giá nhập. Đơn hàng dùng cột chồng theo trạng thái.

Bảng bán hàng hiển thị mỗi màu/biến thể (SKU) một dòng trên toàn kỳ, sắp xếp trong SQL trước khi phân trang. Số lượng nhập, bán, còn và doanh số/lãi của dòng đều theo đúng SKU đó. Tổng hợp và Top 5 sản phẩm không phụ thuộc trang đang xem; Top 5 vẫn gộp theo sản phẩm. Bấm dòng biến thể mở chi tiết đơn của riêng biến thể; bấm Top 5 mở mọi biến thể của sản phẩm. Mã đơn liên kết tới chi tiết đơn. Bộ lọc, tab, sắp xếp, trang, sản phẩm và biến thể đang mở nằm trong URL (`detail`, `variant`) để tải lại/Back giữ đúng ngữ cảnh. Khi mở đơn từ ngăn chi tiết, nút “Quay lại báo cáo” khôi phục đầy đủ URL đó. Tổng giá nhập và lãi ở chi tiết đơn cũng hiện “Chưa đủ dữ liệu” nếu có dòng thiếu giá nhập.

Trên điện thoại, menu quản trị và bộ lọc báo cáo có nút mở/đóng; thẻ chỉ số xếp hai cột. Số tiền lớn rút gọn theo triệu/tỷ, vẫn giữ giá trị đầy đủ trong nhãn truy cập và chú thích. Biểu đồ co theo chiều rộng màn hình và giảm mật độ nhãn để thấy toàn kỳ; bảng dữ liệu tiếp tục cuộn ngang riêng.

Tab Đơn nhập hàng tính theo ngày tạo phiếu (GMT+7), trạng thái hiện tại. Mỗi phiếu được đếm một lần dù có nhiều SKU. Đang xử lý gồm Pending/Approved/Receiving; Completed, Closed, Cancelled, Rejected được phân biệt trên biểu đồ. Bảng từng phiếu có mã mở chi tiết, ngày tạo, nhà cung cấp, trạng thái, số lượng đặt/đã nhận và giá trị đặt. Quay lại từ chi tiết giữ kỳ, bộ lọc và trang.

Số lượng đặt, đã nhận và giá trị đặt trong tổng hợp/biểu đồ/Top 5 nhà cung cấp bỏ phiếu Cancelled/Rejected. Giá trị lấy từ tổng LineTotal của các dòng phù hợp bộ lọc, không phải tiền thực chi hay giá trị hàng thực nhận. Đã nhận là lũy kế hiện tại của các phiếu tạo trong kỳ, kể cả nhận sau kỳ; không phải báo cáo biên nhận theo ngày nhận. Dòng phiếu hủy/từ chối vẫn giữ giá trị đặt để tra cứu, nhưng không cộng vào tổng. Tổng hợp và Top 5 không phụ thuộc trang danh sách.

Tab nhập hàng yêu cầu quyền xem báo cáo đơn hàng và xem phiếu nhập; Staff/Admin hiện có các quyền này. Tồn kho chuyên sâu là phần mở rộng sau. Không dọn/xóa đơn thử hoặc sửa giá nhập lịch sử.

Bảng Bán hàng & lãi gộp bổ sung ba cột cạnh nhau: SL nhập, SL bán, SL còn. SL nhập gồm tồn khai báo ban đầu (StockAdjustments loại Opening, QuantityAfter; chỉ lấy khai báo trước thời điểm kết thúc kỳ, mỗi biến thể một lần) cộng PurchaseReceiptItems.Quantity theo ngày nhận PurchaseReceipts.ReceivedAt trong kỳ GMT+7, kể cả phiếu được tạo ngoài kỳ. SL bán giữ cách tính bán hàng hiện hành. SL còn là StockQuantity hiện tại của đúng biến thể, không phụ thuộc kỳ lọc; biến thể đã xóa hiển thị 0. Các số được tổng hợp riêng theo SKU để tránh nhân bản doanh số hoặc cộng cả các màu khác; không sửa dữ liệu hay schema database.

## Nhãn trạng thái tiếng Việt

Phần “Cách tính” của báo cáo đơn hàng dùng các tên “Đã giao”, “Hoàn tất”, “Đã hủy”, giải thích rõ ngày đặt và ngày giao. Các nhãn trạng thái trên giao diện khách hàng và Admin/Staff dùng tiếng Việt, giữ cách diễn đạt riêng của từng nghiệp vụ (ví dụ hoàn tất đơn hàng khác với trả máy sau đổi/trả). Trạng thái chưa nhận diện hiển thị “Chưa xác định”; dữ liệu trống hiển thị dấu gạch ngang.

Mã trạng thái gửi qua API, lưu trên đơn và dùng để xử lý nghiệp vụ giữ nguyên. Thông báo/lỗi nghiệp vụ được viết bằng tiếng Việt. Thông báo đơn hàng cũ theo mẫu hệ thống có mã trạng thái tiếng Anh được chuyển sang tiếng Việt khi xuất response; không sửa nội dung đã lưu và không thay thế các từ trong ghi chú tự do của khách hoặc nhân viên.

Đợt Việt hóa: 231 test backend và 167 subtest đạt; các kiểm tra nhãn giao diện, build và kiểm tra trình duyệt đạt. Test lọc khoảng ngày không hợp lệ của trang Bảo hành vẫn lỗi và tái hiện khi dùng module bảo hành và layout từ bản đã commit qua cấu hình chẩn đoán riêng.

## API

- `GET /admin/statistics/reports/revenue`: Quantity, Cost, Profit, Margin, LinesMissingCost trong Summary/Chart/Items; Items có ReceivedQuantity, StockQuantity. `group_by=variant` trên giao diện trả mỗi SKU một dòng với ProductVariantId, VariantName, Sku; mặc định API `group_by=product` giữ cách gộp cũ. TopProducts luôn gộp theo sản phẩm. `sort` là một trong `revenue|quantity|cost|profit|margin|name` + `_asc|_desc`, mặc định `revenue_desc`.
- `GET /admin/statistics/reports/revenue/lines`: bắt buộc product_id; dùng cùng date_from/date_to, category_id, brand_id, page/page_size; variant_id tùy chọn để chỉ đọc đúng SKU đang mở. Trả từng dòng bán hàng đã chốt, phân trang trong SQL.
- `GET /admin/statistics/reports/orders`: thêm InProgressOrders và CancellationReasons; Items vẫn theo tháng đặt hàng.
- `GET /admin/statistics/reports/purchases`: date_from/date_to bắt buộc; supplier_id, category_id, brand_id, product_id tùy chọn; page/page_size (mặc định 1/10, tối đa 100). Trả Period, Summary, Chart, Items, Suppliers (Top 5), Total, Page, PageSize. Summary gồm TotalOrders, InProgressOrders, CompletedOrders, ClosedOrders, CancelledOrders, RejectedOrders, OrderedQuantity, ReceivedQuantity, OrderedAmount. Chỉ SELECT từ PurchaseOrders, PurchaseOrderItems, Suppliers và danh mục hiện có.
- `GET /admin/statistics/report-options`: trả Categories, Brands, Products và Suppliers; nhà cung cấp chỉ gồm Id, Name, bao gồm ngừng hoạt động.
- `GET /admin/statistics/reports/orders/cancelled`: danh sách các đơn đặt trong kỳ và hiện đã hủy, dùng chung bộ lọc ngày/danh mục/thương hiệu/sản phẩm với báo cáo Đơn hàng; phân trang trong SQL. Mỗi dòng gồm OrderId, OrderCode, OrderedAt, CustomerName, TotalAmount, CancelReason. Chỉ đọc từ các bảng/cột hiện có.
- `GET /admin/statistics/reports/orders/delivered`: danh sách các đơn đặt trong kỳ và hiện Đã giao/Hoàn tất, dùng cùng bộ lọc và cách phân trang với danh sách đơn hủy. Không yêu cầu giao dịch thanh toán thành công, không lọc theo ngày giao. Mỗi dòng gồm OrderId, OrderCode, OrderedAt, DeliveredAt (có thể null), CustomerName, TotalAmount, OrderStatus. Một đơn nhiều SKU khớp bộ lọc vẫn chỉ xuất hiện một lần.
- `GET /admin/statistics/workload`: tổng PendingOrders, WaitingChats, PendingReturns, NewWarranties hiện tại trong một SELECT.
- `GET /admin/variants`: dùng các bộ lọc tồn kho hiện có `in_stock`, `low_stock`, `out_of_stock`. Không thêm endpoint hoặc bảng SKU.

Tất cả endpoint chỉ đọc, yêu cầu Staff/Admin. Schema response không phải schema database.

## Xác minh

Backend chạy trên SQLite trong bộ nhớ riêng, không kết nối DATABASE_URL:

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/test_admin_variant_list.py tests/test_statistics_reports.py tests/test_statistics_service.py tests/test_statistics_queries.py tests/test_purchase_reports.py tests/test_inventory.py -q -p no:cacheprovider
```

Frontend trên Windows dùng config loader native và worker threads để tránh sandbox chặn fork:

```powershell
cd frontend
npm.cmd test -- --configLoader native --pool threads --maxWorkers 2
npm.cmd run lint
npm.cmd run build -- --configLoader native
```

Kiểm tra trình duyệt dùng API giả lập riêng, không ghi database, ảnh mới nhất tại `output/report-review-fixes/` (bản trước tại `output/report-redesign/`). Hai trang được kiểm tra ở 1440, 1280, 1024, 768, 390 và 320px; trang và biểu đồ không tràn ngang, bảng cuộn riêng. Kiểm tra thêm menu/bộ lọc điện thoại, ngăn chi tiết, đóng bằng Escape và đi từ báo cáo sang đơn rồi quay lại đúng bộ lọc/trang/ngăn chi tiết.

Phần chi tiết đơn hủy: 48 test backend và 53 subtest, 87 test frontend liên quan đạt; build thành công. Trình duyệt kiểm tra mở/đóng bằng chuột và bàn phím, giữ bộ lọc khi mở đơn/quay lại báo cáo, và bố cục danh sách ở cả sáu chiều rộng trên. Ảnh `cancelled-orders-1440.png`, `cancelled-orders-390.png` dùng dữ liệu giả lập. Backend phát triển đã nạp endpoint mới, kiểm tra qua proxy frontend thành công.

Bổ sung chi tiết đơn đã giao: 56 test backend và 53 subtest, 93 test frontend liên quan đạt; build thành công, lint giữ hai cảnh báo có sẵn. Kiểm tra gồm đơn Hoàn tất chưa thanh toán, ngày giao trống hoặc nằm ngoài kỳ, biên ngày GMT+7, lọc nhiều SKU không trùng đơn, phân trang/thu hẹp trang khi làm mới, chuyển danh sách, giữ URL khi mở chi tiết và quay lại. Trình duyệt đạt ở cả sáu chiều rộng, không lỗi JavaScript; ảnh `delivered-orders-1440.png`, `delivered-orders-390.png`. API mới đã nạp và xác minh qua proxy frontend. Không thay đổi database hay dữ liệu nghiệp vụ.

Đợt sửa bổ sung: 71 test backend và 36 subtest đạt; 55 test frontend liên quan đạt; build thành công, lint chỉ còn hai cảnh báo có sẵn. Toàn bộ frontend đạt 1.156/1.157 test; test kiểm tra khoảng ngày không hợp lệ của `ReturnsPage.test.jsx` vẫn lỗi và tái hiện khi thay layout bằng bản đã commit qua cấu hình chẩn đoán riêng. Không sửa trang Đổi trả trong đợt này.

Bổ sung báo cáo nhập hàng: 61 test backend và 53 subtest, 74 test frontend liên quan đạt; build thành công, lint giữ hai cảnh báo có sẵn. Do giới hạn bộ nhớ và ổ C đầy, kiểm thử giao diện dùng cấu hình tạm bỏ plugin CSS; CSS được xác minh riêng trên bản build production bằng Chrome. Admin và Staff đều đạt tại 1440, 1024, 768, 390, 320px; không lỗi JavaScript hay tràn ngang trang. Kiểm tra lọc đồng thời nhà cung cấp/sản phẩm, phân trang, chuyển tab, mở phiếu và quay lại giữ URL. Kết quả/ảnh ở `output/purchase-report/`. Backend local đã nạp endpoint mới, xác minh qua proxy frontend. Không thêm bảng/cột hay ghi dữ liệu nghiệp vụ.
