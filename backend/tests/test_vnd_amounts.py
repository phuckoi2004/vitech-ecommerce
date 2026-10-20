"""Tiền VND nguyên đồng: đầu vào phía bán, giảm giá làm tròn xuống, phân bổ theo đồng, chặn đơn chuyển khoản 0 đồng.

Fake database trong bộ nhớ: không kết nối database, không gọi cổng thanh toán.
"""

import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

from pydantic import ValidationError

from app.models import CartItem, Order, PaymentTransaction, Promotion
from app.schemas import (
    OrderCreate,
    ProductVariantCreate,
    ProductVariantUpdate,
    PromotionCreate,
    PromotionUpdate,
    ShippingMethodCreate,
    ShippingMethodUpdate,
)
from app.schemas.catalog_item import CatalogVariantWrite
from app.services import BusinessRuleError, allocate_discount, calculate_discount
from app.services.promotion import PromotionService, SimpleDiscountLine

from tests.fakes import (
    FakePromotionCategoryRepo, FakePromotionProductRepo, FakePromotionRepo, FakeSession,
    Factory, InMemoryDB, coupon_service, fixed_clock, order_service,
)

WHOLE_VND = "VND nguyên đồng"


def promo(kind="Percentage", value="10", cap=None):
    return NS(DiscountType=kind, DiscountValue=Decimal(value), MaxDiscountAmount=None if cap is None else Decimal(cap))


def lines(*grosses):
    return [SimpleDiscountLine(uuid.uuid4(), uuid.uuid4(), Decimal(gross)) for gross in grosses]


# ======================================================================
# Đầu vào: giá bán, phí vận chuyển, giá trị tiền khuyến mãi
# ======================================================================


class MoneyInputTest(unittest.TestCase):
    def assert_rejected(self, schema, message=WHOLE_VND, **values):
        with self.assertRaises(ValidationError) as ctx:
            schema(**values)
        self.assertIn(message, str(ctx.exception))

    def test_selling_price_is_whole_vnd(self):
        base = {"ProductId": uuid.uuid4(), "Sku": "SKU-1", "VariantName": "Đen"}
        self.assertEqual(ProductVariantCreate(**base, Price="100000").Price, Decimal("100000"))
        self.assertEqual(ProductVariantCreate(**base, Price="100000.00").Price, Decimal("100000"))
        self.assert_rejected(ProductVariantCreate, **base, Price="100000.5")
        self.assertEqual(ProductVariantUpdate(Price="250000").Price, Decimal("250000"))
        self.assert_rejected(ProductVariantUpdate, Price="0.50")
        self.assert_rejected(CatalogVariantWrite, Sku="SKU-2", Color="Trắng", Price="99999.99")

    def test_shipping_fee_is_whole_vnd(self):
        valid = {"Code": "GHN", "Name": "Giao hàng nhanh", "EstimatedDays": 2}
        self.assertEqual(ShippingMethodCreate(**valid, BaseFee="0").BaseFee, Decimal("0"))
        self.assertEqual(ShippingMethodCreate(**valid, BaseFee="30000.00").BaseFee, Decimal("30000"))
        self.assert_rejected(ShippingMethodCreate, **valid, BaseFee="30000.50")
        self.assert_rejected(ShippingMethodUpdate, BaseFee="15000.1")

    def test_promotion_money_is_whole_vnd_but_percentages_keep_decimals(self):
        when = {"StartDate": datetime(2026, 10, 1, tzinfo=timezone.utc), "EndDate": datetime(2026, 11, 1, tzinfo=timezone.utc)}
        base = {"Name": "Ưu đãi", "Status": "Draft", "MinOrderValue": "0", **when}
        self.assertEqual(PromotionCreate(**base, DiscountType="Percentage", DiscountValue="12.5").DiscountValue,
                         Decimal("12.5"))
        self.assertEqual(PromotionCreate(**base, DiscountType="FixedAmount", DiscountValue="50000").DiscountValue,
                         Decimal("50000"))
        self.assert_rejected(PromotionCreate, **base, DiscountType="FixedAmount", DiscountValue="10000.5")
        self.assert_rejected(PromotionCreate, **{**base, "MinOrderValue": "0.5"}, DiscountType="Percentage",
                             DiscountValue="10")
        self.assert_rejected(PromotionCreate, **base, DiscountType="Percentage", DiscountValue="10",
                             MaxDiscountAmount="100.5")
        self.assert_rejected(PromotionUpdate, DiscountType="FixedAmount", DiscountValue="1.5")
        # The type is unknown in a PATCH sending only the value: the Service checks it against the stored type.
        self.assertEqual(PromotionUpdate(DiscountValue="1.5").DiscountValue, Decimal("1.5"))


class _ReachedDetail(Exception):
    pass


class _RecordingPromotionRepo(FakePromotionRepo):
    def __init__(self, db):
        super().__init__(db)
        self.updates = []

    def update(self, obj, values):
        self.updates.append(dict(values))
        return super().update(obj, values)

    def get_detail(self, promotion_id):
        raise _ReachedDetail()


class _RecordingCouponRepo:
    """After saving, update_promotion re-evaluates the promotion's coupons (coupon lifecycle)."""

    def __init__(self):
        self.synchronized = []

    def synchronize(self, now, promotion_id=None):
        self.synchronized.append(promotion_id)


class _PromotionUpdateSession(FakeSession):
    def expire(self, obj):  # update_promotion reloads the promotion after the coupon sync; nothing is cached here
        pass


class PromotionUpdateServiceTest(unittest.TestCase):
    """PATCH is rechecked with the stored discount type (the schema cannot know it)."""

    def setUp(self):
        self.db = InMemoryDB()
        self.f = Factory(self.db)
        self.admin = self.f.user("Admin")
        self.svc = PromotionService(_PromotionUpdateSession(self.db), clock=fixed_clock)
        self.svc.promotions = _RecordingPromotionRepo(self.db)
        self.svc.promotion_products = FakePromotionProductRepo(self.db)
        self.svc.promotion_categories = FakePromotionCategoryRepo(self.db)
        self.svc.coupons = _RecordingCouponRepo()

    def stored(self, kind, value):
        return self.db.add(Promotion(
            CreatedByUserId=self.admin.UserId, Name="KM", ApplyMode="Coupon", DiscountType=kind, DiscountValue=Decimal(value),
            MinOrderValue=Decimal("0"), StartDate=datetime(2026, 1, 1, tzinfo=timezone.utc),
            EndDate=datetime(2026, 12, 31, tzinfo=timezone.utc), Status="Draft",
        ))

    def update(self, promotion, **values):
        return self.svc.update_promotion(self.f.actor(self.admin), promotion.PromotionId, PromotionUpdate(**values))

    def test_fractional_value_for_a_stored_fixed_amount_is_rejected(self):
        promotion = self.stored("FixedAmount", "50000")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.update(promotion, DiscountValue="1000.5")
        self.assertEqual(ctx.exception.code, "invalid_discount_value")
        self.assertEqual(self.svc.promotions.updates, [])

    def test_switching_a_fractional_percentage_to_fixed_amount_is_rejected(self):
        promotion = self.stored("Percentage", "12.5")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.update(promotion, DiscountType="FixedAmount")
        self.assertEqual(ctx.exception.code, "invalid_discount_value")

    def test_legacy_fractional_fixed_amount_can_still_be_renamed(self):
        promotion = self.stored("FixedAmount", "1000.5")
        with self.assertRaises(_ReachedDetail):  # passed the checks and saved; the stub stops at reading details
            self.update(promotion, Name="Đổi tên")
        self.assertEqual(self.svc.promotions.updates, [{"Name": "Đổi tên"}])
        self.assertEqual(self.svc.coupons.synchronized, [promotion.PromotionId])


# ======================================================================
# Giảm giá: làm tròn xuống đến đồng, rồi giới hạn
# ======================================================================


class CalculateDiscountTest(unittest.TestCase):
    def test_percentage_is_rounded_down_to_the_dong(self):
        self.assertEqual(calculate_discount(promo(value="15"), Decimal("333333")), Decimal("49999"))  # 49 999,95
        self.assertEqual(calculate_discount(promo(value="12.5"), Decimal("99999")), Decimal("12499"))  # 12 499,875
        self.assertEqual(calculate_discount(promo(value="10"), Decimal("1000")), Decimal("100"))

    def test_cap_and_subtotal_limit(self):
        self.assertEqual(calculate_discount(promo(value="10", cap="50000"), Decimal("1000000")), Decimal("50000"))
        self.assertEqual(calculate_discount(promo(kind="FixedAmount", value="200000"), Decimal("150000")),
                         Decimal("150000"))
        self.assertEqual(calculate_discount(promo(value="100"), Decimal("250000")), Decimal("250000"))

    def test_legacy_fractional_values_still_give_whole_dong_within_every_limit(self):
        self.assertEqual(calculate_discount(promo(value="10", cap="50000.75"), Decimal("1000000")), Decimal("50000"))
        self.assertEqual(calculate_discount(promo(kind="FixedAmount", value="10000.5"), Decimal("200000")),
                         Decimal("10000"))
        self.assertEqual(calculate_discount(promo(value="100"), Decimal("1234.56")), Decimal("1234"))

    def test_result_is_always_whole_and_never_above_the_exact_value(self):
        for value in ("0.01", "3.33", "7", "15", "33.33", "99.99"):
            for base in ("1", "999", "333333", "1234567"):
                with self.subTest(value=value, base=base):
                    result = calculate_discount(promo(value=value), Decimal(base))
                    self.assertEqual(result, result.to_integral_value())
                    self.assertLessEqual(result, Decimal(base) * Decimal(value) / 100)


# ======================================================================
# Phân bổ theo đồng, phần dư lớn nhất
# ======================================================================


class AllocateDiscountTest(unittest.TestCase):
    def allocated(self, discount, *grosses):
        rows = lines(*grosses)
        allocate_discount(Decimal(discount), rows)
        return [row.discount for row in rows]

    def test_ten_dong_over_three_equal_lines_gives_4_3_3(self):
        self.assertEqual(self.allocated("10", "100", "100", "100"), [Decimal(4), Decimal(3), Decimal(3)])

    def test_largest_remainder_receives_the_missing_dong(self):
        # 7 × (5, 3, 2) / 10 = 3,5 / 2,1 / 1,4 → 3 / 2 / 1 + 1 đồng cho phần dư lớn nhất (0,5).
        self.assertEqual(self.allocated("7", "5", "3", "2"), [Decimal(4), Decimal(2), Decimal(1)])
        self.assertEqual(self.allocated("1000", "100000", "200000", "700000"), [Decimal(100), Decimal(200), Decimal(700)])

    def test_total_is_exact_and_no_line_exceeds_its_value(self):
        result = self.allocated("3", "1", "1", "1")
        self.assertEqual(result, [Decimal(1)] * 3)
        result = self.allocated("66666", "333333", "111111")
        self.assertEqual(sum(result), Decimal("66666"))
        self.assertTrue(all(share == share.to_integral_value() for share in result))

    def test_discount_above_the_lines_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            allocate_discount(Decimal("301"), lines("100", "200"))

    def test_legacy_fractional_lines_fall_back_to_cents(self):
        self.assertEqual(self.allocated("1", "0.50", "0.50"), [Decimal("0.50"), Decimal("0.50")])


# ======================================================================
# Xem trước mã giảm giá và tạo đơn: cùng logic, tổng nguyên đồng; chặn đơn chuyển khoản 0 đồng
# ======================================================================


class OrderMoneyTest(unittest.TestCase):
    def setUp(self):
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.orders = order_service(self.db, self.session)
        self.coupons = coupon_service(self.db, self.session)
        self.customer = self.f.user()
        self.admin = self.f.user("Admin")
        self.qr = self.f.payment_method("QR")
        self.cod = self.f.payment_method("COD")

    def order_input(self, *, fee="30000", method=None, coupon=None) -> OrderCreate:
        return OrderCreate(
            ShippingMethodId=self.f.shipping_method(fee).ShippingMethodId,
            PaymentMethodId=(method or self.qr).PaymentMethodId,
            ReceiverName="Nguyễn Văn A", ReceiverPhone="0900000000", ShippingAddress="1 Đường A",
            CouponCode=coupon,
        )

    def place(self, **kwargs):
        return self.orders.create_order(self.f.actor(self.customer), self.order_input(**kwargs))

    def test_preview_and_order_use_the_same_rounded_down_discount(self):
        self.f.coupon(self.admin, value="15")
        variant = self.f.variant(stock=5, price="333333")
        self.f.cart_with(self.customer, (variant, 1))
        preview = self.coupons.preview_cart_coupon(self.f.actor(self.customer), "SALE10")
        order = self.place(coupon="SALE10")
        self.assertEqual((preview.DiscountAmount, order.DiscountAmount), (Decimal("49999"), Decimal("49999")))
        self.assertEqual(order.TotalAmount, Decimal("333333") - Decimal("49999") + Decimal("30000"))
        self.assertEqual(order.TotalAmount, order.TotalAmount.to_integral_value())

    def test_order_lines_share_the_discount_in_whole_dong(self):
        self.f.coupon(self.admin, value="15")
        first, second = self.f.variant(stock=5, price="333333"), self.f.variant(stock=5, price="111111")
        self.f.cart_with(self.customer, (first, 1), (second, 1))
        order = self.place(coupon="SALE10")
        self.assertEqual(order.DiscountAmount, Decimal("66666"))  # 15 % × 444 444 = 66 666,6
        shares = [item.DiscountAmount for item in order.Items]
        self.assertEqual(sum(shares), order.DiscountAmount)
        self.assertTrue(all(share == share.to_integral_value() for share in shares))
        self.assertTrue(all(item.LineTotal == item.UnitPrice * item.Quantity - item.DiscountAmount for item in order.Items))

    def test_fixed_amount_above_subtotal_leaves_the_shipping_fee(self):
        coupon = self.f.coupon(self.admin, value="10")
        coupon.promotion.DiscountType, coupon.promotion.DiscountValue = "FixedAmount", Decimal("500000")
        variant = self.f.variant(stock=5, price="100000")
        self.f.cart_with(self.customer, (variant, 1))
        order = self.place(coupon="SALE10")
        self.assertEqual((order.DiscountAmount, order.TotalAmount), (Decimal("100000"), Decimal("30000")))

    def test_zero_total_transfer_order_is_refused_before_anything_is_kept(self):
        coupon = self.f.coupon(self.admin, value="100")
        variant = self.f.variant(stock=5, price="100000")
        self.f.cart_with(self.customer, (variant, 1))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.place(coupon="SALE10", fee="0")
        self.assertEqual(ctx.exception.code, "order_total_zero")
        self.assertIn("COD", ctx.exception.message)
        self.assertEqual(self.db.rows(Order), [])
        self.assertEqual((variant.StockQuantity, coupon.UsedCount), (5, 0))
        self.assertEqual(len(self.db.rows(CartItem)), 1)
        self.assertEqual(self.db.rows(PaymentTransaction), [])

    def test_zero_total_without_coupon_is_refused_too(self):
        variant = self.f.variant(stock=5, price="0")
        self.f.cart_with(self.customer, (variant, 1))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.place(fee="0")
        self.assertEqual(ctx.exception.code, "order_total_zero")
        self.assertEqual(self.db.rows(Order), [])

    def test_cod_keeps_its_current_rules_for_zero_totals(self):
        coupon = self.f.coupon(self.admin, value="100")
        variant = self.f.variant(stock=5, price="100000")
        self.f.cart_with(self.customer, (variant, 1))
        order = self.place(coupon="SALE10", fee="0", method=self.cod)
        self.assertEqual((order.TotalAmount, order.PaymentStatus), (Decimal("0"), "Pending"))
        self.assertEqual((variant.StockQuantity, coupon.UsedCount), (4, 1))

    def test_transfer_order_with_a_positive_total_is_unchanged(self):
        variant = self.f.variant(stock=5, price="100000")
        self.f.cart_with(self.customer, (variant, 1))
        order = self.place(fee="0")
        self.assertEqual(order.TotalAmount, Decimal("100000"))


if __name__ == "__main__":
    unittest.main()
