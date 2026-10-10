"""Gán Serial/IMEI thực tế khi đóng gói (đợt 5.1 nhóm C2).

Fake trong bộ nhớ: khóa dòng chỉ được ghi lại (db.locks); không chứng minh concurrency thật của PostgreSQL.
"""

import unittest
import uuid

from app.models import ProductSerial
from app.schemas import OrderItemSerialAssign, OrderSerialAssign, OrderStatusUpdate
from app.services import BusinessRuleError, NotFoundError, PermissionDeniedError

from tests.fakes import FakeSession, Factory, InMemoryDB, order_service


class PackingTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = order_service(self.db, self.session)
        self.customer = self.f.user()
        self.staff = self.f.user("Staff")
        self.cod = self.f.payment_method("COD")
        self.phone = self.f.variant(stock=5, serial_tracked=True)
        self.case = self.f.variant(stock=5)
        self.order = self.f.order(self.customer, self.cod, status="Processing", lines=((self.phone, 2), (self.case, 1)))
        self.phone_item = next(i for i in self.order.items if i.ProductVariantId == self.phone.ProductVariantId)
        self.case_item = next(i for i in self.order.items if i.ProductVariantId == self.case.ProductVariantId)
        self.s = {n: self.serial(n) for n in ("S1", "S2", "S3")}

    def serial(self, number, *, variant=None, status="Available", order_item_id=None):
        return self.db.add(ProductSerial(ProductVariantId=(variant or self.phone).ProductVariantId, SerialNumber=number,
                                         Status=status, OrderItemId=order_item_id))

    def assign(self, *numbers, item=None, order=None, by=None):
        data = OrderSerialAssign(Items=[OrderItemSerialAssign(OrderItemId=(item or self.phone_item).OrderItemId,
                                                              SerialNumbers=list(numbers))])
        return self.svc.assign_order_serials(self.f.actor(by or self.staff), (order or self.order).OrderId, data)

    def ship(self, order=None):
        return self.svc.update_order_status(self.f.actor(self.staff), (order or self.order).OrderId,
                                            OrderStatusUpdate(OrderStatus="Shipping"))

    def states(self):
        return {n: (s.Status, s.OrderItemId) for n, s in sorted((s.SerialNumber, s) for s in self.db.rows(ProductSerial))}


class AssignTest(PackingTestBase):
    def test_assign_scanned_serials(self):
        summary = self.assign(" S1 ", "S2")
        self.assertEqual((self.s["S1"].Status, self.s["S1"].OrderItemId), ("Reserved", self.phone_item.OrderItemId))
        self.assertEqual(self.s["S3"].Status, "Available")
        phone_line = next(l for l in summary if l.OrderItemId == self.phone_item.OrderItemId)
        self.assertEqual((phone_line.SerialNumbers, phone_line.IsSerialTracked), (["S1", "S2"], True))

    def test_shipping_requires_full_assignment_and_scanning_can_be_incremental(self):
        self.assign("S1")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.ship()
        self.assertEqual(ctx.exception.code, "order_serials_not_assigned")
        self.assertEqual(self.order.OrderStatus, "Processing")
        self.assign("S2")
        self.assertEqual(self.ship().OrderStatus, "Shipping")
        self.svc.confirm_cod_delivery(self.f.actor(self.staff), self.order.OrderId)
        self.assertEqual({self.s["S1"].Status, self.s["S2"].Status}, {"Sold"})  # đúng máy đã quét được bán

    def test_invalid_requests_change_nothing(self):
        other_order = self.f.order(self.customer, self.cod, status="Processing", lines=((self.phone, 1),))
        foreign = self.serial("X-1", variant=self.f.variant(stock=1, serial_tracked=True))
        taken = self.serial("T-1", status="Reserved", order_item_id=other_order.items[0].OrderItemId)
        for status in ("Sold", "WrittenOff", "Returned", "Warranty"):
            self.serial(f"Z-{status}", status=status)
        line = OrderItemSerialAssign
        cases = [
            (BusinessRuleError, "too_many_serials", lambda: self.assign("S1", "S2", "S3")),
            (BusinessRuleError, "serial_variant_mismatch", lambda: self.assign("S1", "X-1")),
            (BusinessRuleError, "serial_not_available", lambda: self.assign("S1", "T-1")),
            (NotFoundError, "serial_not_found", lambda: self.assign("S1", "NOPE")),
            (BusinessRuleError, "duplicate_serial_in_request", lambda: self.assign("S1", "S1")),
            (BusinessRuleError, "serials_not_allowed", lambda: self.assign("S1", item=self.case_item)),
            (NotFoundError, "order_item_not_found", lambda: self.assign("S1", item=other_order.items[0])),
            (BusinessRuleError, "duplicate_assign_line", lambda: self.svc.assign_order_serials(
                self.f.actor(self.staff), self.order.OrderId, OrderSerialAssign(Items=[
                    line(OrderItemId=self.phone_item.OrderItemId, SerialNumbers=["S1"]),
                    line(OrderItemId=self.phone_item.OrderItemId, SerialNumbers=["S2"])]))),
        ] + [(BusinessRuleError, "serial_not_available", lambda st=st: self.assign("S1", f"Z-{st}"))
             for st in ("Sold", "WrittenOff", "Returned", "Warranty")]
        before = self.states()
        for error, code, call in cases:
            with self.subTest(code=code), self.assertRaises(error) as ctx:
                call()
            self.assertEqual(ctx.exception.code, code)
            self.assertEqual(self.states(), before)  # không gán dở dang
        self.assertEqual((taken.Status, foreign.Status), ("Reserved", "Available"))

    def test_only_while_packing(self):
        for status in ("Confirmed", "Shipping", "Delivered", "Cancelled"):
            with self.subTest(status=status):
                self.order.OrderStatus = status
                with self.assertRaises(BusinessRuleError) as ctx:
                    self.assign("S1")
                self.assertEqual(ctx.exception.code, "order_not_packing")
        self.assertEqual(self.s["S1"].Status, "Available")

    def test_two_staff_cannot_assign_the_same_serial(self):
        second = self.f.order(self.customer, self.cod, status="Processing", lines=((self.phone, 1),))
        self.db.locks.clear()
        self.assign("S1")
        self.assertEqual([name for name, _ in self.db.locks][:1], ["Order"])  # khóa đơn rồi mới khóa serial
        self.assertIn(("ProductSerial", self.s["S1"].ProductSerialId), self.db.locks)
        with self.assertRaises(BusinessRuleError) as ctx:  # nhân viên khác chờ khóa rồi thấy serial đã Reserved
            self.assign("S1", item=second.items[0], order=second)
        self.assertEqual(ctx.exception.code, "serial_not_available")
        self.assertEqual(self.s["S1"].OrderItemId, self.phone_item.OrderItemId)

    def test_failure_midway_leaves_no_partial_assignment(self):
        def broken(order_id):
            raise RuntimeError("lỗi sau khi ghi")

        self.svc._serial_summary = broken
        before = self.states()
        with self.assertRaises(RuntimeError):
            self.assign("S1", "S2")
        self.assertEqual(self.states(), before)

    def test_only_staff_or_admin(self):
        with self.assertRaises(PermissionDeniedError):
            self.assign("S1", by=self.customer)
        with self.assertRaises(PermissionDeniedError):
            self.svc.release_order_serial(self.f.actor(self.customer), self.order.OrderId, "S1")
        with self.assertRaises(PermissionDeniedError):
            self.svc.get_order_serials(self.f.actor(self.customer), self.order.OrderId)


class ReleaseTest(PackingTestBase):
    def test_release_wrongly_scanned_serial(self):
        self.assign("S1", "S2")
        summary = self.svc.release_order_serial(self.f.actor(self.staff), self.order.OrderId, "S2")
        self.assertEqual((self.s["S2"].Status, self.s["S2"].OrderItemId), ("Available", None))
        self.assertEqual(next(l for l in summary if l.OrderItemId == self.phone_item.OrderItemId).SerialNumbers, ["S1"])
        self.assign("S3")  # gán lại đúng máy
        self.assertEqual(self.ship().OrderStatus, "Shipping")

    def test_release_rules(self):
        other_order = self.f.order(self.customer, self.cod, status="Processing", lines=((self.phone, 1),))
        self.serial("T-1", status="Reserved", order_item_id=other_order.items[0].OrderItemId)
        self.assign("S1", "S2")
        for number, code in (("S3", "serial_not_assigned_to_order"), ("T-1", "serial_not_assigned_to_order")):
            with self.subTest(number=number), self.assertRaises(BusinessRuleError) as ctx:
                self.svc.release_order_serial(self.f.actor(self.staff), self.order.OrderId, number)
            self.assertEqual(ctx.exception.code, code)
        with self.assertRaises(NotFoundError):
            self.svc.release_order_serial(self.f.actor(self.staff), self.order.OrderId, "NOPE")
        self.ship()
        with self.assertRaises(BusinessRuleError) as ctx:  # đã giao đi: xử lý qua hồ sơ hàng hoàn kho
            self.svc.release_order_serial(self.f.actor(self.staff), self.order.OrderId, "S1")
        self.assertEqual(ctx.exception.code, "order_not_packing")
        self.assertEqual(self.s["S1"].Status, "Reserved")

    def test_unknown_order(self):
        with self.assertRaises(NotFoundError):
            self.svc.get_order_serials(self.f.actor(self.staff), uuid.uuid4())


if __name__ == "__main__":
    unittest.main()
