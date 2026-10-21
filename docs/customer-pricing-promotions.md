# Giá ưu đãi sản phẩm và coupon công khai

Phạm vi ngày 19/10/2026: triển khai phần sản phẩm, quản trị khuyến mãi và xem thử giá cho khách. Thành viên khác đang làm giỏ hàng, thanh toán, tạo đơn nên các file nghiệp vụ đó chưa được sửa. Giá ưu đãi trên trang sản phẩm và API xem thử đã hoạt động; giỏ/đơn cũ vẫn cần nối bộ tính giá mới trước khi thử mua hàng theo giá ưu đãi.

**Cập nhật 20/10/2026:** giỏ hàng, `/cart/coupon-preview` và tạo đơn đã tính theo giá sau giảm trực tiếp (dùng chung `variant_price` qua `PromotionRepository.list_automatic`), lưu đơn theo bảng ánh xạ ở mục dưới. Luồng tạo đơn vẫn dùng `CouponService.apply_coupon_to_order` (không gọi `reserve_order_quote`); từ 21/10/2026 nó và `/cart/coupon-preview` áp thêm hai quy tắc: mỗi tài khoản dùng mỗi mã một lần (`coupon_customer_limit`, đơn đã hủy trả lại lượt) và coupon không được làm dòng được giảm thấp hơn giá vốn hoặc áp cho dòng chưa có giá vốn (`coupon_price_floor`). Mã giảm 100 % hay giảm quá tiền hàng vì vậy bị từ chối. Mã công khai không còn hiện ở trang chủ và trang chi tiết; khách chọn trong hộp **Áp dụng mã giảm giá** của giỏ hàng.

Đã [đồng bộ cặp giá niêm yết/giá bán và giảm giá vốn mẫu ngày 19/10/2026](retail-list-and-sample-cost-2026-10-19.md) theo yêu cầu tiếp theo. Bản [rà giá trước đó](market-pricing-2026-10-19.md) và ví dụ lúc seed ghi nhận các bước cũ, không thay thế bảng giá mới nhất.

## CSDL và quy tắc

- Migration `82d6f1a9b407` thêm `Promotions.ApplyMode` (`Coupon` / `Automatic`), CHECK và mặc định `Coupon`. Migration tiếp theo `93e7a2b0c518` thêm `ProductVariants.CompareAtPrice` nullable, CHECK lớn hơn hoặc bằng `Price`. Không thêm bảng.
- `CompareAtPrice` là giá niêm yết công khai; `Price` là giá bán cơ sở trước chương trình Automatic bổ sung, `CostPrice` là giá vốn. Server tính `SalePrice` sau Automatic; `OriginalPrice` lấy giá niêm yết nếu có, nếu không lấy `Price`. Phần trăm/số tiền tiết kiệm so cùng SKU.
- Bộ mẫu hiện dùng đúng cặp giá của CellphoneS/GearVN; 5 Automatic thử của batch đầu đã Cancelled để không giảm thêm ngoài giá bán nguồn. Coupon vẫn áp dụng trên tiền hàng thực tế. `AutomaticDiscount` của báo giá bao gồm tổng chênh từ giá niêm yết đến giá bán thực tế (cả chênh niêm yết/cơ sở và Automatic bổ sung nếu có).
- Automatic: số tiền hoặc phần trăm giảm theo từng chiếc; `MaxDiscountAmount` là trần mỗi chiếc, `MinOrderValue` phải bằng 0. Không gán phạm vi nghĩa là toàn bộ sản phẩm; phạm vi sản phẩm hoặc danh mục khớp trực tiếp, không tự gồm danh mục con. Vì sản phẩm chỉ nằm ở danh mục con, khi admin chọn một danh mục thì giao diện gửi danh mục đó kèm mọi danh mục con hiện có; danh mục con tạo sau hoặc chuyển vào cũng tự được thêm vào các chương trình chưa hủy, chưa kết thúc đang áp cho danh mục cha.
- Nếu nhiều chương trình Automatic cùng hợp lệ, chỉ lấy giá thấp nhất, không cộng các chương trình trực tiếp với nhau; cùng giá chọn theo ID ổn định. Ngày bắt đầu và kết thúc đều bao gồm mốc đó, dùng giờ máy chủ; Draft/Cancelled/Expired không áp dụng.
- Chặn admin lưu chương trình trực tiếp khiến biến thể trong phạm vi có giá sau giảm dưới vốn hoặc chưa có vốn hợp lệ. Nếu vốn/giá thay đổi sau khi lưu, bỏ ưu đãi không còn hợp lệ, không tự đổi mức giảm đã cấu hình.
- Coupon công khai, không nhận/lưu trước. `UsageLimit`/`UsedCount` là tổng lượt dùng chung, không phải số lượt sao chép hoặc xem thử. Hết lượt/chưa bắt đầu/hết hạn không hiển thị ở danh sách công khai.
- Mỗi tài khoản dùng mỗi mã tối đa một lần, kiểm tra lịch sử `Orders.CustomerId` + `CouponId`, bỏ qua đơn `Cancelled`. Chưa thêm cột tùy chỉnh số lần mỗi khách. Đây là kiểm tra trong bộ giá mới; luồng tạo đơn cũ chưa gọi bộ giá mới.
- Một đơn tối đa một coupon. Coupon tính trên giá sau giảm trực tiếp; đơn tối thiểu xét tổng tiền hàng sau giảm trực tiếp, tiền giảm tính trên các dòng thuộc phạm vi coupon. Phí vận chuyển không thuộc cơ sở tính giảm tiền hàng.
- Phân bổ coupon theo giá trị dòng, tổng phân bổ khớp số tiền coupon tới 0,01đ; từ chối nếu sau phân bổ có dòng dưới giá vốn/chưa có giá vốn. Không âm thầm giảm giá trị coupon cố định đã quảng bá.
- Lãi gộp = tiền hàng sau mọi ưu đãi - tổng `UnitCost × Quantity`. Không đưa giá vốn/lãi vào phản hồi công khai. Lãi đơn đã bán dùng `OrderItems.UnitCost` đã chốt, không dùng vốn hiện tại.

## Quản trị và trang khách

Trong Quản lý khuyến mãi, chọn **Cách áp dụng**. Automatic tự đặt đơn tối thiểu bằng 0. (Bảng "Xem giá và lãi dự kiến" đã bỏ ngày 21/10/2026: không tính được mã giảm giá vì mã áp theo đơn; khi lưu, hệ thống vẫn chặn chương trình làm giá dưới giá nhập.) Chương trình đang Active vẫn khóa điều kiện và phạm vi như trước. Form mã giảm giá chỉ chọn chương trình Coupon.

Trang chủ, danh sách, trang chi tiết, sản phẩm tương tự và yêu thích hiện giá ưu đãi theo dữ liệu API. Bộ lọc giá công khai dùng giá sau giảm trong SQL trước phân trang. Badge phần trăm hiển thị tối đa hai chữ số thập phân; số tiền giảm bằng tiền là nguồn tính giá, không tính ngược từ badge làm tròn.

Bốn ô quảng bá trên trang chủ theo [Figma Category Promos, node 917:1708](https://www.figma.com/design/aLG7De0fgbWCfaIpzIrPii/VieTech---Homepage-UI?node-id=917-1708). Trước đây các ô hiện số lượng vì chưa có nguồn giá ưu đãi; hiện dùng `GET /pricing/category-offers`: tổng hợp mức giảm trực tiếp cao nhất của biến thể đang hoạt động, chưa xóa, còn hàng, thuộc sản phẩm Active trong danh mục gốc và các danh mục con đang hoạt động. Laptop hiện số tiền, các nhóm khác hiện phần trăm; không cộng coupon vào dòng quảng bá. Phần trăm làm tròn xuống tối đa hai chữ số để không quảng bá vượt mức giảm thực tế. Truy vấn SQL dùng cùng quy tắc thời hạn/phạm vi/giá vốn với giá sản phẩm, không tải từng chi tiết sản phẩm về trình duyệt.

Tên và liên kết của bốn ô lấy từ danh mục có thật: ưu tiên Điện thoại, Laptop, Phụ kiện, Gia dụng thông minh; nếu thiếu thì dùng danh mục gốc kế tiếp theo thứ tự hiển thị. CSDL thử hiện chưa có Phụ kiện/Gia dụng thông minh nên hai ô sau là Máy tính bảng/Tai nghe. Không thêm danh mục rỗng hoặc hardcode mức 30%, 50%, 5 triệu của bản thiết kế. Không có ưu đãi hiện “Khám phá sản phẩm”; không có sản phẩm còn hàng hiện “Sắp có hàng”. Lỗi tải ưu đãi vẫn giữ liên kết danh mục với lời mời mua sắm chung. Dữ liệu được đọc lại mỗi 30 giây và khi cửa sổ được focus.

Mã công khai (điều kiện, hạn dùng, lượt còn) hiện trong hộp **Nhập hoặc chọn mã khuyến mãi** của giỏ hàng. Mã chưa đạt đơn tối thiểu của các dòng đang chọn ghi số tiền còn thiếu và không chọn được; chọn mã thì kiểm tra bằng `/cart/coupon-preview` trên đúng các dòng đang chọn. Trang chủ và trang chi tiết không còn khối mã ưu đãi (bỏ từ 20/10/2026).

## API cho thành viên làm giỏ hàng/đặt hàng

1. `GET /products/{id}` hoặc `/products/slug/{slug}`: dùng `SalePrice` hiển thị giá thực tế, `OriginalPrice` làm giá gạch ngang. Từ 20/10/2026 `OriginalPrice` luôn bằng `Price`: chỉ khuyến mãi giảm trực tiếp mới tạo giá gạch, `CompareAtPrice` không còn hiện cho khách. `Price` là giá bán trước Automatic bổ sung; `CompareAtPrice` là giá niêm yết lưu riêng theo SKU. Các trường tính toán gồm `DiscountAmount`, `DiscountPercent`, `AppliedPromotionId`, `PromotionName`, `PromotionEndsAt`.
2. `GET /coupons?product_id=<optional>`: mã còn hiệu lực và còn lượt, kèm điều kiện từ chương trình, `RemainingUses`, `PerCustomerUsageLimit = 1`, `EvaluatedAt`. Không chứa người tạo hoặc thông tin khách khác. Đây là gợi ý mã; không bảo đảm đủ đơn tối thiểu hay còn lãi, phải xem thử/kiểm tra khi đặt hàng.
3. `POST /pricing/quote`: xem thử bằng các `ProductVariantId`/`Quantity` và `CouponCode` tùy chọn. Không nhận giá, số tiền giảm hoặc CustomerId do trình duyệt gửi. Bearer tùy chọn; nếu có thì kiểm tra lịch sử mã của chính tài khoản đó.

```json
{
  "Items": [{"ProductVariantId": "<UUID>", "Quantity": 2}],
  "CouponCode": "TEST300K"
}
```

Phản hồi có `OriginalSubtotal`, `Subtotal` (sau Automatic), `AutomaticDiscount`, `CouponDiscount`, `Total` (chưa phí vận chuyển), từng dòng và `PreviewOnly = true`. `AutomaticDiscount` và `CouponDiscount` của từng dòng đã nhân số lượng; `OriginalPrice` và `SalePrice` là đơn giá.

## Nối vào giao dịch tạo đơn sau này

`PricingService.reserve_order_quote(actor, items, coupon_code=...)` là helper sẵn có, CHƯA được gọi từ OrderService hiện tại. Cách dùng:

```python
# Bên trong giao dịch tạo đơn hiện có, sau khi khóa giỏ và các biến thể theo thứ tự ID:
quote = PricingService(session).reserve_order_quote(actor, items, coupon_code=data.CouponCode)
# Tạo Order + OrderItems trong chính transaction này. Lỗi bất kỳ bước nào phải rollback.
```

Helper yêu cầu enclosing transaction và Actor Customer, kiểm tra lại giá/vốn/tồn/hiệu lực/phạm vi/đơn tối thiểu/lịch sử mã, khóa dòng Coupon (`FOR UPDATE`) trước kiểm tra giới hạn và tăng UsedCount. Nó không tự tạo đơn, không tự commit và không tự trừ tồn kho. **Caller bắt buộc tạo Order có CouponId trước commit cùng transaction**, không gọi helper riêng rồi commit một lượt mã không có đơn.

Ánh xạ vào schema đơn hiện có:

| Trường đơn | Giá trị |
|---|---|
| `Orders.Subtotal` | `quote.OriginalSubtotal` |
| `Orders.DiscountAmount` | `quote.AutomaticDiscount + quote.CouponDiscount` |
| `Orders.TotalAmount` | `quote.Total + ShippingFee` |
| `Orders.CouponId` | `quote.CouponId` |
| `OrderItems.UnitPrice` | Dòng `OriginalPrice` |
| `OrderItems.DiscountAmount` | Dòng `AutomaticDiscount + CouponDiscount` |
| `OrderItems.LineTotal` | Dòng `LineTotal` |
| `OrderItems.UnitCost` | Giá vốn của biến thể đã khóa tại thời điểm mua |

Không gọi thêm `CouponService.apply_coupon_to_order` cũ trong cùng lần tạo đơn, tránh giảm/trừ lượt hai lần. Giỏ hàng nên dùng `/pricing/quote` cho các dòng đang chọn; frontend chỉ trình bày kết quả server, không tự tính lại mức giảm. Đồng bộ `/cart/coupon-preview` cũ với bộ giá mới khi thành viên phụ trách nối luồng. Giữ cơ chế hủy hợp lệ trả coupon một lần, hoàn tồn kho và kiểm tra lại điều kiện khi đặt hàng.

## Dữ liệu thử

`backend/scripts/seed_test_promotions.py` mặc định chỉ xem trước; `--apply` thêm các bản ghi còn thiếu. Không cập nhật giá/vốn/tồn hoặc tạo đơn; chạy lại không reset UsedCount hay ghi đè chương trình đã tồn tại. Tên chương trình có tiền tố `[TEST] public-pricing-test-v1`, có thể hủy từ admin khi thử xong.

```powershell
cd E:\vitech-ecommerce\backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe scripts\seed_test_promotions.py --apply --report ..\output\pricing\seed-applied.json
```

Mức thử theo nhóm sản phẩm: 2.000.000đ, 200.000đ, 100.000đ, 50.000đ, 10.000đ; chỉ gán mức còn từ giá vốn trở lên cho tất cả biến thể hoạt động của sản phẩm. Báo cáo JSON chứa các URL sản phẩm để mở thử.

| Mã | Điều kiện thử |
|---|---|
| `TEST300K` | Giảm 300.000đ, đơn từ 20 triệu, 100 lượt |
| `TEST100K` | Giảm 100.000đ, đơn từ 2 triệu, 100 lượt |
| `TEST10P` | Giảm 10%, tối đa 50.000đ, đơn từ 500.000đ, 20 lượt |
| `TESTHETLUOT` | UsageLimit=0, không xuất hiện ở khách; nhập thử báo hết lượt |
| `TESTSAPTOI` | Bắt đầu sau ngày tạo 1 ngày, chưa xuất hiện ở khách |

Mã đều phải qua kiểm tra vốn sau cộng dồn. Việc xem thử không làm giảm số lượt, không tạo lịch sử mua. Có thể đổi sang biến thể khác để xem đúng giá của màu/cấu hình đó.
