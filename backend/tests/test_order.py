"""OrderService: đặt hàng, quyền sở hữu, hủy đơn chống xử lý lặp, chuyển trạng thái và COD."""

import unittest
import uuid
from decimal import Decimal

from app.models import CartItem, Order, PaymentTransaction, ProductSerial
from app.schemas import OrderAdminUpdate, OrderCancelRequest, OrderCreate, OrderStatusUpdate
from app.services import BusinessRuleError, NotFoundError, PermissionDeniedError

from tests.fakes import FakeSession, Factory, InMemoryDB, order_service


class OrderTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = order_service(self.db, self.session)
        self.customer = self.f.user()
        self.other = self.f.user()
        self.staff = self.f.user("Staff")
        self.admin = self.f.user("Admin")
        self.qr = self.f.payment_method("QR")
        self.cod = self.f.payment_method("COD")

    def order_input(self, **kwargs) -> OrderCreate:
        values = dict(
            ShippingMethodId=self.f.shipping_method("30000.00").ShippingMethodId,
            PaymentMethodId=self.qr.PaymentMethodId,
            ReceiverName="Nguyễn Văn A",
            ReceiverPhone="0900000000",
            ShippingAddress="1 Đường A",
        )
        values.update(kwargs)
        return OrderCreate(**values)

    def set_status(self, order_id, status):
        return self.svc.update_order_status(self.f.actor(self.staff), order_id, OrderStatusUpdate(OrderStatus=status))

    def tx_for(self, order):
        return [t for t in self.db.rows(PaymentTransaction) if t.OrderId == order.OrderId]


class CreateOrderTest(OrderTestBase):
    def test_prices_and_cost_snapshot_come_from_server(self):
        variant = self.f.variant(stock=5, price="100000.00", cost="70000.00")
        self.f.cart_with(self.customer, (variant, 2), unit_price="1.00")  # giá trong giỏ không đáng tin
        order = self.svc.create_order(self.f.actor(self.customer), self.order_input())
        self.assertEqual(order.Subtotal, Decimal("200000.00"))
        self.assertEqual(order.TotalAmount, Decimal("230000.00"))
        self.assertEqual(order.Items[0].UnitPrice, Decimal("100000.00"))
        stored_item = self.db.get(Order, order.OrderId).items[0]
        self.assertEqual(stored_item.UnitCost, Decimal("70000.00"))
        self.assertEqual((order.OrderStatus, order.PaymentStatus), ("Pending", "Pending"))
        self.assertEqual(variant.StockQuantity, 3)
        self.assertEqual(self.db.rows(CartItem), [])
        self.assertIn(("ProductVariant", variant.ProductVariantId), self.db.locks)
        self.assertEqual(self.session.commits, 1)

    def test_insufficient_stock_rolls_back_everything(self):
        variant = self.f.variant(stock=1)
        self.f.cart_with(self.customer, (variant, 2))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.create_order(self.f.actor(self.customer), self.order_input())
        self.assertEqual(ctx.exception.code, "insufficient_stock")
        self.assertEqual(variant.StockQuantity, 1)
        self.assertEqual(self.db.rows(Order), [])
        self.assertEqual(len(self.db.rows(CartItem)), 1)

    def test_last_unit_cannot_be_sold_twice(self):
        variant = self.f.variant(stock=1)
        self.f.cart_with(self.customer, (variant, 1))
        self.f.cart_with(self.other, (variant, 1))
        self.svc.create_order(self.f.actor(self.customer), self.order_input())
        with self.assertRaises(BusinessRuleError):
            self.svc.create_order(self.f.actor(self.other), self.order_input())
        self.assertEqual(variant.StockQuantity, 0)
        self.assertEqual(len(self.db.rows(Order)), 1)

    def test_coupon_applied_once_and_discount_allocated(self):
        coupon = self.f.coupon(self.admin, usage_limit=1)
        variant = self.f.variant(stock=5)
        self.f.cart_with(self.customer, (variant, 2))
        order = self.svc.create_order(self.f.actor(self.customer), self.order_input(CouponCode="sale10"))
        self.assertEqual(order.DiscountAmount, Decimal("20000.00"))
        self.assertEqual(sum(i.DiscountAmount for i in order.Items), order.DiscountAmount)
        self.assertEqual(order.TotalAmount, Decimal("210000.00"))
        self.assertEqual(coupon.UsedCount, 1)

    def test_exhausted_coupon_rolls_back_order_and_stock(self):
        coupon = self.f.coupon(self.admin, usage_limit=1, used=1)
        variant = self.f.variant(stock=5)
        self.f.cart_with(self.customer, (variant, 2))
        with self.assertRaises(BusinessRuleError):
            self.svc.create_order(self.f.actor(self.customer), self.order_input(CouponCode="SALE10"))
        self.assertEqual((variant.StockQuantity, coupon.UsedCount), (5, 1))
        self.assertEqual(self.db.rows(Order), [])

    def test_inactive_product_cannot_be_ordered(self):
        variant = self.f.variant(stock=5, status="Inactive")
        self.f.cart_with(self.customer, (variant, 1))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.create_order(self.f.actor(self.customer), self.order_input())
        self.assertEqual(ctx.exception.code, "variant_not_available")


class OwnershipAndCancelTest(OrderTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.variant = self.f.variant(stock=3)
        self.coupon = self.f.coupon(self.admin, used=1)
        self.order = self.f.order(self.customer, self.qr, lines=((self.variant, 2),), coupon=self.coupon)

    def test_other_customer_cannot_read_or_cancel(self):
        with self.assertRaises(NotFoundError):
            self.svc.get_order(self.f.actor(self.other), self.order.OrderId)
        with self.assertRaises(NotFoundError):
            self.svc.get_order_status_history(self.f.actor(self.other), self.order.OrderId)
        with self.assertRaises(NotFoundError):
            self.svc.get_customer_order_item(self.f.actor(self.other), self.order.items[0].OrderItemId)
        with self.assertRaises(NotFoundError):
            self.svc.cancel_customer_order(self.f.actor(self.other), self.order.OrderId, OrderCancelRequest())
        self.assertEqual(self.order.OrderStatus, "Pending")
        self.assertEqual(self.variant.StockQuantity, 3)

    def test_owner_reads_own_order(self):
        self.assertEqual(self.svc.get_order(self.f.actor(self.customer), self.order.OrderId).OrderId, self.order.OrderId)

    def test_cancel_restores_stock_and_coupon_exactly_once(self):
        cancelled = self.svc.cancel_customer_order(self.f.actor(self.customer), self.order.OrderId, OrderCancelRequest(CancelReason="Đổi ý"))
        self.assertEqual((cancelled.OrderStatus, cancelled.PaymentStatus), ("Cancelled", "Cancelled"))
        self.assertEqual((self.variant.StockQuantity, self.coupon.UsedCount), (5, 0))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.cancel_customer_order(self.f.actor(self.customer), self.order.OrderId, OrderCancelRequest())
        self.assertEqual(ctx.exception.code, "order_not_cancellable")
        with self.assertRaises(BusinessRuleError):
            self.svc.update_order_status(
                self.f.actor(self.staff), self.order.OrderId, OrderStatusUpdate(OrderStatus="Cancelled")
            )
        self.assertEqual((self.variant.StockQuantity, self.coupon.UsedCount), (5, 0))
        self.assertEqual(sum(1 for h in self.order.status_histories if h.NewStatus == "Cancelled"), 1)

    def test_customer_can_cancel_only_pending(self):
        self.set_status(self.order.OrderId, "Confirmed")
        with self.assertRaises(BusinessRuleError):
            self.svc.cancel_customer_order(self.f.actor(self.customer), self.order.OrderId, OrderCancelRequest())
        self.assertEqual(self.variant.StockQuantity, 3)

    def test_cancel_keeps_paid_status_for_refund_flow(self):
        self.order.PaymentStatus = "Paid"
        self.svc.cancel_customer_order(self.f.actor(self.customer), self.order.OrderId, OrderCancelRequest())
        self.assertEqual((self.order.OrderStatus, self.order.PaymentStatus), ("Cancelled", "Paid"))


class StatusTransitionTest(OrderTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.variant = self.f.variant(stock=3)

    def test_only_staff_or_admin_change_status(self):
        order = self.f.order(self.customer, self.qr, lines=((self.variant, 1),))
        with self.assertRaises(PermissionDeniedError):
            self.svc.update_order_status(self.f.actor(self.customer), order.OrderId, OrderStatusUpdate(OrderStatus="Confirmed"))
        with self.assertRaises(TypeError):
            self.svc.update_order_status(self.staff.UserId, order.OrderId, OrderStatusUpdate(OrderStatus="Confirmed"))
        self.assertEqual(order.OrderStatus, "Pending")

    def test_transitions_are_sequential(self):
        order = self.f.order(self.customer, self.qr, lines=((self.variant, 1),))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.set_status(order.OrderId, "Shipping")
        self.assertEqual(ctx.exception.code, "invalid_status_transition")
        self.assertEqual(self.set_status(order.OrderId, "Confirmed").ConfirmedAt is not None, True)
        with self.assertRaises(BusinessRuleError):
            self.set_status(order.OrderId, "Confirmed")  # gọi lặp

    def test_non_cod_must_be_paid_before_shipping(self):
        order = self.f.order(self.customer, self.qr, status="Processing", lines=((self.variant, 1),))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.set_status(order.OrderId, "Shipping")
        self.assertEqual(ctx.exception.code, "order_not_paid")
        order.PaymentStatus = "Paid"
        self.assertEqual(self.set_status(order.OrderId, "Shipping").OrderStatus, "Shipping")
        self.assertEqual(self.set_status(order.OrderId, "Delivered").PaymentStatus, "Paid")

    def test_cod_is_not_paid_by_generic_delivered_transition(self):
        order = self.f.order(self.customer, self.cod, status="Shipping", lines=((self.variant, 1),))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.set_status(order.OrderId, "Delivered")
        self.assertEqual(ctx.exception.code, "cod_delivery_requires_collection")
        self.assertEqual((order.OrderStatus, order.PaymentStatus), ("Shipping", "Pending"))
        self.assertEqual(self.tx_for(order), [])

    def test_confirm_cod_delivery_records_payment_once(self):
        order = self.f.order(self.customer, self.cod, status="Shipping", total="250000.00", lines=((self.variant, 1),))
        serial = self.db.add(ProductSerial(ProductVariantId=self.variant.ProductVariantId, OrderItemId=order.items[0].OrderItemId,
                                           SerialNumber="IMEI-1", Status="Reserved"))
        result = self.svc.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId, note="Đã thu tiền")
        self.assertEqual((result.OrderStatus, result.PaymentStatus), ("Delivered", "Paid"))
        self.assertIsNotNone(result.DeliveredAt)
        [tx] = self.tx_for(order)
        self.assertEqual((tx.TransactionType, tx.Status, tx.Amount), ("Payment", "Success", Decimal("250000.00")))
        self.assertEqual(serial.Status, "Sold")
        with self.assertRaises(BusinessRuleError):
            self.svc.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId)
        self.assertEqual(len(self.tx_for(order)), 1)

    def test_confirm_cod_delivery_guards(self):
        qr_order = self.f.order(self.customer, self.qr, status="Shipping", payment_status="Paid", lines=((self.variant, 1),))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.confirm_cod_delivery(self.f.actor(self.staff), qr_order.OrderId)
        self.assertEqual(ctx.exception.code, "payment_method_not_cod")
        cod_processing = self.f.order(self.customer, self.cod, status="Processing", lines=((self.variant, 1),))
        with self.assertRaises(BusinessRuleError):
            self.svc.confirm_cod_delivery(self.f.actor(self.staff), cod_processing.OrderId)
        cod_shipping = self.f.order(self.customer, self.cod, status="Shipping", lines=((self.variant, 1),))
        with self.assertRaises(PermissionDeniedError):
            self.svc.confirm_cod_delivery(self.f.actor(self.customer), cod_shipping.OrderId)
        with self.assertRaises(NotFoundError):
            self.svc.confirm_cod_delivery(self.f.actor(self.staff), uuid.uuid4())
        self.assertEqual([t for t in self.db.rows(PaymentTransaction)], [])
        self.assertEqual(cod_shipping.PaymentStatus, "Pending")

    def test_staff_cancel_of_shipping_order_waits_for_goods_to_return(self):
        # Quyết định đợt 5.1 (C1): hàng còn ở bên vận chuyển → không hoàn tồn ngay; chờ nhận lại và kiểm tra.
        order = self.f.order(self.customer, self.cod, status="Shipping", lines=((self.variant, 2),))
        self.svc.update_order_status(
            self.f.actor(self.admin), order.OrderId, OrderStatusUpdate(OrderStatus="Cancelled", CancelReason="Giao thất bại")
        )
        self.assertEqual((order.OrderStatus, order.PaymentStatus, self.variant.StockQuantity), ("Cancelled", "Cancelled", 3))
        self.assertEqual(self.svc.get_shipment_return(self.f.actor(self.staff), order.OrderId).Status, "AwaitingReturn")
        delivered = self.f.order(self.customer, self.cod, status="Delivered", payment_status="Paid", lines=((self.variant, 1),))
        with self.assertRaises(BusinessRuleError):
            self.svc.update_order_status(self.f.actor(self.admin), delivered.OrderId, OrderStatusUpdate(OrderStatus="Cancelled"))


class RolePermissionTest(OrderTestBase):
    def test_customer_use_cases_require_customer_role(self):
        variant = self.f.variant(stock=3)
        self.f.cart_with(self.staff, (variant, 1))
        with self.assertRaises(PermissionDeniedError):
            self.svc.create_order(self.f.actor(self.staff), self.order_input())
        order = self.f.order(self.customer, self.qr, lines=((variant, 1),))
        for call in (
            lambda a: self.svc.get_order(a, order.OrderId),
            lambda a: self.svc.list_customer_orders(a),
            lambda a: self.svc.cancel_customer_order(a, order.OrderId, OrderCancelRequest()),
        ):
            with self.assertRaises(PermissionDeniedError):
                call(self.f.actor(self.admin))
            with self.assertRaises(PermissionDeniedError):
                call(None)
        self.assertEqual((variant.StockQuantity, order.OrderStatus), (3, "Pending"))

    def test_admin_use_cases_reject_customers(self):
        order = self.f.order(self.customer, self.qr)
        for call in (
            lambda a: self.svc.admin_get_order(a, order.OrderId),
            lambda a: self.svc.admin_list_orders(a),
            lambda a: self.svc.admin_get_order_status_history(a, order.OrderId),
            lambda a: self.svc.update_order_admin_info(a, order.OrderId, OrderAdminUpdate(InternalNote="x")),
        ):
            with self.assertRaises(PermissionDeniedError):
                call(self.f.actor(self.customer))
        self.assertEqual(self.svc.admin_get_order(self.f.actor(self.staff), order.OrderId).OrderId, order.OrderId)

    def test_cogs_is_admin_only(self):
        variant = self.f.variant(stock=3, cost="70000.00")
        order = self.f.order(self.customer, self.qr, lines=((variant, 2),))
        with self.assertRaises(PermissionDeniedError):
            self.svc.get_order_cogs(self.f.actor(self.staff), order.OrderId)
        self.assertEqual(self.svc.get_order_cogs(self.f.actor(self.admin), order.OrderId), Decimal("140000.00"))

    def test_customer_list_only_contains_own_orders(self):
        self.svc.orders.list_orders = lambda **f: [o for o in self.db.rows(Order) if o.CustomerId == f["customer_id"]]
        self.svc.orders.count_orders = lambda **f: len(self.svc.orders.list_orders(**f))
        mine = self.f.order(self.customer, self.qr)
        self.f.order(self.other, self.qr)
        page = self.svc.list_customer_orders(self.f.actor(self.customer))
        self.assertEqual([o.OrderId for o in page.Items], [mine.OrderId])


class SerialReservationTest(OrderTestBase):
    def test_processing_does_not_pick_serials_automatically(self):
        # Quyết định đợt 5.1 (C2): serial do Staff quét khi đóng gói; Processing không tự chọn serial.
        variant = self.f.variant(stock=3, serial_tracked=True)
        order = self.f.order(self.customer, self.qr, status="Confirmed", lines=((variant, 2),))
        serial = self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId, SerialNumber="S1", Status="Available"))
        self.set_status(order.OrderId, "Processing")
        self.assertEqual((serial.Status, serial.OrderItemId), ("Available", None))

    def test_untracked_variant_ignores_serials(self):
        variant = self.f.variant(stock=3, serial_tracked=False)
        order = self.f.order(self.customer, self.qr, status="Confirmed", lines=((variant, 1),))
        serial = self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId, SerialNumber="S1", Status="Available"))
        self.set_status(order.OrderId, "Processing")
        self.assertEqual(serial.Status, "Available")


class QrExpiryTest(OrderTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.variant = self.f.variant(stock=3)
        self.coupon = self.f.coupon(self.admin, used=1)

    def old(self, minutes):
        from datetime import timedelta

        from tests.fakes import NOW

        return NOW - timedelta(minutes=minutes)

    def test_expires_only_unpaid_pending_qr_orders_older_than_15_minutes(self):
        expired = self.f.order(self.customer, self.qr, lines=((self.variant, 2),), coupon=self.coupon, ordered_at=self.old(16))
        failed = self.f.order(self.customer, self.qr, payment_status="Failed", ordered_at=self.old(30))
        exactly = self.f.order(self.customer, self.qr, ordered_at=self.old(15))
        fresh = self.f.order(self.customer, self.qr, ordered_at=self.old(14))
        cod = self.f.order(self.customer, self.cod, ordered_at=self.old(60))
        paid = self.f.order(self.customer, self.qr, payment_status="Paid", ordered_at=self.old(60))
        confirmed = self.f.order(self.customer, self.qr, status="Confirmed", ordered_at=self.old(60))
        pending_qr = self.f.payment(expired, status="Pending", gateway_code="GW-EXP")
        pending_qr.QrData = "qr://x"

        self.assertEqual(self.svc.expire_unpaid_qr_orders(), 3)
        for order in (expired, failed, exactly):
            self.assertEqual((order.OrderStatus, order.PaymentStatus), ("Cancelled", "Cancelled"))
            self.assertEqual(order.CancelReason, "Hết hạn thanh toán QR (15 phút)")
        for order, status in ((fresh, "Pending"), (cod, "Pending"), (paid, "Pending"), (confirmed, "Confirmed")):
            self.assertEqual(order.OrderStatus, status)
        self.assertEqual((self.variant.StockQuantity, self.coupon.UsedCount), (5, 0))
        self.assertEqual(pending_qr.Status, "Cancelled")
        [history] = [h for h in expired.status_histories if h.NewStatus == "Cancelled"]
        self.assertIsNone(history.ChangedByUserId)

    def test_deadline_boundary_is_exactly_15_minutes_after_ordered_at(self):
        from datetime import timedelta

        from tests.fakes import NOW

        just_before = self.f.order(self.customer, self.qr, ordered_at=NOW - timedelta(minutes=15) + timedelta(microseconds=1))
        at_deadline = self.f.order(self.customer, self.qr, ordered_at=NOW - timedelta(minutes=15))
        self.assertEqual(self.svc.expire_unpaid_qr_orders(), 1)
        self.assertEqual((just_before.OrderStatus, at_deadline.OrderStatus), ("Pending", "Cancelled"))
        self.assertFalse(self.svc.is_qr_payment_expired(just_before))

    def test_running_twice_restores_stock_and_coupon_once(self):
        self.f.order(self.customer, self.qr, lines=((self.variant, 2),), coupon=self.coupon, ordered_at=self.old(20))
        self.assertEqual(self.svc.expire_unpaid_qr_orders(), 1)
        self.assertEqual(self.svc.expire_unpaid_qr_orders(), 0)
        self.assertEqual((self.variant.StockQuantity, self.coupon.UsedCount), (5, 0))

    def test_order_paid_after_listing_is_not_expired(self):
        order = self.f.order(self.customer, self.qr, lines=((self.variant, 2),), ordered_at=self.old(20))
        original = self.svc.orders.get_by_id_for_update

        def paid_meanwhile(order_id):
            locked = original(order_id)
            locked.PaymentStatus = "Paid"  # callback thành công đã commit trước khi tác vụ khóa được đơn
            return locked

        self.svc.orders.get_by_id_for_update = paid_meanwhile
        self.assertEqual(self.svc.expire_unpaid_qr_orders(), 0)
        self.assertEqual((order.OrderStatus, self.variant.StockQuantity), ("Pending", 3))

    def test_expiry_must_run_as_own_use_case(self):
        with self.assertRaises(BusinessRuleError) as ctx:
            with self.svc.transaction():
                self.svc.expire_unpaid_qr_orders()
        self.assertEqual(ctx.exception.code, "expiry_requires_own_transaction")


if __name__ == "__main__":
    unittest.main()
