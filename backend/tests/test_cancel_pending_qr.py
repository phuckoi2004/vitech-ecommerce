"""Đợt 5.13: hủy đơn thì yêu cầu thanh toán QR còn Pending → Cancelled (mọi đường hủy), giữ dữ liệu đối soát.

Đánh dấu Cancelled không chứng minh khách không thể chuyển khoản: callback/chuyển khoản đến sau khi hủy vẫn được ghi
nhận (Success + đối soát PaymentAfterCancellation; đơn giữ Cancelled, PaymentStatus Paid = đã nhận tiền chờ hoàn thủ
công — cơ chế sẵn có), không tự hoàn tiền, không gọi cổng hoàn tiền.
Fake trong bộ nhớ: khóa dòng/đồng thời chỉ được giả lập (thứ tự gọi, db.locks); không chứng minh hành vi PostgreSQL thật.
"""

from datetime import timedelta
from decimal import Decimal

from app.models import Notification, PaymentReconciliation, PaymentTransaction
from app.schemas import OrderCancelRequest, OrderStatusUpdate
from app.services import BusinessRuleError, PaymentGatewayError
from app.services.payment import BankTransfer

from tests.fakes import NOW, order_service
from tests.test_payment import PaymentTestBase


class CancelPendingQrTestBase(PaymentTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.orders = order_service(self.db, self.session)
        self.variant = self.f.variant(stock=5, price="100000.00")
        self.order = self.f.order(self.customer, self.qr, status="Pending", payment_status="Pending",
                                  total="100000.00", lines=((self.variant, 1),), ordered_at=NOW)
        self.qr_tx = self.db.get(PaymentTransaction,
                                 self.svc.create_qr_payment(self.f.actor(self.customer), self.order.OrderId).PaymentTransactionId)

    def customer_cancel(self, order=None):
        return self.orders.cancel_customer_order(self.f.actor(self.customer), (order or self.order).OrderId,
                                                 OrderCancelRequest(CancelReason="Đổi ý"))

    def staff_cancel(self, order=None):
        return self.orders.update_order_status(self.f.actor(self.staff), (order or self.order).OrderId,
                                               OrderStatusUpdate(OrderStatus="Cancelled", CancelReason="Hết hàng"))

    def callback(self, amount=None, success=True, code=None):
        return self.svc.handle_payment_callback({"code": code or self.qr_tx.GatewayTransactionCode,
                                                 "amount": str(amount or self.qr_tx.Amount), "success": success})

    def snapshot(self, tx):
        return (tx.GatewayTransactionCode, tx.QrData, tx.ResponseData, tx.Amount)

    def reconciliations(self, issue=None):
        return [r for r in self.db.rows(PaymentReconciliation) if issue is None or r.IssueType == issue]

    def refunds(self):
        return [t for t in self.db.rows(PaymentTransaction) if t.TransactionType == "Refund"]

    def assert_code(self, error, code, call):
        with self.assertRaises(error) as ctx:
            call()
        self.assertEqual(ctx.exception.code, code)


class CancelMarksPendingQrTest(CancelPendingQrTestBase):
    def test_customer_cancel_cancels_pending_qr_and_keeps_its_data(self):
        before = self.snapshot(self.qr_tx)
        self.assertEqual((self.qr_tx.Status, bool(self.qr_tx.QrData)), ("Pending", True))
        self.customer_cancel()
        self.assertEqual((self.qr_tx.Status, self.snapshot(self.qr_tx)), ("Cancelled", before))  # chỉ đổi Status
        self.assertEqual((self.order.OrderStatus, self.order.PaymentStatus), ("Cancelled", "Cancelled"))
        self.assertIn(("Order", self.order.OrderId), self.db.locks)
        self.assert_code(BusinessRuleError, "payment_not_pending",
                         lambda: self.svc.cancel_qr_payment(self.f.actor(self.customer), self.qr_tx.PaymentTransactionId))
        self.assert_code(BusinessRuleError, "order_not_payable",
                         lambda: self.svc.create_qr_payment(self.f.actor(self.customer), self.order.OrderId))
        self.assert_code(BusinessRuleError, "order_not_cancellable", self.customer_cancel)  # gọi lặp
        self.assertEqual(self.qr_tx.Status, "Cancelled")

    def test_staff_cancel_of_unpaid_order_cancels_pending_qr(self):
        self.order.OrderStatus = "Confirmed"
        self.staff_cancel()
        self.assertEqual((self.qr_tx.Status, self.order.PaymentStatus), ("Cancelled", "Cancelled"))

    def test_qr_expiry_still_cancels_pending_qr_exactly_once(self):
        self.order.OrderedAt = NOW - timedelta(minutes=16)  # quá hạn 15 phút
        self.assertEqual(self.orders.expire_unpaid_qr_orders(), 1)
        self.assertEqual((self.qr_tx.Status, self.order.OrderStatus, self.order.CancelReason),
                         ("Cancelled", "Cancelled", "Hết hạn thanh toán QR (15 phút)"))
        self.assertEqual(self.orders.expire_unpaid_qr_orders(), 0)

    def test_successful_payment_is_never_cancelled_and_paid_order_awaits_manual_refund(self):
        self.callback()
        self.assertEqual((self.qr_tx.Status, self.order.PaymentStatus), ("Success", "Paid"))
        self.order.OrderStatus = "Confirmed"
        self.staff_cancel()
        self.assertEqual((self.qr_tx.Status, self.order.OrderStatus, self.order.PaymentStatus),
                         ("Success", "Cancelled", "Paid"))
        queue = self.svc.list_orders_awaiting_refund(self.f.actor(self.staff)).Items
        self.assertEqual([o.OrderId for o in queue], [self.order.OrderId])
        self.assertEqual((self.refunds(), self.gateway.refund_calls), ([], []))  # không tự hoàn tiền

    def test_inconsistent_state_only_pending_payment_requests_are_cancelled(self):
        """Dữ liệu bất thường dựng tay: đơn đã Paid vẫn còn yêu cầu QR Pending, có giao dịch Failed và Refund Pending."""
        self.callback()
        stray = self.f.payment(self.order, status="Pending", gateway_code="GW-STRAY")
        failed = self.f.payment(self.order, status="Failed", gateway_code="GW-FAILED")
        refund = self.f.payment(self.order, status="Pending", gateway_code=None, tx_type="Refund", refund_of=self.qr_tx,
                                amount="10000.00")
        self.order.OrderStatus = "Processing"
        self.staff_cancel()
        self.assertEqual([(t.TransactionType, t.Status) for t in (self.qr_tx, stray, failed, refund)],
                         [("Payment", "Success"), ("Payment", "Cancelled"), ("Payment", "Failed"), ("Refund", "Pending")])
        self.assertEqual(self.order.PaymentStatus, "Paid")


class LateMoneyAfterCancellationTest(CancelPendingQrTestBase):
    def staff_notifications(self):
        return [n for n in self.db.rows(Notification) if n.UserId in (self.staff.UserId, self.admin.UserId)]

    def test_late_success_callback_is_recorded_and_reconciled_not_ignored(self):
        self.customer_cancel()
        alerts = len(self.staff_notifications())
        result = self.callback()
        self.assertEqual((result.Status, self.qr_tx.Status, self.qr_tx.PaidAt), ("Success", "Success", NOW))
        self.assertEqual(self.order.OrderStatus, "Cancelled")  # không khôi phục đơn
        self.assertEqual(self.order.PaymentStatus, "Paid")  # cơ chế sẵn có: đã nhận tiền, chờ hoàn thủ công
        [record] = self.reconciliations()
        self.assertEqual((record.IssueType, record.OrderId, record.PaymentTransactionId, record.ReceivedAmount),
                         ("PaymentAfterCancellation", self.order.OrderId, self.qr_tx.PaymentTransactionId,
                          Decimal("100000.00")))
        self.assertGreater(len(self.staff_notifications()), alerts)
        self.assertEqual((self.refunds(), self.gateway.refund_calls), ([], []))  # không tự hoàn tiền
        self.assertEqual([o.OrderId for o in self.svc.list_orders_awaiting_refund(self.f.actor(self.staff)).Items],
                         [self.order.OrderId])
        self.assertEqual(self.callback().Status, "Success")  # gửi lặp: không tạo thêm đối soát
        self.assertEqual(len(self.reconciliations()), 1)

    def test_late_callback_with_wrong_amount_opens_amount_mismatch_and_keeps_order_unpaid(self):
        self.customer_cancel()
        self.assert_code(BusinessRuleError, "payment_amount_mismatch", lambda: self.callback(amount="90000.00"))
        self.assertEqual((self.qr_tx.Status, self.order.OrderStatus, self.order.PaymentStatus),
                         ("Cancelled", "Cancelled", "Cancelled"))
        [record] = self.reconciliations()
        self.assertEqual((record.IssueType, record.ReceivedAmount), ("AmountMismatch", Decimal("90000.00")))

    def test_late_failed_callback_does_not_turn_cancelled_into_failed(self):
        self.customer_cancel()
        self.callback(success=False)
        self.assertEqual((self.qr_tx.Status, self.order.PaymentStatus, self.reconciliations()),
                         ("Cancelled", "Cancelled", []))

    def test_late_bank_transfer_after_cancellation_is_recorded_and_reconciled(self):
        self.customer_cancel()
        transfer = BankTransfer(reconciliation_key="SEPAY-TX-1", payment_code=self.qr_tx.GatewayTransactionCode,
                                amount=Decimal("100000.00"), response_data={"id": 1})
        with self.svc.transaction():
            outcome, tx_id = self.svc.apply_bank_transfer(transfer)
        self.assertEqual((outcome, tx_id, self.qr_tx.Status), ("payment_after_cancellation", self.qr_tx.PaymentTransactionId,
                                                               "Success"))
        self.assertEqual((self.order.OrderStatus, [r.IssueType for r in self.reconciliations()]),
                         ("Cancelled", ["PaymentAfterCancellation"]))
        self.assertEqual(self.refunds(), [])

    def test_order_cancelled_while_gateway_creates_qr_keeps_gateway_code_for_reconciliation(self):
        """Đơn bị hủy trong lúc đang gọi cổng tạo QR (ngoài transaction): giao dịch giữ chỗ bị hủy theo đơn, mã cổng vẫn
        được lưu để đối soát, QR không được trả cho khách; nếu khách vẫn trả bằng mã đó thì tiền được ghi nhận."""
        other = self.f.order(self.customer, self.qr, status="Pending", payment_status="Pending", total="100000.00",
                             lines=((self.variant, 1),), ordered_at=NOW)
        self.gateway.on_create_qr = lambda: self.customer_cancel(other)
        self.assert_code(BusinessRuleError, "payment_request_cancelled",
                         lambda: self.svc.create_qr_payment(self.f.actor(self.customer), other.OrderId))
        [placeholder] = [t for t in self.db.rows(PaymentTransaction) if t.OrderId == other.OrderId]
        self.assertEqual((placeholder.Status, placeholder.QrData, other.OrderStatus), ("Cancelled", None, "Cancelled"))
        self.assertIsNotNone(placeholder.GatewayTransactionCode)
        self.callback(code=placeholder.GatewayTransactionCode)
        self.assertEqual((placeholder.Status, other.PaymentStatus,
                          [r.IssueType for r in self.reconciliations() if r.OrderId == other.OrderId]),
                         ("Success", "Paid", ["PaymentAfterCancellation"]))

    def test_gateway_error_during_qr_creation_is_unaffected(self):
        other = self.f.order(self.customer, self.qr, status="Pending", payment_status="Pending", total="100000.00",
                             lines=((self.variant, 1),), ordered_at=NOW)
        self.gateway.qr_error = TimeoutError("cổng không phản hồi")
        with self.assertRaises(PaymentGatewayError):
            self.svc.create_qr_payment(self.f.actor(self.customer), other.OrderId)
        self.customer_cancel(other)
        self.assertEqual([t.Status for t in self.db.rows(PaymentTransaction) if t.OrderId == other.OrderId],
                         ["Cancelled"])
