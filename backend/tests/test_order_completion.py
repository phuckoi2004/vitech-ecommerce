"""Active orders close at Delivered; record sales counters exactly once there.

This replaces the retired Delivered -> Completed workflow. Historical Completed
rows remain readable; warranty and refund policies are not changed.
"""
from decimal import Decimal
from app.models import OrderStatusHistory, ProductSerial
from app.schemas import OrderStatusUpdate
from app.services import BusinessRuleError
from tests.test_order import OrderTestBase


class DeliveryCompletionTest(OrderTestBase):
    def setUp(self):
        super().setUp()
        self.variant = self.f.variant(serial_tracked=True)
        self.order = self.f.order(self.customer, self.cod, status="Shipping", total="100000.00",
                                  lines=((self.variant, 2),), assigned_staff=self.staff)
        self.serials = [self.db.add(ProductSerial(ProductVariantId=self.variant.ProductVariantId,
                       OrderItemId=self.order.items[0].OrderItemId, SerialNumber=f"SERIAL-{i}", Status="Reserved"))
                       for i in range(2)]

    def counters(self):
        return self.customer.TotalOrders, self.customer.TotalSpent, self.variant.product.SoldQuantity

    def test_delivery_closes_and_records_counters_serials_payment_once(self):
        result = self.svc.confirm_cod_delivery(self.f.actor(self.staff), self.order.OrderId)
        self.assertEqual((result.OrderStatus, result.PaymentStatus), ("Delivered", "Paid"))
        self.assertEqual(result.CompletedAt, result.DeliveredAt)
        self.assertEqual(self.counters(), (1, Decimal("100000.00"), 2))
        self.assertTrue(all(s.Status == "Sold" and s.WarrantyStartDate is not None for s in self.serials))
        self.assertEqual([h.NewStatus for h in self.db.rows(OrderStatusHistory)], ["Delivered"])
        with self.assertRaises(BusinessRuleError):
            self.svc.confirm_cod_delivery(self.f.actor(self.staff), self.order.OrderId)
        self.assertEqual(self.counters(), (1, Decimal("100000.00"), 2))
        self.assertEqual(len(self.tx_for(self.order)), 1)

    def test_delivered_has_no_separate_completion_or_cancellation(self):
        self.svc.confirm_cod_delivery(self.f.actor(self.staff), self.order.OrderId)
        for target in ("Completed", "Processing", "Shipping", "Cancelled"):
            with self.subTest(target=target), self.assertRaises(BusinessRuleError):
                self.svc.update_order_status(self.f.actor(self.admin), self.order.OrderId,
                                             OrderStatusUpdate(OrderStatus=target))
        self.assertEqual(self.counters(), (1, Decimal("100000.00"), 2))

    def test_transfer_delivery_also_records_counters(self):
        self.order.PaymentMethodId = self.qr.PaymentMethodId
        self.order.PaymentStatus = "Paid"
        self.assertEqual(self.set_status(self.order.OrderId, "Delivered").OrderStatus, "Delivered")
        self.assertEqual(self.counters(), (1, Decimal("100000.00"), 2))
        self.assertEqual(self.tx_for(self.order), [])

    def test_failed_delivery_rolls_back_counters_serials_and_payment(self):
        def broken(*args, **kwargs):
            raise RuntimeError("persistence failure")
        self.svc._record_history = broken
        with self.assertRaises(RuntimeError):
            self.svc.confirm_cod_delivery(self.f.actor(self.staff), self.order.OrderId)
        self.assertEqual((self.order.OrderStatus, self.order.CompletedAt), ("Shipping", None))
        self.assertEqual(self.counters(), (0, Decimal("0"), 0))
        self.assertTrue(all(s.Status == "Reserved" and s.WarrantyStartDate is None for s in self.serials))
        self.assertEqual(self.tx_for(self.order), [])

    def test_historical_completed_is_readable_but_not_advanced(self):
        self.order.OrderStatus = "Completed"
        self.assertEqual(self.svc.admin_get_order(self.f.actor(self.staff), self.order.OrderId).OrderStatus, "Completed")
        with self.assertRaises(BusinessRuleError):
            self.set_status(self.order.OrderId, "Delivered")
