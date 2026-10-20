# Đề xuất bổ sung đặc tả nhận hàng theo nhiều đợt

Ngày lập: 20/10/2026.

Tình trạng: BẢN ĐỀ XUẤT ĐỂ ĐƯA VÀO BÁO CÁO. Tài liệu mô tả luồng đang có trong hệ thống; chưa tự sửa báo cáo gốc hoặc thay đổi CSDL.

## 1. Vị trí bổ sung trong báo cáo

- Bảng 3.17 - Quản lý phiếu nhập hàng: bổ sung nghiệp vụ nhận hàng theo từng đợt và trường hợp kết thúc khi NCC không giao đủ. Có thể đặt thành hai bảng con 3.17a và 3.17b để không đánh lại số các bảng phía sau.
- Bảng 3.18 - Quản lý lịch sử nhập hàng: phân biệt danh sách các phiếu nhập với lịch sử từng lần thực nhận của mỗi phiếu.
- Phần thiết kế CSDL: cập nhật trạng thái và thông tin đóng phiếu trong PurchaseOrders; mô tả rõ OrderedQuantity/ReceivedQuantity; bổ sung hai bảng PurchaseReceipts và PurchaseReceiptItems cùng quan hệ khóa ngoại.
- Cập nhật mô hình quan hệ và các sơ đồ hoạt động liên quan nếu báo cáo có các sơ đồ này. Không chỉ bổ sung một đoạn văn rồi giữ nguyên các bảng/sơ đồ mâu thuẫn.

## 2. Bảng 3.17a - Tiếp nhận hàng theo từng đợt

| Thành phần | Nội dung đề xuất |
|---|---|
| Tên chức năng | Tiếp nhận hàng theo từng đợt của phiếu nhập đã được duyệt. |
| Tác nhân | Nhân viên, Quản trị viên. |
| Mô tả | Một phiếu nhập có thể được nhà cung cấp giao thành nhiều đợt. Mỗi lần tiếp nhận, người thực hiện ghi số lượng thực nhận của từng biến thể; hệ thống lưu lịch sử và cập nhật kho theo lượng nhận thực tế. |
| Sự kiện kích hoạt | Người thực hiện mở chi tiết phiếu nhập và chọn Nhận hàng vào kho. |
| Đầu vào | Mã phiếu; các dòng hàng nhận; số lượng nhận trong đợt; Serial/IMEI tương ứng với biến thể có quản lý Serial; ghi chú nếu có. |
| Điều kiện trước | Người thực hiện đã đăng nhập bằng vai trò NV/QTV; phiếu ở Đã duyệt hoặc Đang nhận hàng; còn ít nhất một dòng chưa nhận đủ. |
| Kết quả thành công | Lưu một lần nhận hàng; cộng dồn thực nhận; cập nhật tồn kho, giá vốn, Serial; phiếu ở Đang nhận hàng hoặc Đã nhận đủ. |
| Kết quả khi thất bại | Không lưu một phần: lịch sử, số lượng thực nhận, kho, giá vốn và Serial của lần nhận đều được hoàn tác. |

### Luồng sự kiện chính

1. Người thực hiện mở chi tiết một phiếu Đã duyệt hoặc Đang nhận hàng.
2. Hệ thống hiển thị từng SKU, số lượng đặt, tổng thực nhận và số lượng còn thiếu.
3. Người thực hiện nhập số lượng thực nhận TRONG ĐỢT NÀY cho những dòng có nhận hàng, nhập Serial/IMEI nếu biến thể yêu cầu và ghi chú nếu có. Không nhập lại tổng cộng dồn.
4. Hệ thống kiểm tra dòng hàng thuộc phiếu, số lượng hợp lệ và tổng thực nhận sau đợt không vượt số đặt. Mỗi sản phẩm quản lý Serial phải có đúng một mã thực tế, không trùng với mã đã ghi nhận.
5. Hệ thống ghi người nhận và thời điểm nhận theo tài khoản đăng nhập và đồng hồ máy chủ.
6. Trong một giao dịch, hệ thống tạo lịch sử lần nhận, tạo các dòng nhận, cộng ReceivedQuantity, cập nhật tồn kho/giá vốn và ghi Serial tương ứng.
7. Nếu còn bất kỳ dòng nào nhận chưa đủ thì phiếu ở Đang nhận hàng. Nếu mọi dòng đều nhận đủ thì chuyển Đã nhận đủ và không tiếp nhận thêm hàng trên phiếu đó.
8. Hệ thống hiển thị kết quả và lịch sử lần nhận vừa ghi. Các đợt tiếp theo lặp lại cùng quy trình khi phiếu vẫn Đang nhận hàng.

### Luồng thay thế

- NCC giao đủ ngay đợt đầu: chuyển thẳng Đã duyệt sang Đã nhận đủ.
- Một đợt chỉ giao một số SKU: chỉ nhập các dòng có nhận, các dòng còn lại giữ nguyên số thực nhận.
- Vượt số còn thiếu, sai dòng, thiếu/trùng Serial hoặc lỗi ghi dữ liệu: báo lỗi và hoàn tác toàn bộ đợt nhận.
- Phiếu chưa được duyệt, đã từ chối, đã nhận đủ hoặc đã đóng thiếu: từ chối thao tác nhận hàng.
- NCC xác nhận không giao phần còn lại: thực hiện chức năng Đóng phiếu nhập thiếu, không tự động kết thúc sau một khoảng thời gian.

## 3. Bảng 3.17b - Đóng phiếu nhập thiếu

| Thành phần | Nội dung đề xuất |
|---|---|
| Tên chức năng | Đóng phiếu nhập khi NCC không giao đủ hàng. |
| Tác nhân | Quản trị viên. |
| Điều kiện trước | Phiếu Đang nhận hàng, đã nhận một phần và vẫn còn thiếu. |
| Đầu vào | Phiếu nhập và lý do kết thúc bắt buộc nhập. |
| Luồng chính | QTV chọn Đóng phiếu nhận thiếu; nhập lý do; hệ thống kiểm tra điều kiện, ghi người/thời điểm/lý do và chuyển phiếu thành Đóng phiếu thiếu. |
| Đầu ra | Giữ nguyên số đặt, số thực nhận và lịch sử các đợt đã nhận; không cộng lượng thiếu vào kho; không tiếp nhận thêm trên phiếu đã đóng. |
| Luồng thay thế | Không đủ quyền, thiếu lý do hoặc phiếu không còn ở Đang nhận hàng thì báo lỗi, không thay đổi dữ liệu. |

Đóng thiếu khác với Từ chối: Từ chối diễn ra trước khi tiếp nhận hàng, còn Đóng thiếu kết thúc một phiếu đã nhận một phần. Đây là hai trường hợp có dữ liệu kho khác nhau.

## 4. Quy tắc và trạng thái cần ghi thống nhất

| Trạng thái | Ý nghĩa và thao tác |
|---|---|
| Pending - Chờ duyệt | Người tạo được sửa; QTV xét duyệt hoặc từ chối. Không nhận hàng. |
| Approved - Đã duyệt | Khóa nội dung đặt hàng; NV/QTV được ghi nhận hàng thực tế. |
| Rejected - Từ chối | Phiếu kết thúc, giữ lý do/người/thời điểm từ chối; không sửa hoặc nhận hàng. Nhu cầu mới phải lập phiếu mới. |
| Receiving - Đang nhận hàng | Đã nhận một phần, còn thiếu; tiếp tục nhận hoặc QTV đóng thiếu. |
| Completed - Đã nhận đủ | Mọi dòng đã nhận đủ; không sửa nội dung hoặc tiếp nhận thêm. |
| Closed - Đóng phiếu thiếu | QTV kết thúc phiếu còn thiếu; không tiếp nhận thêm, giữ số liệu thực tế. |

- Giữ đúng hệ thống hiện tại: NV lập phiếu ở Pending; QTV lập được Approved ngay. Nếu muốn thay quy tắc này thì cần chốt riêng, không suy ra từ nghiệp vụ nhận nhiều đợt.
- Cả NV và QTV chỉ được sửa phiếu của mình và chỉ khi Pending. Quyền tiếp nhận hàng hiện dành cho NV/QTV, không giới hạn theo người tạo.
- Quyết định duyệt thủ công do QTV khác người tạo thực hiện. Duyệt chưa cộng tồn kho.
- Mỗi lần nhận phải là một giao dịch: một dòng lỗi thì không dòng nào của đợt đó được ghi nhận.
- Không xóa/sửa riêng từng lần nhận để chỉnh tồn kho. Quyền xóa toàn bộ chứng từ của QTV là nghiệp vụ riêng đã được chốt; khi xóa chứng từ và lịch sử liên quan, tồn kho, giá vốn và Serial đã ghi nhận vẫn giữ nguyên.
- Giá trị Cancelled còn được hệ thống giữ để đọc dữ liệu cũ; không có thao tác tạo mới trạng thái này trong luồng hiện hành.

## 5. Bổ sung mô tả CSDL

### PurchaseOrders

Mô tả Status cần bổ sung Receiving, Completed và Closed theo bảng trạng thái phía trên. Giữ các trường đóng phiếu sau:

| Thuộc tính | Ý nghĩa |
|---|---|
| ClosedByUserId | QTV đóng phiếu; tham chiếu Users. |
| ClosedAt | Thời điểm đóng phiếu. |
| CloseReason | Lý do đóng thiếu. Bắt buộc có nội dung khi Status=Closed. |

### PurchaseOrderItems

| Thuộc tính | Ý nghĩa |
|---|---|
| OrderedQuantity | Số lượng đặt, lớn hơn 0. |
| ReceivedQuantity | Tổng số đã thực nhận qua mọi đợt; khởi tạo 0, không âm và không vượt OrderedQuantity. |
| UnitPrice | Đơn giá nhập theo phiếu đã duyệt. |
| LineTotal | OrderedQuantity nhân UnitPrice. |

Số còn thiếu = OrderedQuantity - ReceivedQuantity, được tính khi đọc dữ liệu, không cần thêm cột MissingQuantity trong CSDL.

### PurchaseReceipts - từng đợt tiếp nhận

| Thuộc tính | Kiểu/quan hệ và ý nghĩa |
|---|---|
| PurchaseReceiptId | UUID, khóa chính của đợt nhận. |
| PurchaseOrderId | UUID, khóa ngoại tới PurchaseOrders; xác định phiếu được nhận hàng. |
| ReceivedByUserId | UUID, khóa ngoại tới Users; người nhận thực tế. |
| ReceivedAt | Thời điểm nhận do máy chủ ghi. |
| Note | Ghi chú cho đợt nhận, có thể để trống. |

### PurchaseReceiptItems - các dòng hàng trong đợt nhận

| Thuộc tính | Kiểu/quan hệ và ý nghĩa |
|---|---|
| PurchaseReceiptId | UUID, khóa ngoại tới PurchaseReceipts. |
| PurchaseOrderItemId | UUID, khóa ngoại tới PurchaseOrderItems. |
| Quantity | Số nhận thêm TRONG ĐỢT, lớn hơn 0. |
| UnitPrice | Đơn giá theo dòng phiếu nhập, lưu tại thời điểm nhận. |

Khóa chính ghép: PurchaseReceiptId + PurchaseOrderItemId. Một phiếu có nhiều đợt nhận; mỗi đợt có nhiều dòng nhận; một dòng đặt có thể xuất hiện ở nhiều đợt.

### Tồn kho và giá trị

- ProductVariants.StockQuantity chỉ tăng bằng Quantity nhận trong đợt, không tăng bằng OrderedQuantity khi duyệt.
- ProductVariants.CostPrice được cập nhật theo giá vốn bình quân gia quyền khi nhận hàng; ProductSerials ghi các mã nhận thực tế cho biến thể quản lý Serial.
- PurchaseOrders.TotalAmount hiện là tổng giá trị ĐẶT theo phiếu, không tự giảm khi đóng thiếu. Giá trị hàng nhận thực tế tính từ tổng Quantity nhân UnitPrice của PurchaseReceiptItems. Không đồng nhất hai con số này và không tự suy ra đã thanh toán NCC.

## 6. Ví dụ nghiệm thu

Phiếu đặt 10 chiếc, đơn giá 100.000 đồng: tổng giá trị đặt 1.000.000 đồng.

- Đợt 1 nhận 6: ReceivedQuantity=6; số thiếu=4; tồn tăng 6; Status=Receiving; lưu một PurchaseReceipt và dòng Quantity=6.
- Nếu đợt 2 nhận thêm 4: ReceivedQuantity=10; số thiếu=0; tồn tăng thêm 4; Status=Completed; lưu đợt nhận thứ hai.
- Nếu NCC không giao thêm: QTV đóng thiếu, bắt buộc ghi lý do; ReceivedQuantity giữ 6; thiếu 4; Status=Closed; tồn không đổi vì thao tác đóng phiếu.
- Trường hợp đóng ở 6 chiếc: giá trị đặt vẫn 1.000.000 đồng, giá trị thực nhận là 600.000 đồng. Đây không phải phép tính xác nhận thanh toán.
- Thử nhận thêm khi Completed/Closed, nhận vượt số còn thiếu hoặc thiếu Serial: hệ thống từ chối và không thay đổi tồn/lịch sử.

## 7. Nguồn đối chiếu

- Bản báo cáo đầy đủ được cung cấp: Bảng 3.17, Bảng 3.18, bảng thiết kế PurchaseOrders và PurchaseOrderItems.
- Source: backend/app/models/purchasing.py; backend/app/services/purchasing.py; backend/app/schemas/purchasing.py.
- Giao diện: frontend/src/admin/pages/PurchaseDetailPage.jsx và frontend/src/admin/components/PurchaseDialogs.jsx.
- Bản báo cáo hiện có các cột số đặt/thực nhận, nhưng chưa mô tả nhận nhiều đợt, đóng thiếu và hai bảng lịch sử từng đợt. Nội dung trong tài liệu này là đề xuất bổ sung để thống nhất với phần hệ thống đã triển khai.
