"""Hủy/xác nhận đơn theo trạng thái thanh toán, và tiền về muộn (sau rà soát luồng đặt hàng - thanh toán).

- Khách không tự hủy đơn đã Paid (order_paid_not_cancellable). Staff/Admin vẫn hủy được; PaymentStatus giữ Paid để
  hoàn tiền thủ công (cơ chế sẵn có).
- Staff/Admin chỉ xác nhận (Confirmed) đơn không phải COD khi đã Paid (order_not_paid). Đơn COD xác nhận khi chưa thu.
- Tiền về đúng số tiền: đơn chưa bị hủy (kể cả đã quá 15 phút mà tác vụ hết hạn chưa chạy) được ghi nhận Paid như
  thường; đơn đã bị hủy → giao dịch Success + đối soát PaymentAfterCancellation, Paid, chờ hoàn thủ công. Khoản tiền
  nhận được luôn có dấu vết (giao dịch hoặc bản ghi đối soát).
Đi qua PaymentService.apply_bank_transfer như webhook SePay. Fake trong bộ nhớ: không chứng minh khóa của PostgreSQL thật.
"""

from datetime import timedelta
from decimal import Decimal

from app.models import PaymentReconciliation, PaymentTransaction
from app.schemas import OrderCancelRequest, OrderStatusUpdate
from app.services import BusinessRuleError
from app.services.payment import BankTransfer

from tests.fakes import NOW, order_service
from tests.test_payment import PaymentTestBase


class OrderPaymentRulesBase(PaymentTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.orders = order_service(self.db, self.session)
        self.variant = self.f.variant(stock=5, price="100000.00")
        self.coupon = self.f.coupon(self.admin, used=1)

    def make_order(self, method, **changes):
        return self.f.order(self.customer, method, total="100000.00", lines=((self.variant, 1),), coupon=self.coupon,
                            ordered_at=NOW, **changes)

    def qr_order_with_qr(self):
        order = self.make_order(self.qr)
        tx = self.db.get(PaymentTransaction,
                         self.svc.create_qr_payment(self.f.actor(self.customer), order.OrderId).PaymentTransactionId)
        return order, tx

    def bank_transfer(self, tx, amount="100000.00", key="sepay:0123456789:1001"):
        """Tiền vào khớp mã thanh toán của QR, như PaymentWebhookService.process_event."""
        transfer = BankTransfer(reconciliation_key=key, payment_code=tx.GatewayTransactionCode, amount=Decimal(amount),
                                response_data={"id": key})
        with self.svc.transaction():
            outcome, _ = self.svc.apply_bank_transfer(transfer)
        return outcome

    def customer_cancel(self, order):
        return self.orders.cancel_customer_order(self.f.actor(self.customer), order.OrderId, OrderCancelRequest())

    def set_status(self, order, status, actor=None):
        return self.orders.update_order_status(self.f.actor(actor or self.staff), order.OrderId,
                                               OrderStatusUpdate(OrderStatus=status))

    def expire_after_deadline(self, order):
        order.OrderedAt = NOW - timedelta(minutes=16)

    def history(self, order):
        return [h.NewStatus for h in order.status_histories]

    def reconciliations(self, issue=None):
        return [r for r in self.db.rows(PaymentReconciliation) if issue is None or r.IssueType == issue]

    def refund_transactions(self):
        return [t for t in self.db.rows(PaymentTransaction) if t.TransactionType == "Refund"]

    def titles(self, user):
        return [n.Title for n in self.f.notifications_for(user)]

    def assert_code(self, code, call):
        with self.assertRaises(BusinessRuleError) as ctx:
            call()
        self.assertEqual(ctx.exception.code, code)


class CustomerCancelTest(OrderPaymentRulesBase):
    def test_unpaid_pending_transfer_order_can_still_be_cancelled_by_the_customer(self):
        order, tx = self.qr_order_with_qr()
        self.customer_cancel(order)
        self.assertEqual((order.OrderStatus, order.PaymentStatus, tx.Status), ("Cancelled", "Cancelled", "Cancelled"))
        self.assertEqual((self.variant.StockQuantity, self.coupon.UsedCount), (6, 0))

    def test_pending_cod_order_can_be_cancelled_by_the_customer(self):
        order = self.make_order(self.cod)
        self.customer_cancel(order)
        self.assertEqual((order.OrderStatus, order.PaymentStatus), ("Cancelled", "Cancelled"))

    def test_paid_order_cannot_be_cancelled_by_the_customer_and_nothing_changes(self):
        order, tx = self.qr_order_with_qr()
        self.assertEqual(self.bank_transfer(tx), "paid")
        before = self.history(order)

        self.assert_code("order_paid_not_cancellable", lambda: self.customer_cancel(order))
        self.assertEqual((order.OrderStatus, order.PaymentStatus, tx.Status), ("Pending", "Paid", "Success"))
        self.assertEqual((self.variant.StockQuantity, self.coupon.UsedCount), (5, 1))
        self.assertEqual((self.history(order), order.CancelledAt), (before, None))
        self.assertNotIn("Cần hoàn tiền", self.titles(self.staff))
        self.assertEqual(self.refund_transactions(), [])

    def test_the_order_status_is_checked_before_the_payment(self):
        order = self.make_order(self.qr, status="Confirmed", payment_status="Paid")
        self.assert_code("order_not_cancellable", lambda: self.customer_cancel(order))

    def test_staff_still_cancel_a_paid_order_which_then_awaits_a_manual_refund(self):
        order, tx = self.qr_order_with_qr()
        self.bank_transfer(tx)
        self.set_status(order, "Cancelled")
        self.assertEqual((order.OrderStatus, order.PaymentStatus, tx.Status), ("Cancelled", "Paid", "Success"))
        self.assertEqual((self.variant.StockQuantity, self.coupon.UsedCount), (6, 0))
        self.assertIn("Cần hoàn tiền", self.titles(self.staff))
        awaiting = self.svc.list_orders_awaiting_refund(self.f.actor(self.staff)).Items
        self.assertEqual([o.OrderId for o in awaiting], [order.OrderId])
        self.assertEqual((self.refund_transactions(), self.gateway.refund_calls), ([], []))  # không tự hoàn tiền


class StaffConfirmTest(OrderPaymentRulesBase):
    def test_unpaid_transfer_order_cannot_be_confirmed_by_staff_or_admin(self):
        for payment_status in ("Pending", "Failed"):
            order = self.make_order(self.qr, payment_status=payment_status)
            for actor in (self.staff, self.admin):
                self.assert_code("order_not_paid", lambda: self.set_status(order, "Confirmed", actor))
            self.assertEqual((order.OrderStatus, order.ConfirmedAt, self.history(order)), ("Pending", None, []))

    def test_paid_transfer_order_is_confirmed_and_moves_on(self):
        order, tx = self.qr_order_with_qr()
        self.bank_transfer(tx)
        self.assertEqual(self.set_status(order, "Confirmed").OrderStatus, "Confirmed")
        self.assertIsNotNone(order.ConfirmedAt)
        self.assertEqual(self.set_status(order, "Processing").OrderStatus, "Processing")
        self.assertEqual(self.history(order), ["Confirmed", "Processing"])

    def test_unpaid_cod_order_is_confirmed_before_cash_is_collected(self):
        order = self.make_order(self.cod)
        self.assertEqual(self.set_status(order, "Confirmed").OrderStatus, "Confirmed")
        self.assertEqual(order.PaymentStatus, "Pending")

    def test_an_unpaid_transfer_order_stays_pending_and_the_expiry_job_cancels_it(self):
        order, tx = self.qr_order_with_qr()
        self.assert_code("order_not_paid", lambda: self.set_status(order, "Confirmed"))
        self.expire_after_deadline(order)
        self.assertEqual(self.orders.expire_unpaid_qr_orders().processed, 1)
        self.assertEqual((order.OrderStatus, order.PaymentStatus, tx.Status), ("Cancelled", "Cancelled", "Cancelled"))
        self.assertEqual((self.variant.StockQuantity, self.coupon.UsedCount), (6, 0))

    def test_existing_confirmed_unpaid_transfer_orders_are_left_as_they_are(self):
        """Dữ liệu trước quy tắc này: không tự sửa; vẫn chưa giao được khi chưa Paid và Staff vẫn hủy được."""
        order = self.make_order(self.qr, status="Confirmed")
        self.assertEqual(self.set_status(order, "Processing").OrderStatus, "Processing")
        self.assert_code("order_not_paid", lambda: self.set_status(order, "Shipping"))
        self.set_status(order, "Cancelled")
        self.assertEqual((order.OrderStatus, order.PaymentStatus), ("Cancelled", "Cancelled"))


class LatePaymentTest(OrderPaymentRulesBase):
    def test_payment_after_the_deadline_but_before_the_expiry_job_is_accepted(self):
        order, tx = self.qr_order_with_qr()
        self.expire_after_deadline(order)

        self.assertEqual(self.bank_transfer(tx), "paid")
        self.assertEqual((order.OrderStatus, order.PaymentStatus, tx.Status), ("Pending", "Paid", "Success"))
        self.assertEqual(self.reconciliations(), [])
        # The expiry job leaves a paid order alone: its stock and coupon stay with it.
        self.assertEqual(self.orders.expire_unpaid_qr_orders().processed, 0)
        self.assertEqual((order.OrderStatus, self.variant.StockQuantity, self.coupon.UsedCount), ("Pending", 5, 1))
        self.assertEqual(self.set_status(order, "Confirmed").OrderStatus, "Confirmed")

    def test_payment_after_the_expiry_job_cancelled_the_order_is_kept_for_a_manual_refund(self):
        order, tx = self.qr_order_with_qr()
        self.expire_after_deadline(order)
        self.assertEqual(self.orders.expire_unpaid_qr_orders().processed, 1)
        self.assertEqual((tx.Status, self.variant.StockQuantity, self.coupon.UsedCount), ("Cancelled", 6, 0))

        self.assertEqual(self.bank_transfer(tx), "payment_after_cancellation")
        # The money is not lost: the QR transaction records it, and the order is not revived.
        self.assertEqual((tx.Status, order.OrderStatus, order.PaymentStatus), ("Success", "Cancelled", "Paid"))
        self.assertEqual((self.variant.StockQuantity, self.coupon.UsedCount), (6, 0))
        [record] = self.reconciliations()
        self.assertEqual((record.IssueType, record.Status, record.ReceivedAmount, record.PaymentTransactionId),
                         ("PaymentAfterCancellation", "Open", Decimal("100000.00"), tx.PaymentTransactionId))
        self.assertIn("Cần hoàn tiền thủ công", self.titles(self.staff))
        self.assertIn("Đã nhận thanh toán", self.titles(self.customer))
        awaiting = self.svc.list_orders_awaiting_refund(self.f.actor(self.staff)).Items
        self.assertEqual([o.OrderId for o in awaiting], [order.OrderId])
        self.assertEqual((self.refund_transactions(), self.gateway.refund_calls), ([], []))
        self.assert_code("order_not_cancellable", lambda: self.customer_cancel(order))

    def test_payment_after_the_customer_cancelled_is_kept_for_a_manual_refund(self):
        order, tx = self.qr_order_with_qr()
        self.customer_cancel(order)
        self.assertEqual(self.bank_transfer(tx), "payment_after_cancellation")
        self.assertEqual((tx.Status, order.OrderStatus, order.PaymentStatus), ("Success", "Cancelled", "Paid"))
        self.assertEqual([r.IssueType for r in self.reconciliations()], ["PaymentAfterCancellation"])

    def test_a_wrong_amount_after_cancellation_is_reconciled_without_marking_the_order_paid(self):
        order, tx = self.qr_order_with_qr()
        self.expire_after_deadline(order)
        self.orders.expire_unpaid_qr_orders()

        self.assertEqual(self.bank_transfer(tx, amount="90000.00"), "amount_mismatch")
        self.assertEqual((tx.Status, order.OrderStatus, order.PaymentStatus), ("Cancelled", "Cancelled", "Cancelled"))
        [record] = self.reconciliations()
        self.assertEqual((record.IssueType, record.ExpectedAmount, record.ReceivedAmount),
                         ("AmountMismatch", Decimal("100000.00"), Decimal("90000.00")))
