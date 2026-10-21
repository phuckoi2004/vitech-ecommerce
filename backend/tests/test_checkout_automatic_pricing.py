"""Giỏ hàng, xem trước mã và tạo đơn dùng giá sau giảm trực tiếp (Automatic), cùng giá với trang sản phẩm."""

from datetime import datetime, timezone
from decimal import Decimal

from app.models import Promotion, PromotionProduct
from app.schemas import CartItemCreate
from app.services import BusinessRuleError

from tests.fakes import coupon_service
from tests.test_checkout_cart_locking import cart_service
from tests.test_order import OrderTestBase


class CheckoutAutomaticPricingTest(OrderTestBase):
    def setUp(self):
        super().setUp()
        self.variant = self.f.variant(stock=5, price="35000000", cost="31000000")
        self.program(self.variant)
        self.cart = self.f.cart_with(self.customer, (self.variant, 2))

    def program(self, variant, amount="2000000"):
        promotion = self.db.add(Promotion(
            CreatedByUserId=self.admin.UserId, Name="Giảm trực tiếp", ApplyMode="Automatic", Status="Active",
            DiscountType="FixedAmount", DiscountValue=Decimal(amount), MinOrderValue=Decimal("0"),
            StartDate=datetime(2026, 1, 1, tzinfo=timezone.utc), EndDate=datetime(2026, 12, 31, tzinfo=timezone.utc)))
        self.db.add(PromotionProduct(PromotionId=promotion.PromotionId, ProductId=variant.ProductId))
        return promotion

    def test_cart_lines_and_totals_use_the_sale_price(self):
        summary = cart_service(self.db, self.session).get_cart(self.f.actor(self.customer))
        [line] = summary.Items
        self.assertEqual((line.OriginalPrice, line.CurrentPrice, line.LineTotal),
                         (Decimal("35000000"), Decimal("33000000"), Decimal("66000000")))
        self.assertEqual(summary.SelectedSubtotal, Decimal("66000000"))

    def test_added_line_remembers_the_sale_price(self):
        other = self.f.variant(stock=5, price="35000000", cost="31000000")
        self.program(other, amount="1000000")
        summary = cart_service(self.db, self.session).add_item(
            self.f.actor(self.customer), CartItemCreate(ProductVariantId=other.ProductVariantId, Quantity=1))
        line = next(item for item in summary.Items if item.ProductVariantId == other.ProductVariantId)
        self.assertEqual((line.UnitPrice, line.CurrentPrice), (Decimal("34000000"), Decimal("34000000")))

    def test_coupon_preview_prices_the_same_lines_as_the_cart(self):
        self.f.coupon(self.admin, value="1")
        preview = coupon_service(self.db, self.session).preview_cart_coupon(self.f.actor(self.customer), "SALE10")
        self.assertEqual((preview.Subtotal, preview.DiscountAmount), (Decimal("66000000"), Decimal("660000")))

    def test_order_charges_the_sale_price_and_records_both_discounts(self):
        coupon = self.f.coupon(self.admin, value="1")
        order = self.svc.create_order(self.f.actor(self.customer), self.order_input(CouponCode="SALE10"))
        self.assertEqual((order.Subtotal, order.DiscountAmount, order.TotalAmount),
                         (Decimal("70000000"), Decimal("4660000"), Decimal("65370000")))  # 66 tr − 660 k + 30 k phí
        [item] = order.Items
        self.assertEqual((item.UnitPrice, item.DiscountAmount, item.LineTotal),
                         (Decimal("35000000"), Decimal("4660000"), Decimal("65340000")))
        self.assertEqual(item.LineTotal, item.UnitPrice * item.Quantity - item.DiscountAmount)
        self.assertEqual(coupon.UsedCount, 1)

    def test_coupon_minimum_is_checked_on_the_sale_subtotal(self):
        self.f.coupon(self.admin, min_order="67000000")  # 70 tr trước giảm, 66 tr sau giảm trực tiếp
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.create_order(self.f.actor(self.customer), self.order_input(CouponCode="SALE10"))
        self.assertEqual(ctx.exception.code, "coupon_min_order_value")

    def test_program_of_another_product_does_not_change_the_price(self):
        other = self.f.variant(stock=5, price="100000")
        self.f.cart_with(self.other, (other, 1))
        order = self.svc.create_order(self.f.actor(self.other), self.order_input())
        self.assertEqual((order.Subtotal, order.DiscountAmount, order.TotalAmount),
                         (Decimal("100000"), Decimal("0"), Decimal("130000")))
