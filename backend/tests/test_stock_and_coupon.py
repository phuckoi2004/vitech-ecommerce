"""Tồn kho (ProductVariantService.change_stock + cảnh báo tồn thấp) và lượt dùng coupon (CouponService)."""

import random
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.models import Notification
from app.services import BusinessRuleError, NotFoundError, allocate_discount, calculate_discount
from app.services.promotion import SimpleDiscountLine

from tests.fakes import FakeSession, Factory, InMemoryDB, coupon_service, variant_service


class ChangeStockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = variant_service(self.db, self.session)

    def change(self, deltas):
        """change_stock là helper nội bộ: luôn chạy bên trong một use case."""
        with self.svc.transaction():
            return self.svc.change_stock(deltas)

    def test_changes_are_applied_on_locked_rows_in_id_order(self):
        a, b = self.f.variant(stock=5), self.f.variant(stock=2)
        result = self.change({a.ProductVariantId: -3, b.ProductVariantId: 4})
        self.assertEqual((a.StockQuantity, b.StockQuantity), (2, 6))
        self.assertEqual(result, {a.ProductVariantId: 2, b.ProductVariantId: 6})
        locked = [key for name, key in self.db.locks if name == "ProductVariant"]
        self.assertEqual(locked, sorted([a.ProductVariantId, b.ProductVariantId]))
        self.assertEqual(self.session.commits, 1)

    def test_insufficient_stock_changes_nothing(self):
        a, b = self.f.variant(stock=5), self.f.variant(stock=1)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.change({a.ProductVariantId: -1, b.ProductVariantId: -2})
        self.assertEqual(ctx.exception.code, "insufficient_stock")
        self.assertEqual((a.StockQuantity, b.StockQuantity), (5, 1))
        self.assertEqual((self.session.commits, self.session.rollbacks), (0, 1))

    def test_missing_variant(self):
        with self.assertRaises(NotFoundError):
            self.change({uuid.uuid4(): -1})

    def test_zero_deltas_do_not_lock(self):
        a = self.f.variant(stock=5)
        self.assertEqual(self.change({a.ProductVariantId: 0}), {})
        self.assertEqual(self.db.locks, [])

    def test_last_unit_can_only_be_taken_once(self):
        a = self.f.variant(stock=1)
        self.change({a.ProductVariantId: -1})
        with self.assertRaises(BusinessRuleError):
            self.change({a.ProductVariantId: -1})
        self.assertEqual(a.StockQuantity, 0)

    def test_change_stock_cannot_be_called_outside_a_use_case(self):
        a = self.f.variant(stock=5)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.change_stock({a.ProductVariantId: -1})
        self.assertEqual(ctx.exception.code, "internal_operation")
        self.assertEqual(a.StockQuantity, 5)

    def test_cost_price_is_not_changed_by_stock_changes(self):
        a = self.f.variant(stock=5, cost="70000.00")
        self.change({a.ProductVariantId: -2})
        self.change({a.ProductVariantId: 2})  # ví dụ hoàn kho khi hủy đơn
        self.assertEqual(a.CostPrice, Decimal("70000.00"))


class LowStockAlertTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = variant_service(self.db, self.session)
        self.staff, self.admin = self.f.user("Staff"), self.f.user("Admin")
        self.f.user("Customer")
        self.f.user("Staff", status="Locked")

    def change(self, variant, delta):
        with self.svc.transaction():
            self.svc.change_stock({variant.ProductVariantId: delta})

    def alerts(self):
        return [n for n in self.db.rows(Notification) if n.NotificationType == "LowStock"]

    def test_alert_once_when_crossing_threshold(self):
        variant = self.f.variant(stock=6, min_stock=5)
        self.change(variant, -1)  # 5 <= 5: vừa chạm ngưỡng
        self.assertEqual({n.UserId for n in self.alerts()}, {self.staff.UserId, self.admin.UserId})
        self.assertEqual(self.alerts()[0].ReferenceId, variant.ProductVariantId)
        self.change(variant, -2)  # vẫn đang thấp: không lặp
        self.assertEqual(len(self.alerts()), 2)

    def test_alert_again_after_recovering_above_threshold(self):
        variant = self.f.variant(stock=6, min_stock=5)
        self.change(variant, -1)
        self.change(variant, 10)  # tăng lại trên ngưỡng: không cảnh báo
        self.assertEqual(len(self.alerts()), 2)
        self.change(variant, -10)
        self.assertEqual(len(self.alerts()), 4)

    def test_zero_threshold_never_alerts(self):
        variant = self.f.variant(stock=1, min_stock=0)
        self.change(variant, -1)
        self.assertEqual(self.alerts(), [])

    def test_rollback_discards_alert(self):
        a = self.f.variant(stock=6, min_stock=5)
        b = self.f.variant(stock=0)
        with self.assertRaises(BusinessRuleError):
            with self.svc.transaction():
                self.svc.change_stock({a.ProductVariantId: -2, b.ProductVariantId: -1})
        self.assertEqual((a.StockQuantity, self.alerts()), (6, []))


class CouponUsageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = coupon_service(self.db, self.session)
        self.admin = self.f.user("Admin")
        self.customer = self.f.user()

    def lines(self, variant=None, gross="200000.00"):
        variant = variant or self.f.variant()
        return [SimpleDiscountLine(variant.ProductId, variant.product.CategoryId, Decimal(gross))]

    def apply(self, code, lines, subtotal, svc=None):
        svc = svc or self.svc
        with svc.transaction():
            return svc.apply_coupon_to_order(code, lines, subtotal)

    def test_apply_locks_coupon_and_increments_used_count_once(self):
        coupon = self.f.coupon(self.admin, usage_limit=5, used=1)
        lines = self.lines()
        locked, discount = self.apply("sale10", lines, Decimal("200000.00"))
        self.assertIs(locked, coupon)
        self.assertEqual(discount, Decimal("20000.00"))
        self.assertEqual(sum(line.discount for line in lines), discount)
        self.assertEqual(coupon.UsedCount, 2)
        self.assertIn(("Coupon", coupon.CouponId), self.db.locks)

    def test_usage_limit_is_enforced_on_locked_row(self):
        coupon = self.f.coupon(self.admin, usage_limit=1, used=0)
        self.apply("SALE10", self.lines(), Decimal("200000.00"))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.apply("SALE10", self.lines(), Decimal("200000.00"))
        self.assertEqual(ctx.exception.code, "coupon_usage_exceeded")
        self.assertEqual(coupon.UsedCount, 1)

    def test_internal_coupon_operations_require_enclosing_use_case(self):
        coupon = self.f.coupon(self.admin, used=1)
        with self.assertRaises(BusinessRuleError):
            self.svc.apply_coupon_to_order("SALE10", self.lines(), Decimal("200000.00"))
        with self.assertRaises(BusinessRuleError):
            self.svc.release_coupon_usage(coupon.CouponId)
        self.assertEqual(coupon.UsedCount, 1)

    def test_invalid_coupons_are_rejected(self):
        cases = {
            "coupon_invalid": dict(active=False),
            "coupon_expired": dict(end=datetime(2026, 1, 31, tzinfo=timezone.utc)),
            "coupon_min_order_value": dict(min_order="500000"),
        }
        for code, kwargs in cases.items():
            with self.subTest(code=code):
                db = InMemoryDB()
                f = Factory(db)
                svc = coupon_service(db, FakeSession(db))
                coupon = f.coupon(f.user("Admin"), **kwargs)
                variant = f.variant()
                lines = [SimpleDiscountLine(variant.ProductId, variant.product.CategoryId, Decimal("200000.00"))]
                with self.assertRaises(BusinessRuleError) as ctx:
                    self.apply("SALE10", lines, Decimal("200000.00"), svc=svc)
                self.assertEqual(ctx.exception.code, code)
                self.assertEqual(coupon.UsedCount, 0)

    def test_promotion_not_active_status_is_rejected(self):
        self.f.coupon(self.admin, promotion_status="Scheduled")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.apply("SALE10", self.lines(), Decimal("200000.00"))
        self.assertEqual(ctx.exception.code, "coupon_expired")

    def test_coupon_scoped_to_other_product_is_not_applicable(self):
        from app.models import PromotionProduct

        coupon = self.f.coupon(self.admin)
        other = self.f.variant()
        self.db.add(PromotionProduct(PromotionId=coupon.PromotionId, ProductId=other.ProductId))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.apply("SALE10", self.lines(), Decimal("200000.00"))
        self.assertEqual(ctx.exception.code, "coupon_not_applicable")

    def test_release_returns_one_use_and_never_goes_negative(self):
        coupon = self.f.coupon(self.admin, used=1)
        for _ in range(2):
            with self.svc.transaction():
                self.svc.release_coupon_usage(coupon.CouponId)
        self.assertEqual(coupon.UsedCount, 0)

    def test_preview_does_not_lock_or_consume_usage(self):
        variant = self.f.variant(stock=3)
        self.f.cart_with(self.customer, (variant, 2))
        coupon = self.f.coupon(self.admin, usage_limit=1)
        preview = self.svc.preview_cart_coupon(self.f.actor(self.customer), "sale10")
        self.assertEqual(preview.DiscountAmount, Decimal("20000.00"))
        self.assertEqual(coupon.UsedCount, 0)
        self.assertEqual(self.db.locks, [])


class DiscountMathTest(unittest.TestCase):
    def test_allocation_always_sums_to_discount_and_never_exceeds_line(self):
        rng = random.Random(7)
        for _ in range(3000):
            lines = [
                SimpleDiscountLine(uuid.uuid4(), uuid.uuid4(), Decimal(rng.randint(1, 10**7)) / 100)
                for _ in range(rng.randint(1, 6))
            ]
            base = sum(line.gross for line in lines)
            discount = Decimal(rng.randint(0, int(base * 100))) / 100
            allocate_discount(discount, lines)
            self.assertEqual(sum(line.discount for line in lines), discount)
            self.assertTrue(all(Decimal("0") <= line.discount <= line.gross for line in lines))

    def test_calculate_discount_caps(self):
        from types import SimpleNamespace as NS

        pct = NS(DiscountType="Percentage", DiscountValue=Decimal("10"), MaxDiscountAmount=Decimal("50000"))
        self.assertEqual(calculate_discount(pct, Decimal("1000000.00")), Decimal("50000"))
        fixed = NS(DiscountType="FixedAmount", DiscountValue=Decimal("200000"), MaxDiscountAmount=None)
        self.assertEqual(calculate_discount(fixed, Decimal("150000.00")), Decimal("150000.00"))


if __name__ == "__main__":
    unittest.main()
