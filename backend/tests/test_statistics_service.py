"""StatisticsService (đợt 5.6): đơn hàng, doanh thu (thu/hoàn Success), giá vốn snapshot, sản phẩm bán chạy, tồn kho.

Service được test với FakeStatisticsRepo (cùng hợp đồng, tính bằng Python). Câu SQL thật của StatisticsRepository được
kiểm tra cấu trúc ở tests/test_statistics_queries.py; không chứng minh kết quả/hiệu năng trên PostgreSQL thật.
"""

import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from app.models import Order, OrderItem, ProductSerial, ReturnRequest
from app.services import BusinessRuleError, PermissionDeniedError, statistics_period

from tests.fakes import Factory, FakeSession, InMemoryDB, statistics_service


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


OCT_1, OCT_31 = date(2026, 10, 1), date(2026, 10, 31)
IN_OCT = utc(2026, 10, 9, 3, 0)


class StatisticsTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = statistics_service(self.db, self.session)
        self.admin = self.f.user("Admin")
        self.staff = self.f.user("Staff")
        self.customer = self.f.user()
        self.qr = self.f.payment_method("QR")
        self.phone = self.f.variant(price="100000.00", cost="70000.00", serial_tracked=True)
        self.cable = self.f.variant(price="30000.00", cost="20000.00")

    def a(self, user):
        return self.f.actor(user)

    def order(self, status="Delivered", *, delivered_at=IN_OCT, ordered_at=IN_OCT, lines=None, total=None, shipping="0"):
        lines = lines if lines is not None else ((self.phone, 1),)
        computed = sum((v.Price * q for v, q in lines), Decimal("0")) + Decimal(shipping)
        order = self.f.order(self.customer, self.qr, status=status, payment_status="Paid",
                             total=str(total if total is not None else computed), lines=lines, ordered_at=ordered_at)
        order.ShippingFee = Decimal(shipping)
        order.DeliveredAt = delivered_at if status in ("Delivered", "Completed") else None
        return order

    def pay(self, order, amount=None, status="Success", code="GW"):
        return self.f.payment(order, status=status, amount=amount, gateway_code=f"{code}-{uuid.uuid4().hex[:6]}")

    def refund(self, order, source, amount, status="Success"):
        return self.f.payment(order, status=status, amount=amount, tx_type="Refund", refund_of=source,
                              gateway_code=f"RF-{uuid.uuid4().hex[:6]}")

    def assert_error(self, error, code, call):
        with self.assertRaises(error) as ctx:
            call()
        self.assertEqual(ctx.exception.code, code)


class AccessAndPeriodTest(StatisticsTestBase):
    def calls(self):
        return [
            lambda a: self.svc.order_statistics(a, OCT_1, OCT_31),
            lambda a: self.svc.revenue_statistics(a, OCT_1, OCT_31),
            lambda a: self.svc.cogs_statistics(a, OCT_1, OCT_31),
            lambda a: self.svc.top_products(a, OCT_1, OCT_31),
            lambda a: self.svc.inventory_statistics(a),
        ]

    def test_only_admin_can_read_statistics(self):
        for index, call in enumerate(self.calls()):
            for user in (self.staff, self.customer):
                with self.subTest(call=index, role=user.Role):
                    self.assert_error(PermissionDeniedError, "permission_denied", lambda c=call, u=user: c(self.a(u)))
            with self.subTest(call=index, role=None):
                self.assert_error(PermissionDeniedError, "authentication_required", lambda c=call: c(None))

    def test_period_is_vietnam_calendar_days_inclusive_as_half_open_utc(self):
        start, end = statistics_period(OCT_1, OCT_31)
        self.assertEqual((start, end), (utc(2026, 9, 30, 17, 0), utc(2026, 10, 31, 17, 0)))
        self.assertEqual(statistics_period(OCT_1, OCT_1), (utc(2026, 9, 30, 17, 0), utc(2026, 10, 1, 17, 0)))
        cases = [(OCT_31, OCT_1), (datetime(2026, 10, 1), OCT_31), ("2026-10-01", OCT_31), (OCT_1, date.max), (None, OCT_31)]
        for date_from, date_to in cases:
            with self.subTest(date_from=date_from, date_to=date_to):
                self.assert_error(BusinessRuleError, "invalid_statistics_period",
                                  lambda f=date_from, t=date_to: self.svc.order_statistics(self.a(self.admin), f, t))

    def test_boundary_moments(self):
        inside = (utc(2026, 9, 30, 17, 0), utc(2026, 10, 31, 16, 59, 59, 999999))  # 00:00 01/10, 23:59:59.999999 31/10 VN
        for moment in inside:
            self.pay(self.order(ordered_at=moment, delivered_at=moment))
        for moment in (utc(2026, 9, 30, 16, 59, 59), utc(2026, 10, 31, 17, 0)):  # ngoài khoảng
            self.pay(self.order(ordered_at=moment, delivered_at=moment))
        admin = self.a(self.admin)
        self.assertEqual(self.svc.order_statistics(admin, OCT_1, OCT_31).TotalOrders, 2)
        self.assertEqual(self.svc.revenue_statistics(admin, OCT_1, OCT_31).OrderCount, 2)
        self.assertEqual(self.svc.order_statistics(admin, date(2026, 10, 31), date(2026, 10, 31)).TotalOrders, 1)

    def test_empty_data_returns_zeros_not_fake_numbers(self):
        admin = self.a(self.admin)
        orders = self.svc.order_statistics(admin, OCT_1, OCT_31)
        self.assertEqual((orders.TotalOrders, orders.InProgress, orders.Completed, orders.Cancelled), (0, 0, 0, 0))
        self.assertEqual(set(orders.ByStatus), {"Pending", "Confirmed", "Processing", "Shipping", "Delivered",
                                                "Completed", "Cancelled"})
        revenue = self.svc.revenue_statistics(admin, OCT_1, OCT_31)
        self.assertEqual((revenue.OrderCount, revenue.CollectedAmount, revenue.RefundedAmount, revenue.NetRevenue),
                         (0, Decimal("0"), Decimal("0"), Decimal("0")))
        cogs = self.svc.cogs_statistics(admin, OCT_1, OCT_31)
        self.assertEqual((cogs.LineCount, cogs.IsComplete, cogs.Cogs), (0, True, Decimal("0")))
        self.assertEqual(self.svc.top_products(admin, OCT_1, OCT_31), [])
        self.assertEqual(self.session.commits + self.session.rollbacks, 0)  # chỉ đọc


class OrderStatisticsTest(StatisticsTestBase):
    def test_counts_by_status_and_groups(self):
        for status, count in (("Pending", 2), ("Confirmed", 1), ("Processing", 1), ("Shipping", 1), ("Delivered", 2),
                              ("Completed", 3), ("Cancelled", 1)):
            for _ in range(count):
                self.order(status)
        self.order("Completed", ordered_at=utc(2026, 11, 2, 0, 0))  # ngoài khoảng (lọc theo OrderedAt)
        result = self.svc.order_statistics(self.a(self.admin), OCT_1, OCT_31)
        self.assertEqual(result.TotalOrders, 11)
        self.assertEqual((result.InProgress, result.Delivered, result.Completed, result.Cancelled), (5, 2, 3, 1))
        self.assertEqual(result.ByStatus["Pending"], 2)
        self.assertEqual(result.Period.EndsBefore, utc(2026, 10, 31, 17, 0))
        self.assertEqual({o.OrderStatus for o in self.db.rows(Order)},
                         {"Pending", "Confirmed", "Processing", "Shipping", "Delivered", "Completed", "Cancelled"})


class RevenueStatisticsTest(StatisticsTestBase):
    def test_only_successful_money_of_delivered_orders_counts_once(self):
        a = self.order("Delivered")  # 100.000
        self.pay(a, status="Success")
        self.pay(a, status="Failed")
        self.pay(a, status="Pending")
        b = self.order("Completed", lines=((self.cable, 2),), shipping="20000")  # 80.000
        p1 = self.pay(b, status="Success")
        self.pay(b, status="Success")  # thanh toán trùng: tiền thực thu
        self.refund(b, p1, "80000.00", status="Success")  # hoàn phần trùng
        self.refund(b, p1, "10000.00", status="Pending")
        self.refund(b, p1, "5000.00", status="Failed")
        no_pay = self.order("Delivered")
        self.pay(no_pay, status="Pending")
        cancelled = self.order("Cancelled")
        c1 = self.pay(cancelled)
        self.refund(cancelled, c1, "100000.00")
        self.pay(self.order("Shipping"))
        self.pay(self.order("Delivered", delivered_at=utc(2026, 11, 5, 0, 0)))
        statuses_before = [(o.OrderStatus, o.PaymentStatus) for o in self.db.rows(Order)]
        result = self.svc.revenue_statistics(self.a(self.admin), OCT_1, OCT_31)
        self.assertEqual(result.OrderCount, 2)
        self.assertEqual(result.OrderValue, Decimal("180000.00"))
        self.assertEqual(result.ShippingFee, Decimal("20000"))
        self.assertEqual(result.CollectedAmount, Decimal("260000.00"))  # 100k + 2×80k
        self.assertEqual(result.RefundedAmount, Decimal("80000.00"))  # không tính Pending/Failed
        self.assertEqual(result.NetRevenue, Decimal("180000.00"))
        self.assertEqual(result.PendingRefundAmount, Decimal("10000.00"))
        self.assertEqual(result.DeliveredWithoutConfirmedPayment, 1)
        self.assertTrue(any("không phải lợi nhuận" in note for note in result.Limitations))
        self.assertEqual([(o.OrderStatus, o.PaymentStatus) for o in self.db.rows(Order)], statuses_before)
        self.assertEqual(self.session.commits, 0)

    def test_refund_after_period_end_is_included_for_the_cohort(self):
        order = self.order("Delivered")
        payment = self.pay(order)
        later = self.refund(order, payment, "30000.00")
        later.PaidAt = utc(2026, 12, 1, 0, 0)  # hoàn sau kỳ: vẫn trừ vào doanh thu của đơn giao trong kỳ
        result = self.svc.revenue_statistics(self.a(self.admin), OCT_1, OCT_31)
        self.assertEqual((result.CollectedAmount, result.RefundedAmount, result.NetRevenue),
                         (Decimal("100000.00"), Decimal("30000.00"), Decimal("70000.00")))


class CogsStatisticsTest(StatisticsTestBase):
    def test_cogs_uses_order_item_snapshot_not_current_catalog_cost(self):
        order = self.order("Delivered", lines=((self.phone, 2), (self.cable, 3)))
        self.pay(order)
        self.phone.CostPrice = Decimal("999999.00")  # giá vốn hiện tại không được dùng
        unpaid = self.order("Delivered", lines=((self.phone, 5),))
        self.pay(unpaid, status="Failed")
        result = self.svc.cogs_statistics(self.a(self.admin), OCT_1, OCT_31)
        self.assertEqual((result.LineCount, result.UnitCount, result.LinesMissingCost, result.IsComplete),
                         (2, 5, 0, True))
        self.assertEqual(result.Cogs, Decimal("200000.00"))  # 2×70k + 3×20k
        self.assertEqual(result.KnownCogs, result.Cogs)
        self.assertTrue(any("Không tính lợi nhuận" in note for note in result.Limitations))

    def test_missing_cost_is_reported_instead_of_a_misleading_total(self):
        order = self.order("Delivered", lines=((self.phone, 1), (self.cable, 1)))
        self.pay(order)
        cable_line = next(i for i in self.db.rows(OrderItem) if i.ProductVariantId == self.cable.ProductVariantId)
        cable_line.UnitCost = Decimal("0")  # chưa có giá vốn lúc bán
        result = self.svc.cogs_statistics(self.a(self.admin), OCT_1, OCT_31)
        self.assertEqual((result.IsComplete, result.Cogs, result.KnownCogs, result.LinesMissingCost),
                         (False, None, Decimal("70000.00"), 1))
        self.assertIn("1 dòng đơn chưa có giá vốn", result.Limitations[0])


class TopProductsTest(StatisticsTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.case = self.f.variant(price="50000.00", cost="10000.00")
        first = self.order("Delivered", lines=((self.phone, 1), (self.cable, 4), (self.case, 1)))
        self.pay(first)
        second = self.order("Completed", lines=((self.cable, 1), (self.case, 2)))
        self.pay(second)
        self.cable_line = next(i for i in first.items if i.ProductVariantId == self.cable.ProductVariantId)
        # Không tính: đơn hủy, đơn chưa giao, đơn giao nhưng chưa thu tiền
        self.pay(self.order("Cancelled", lines=((self.phone, 9),)))
        self.pay(self.order("Processing", lines=((self.phone, 9),)))
        self.order("Delivered", lines=((self.phone, 9),))

    def add_return(self, item, quantity, *, status="Completed", request_type="Return"):
        self.db.add(ReturnRequest(RequestCode=f"DT{uuid.uuid4().hex[:8]}", CustomerId=self.customer.UserId,
                                  OrderItemId=item.OrderItemId, RequestType=request_type, Reason="x", Status=status,
                                  Quantity=quantity))

    def test_rank_by_quantity_and_revenue(self):
        admin = self.a(self.admin)
        by_quantity = self.svc.top_products(admin, OCT_1, OCT_31)
        self.assertEqual([(p.Sku, p.QuantitySold, p.Revenue) for p in by_quantity], [
            (self.cable.Sku, 5, Decimal("150000.00")), (self.case.Sku, 3, Decimal("150000.00")),
            (self.phone.Sku, 1, Decimal("100000.00"))])
        self.assertEqual([p.Rank for p in by_quantity], [1, 2, 3])
        by_revenue = self.svc.top_products(admin, OCT_1, OCT_31, rank_by="revenue", limit=2)
        self.assertEqual([p.Sku for p in by_revenue], [self.cable.Sku, self.case.Sku])  # hòa doanh thu: SL cao trước
        self.assertEqual(by_revenue[0].ProductName, self.cable.product.Name)

    def test_returned_quantity_is_reported_separately(self):
        self.add_return(self.cable_line, 2)
        self.add_return(self.cable_line, 1, status="Processing")  # chưa hoàn tất: không tính
        self.add_return(self.cable_line, 1, request_type="Exchange", status="Pending")
        result = {p.Sku: p for p in self.svc.top_products(self.a(self.admin), OCT_1, OCT_31)}
        self.assertEqual((result[self.cable.Sku].QuantitySold, result[self.cable.Sku].ReturnedQuantity), (5, 2))
        self.assertEqual(result[self.phone.Sku].ReturnedQuantity, 0)

    def test_parameters_are_validated(self):
        admin = self.a(self.admin)
        self.assert_error(BusinessRuleError, "invalid_rank_by",
                          lambda: self.svc.top_products(admin, OCT_1, OCT_31, rank_by="profit"))
        for limit in (0, 101, True, "5"):
            with self.subTest(limit=limit):
                self.assert_error(BusinessRuleError, "invalid_limit",
                                  lambda lim=limit: self.svc.top_products(admin, OCT_1, OCT_31, limit=lim))


class InventoryStatisticsTest(StatisticsTestBase):
    def test_stock_and_serial_status_breakdown(self):
        for index, status in enumerate(("Available", "Available", "Reserved", "Sold", "Warranty", "Returned",
                                        "WrittenOff")):
            self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber=f"IMEI-{index}",
                                      Status=status))
        self.phone.StockQuantity, self.phone.MinStockLevel = 2, 3
        deleted = self.f.variant(stock=7)
        deleted.IsDeleted = True
        stock_before = {v: v.StockQuantity for v in (self.phone, self.cable, deleted)}
        result = self.svc.inventory_statistics(self.a(self.admin))
        items = {i.Sku: i for i in result.Items}
        self.assertNotIn(deleted.Sku, items)
        phone = items[self.phone.Sku]
        self.assertEqual((phone.StockQuantity, phone.IsLowStock), (2, True))
        self.assertEqual(phone.Serials.model_dump(),
                         {"Available": 2, "Reserved": 1, "Sold": 1, "Warranty": 1, "Returned": 1, "WrittenOff": 1})
        cable = items[self.cable.Sku]
        self.assertEqual((cable.Serials, cable.IsLowStock, cable.StockQuantity), (None, False, 10))
        self.cable.StockQuantity = 0  # hết hàng nhưng không đặt ngưỡng: không cảnh báo (cùng quy tắc tồn thấp hiện có)
        cable = {i.Sku: i for i in self.svc.inventory_statistics(self.a(self.admin)).Items}[self.cable.Sku]
        self.assertFalse(cable.IsLowStock)
        self.cable.StockQuantity = 10
        self.assertEqual((result.Total, result.Totals.VariantCount, result.Totals.StockQuantity), (2, 2, 12))
        self.assertEqual(result.Totals.Serials.Available, 2)
        self.assertEqual({v: v.StockQuantity for v in stock_before}, stock_before)  # không đổi tồn kho
        self.assertEqual(self.session.commits, 0)

    def test_pagination_and_empty_inventory(self):
        page = self.svc.inventory_statistics(self.a(self.admin), page=2, page_size=1)
        self.assertEqual((len(page.Items), page.Total, page.Page), (1, 2, 2))
        self.assertEqual(page.Totals.StockQuantity, 20)  # tổng của mọi biến thể, không chỉ trang hiện tại
        self.assert_error(BusinessRuleError, "invalid_pagination",
                          lambda: self.svc.inventory_statistics(self.a(self.admin), page=0))
        for variant in (self.phone, self.cable):
            variant.IsDeleted = True
        empty = self.svc.inventory_statistics(self.a(self.admin))
        self.assertEqual((empty.Items, empty.Total, empty.Totals.StockQuantity), ([], 0, 0))
        self.assertEqual(empty.Totals.Serials.model_dump(),
                         {"Available": 0, "Reserved": 0, "Sold": 0, "Warranty": 0, "Returned": 0, "WrittenOff": 0})


if __name__ == "__main__":
    unittest.main()
