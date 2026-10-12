"""Giao hàng thất bại (đợt 5.1 nhóm C1): hủy khi đang giao không hoàn tồn ngay; nhận lại + kiểm tra mới nhập kho.

Fake trong bộ nhớ: khóa dòng chỉ được ghi lại (db.locks); không chứng minh concurrency thật của PostgreSQL.
"""

import unittest

from app.models import Notification, ProductSerial, ShipmentReturn, ShipmentReturnItem
from app.schemas import OrderStatusUpdate, ShipmentReturnItemReceive, ShipmentReturnReceive
from app.services import BusinessRuleError, NotFoundError, PermissionDeniedError

from tests.fakes import FakeSession, Factory, InMemoryDB, NOW, order_service, payment_service, resolve_refund


class ShipmentReturnTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = order_service(self.db, self.session)
        self.payments = payment_service(self.db, self.session)
        self.customer = self.f.user()
        self.staff = self.f.user("Staff")
        self.admin = self.f.user("Admin")
        self.qr = self.f.payment_method("QR")
        self.cod = self.f.payment_method("COD")
        self.case = self.f.variant(stock=3)  # ốp lưng: không quản lý serial (tồn sau khi đã bán)
        self.phone = self.f.variant(stock=0, serial_tracked=True)
        self.order = self.f.order(self.customer, self.cod, status="Shipping", lines=((self.case, 2), (self.phone, 1)))
        self.case_item, self.phone_item = sorted(self.order.items, key=lambda i: i.ProductVariantId != self.case.ProductVariantId)
        self.p1 = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber="P-1",
                                            Status="Reserved", OrderItemId=self.phone_item.OrderItemId))

    def cancel(self, order=None, by=None):
        return self.svc.update_order_status(self.f.actor(by or self.admin), (order or self.order).OrderId,
                                            OrderStatusUpdate(OrderStatus="Cancelled", CancelReason="Giao thất bại"))

    def receive(self, *, restocked=2, damaged=0, good=("P-1",), bad=(), items=None, by=None, note="Kiểm tra xong"):
        lines = items if items is not None else [
            ShipmentReturnItemReceive(OrderItemId=self.case_item.OrderItemId, RestockedQuantity=restocked, DamagedQuantity=damaged)
        ]
        data = ShipmentReturnReceive(Items=lines, RestockedSerialNumbers=list(good), DamagedSerialNumbers=list(bad), Note=note)
        return self.svc.receive_shipment_return(self.f.actor(by or self.staff), self.order.OrderId, data)

    def record(self):
        rows = [r for r in self.db.rows(ShipmentReturn) if r.OrderId == self.order.OrderId]
        return rows[0] if rows else None

    def state(self):
        record = self.record()
        return (
            self.case.StockQuantity,
            self.phone.StockQuantity,
            (self.p1.Status, self.p1.OrderItemId),
            record.Status if record else None,
            sorted((str(i.ProductSerialId), i.RestockedQuantity, i.DamagedQuantity) for i in self.db.rows(ShipmentReturnItem)),
        )


class CancellationTest(ShipmentReturnTestBase):
    def test_cancel_before_shipping_restocks_immediately(self):
        self.order.OrderStatus = "Processing"
        self.cancel()
        self.assertEqual((self.case.StockQuantity, self.phone.StockQuantity), (5, 1))
        self.assertEqual((self.p1.Status, self.p1.OrderItemId), ("Available", None))
        self.assertIsNone(self.record())

    def test_cancel_during_shipping_keeps_stock_and_opens_return(self):
        self.cancel()
        self.assertEqual((self.order.OrderStatus, self.order.PaymentStatus), ("Cancelled", "Cancelled"))
        self.assertEqual((self.case.StockQuantity, self.phone.StockQuantity), (3, 0))  # hàng còn ở bên vận chuyển
        self.assertEqual((self.p1.Status, self.p1.OrderItemId), ("Reserved", self.phone_item.OrderItemId))
        record = self.record()
        self.assertEqual((record.Status, record.CreatedByUserId, record.ReceivedAt), ("AwaitingReturn", self.admin.UserId, None))
        expected = {(self.case_item.OrderItemId, None, 2), (self.phone_item.OrderItemId, self.p1.ProductSerialId, 1)}
        self.assertEqual({(i.OrderItemId, i.ProductSerialId, i.ExpectedQuantity) for i in record.items}, expected)
        self.assertEqual(self.order.status_histories[-1].NewStatus, "Cancelled")

    def test_cancel_twice_is_rejected_with_single_record(self):
        self.cancel()
        with self.assertRaises(BusinessRuleError) as ctx:
            self.cancel()
        self.assertEqual(ctx.exception.code, "order_not_cancellable")
        self.assertEqual(len(self.db.rows(ShipmentReturn)), 1)

    def test_incomplete_serials_block_shipping_cancellation(self):
        self.phone_item.Quantity = 2  # chỉ có 1 serial đang giữ cho 2 máy: dữ liệu không nhất quán
        with self.assertRaises(BusinessRuleError) as ctx:
            self.cancel()
        self.assertEqual(ctx.exception.code, "shipment_serials_incomplete")
        self.assertEqual((self.order.OrderStatus, self.record(), self.db.rows(ShipmentReturnItem)), ("Shipping", None, []))


class ReceiveTest(ShipmentReturnTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.cancel()

    def test_good_goods_are_restocked_and_serials_freed(self):
        result = self.receive()
        self.assertEqual((self.case.StockQuantity, self.phone.StockQuantity), (5, 1))
        self.assertEqual((self.p1.Status, self.p1.OrderItemId), ("Available", None))
        self.assertEqual((result.Status, result.ReceivedByUserId, result.ReceivedAt, result.Note),
                         ("Received", self.staff.UserId, NOW, "Kiểm tra xong"))
        self.assertEqual({(i.RestockedQuantity, i.DamagedQuantity) for i in result.Items}, {(2, 0), (1, 0)})

    def test_damaged_goods_are_not_restocked_and_not_written_off(self):
        self.receive(restocked=1, damaged=1, good=(), bad=("P-1",))
        self.assertEqual((self.case.StockQuantity, self.phone.StockQuantity), (4, 0))
        self.assertEqual((self.p1.Status, self.p1.OrderItemId), ("Returned", None))
        outcomes = {(str(i.ProductSerialId), i.RestockedQuantity, i.DamagedQuantity) for i in self.record().items}
        self.assertEqual(outcomes, {("None", 1, 1), (str(self.p1.ProductSerialId), 0, 1)})

    def test_receiving_twice_never_restocks_twice(self):
        self.receive()
        before = self.state()
        with self.assertRaises(BusinessRuleError) as ctx:
            self.receive()
        self.assertEqual(ctx.exception.code, "shipment_return_already_received")
        self.assertEqual(self.state(), before)

    def test_receipt_must_account_for_every_unit(self):
        other = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber="P-9", Status="Available"))
        line = ShipmentReturnItemReceive
        cases = [
            ("shipment_return_items_mismatch", dict(items=[])),
            ("shipment_return_items_mismatch", dict(items=[
                line(OrderItemId=self.case_item.OrderItemId, RestockedQuantity=2, DamagedQuantity=0),
                line(OrderItemId=self.phone_item.OrderItemId, RestockedQuantity=1, DamagedQuantity=0)])),
            ("shipment_return_quantity_mismatch", dict(restocked=1, damaged=0)),
            ("shipment_return_quantity_mismatch", dict(restocked=2, damaged=1)),
            ("duplicate_return_line", dict(items=[
                line(OrderItemId=self.case_item.OrderItemId, RestockedQuantity=1, DamagedQuantity=1),
                line(OrderItemId=self.case_item.OrderItemId, RestockedQuantity=2, DamagedQuantity=0)])),
            ("shipment_return_serials_mismatch", dict(good=())),
            ("shipment_return_serials_mismatch", dict(good=("P-1", other.SerialNumber))),
            ("shipment_return_serials_mismatch", dict(good=("NOPE",))),
            ("duplicate_serial_in_request", dict(good=("P-1",), bad=("P-1",))),
        ]
        before = self.state()
        for code, kwargs in cases:
            with self.subTest(code=code, kwargs=kwargs), self.assertRaises(BusinessRuleError) as ctx:
                self.receive(**kwargs)
            self.assertEqual(ctx.exception.code, code)
            self.assertEqual(self.state(), before)
        self.assertEqual(other.Status, "Available")

    def test_serial_no_longer_in_transit_is_rejected(self):
        self.p1.Status = "Available"  # dữ liệu lệch: serial của hồ sơ đã bị đổi trạng thái
        with self.assertRaises(BusinessRuleError) as ctx:
            self.receive()
        self.assertEqual(ctx.exception.code, "serial_not_in_transit")
        self.assertEqual(self.case.StockQuantity, 3)

    def test_failure_midway_rolls_back_everything(self):
        def broken(deltas):
            raise RuntimeError("cập nhật tồn lỗi")

        self.svc.variant_service.change_stock = broken
        before = self.state()
        with self.assertRaises(RuntimeError):
            self.receive()
        self.assertEqual(self.state(), before)

    def test_locks_order_record_variants_then_serials(self):
        self.db.locks.clear()
        self.receive()
        names = [name for name, _ in self.db.locks]
        first = {name: names.index(name) for name in ("Order", "ShipmentReturn", "ProductVariant", "ProductSerial")}
        self.assertLess(first["Order"], first["ShipmentReturn"])
        self.assertLess(first["ShipmentReturn"], first["ProductVariant"])
        self.assertLess(first["ProductVariant"], first["ProductSerial"])

    def test_only_staff_or_admin_receive_and_list(self):
        with self.assertRaises(PermissionDeniedError):
            self.receive(by=self.customer)
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_shipment_returns(self.f.actor(self.customer))
        self.assertEqual(self.record().Status, "AwaitingReturn")
        page = self.svc.list_shipment_returns(self.f.actor(self.staff), status="AwaitingReturn")
        self.assertEqual([r.OrderId for r in page.Items], [self.order.OrderId])
        with self.assertRaises(BusinessRuleError):
            self.svc.list_shipment_returns(self.f.actor(self.staff), status="Lost")
        with self.assertRaises(NotFoundError):
            self.svc.get_shipment_return(self.f.actor(self.staff), self.f.order(self.customer, self.cod).OrderId)


class PaidCancellationRefundQueueTest(ShipmentReturnTestBase):
    def test_paid_order_cancelled_is_queued_for_refund_not_marked_refunded(self):
        paid = self.f.order(self.customer, self.qr, status="Shipping", payment_status="Paid", lines=((self.case, 1),))
        early = self.f.order(self.customer, self.qr, status="Confirmed", payment_status="Paid", lines=((self.case, 1),))
        payment = self.f.payment(paid, status="Success", gateway_code=None)
        self.cancel(paid)
        self.cancel(early)
        self.assertEqual((paid.PaymentStatus, early.PaymentStatus), ("Paid", "Paid"))  # chưa hoàn tiền
        alerts = [n for n in self.db.rows(Notification) if n.Title == "Cần hoàn tiền"]
        self.assertEqual({(n.UserId, n.ReferenceId) for n in alerts},
                         {(u.UserId, o.OrderId) for u in (self.staff, self.admin) for o in (paid, early)})
        queue = self.payments.list_orders_awaiting_refund(self.f.actor(self.staff))
        self.assertEqual({o.OrderId for o in queue.Items}, {paid.OrderId, early.OrderId})
        refund = self.payments.refund_order(self.f.actor(self.staff), paid.OrderId,
                                            payment_transaction_id=payment.PaymentTransactionId)
        self.assertEqual((refund.Status, paid.PaymentStatus), ("Pending", "Paid"))  # đợt 5.11: chờ Admin xác nhận
        self.assertEqual(len(self.payments.list_orders_awaiting_refund(self.f.actor(self.staff)).Items), 2)
        resolve_refund(self.payments, self.f.actor(self.admin), refund.PaymentTransactionId)
        self.assertEqual(paid.PaymentStatus, "Refunded")
        queue = self.payments.list_orders_awaiting_refund(self.f.actor(self.staff))
        self.assertEqual([o.OrderId for o in queue.Items], [early.OrderId])
        with self.assertRaises(PermissionDeniedError):
            self.payments.list_orders_awaiting_refund(self.f.actor(self.customer))

    def test_unpaid_cancellation_does_not_alert_refund(self):
        self.cancel()
        self.assertEqual([n for n in self.db.rows(Notification) if n.Title == "Cần hoàn tiền"], [])


if __name__ == "__main__":
    unittest.main()
