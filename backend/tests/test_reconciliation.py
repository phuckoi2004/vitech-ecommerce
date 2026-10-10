"""Đối soát thanh toán (PaymentReconciliations) và hoàn thủ công phần thu dư."""

import unittest
from decimal import Decimal

from pydantic import ValidationError

from app.models import Notification, PaymentReconciliation, PaymentTransaction
from app.repositories import PaymentReconciliationRepository
from app.schemas import PaymentReconciliationResolve
from app.services import BusinessRuleError, NotFoundError, PaymentGatewayError, PermissionDeniedError

from tests.fakes import NOW, FakeSession, Factory, InMemoryDB, payment_service
from tests.test_payment import FakeGateway


class ReconciliationTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.gateway = FakeGateway(self.session)
        self.svc = payment_service(self.db, self.session, gateway=self.gateway)
        self.customer = self.f.user()
        self.staff = self.f.user("Staff")
        self.admin = self.f.user("Admin")
        self.qr = self.f.payment_method("QR")
        self.order = self.f.order(self.customer, self.qr, total="130000.00")

    def callback(self, code, amount, success=True):
        return self.svc.handle_payment_callback({"code": code, "amount": str(amount), "success": success})

    def records(self, issue_type=None):
        return [r for r in self.db.rows(PaymentReconciliation) if issue_type is None or r.IssueType == issue_type]

    def staff_alerts(self, title):
        return [n for n in self.db.rows(Notification) if n.Title == title and n.UserId in (self.staff.UserId, self.admin.UserId)]

    def pending_qr(self, code):
        tx = self.f.payment(self.order, status="Pending", gateway_code=code)
        tx.QrData = "qr://pay"
        return tx


class AmountMismatchTest(ReconciliationTestBase):
    def test_mismatch_is_persisted_without_marking_paid(self):
        tx = self.pending_qr("GW-1")
        with self.assertLogs("app.services.payment", level="WARNING"), self.assertRaises(BusinessRuleError) as ctx:
            self.callback("GW-1", "100000.00")
        self.assertEqual(ctx.exception.code, "payment_amount_mismatch")
        [record] = self.records()
        self.assertEqual(
            (record.IssueType, record.GatewayTransactionCode, record.ExpectedAmount, record.ReceivedAmount, record.Status),
            ("AmountMismatch", "GW-1", Decimal("130000.00"), Decimal("100000.00"), "Open"),
        )
        self.assertEqual((record.OrderId, record.PaymentTransactionId), (self.order.OrderId, tx.PaymentTransactionId))
        self.assertEqual((tx.Status, self.order.PaymentStatus), ("Pending", "Pending"))
        self.assertEqual(self.session.commits, 1)  # bản ghi đối soát đã commit trước khi báo lỗi
        self.assertEqual(len(self.staff_alerts("Thanh toán sai số tiền")), 2)

    def test_repeated_mismatch_callback_does_not_duplicate_record_or_alert(self):
        self.pending_qr("GW-1")
        for _ in range(3):
            with self.assertLogs("app.services.payment", level="WARNING"), self.assertRaises(BusinessRuleError):
                self.callback("GW-1", "100000.00")
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(len(self.staff_alerts("Thanh toán sai số tiền")), 2)

    def test_failed_callback_with_wrong_amount_creates_no_record(self):
        self.pending_qr("GW-1")
        with self.assertLogs("app.services.payment", level="WARNING"), self.assertRaises(BusinessRuleError):
            self.callback("GW-1", "1.00", success=False)
        self.assertEqual(self.records(), [])

    def test_later_correct_callback_pays_but_keeps_reconciliation_open(self):
        tx = self.pending_qr("GW-1")
        with self.assertLogs("app.services.payment", level="WARNING"), self.assertRaises(BusinessRuleError):
            self.callback("GW-1", "1.00")
        self.callback("GW-1", "130000.00")
        self.assertEqual((tx.Status, self.order.PaymentStatus, self.records()[0].Status), ("Success", "Paid", "Open"))

    def test_failure_while_recording_reconciliation_rolls_back(self):
        self.pending_qr("GW-1")

        def broken(values):
            raise RuntimeError("ghi đối soát lỗi")

        self.svc.reconciliations.create = broken
        with self.assertLogs("app.services.payment", level="WARNING"), self.assertRaises(RuntimeError):
            self.callback("GW-1", "1.00")
        self.assertEqual((self.records(), self.db.rows(Notification)), ([], []))
        self.assertEqual(self.session.rollbacks, 1)


class DuplicateAndLatePaymentTest(ReconciliationTestBase):
    def test_second_payment_is_recorded_separately_and_flagged_once(self):
        first, second = self.pending_qr("GW-A"), self.pending_qr("GW-B")
        self.callback("GW-A", "130000.00")
        first_paid_at, first_response = first.PaidAt, first.ResponseData
        self.callback("GW-B", "130000.00")  # khách trả QR thứ hai (đã bị hủy sau khi khoản A thành công)
        self.assertEqual((first.Status, second.Status, self.order.PaymentStatus), ("Success", "Success", "Paid"))
        self.assertEqual((first.PaidAt, first.ResponseData), (first_paid_at, first_response))  # không ghi đè khoản trước
        [record] = self.records("DuplicatePayment")
        self.assertEqual((record.GatewayTransactionCode, record.PaymentTransactionId), ("GW-B", second.PaymentTransactionId))
        self.callback("GW-B", "130000.00")  # gửi lặp
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(len(self.staff_alerts("Thanh toán trùng")), 2)
        self.assertEqual(self.gateway.refund_calls, [])  # không tự hoàn

    def test_payment_after_cancellation_is_flagged(self):
        self.pending_qr("GW-1")
        self.order.OrderStatus, self.order.PaymentStatus = "Cancelled", "Cancelled"
        self.callback("GW-1", "130000.00")
        [record] = self.records("PaymentAfterCancellation")
        self.assertEqual((record.Status, self.order.PaymentStatus), ("Open", "Paid"))
        self.assertEqual(self.gateway.refund_calls, [])


class ManualResolutionTest(ReconciliationTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.pending_qr("GW-1")
        with self.assertLogs("app.services.payment", level="WARNING"), self.assertRaises(BusinessRuleError):
            self.callback("GW-1", "1.00")
        [self.record] = self.records()

    def resolve(self, note="Đã liên hệ khách và hoàn 1.00 qua chuyển khoản", user=None):
        return self.svc.resolve_reconciliation(
            self.f.actor(user or self.staff), self.record.PaymentReconciliationId, PaymentReconciliationResolve(ResolutionNote=note)
        )

    def test_staff_resolves_without_automatic_refund(self):
        result = self.resolve(note="  Đã hoàn thủ công  ")
        self.assertEqual((result.Status, result.ResolvedByUserId, result.ResolutionNote), ("Resolved", self.staff.UserId, "Đã hoàn thủ công"))
        self.assertEqual(result.ResolvedAt, NOW)
        self.assertEqual(self.gateway.refund_calls, [])
        self.assertEqual([t for t in self.db.rows(PaymentTransaction) if t.TransactionType == "Refund"], [])

    def test_resolution_is_not_repeated_or_overwritten(self):
        self.resolve()
        with self.assertRaises(BusinessRuleError) as ctx:
            self.resolve(note="ghi đè", user=self.admin)
        self.assertEqual(ctx.exception.code, "reconciliation_already_resolved")
        self.assertEqual(self.record.ResolvedByUserId, self.staff.UserId)

    def test_note_required_and_customers_denied(self):
        with self.assertRaises(ValidationError):
            PaymentReconciliationResolve(ResolutionNote="   ")
        with self.assertRaises(BusinessRuleError):
            self.svc.resolve_reconciliation(self.f.actor(self.staff), self.record.PaymentReconciliationId,
                                            PaymentReconciliationResolve.model_construct(ResolutionNote=" "))
        with self.assertRaises(PermissionDeniedError):
            self.resolve(user=self.customer)
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_reconciliations(self.f.actor(self.customer))
        self.assertEqual(self.record.Status, "Open")

    def test_list_open_reconciliations(self):
        page = self.svc.list_reconciliations(self.f.actor(self.admin), status="Open")
        self.assertEqual([r.PaymentReconciliationId for r in page.Items], [self.record.PaymentReconciliationId])
        with self.assertRaises(BusinessRuleError):
            self.svc.list_reconciliations(self.f.actor(self.admin), status="Closed")

    def test_unknown_record_and_no_delete(self):
        import uuid

        with self.assertRaises(NotFoundError):
            self.svc.resolve_reconciliation(self.f.actor(self.staff), uuid.uuid4(), PaymentReconciliationResolve(ResolutionNote="x"))
        with self.assertRaises(PermissionError):
            PaymentReconciliationRepository(session=None).delete(self.record)


class OverpaymentRefundTest(ReconciliationTestBase):
    """Hoàn thủ công khoản thanh toán trùng cho đơn chưa hủy: chỉ phần thu dư, không hoàn lặp/vượt."""

    def setUp(self) -> None:
        super().setUp()
        self.first, self.second = self.pending_qr("GW-A"), self.pending_qr("GW-B")
        self.callback("GW-A", "130000.00")
        self.callback("GW-B", "130000.00")

    def refund(self, **kwargs):
        return self.svc.refund_order(self.f.actor(self.staff), self.order.OrderId, **kwargs)

    def test_refund_only_excess_against_duplicate_payment(self):
        result = self.refund(payment_transaction_id=self.second.PaymentTransactionId)
        [call] = self.gateway.refund_calls
        self.assertEqual((call["code"], call["amount"], call["depth"]), ("GW-B", Decimal("130000.00"), 0))
        self.assertEqual((result.Status, self.order.PaymentStatus), ("Success", "Paid"))  # đơn vẫn đã thanh toán
        with self.assertRaises(BusinessRuleError) as ctx:
            self.refund(payment_transaction_id=self.second.PaymentTransactionId)
        self.assertEqual(ctx.exception.code, "nothing_to_refund")
        self.assertEqual(len(self.gateway.refund_calls), 1)

    def test_cannot_refund_more_than_excess(self):
        with self.assertRaises(BusinessRuleError) as ctx:
            self.refund(amount=Decimal("130000.01"))
        self.assertEqual(ctx.exception.code, "refund_exceeds_paid")
        self.assertEqual(self.gateway.refund_calls, [])

    def test_pending_refund_blocks_second_request(self):
        self.gateway.refund_error = TimeoutError("timeout")
        with self.assertLogs("app.services.payment", level="WARNING"), self.assertRaises(PaymentGatewayError):
            self.refund(payment_transaction_id=self.second.PaymentTransactionId)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.refund(payment_transaction_id=self.second.PaymentTransactionId)
        self.assertEqual(ctx.exception.code, "refund_pending")
        self.assertEqual(len(self.gateway.refund_calls), 1)

    def test_unknown_source_payment(self):
        import uuid

        with self.assertRaises(NotFoundError):
            self.refund(payment_transaction_id=uuid.uuid4())


class RefundGuardTest(ReconciliationTestBase):
    def test_active_order_without_overpayment_cannot_be_refunded(self):
        self.pending_qr("GW-1")
        self.callback("GW-1", "130000.00")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.refund_order(self.f.actor(self.staff), self.order.OrderId)
        self.assertEqual(ctx.exception.code, "refund_not_allowed")

    def test_refund_cannot_exceed_source_payment(self):
        self.order.OrderStatus, self.order.PaymentStatus = "Cancelled", "Paid"
        small = self.f.payment(self.order, status="Success", amount="30000.00", gateway_code="GW-S")
        self.f.payment(self.order, status="Success", amount="100000.00", gateway_code="GW-L")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.refund_order(self.f.actor(self.staff), self.order.OrderId, payment_transaction_id=small.PaymentTransactionId)
        self.assertEqual(ctx.exception.code, "refund_exceeds_source_payment")
        self.svc.refund_order(self.f.actor(self.staff), self.order.OrderId, amount=Decimal("30000.00"),
                              payment_transaction_id=small.PaymentTransactionId)
        self.assertEqual(self.gateway.refund_calls[0]["code"], "GW-S")
        self.assertEqual(self.order.PaymentStatus, "Paid")  # mới hoàn một phần
        self.svc.refund_order(self.f.actor(self.staff), self.order.OrderId)  # mặc định: khoản đủ lớn (GW-L)
        self.assertEqual(self.gateway.refund_calls[1]["code"], "GW-L")
        self.assertEqual(self.order.PaymentStatus, "Refunded")

    def test_default_source_never_refunds_more_than_a_single_gateway_payment(self):
        self.order.OrderStatus, self.order.PaymentStatus = "Cancelled", "Paid"
        self.f.payment(self.order, status="Success", amount="60000.00", gateway_code="GW-1")
        self.f.payment(self.order, status="Success", amount="70000.00", gateway_code="GW-2")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.refund_order(self.f.actor(self.staff), self.order.OrderId)  # 130000 > mỗi khoản
        self.assertEqual(ctx.exception.code, "refund_requires_source_payment")
        self.assertEqual(self.gateway.refund_calls, [])


if __name__ == "__main__":
    unittest.main()
