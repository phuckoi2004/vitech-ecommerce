"""Bảo hành khi đơn Delivered: bắt đầu = ngày lịch Việt Nam của thời điểm Delivered (UTC), hết hạn = bắt đầu
+ OrderItems.WarrantyMonths − 1 ngày (quy tắc đợt 5.1.1); không tính lại khi gọi lặp."""

import unittest
from datetime import date, datetime, timezone

from app.models import OrderStatusHistory, PaymentTransaction, ProductSerial
from app.schemas import OrderStatusUpdate
from app.services import BusinessRuleError
from app.services.order import warranty_start_date

from tests.fakes import FakeSession, Factory, InMemoryDB, order_service


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class WarrantyStartDateTest(unittest.TestCase):
    def test_vietnam_calendar_day_of_utc_timestamp(self):
        cases = [
            (utc(2026, 10, 9, 8, 0), date(2026, 10, 9)),
            (utc(2026, 10, 9, 16, 59, 59), date(2026, 10, 9)),  # 23:59:59 giờ Việt Nam
            (utc(2026, 10, 9, 17, 0, 0), date(2026, 10, 10)),  # 00:00 giờ Việt Nam ngày hôm sau
            (utc(2026, 12, 31, 18, 30), date(2027, 1, 1)),  # sang năm mới tại Việt Nam
        ]
        for delivered_at, expected in cases:
            with self.subTest(delivered_at=delivered_at):
                self.assertEqual(warranty_start_date(delivered_at), expected)

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            warranty_start_date(datetime(2026, 10, 9, 8, 0))


class DeliveredWarrantyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.customer = self.f.user()
        self.staff = self.f.user("Staff")
        self.qr = self.f.payment_method("QR")
        self.cod = self.f.payment_method("COD")
        self.phone = self.f.variant(stock=5, serial_tracked=True)
        self.laptop = self.f.variant(stock=5, serial_tracked=True)
        self.cable = self.f.variant(stock=5)  # không quản lý serial

    def service(self, at=None):
        if at is None:
            return order_service(self.db, self.session)
        return order_service(self.db, self.session, clock=lambda: at)

    def shipping_order(self, payment_method=None, lines=None):
        payment_method = payment_method or self.qr
        order = self.f.order(
            self.customer, payment_method, status="Shipping",
            payment_status="Paid" if payment_method is self.qr else "Pending",
            lines=lines or ((self.phone, 2), (self.laptop, 1), (self.cable, 3)),
        )
        for item in order.items:
            variant = self.db.get(type(self.phone), item.ProductVariantId)
            if variant.IsSerialTracked:
                for n in range(item.Quantity):
                    self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId, OrderItemId=item.OrderItemId,
                                              SerialNumber=f"{variant.Sku}-{n}", Status="Reserved"))
        return order

    def serials(self, order):
        item_ids = {i.OrderItemId for i in order.items}
        return [s for s in self.db.rows(ProductSerial) if s.OrderItemId in item_ids]

    def deliver(self, order, svc=None):
        svc = svc or self.service()
        return svc.update_order_status(self.f.actor(self.staff), order.OrderId, OrderStatusUpdate(OrderStatus="Delivered"))

    def test_first_delivery_sets_start_date_for_every_serial_of_the_order(self):
        order = self.shipping_order()
        self.deliver(order)
        serials = self.serials(order)
        self.assertEqual(len(serials), 3)  # 2 điện thoại + 1 laptop; dây cáp không có serial
        for serial in serials:
            # Factory: OrderItems.WarrantyMonths = 12 → 09/10/2026 + 12 tháng − 1 ngày = 08/10/2027.
            self.assertEqual((serial.Status, serial.WarrantyStartDate, serial.WarrantyEndDate),
                             ("Sold", date(2026, 10, 9), date(2027, 10, 8)))
        self.assertEqual(order.DeliveredAt, utc(2026, 10, 9, 8, 0))
        locked = {key for name, key in self.db.locks if name == "ProductSerial"}
        self.assertEqual(locked, {s.ProductSerialId for s in serials})

    def test_delivery_just_after_midnight_vietnam_uses_next_day(self):
        order = self.shipping_order(lines=((self.phone, 1),))
        self.deliver(order, self.service(at=utc(2026, 10, 9, 17, 5)))
        [serial] = self.serials(order)
        self.assertEqual(serial.WarrantyStartDate, date(2026, 10, 10))
        self.assertEqual(order.DeliveredAt, utc(2026, 10, 9, 17, 5))  # timestamp vẫn lưu UTC

    def test_repeated_delivery_does_not_recompute_warranty(self):
        order = self.shipping_order(lines=((self.phone, 1),))
        self.deliver(order)
        [serial] = self.serials(order)
        with self.assertRaises(BusinessRuleError):
            self.deliver(order, self.service(at=utc(2026, 11, 1, 8, 0)))
        self.assertEqual(serial.WarrantyStartDate, date(2026, 10, 9))
        self.assertEqual(order.DeliveredAt, utc(2026, 10, 9, 8, 0))

    def test_cod_confirmation_sets_warranty_with_same_timestamp(self):
        order = self.shipping_order(payment_method=self.cod, lines=((self.phone, 1),))
        svc = self.service(at=utc(2026, 10, 9, 23, 0))
        svc.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId)
        [serial] = self.serials(order)
        self.assertEqual(serial.WarrantyStartDate, date(2026, 10, 10))
        self.assertEqual(order.DeliveredAt, utc(2026, 10, 9, 23, 0))

    def test_resold_serial_gets_the_period_of_the_new_sale(self):
        order = self.shipping_order(lines=((self.phone, 1),))
        [serial] = self.serials(order)
        serial.WarrantyStartDate, serial.WarrantyEndDate = date(2024, 1, 1), date(2025, 1, 1)  # lần bán trước
        self.deliver(order)
        self.assertEqual((serial.WarrantyStartDate, serial.WarrantyEndDate), (date(2026, 10, 9), date(2027, 10, 8)))

    def test_serials_not_reserved_for_this_order_are_untouched(self):
        order = self.shipping_order(lines=((self.phone, 1),))
        [serial] = self.serials(order)
        serial.Status, serial.WarrantyStartDate = "Sold", date(2025, 5, 5)  # đã xử lý theo nghiệp vụ khác
        self.deliver(order)
        self.assertEqual((serial.Status, serial.WarrantyStartDate), ("Sold", date(2025, 5, 5)))

    def test_zero_warranty_months_means_no_warranty(self):
        order = self.shipping_order(lines=((self.phone, 1),))
        order.items[0].WarrantyMonths = 0
        self.deliver(order)
        [serial] = self.serials(order)
        self.assertEqual((serial.Status, serial.WarrantyStartDate, serial.WarrantyEndDate), ("Sold", None, None))
        self.assertEqual(order.OrderStatus, "Delivered")

    def test_invalid_warranty_months_rolls_back_delivery(self):
        for months in (-1, None, 1.5, True):
            with self.subTest(months=months):
                order = self.shipping_order(lines=((self.phone, 1),))
                order.items[0].WarrantyMonths = months
                with self.assertRaises(BusinessRuleError) as ctx:
                    self.deliver(order)
                self.assertEqual(ctx.exception.code, "invalid_warranty_months")
                [serial] = self.serials(order)
                self.assertEqual((order.OrderStatus, serial.Status, serial.WarrantyStartDate),
                                 ("Shipping", "Reserved", None))

    def test_each_item_uses_its_own_snapshot_months(self):
        order = self.shipping_order(lines=((self.phone, 1), (self.laptop, 1)))
        phone_item = next(i for i in order.items if i.ProductVariantId == self.phone.ProductVariantId)
        laptop_item = next(i for i in order.items if i.ProductVariantId == self.laptop.ProductVariantId)
        phone_item.WarrantyMonths, laptop_item.WarrantyMonths = 6, 24
        self.phone.product.WarrantyMonths = 36  # giá trị hiện tại của sản phẩm không được dùng
        self.deliver(order)
        ends = {s.OrderItemId: s.WarrantyEndDate for s in self.serials(order)}
        self.assertEqual(ends, {phone_item.OrderItemId: date(2027, 4, 8), laptop_item.OrderItemId: date(2028, 10, 8)})

    def test_failure_on_one_serial_rolls_back_whole_delivery(self):
        order = self.shipping_order(payment_method=self.cod, lines=((self.phone, 1), (self.laptop, 1)))
        svc = self.service()
        original = svc.serials.list_by_order_item_for_update
        calls = []

        def fail_on_second_item(order_item_id):
            calls.append(order_item_id)
            if len(calls) == 2:
                raise RuntimeError("không khóa được serial")
            return original(order_item_id)

        svc.serials.list_by_order_item_for_update = fail_on_second_item
        rollbacks = self.session.rollbacks
        with self.assertRaises(RuntimeError):
            svc.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId)
        self.assertEqual(self.session.rollbacks, rollbacks + 1)
        self.assertEqual((order.OrderStatus, order.PaymentStatus, order.DeliveredAt), ("Shipping", "Pending", None))
        for serial in self.serials(order):
            self.assertEqual((serial.Status, serial.WarrantyStartDate), ("Reserved", None))
        self.assertEqual([t for t in self.db.rows(PaymentTransaction) if t.OrderId == order.OrderId], [])
        self.assertFalse([h for h in self.db.rows(OrderStatusHistory) if h.NewStatus == "Delivered"])


if __name__ == "__main__":
    unittest.main()
