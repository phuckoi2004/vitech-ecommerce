"""PaymentService: QR, callback (gửi lặp/đến muộn), hoàn tiền tách khỏi transaction, đối soát, COD."""

import unittest
import uuid
from decimal import Decimal

from app.models import PaymentTransaction
from app.services import (
    BusinessRuleError,
    ConflictError,
    GatewayPaymentResult,
    GatewayRefundResult,
    NotFoundError,
    PaymentGatewayError,
    PermissionDeniedError,
    QrPaymentRequest,
)
from app.services.base import _DEPTH_KEY

from tests.fakes import FakeSession, Factory, InMemoryDB, payment_service, resolve_refund


class FakeGateway:
    """Cổng thanh toán giả; ghi lại trạng thái transaction database tại thời điểm được gọi."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.qr_calls: list = []
        self.refund_calls: list = []
        self.refund_result = GatewayRefundResult(success=True, response_data={"result": "ok"}, gateway_transaction_code="RF-1")
        self.refund_error: Exception | None = None
        self.qr_error: Exception | None = None
        self.on_create_qr = None

    def create_qr_payment(self, *, order_code, amount):
        self.qr_calls.append(
            {
                "order_code": order_code,
                "amount": amount,
                "depth": self.session.info.get(_DEPTH_KEY, 0),
                "commits": self.session.commits,
            }
        )
        if self.on_create_qr is not None:
            self.on_create_qr()
        if self.qr_error is not None:
            raise self.qr_error
        code = f"GW-{order_code}" if len(self.qr_calls) == 1 else f"GW-{order_code}-{len(self.qr_calls)}"
        return QrPaymentRequest(gateway_transaction_code=code, qr_data="qr://pay", response_data={"q": 1})

    def verify_callback(self, payload):
        return GatewayPaymentResult(
            gateway_transaction_code=payload["code"],
            amount=Decimal(payload["amount"]),
            success=payload["success"],
            response_data=dict(payload),
        )

    def refund(self, *, gateway_transaction_code, amount):
        self.refund_calls.append(
            {
                "code": gateway_transaction_code,
                "amount": amount,
                "depth": self.session.info.get(_DEPTH_KEY, 0),
                "commits": self.session.commits,
            }
        )
        if self.refund_error is not None:
            raise self.refund_error
        return self.refund_result


class PaymentTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.gateway = FakeGateway(self.session)
        self.svc = payment_service(self.db, self.session, gateway=self.gateway)
        self.customer = self.f.user()
        self.other = self.f.user()
        self.staff = self.f.user("Staff")
        self.admin = self.f.user("Admin")
        self.qr = self.f.payment_method("QR")
        self.cod = self.f.payment_method("COD")

    def callback(self, code, amount, success=True):
        return self.svc.handle_payment_callback({"code": code, "amount": str(amount), "success": success})

    def txs(self, order, tx_type=None):
        return [t for t in self.db.rows(PaymentTransaction)
                if t.OrderId == order.OrderId and (tx_type is None or t.TransactionType == tx_type)]


class QrAndCallbackTest(PaymentTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.order = self.f.order(self.customer, self.qr, total="130000.00")

    def test_create_qr_checks_owner_and_reuses_pending(self):
        with self.assertRaises(NotFoundError):
            self.svc.create_qr_payment(self.f.actor(self.other), self.order.OrderId)
        self.assertEqual(self.gateway.qr_calls, [])
        first = self.svc.create_qr_payment(self.f.actor(self.customer), self.order.OrderId)
        second = self.svc.create_qr_payment(self.f.actor(self.customer), self.order.OrderId)
        self.assertEqual(first.PaymentTransactionId, second.PaymentTransactionId)
        self.assertEqual((first.Status, first.Amount), ("Pending", Decimal("130000.00")))
        self.assertEqual(len(self.gateway.qr_calls), 1)

    def test_cod_order_cannot_create_qr(self):
        cod_order = self.f.order(self.customer, self.cod)
        with self.assertRaises(BusinessRuleError):
            self.svc.create_qr_payment(self.f.actor(self.customer), cod_order.OrderId)

    def test_success_callback_marks_paid_and_duplicate_is_ignored(self):
        tx = self.svc.create_qr_payment(self.f.actor(self.customer), self.order.OrderId)
        code = f"GW-{self.order.OrderCode}"
        self.callback(code, "130000.00")
        self.assertEqual(self.order.PaymentStatus, "Paid")
        notifications = len(self.f.notifications_for(self.customer))
        again = self.callback(code, "130000.00")
        self.assertEqual(again.PaymentTransactionId, tx.PaymentTransactionId)
        self.assertEqual(len(self.txs(self.order)), 1)
        self.assertEqual(len(self.f.notifications_for(self.customer)), notifications)
        self.callback(code, "130000.00", success=False)  # thất bại đến sau thành công: bỏ qua
        self.assertEqual((self.txs(self.order)[0].Status, self.order.PaymentStatus), ("Success", "Paid"))

    def test_amount_mismatch_changes_nothing_but_is_logged_for_reconciliation(self):
        tx = self.svc.create_qr_payment(self.f.actor(self.customer), self.order.OrderId)
        with self.assertLogs("app.services.payment", level="WARNING") as logs, self.assertRaises(BusinessRuleError) as ctx:
            self.callback(f"GW-{self.order.OrderCode}", "1000.00")
        self.assertEqual(ctx.exception.code, "payment_amount_mismatch")
        self.assertIn(str(tx.PaymentTransactionId), "\n".join(logs.output))
        self.assertEqual((self.txs(self.order)[0].Status, self.order.PaymentStatus), ("Pending", "Pending"))

    def test_success_cancels_other_pending_qr_requests(self):
        paid = self.f.payment(self.order, status="Pending", gateway_code="GW-A")
        other = self.f.payment(self.order, status="Pending", gateway_code="GW-B")
        self.callback("GW-A", "130000.00")
        self.assertEqual((paid.Status, other.Status, self.order.PaymentStatus), ("Success", "Cancelled", "Paid"))
        # Khách vẫn trả QR kia: ghi nhận tiền vào và báo Staff/Admin (thanh toán trùng), không mất dấu khoản tiền.
        self.callback("GW-B", "130000.00")
        self.assertEqual(other.Status, "Success")
        self.assertIn("Thanh toán trùng", [n.Title for n in self.f.notifications_for(self.admin)])

    def test_failed_callback(self):
        self.svc.create_qr_payment(self.f.actor(self.customer), self.order.OrderId)
        self.callback(f"GW-{self.order.OrderCode}", "130000.00", success=False)
        self.assertEqual((self.txs(self.order)[0].Status, self.order.PaymentStatus), ("Failed", "Failed"))

    def test_unknown_gateway_code(self):
        with self.assertRaises(NotFoundError):
            self.callback("GW-UNKNOWN", "1.00")

    def test_late_success_on_cancelled_order_is_recorded_without_refund(self):
        self.svc.create_qr_payment(self.f.actor(self.customer), self.order.OrderId)
        self.order.OrderStatus, self.order.PaymentStatus = "Cancelled", "Cancelled"
        self.callback(f"GW-{self.order.OrderCode}", "130000.00")
        [tx] = self.txs(self.order)
        self.assertEqual(tx.Status, "Success")
        self.assertEqual((self.order.OrderStatus, self.order.PaymentStatus), ("Cancelled", "Paid"))
        self.assertEqual(self.gateway.refund_calls, [])
        for user in (self.staff, self.admin):
            titles = [n.Title for n in self.f.notifications_for(user)]
            self.assertIn("Cần hoàn tiền thủ công", titles)
        self.assertEqual(self.txs(self.order, "Refund"), [])

    def test_second_successful_payment_alerts_staff(self):
        self.f.payment(self.order, status="Success", gateway_code="GW-OLD")
        self.order.PaymentStatus = "Paid"
        self.f.payment(self.order, status="Pending", gateway_code="GW-NEW")
        self.callback("GW-NEW", "130000.00")
        self.assertEqual(self.order.PaymentStatus, "Paid")
        self.assertIn("Thanh toán trùng", [n.Title for n in self.f.notifications_for(self.admin)])

    def test_customer_cannot_cancel_or_list_other_customers_transactions(self):
        tx = self.svc.create_qr_payment(self.f.actor(self.customer), self.order.OrderId)
        with self.assertRaises(NotFoundError):
            self.svc.cancel_qr_payment(self.f.actor(self.other), tx.PaymentTransactionId)
        with self.assertRaises(NotFoundError):
            self.svc.list_order_transactions(self.f.actor(self.other), self.order.OrderId)
        self.assertEqual(self.svc.cancel_qr_payment(self.f.actor(self.customer), tx.PaymentTransactionId).Status, "Cancelled")


class QrCreationFlowTest(PaymentTestBase):
    """Tạo QR 3 bước: giữ chỗ (commit) → gọi cổng ngoài transaction → gắn QR."""

    def setUp(self) -> None:
        super().setUp()
        self.order = self.f.order(self.customer, self.qr, total="130000.00")

    def create(self, user=None):
        return self.svc.create_qr_payment(self.f.actor(user or self.customer), self.order.OrderId)

    def test_gateway_called_outside_transaction_after_placeholder_committed(self):
        tx = self.create()
        [call] = self.gateway.qr_calls
        self.assertEqual((call["depth"], call["commits"]), (0, 1))
        self.assertEqual(call["amount"], Decimal("130000.00"))  # số tiền lấy từ Order ở server
        self.assertEqual((tx.Status, tx.QrData), ("Pending", "qr://pay"))
        [stored] = self.txs(self.order)
        self.assertEqual(stored.GatewayTransactionCode, f"GW-{self.order.OrderCode}")

    def test_retry_returns_same_request_without_new_gateway_call(self):
        first, second = self.create(), self.create()
        self.assertEqual(first.PaymentTransactionId, second.PaymentTransactionId)
        self.assertEqual((len(self.gateway.qr_calls), len(self.txs(self.order))), (1, 1))

    def test_gateway_error_cancels_placeholder_and_allows_retry(self):
        self.gateway.qr_error = ConnectionError("down token=abc")
        with self.assertLogs("app.services.payment", level="WARNING") as logs, self.assertRaises(PaymentGatewayError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.code, "qr_payment_unavailable")
        self.assertNotIn("token=abc", "\n".join(logs.output))
        [abandoned] = self.txs(self.order)
        self.assertEqual((abandoned.Status, abandoned.QrData), ("Cancelled", None))
        self.gateway.qr_error = None
        retried = self.create()
        self.assertEqual((retried.Status, retried.QrData), ("Pending", "qr://pay"))
        self.assertEqual(len(self.txs(self.order)), 2)

    def test_interrupted_request_blocks_until_customer_cancels_it(self):
        stuck = self.f.payment(self.order, status="Pending", gateway_code=None)  # giữ chỗ, chưa có QR
        with self.assertRaises(ConflictError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.code, "qr_payment_in_progress")
        self.assertEqual(self.gateway.qr_calls, [])
        self.svc.cancel_qr_payment(self.f.actor(self.customer), stuck.PaymentTransactionId)
        self.assertEqual(self.create().QrData, "qr://pay")

    def test_request_cancelled_while_calling_gateway_keeps_code_but_returns_no_qr(self):
        def customer_cancels_meanwhile():
            [placeholder] = self.txs(self.order)
            placeholder.Status = "Cancelled"

        self.gateway.on_create_qr = customer_cancels_meanwhile
        with self.assertRaises(BusinessRuleError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.code, "payment_request_cancelled")
        [tx] = self.txs(self.order)
        self.assertEqual((tx.Status, tx.QrData, tx.GatewayTransactionCode), ("Cancelled", None, f"GW-{self.order.OrderCode}"))

    def test_order_cancelled_while_calling_gateway(self):
        def order_cancelled_meanwhile():
            self.order.OrderStatus, self.order.PaymentStatus = "Cancelled", "Cancelled"

        self.gateway.on_create_qr = order_cancelled_meanwhile
        with self.assertRaises(BusinessRuleError):
            self.create()
        [tx] = self.txs(self.order)
        self.assertEqual((tx.Status, tx.QrData), ("Cancelled", None))

    def test_expired_order_cannot_create_qr(self):
        from datetime import timedelta

        from tests.fakes import NOW

        self.order.OrderedAt = NOW - timedelta(minutes=15)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.code, "order_payment_expired")
        self.assertEqual((self.gateway.qr_calls, self.txs(self.order)), ([], []))

    def test_permissions_and_nesting(self):
        with self.assertRaises(PermissionDeniedError):
            self.create(self.staff)
        with self.assertRaises(NotFoundError):
            self.create(self.other)
        with self.assertRaises(BusinessRuleError) as ctx:
            with self.svc.transaction():
                self.create()
        self.assertEqual(ctx.exception.code, "qr_payment_requires_own_transaction")
        self.assertEqual(self.gateway.qr_calls, [])


class LateCallbackAfterExpiryTest(PaymentTestBase):
    def test_payment_after_expiry_is_recorded_and_staff_alerted_without_refund(self):
        from datetime import timedelta

        from tests.fakes import NOW, order_service

        variant = self.f.variant(stock=3)
        order = self.f.order(self.customer, self.qr, total="130000.00", lines=((variant, 2),))
        self.svc.create_qr_payment(self.f.actor(self.customer), order.OrderId)
        order.OrderedAt = NOW - timedelta(minutes=16)
        self.assertEqual(order_service(self.db, self.session).expire_unpaid_qr_orders(), 1)
        self.assertEqual((order.OrderStatus, variant.StockQuantity, self.txs(order)[0].Status), ("Cancelled", 5, "Cancelled"))

        self.callback(f"GW-{order.OrderCode}", "130000.00")
        [tx] = self.txs(order, "Payment")
        self.assertEqual((tx.Status, order.OrderStatus, order.PaymentStatus), ("Success", "Cancelled", "Paid"))
        self.assertEqual(self.gateway.refund_calls, [])
        self.assertEqual(variant.StockQuantity, 5)  # không khôi phục đơn, không trừ lại tồn
        for user in (self.staff, self.admin):
            self.assertIn("Cần hoàn tiền thủ công", [n.Title for n in self.f.notifications_for(user)])
        from app.models import PaymentReconciliation

        [record] = self.db.rows(PaymentReconciliation)
        self.assertEqual((record.IssueType, record.Status, record.OrderId), ("PaymentAfterCancellation", "Open", order.OrderId))


class QrDeadlineBoundaryTest(PaymentTestBase):
    def test_qr_can_be_created_until_just_before_deadline(self):
        from datetime import timedelta

        from tests.fakes import NOW

        order = self.f.order(self.customer, self.qr, ordered_at=NOW - timedelta(minutes=15) + timedelta(microseconds=1))
        self.assertEqual(self.svc.create_qr_payment(self.f.actor(self.customer), order.OrderId).Status, "Pending")
        late = self.f.order(self.customer, self.qr, ordered_at=NOW - timedelta(minutes=15))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.create_qr_payment(self.f.actor(self.customer), late.OrderId)
        self.assertEqual(ctx.exception.code, "order_payment_expired")


class PaymentMethodPermissionTest(PaymentTestBase):
    def test_public_sees_active_methods_only(self):
        self.svc.methods.list_methods = lambda is_active=None: [
            m for m in self.db.rows(type(self.qr)) if is_active is None or m.IsActive == is_active
        ]
        self.cod.IsActive = False
        self.assertEqual([m.Code for m in self.svc.list_payment_methods(active_only=True)], ["QR"])
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_payment_methods()
        with self.assertRaises(NotFoundError):
            self.svc.get_payment_method(self.cod.PaymentMethodId)
        self.assertEqual(self.svc.get_payment_method(self.cod.PaymentMethodId, actor=self.f.actor(self.staff)).Code, "COD")
        with self.assertRaises(PermissionDeniedError):
            self.svc.delete_payment_method(self.f.actor(self.staff), self.cod.PaymentMethodId)
        with self.assertRaises(PermissionDeniedError):
            self.svc.admin_list_order_transactions(self.f.actor(self.customer), uuid.uuid4())


class RefundTest(PaymentTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.order = self.f.order(self.customer, self.qr, status="Cancelled", payment_status="Paid", total="130000.00")
        self.f.payment(self.order, status="Success", gateway_code="GW-PAY")

    def refund(self, by=None, **kwargs):
        return self.svc.refund_order(self.f.actor(by or self.staff), self.order.OrderId, **kwargs)

    def test_gateway_is_called_outside_database_transaction(self):
        result = self.refund()
        [call] = self.gateway.refund_calls
        self.assertEqual(call["depth"], 0)  # không giữ transaction/khóa dòng khi gọi cổng
        self.assertEqual(call["commits"], 1)  # giao dịch Refund Pending đã được commit trước
        self.assertEqual((call["code"], call["amount"]), ("GW-PAY", Decimal("130000.00")))
        self.assertEqual((result.Status, result.GatewayTransactionCode), ("Success", "RF-1"))
        self.assertEqual(self.order.PaymentStatus, "Refunded")

    def test_gateway_failure_result_marks_refund_failed(self):
        self.gateway.refund_result = GatewayRefundResult(success=False, response_data={"result": "declined"})
        result = self.refund()
        self.assertEqual(result.Status, "Failed")
        self.assertEqual(self.order.PaymentStatus, "Paid")

    def test_gateway_error_keeps_pending_for_reconciliation(self):
        self.gateway.refund_error = TimeoutError("timeout secret-api-key=abc")
        with self.assertLogs("app.services.payment", level="WARNING") as logs, self.assertRaises(PaymentGatewayError) as ctx:
            self.refund()
        self.assertEqual(ctx.exception.code, "refund_pending_reconciliation")
        self.assertNotIn("secret-api-key", "\n".join(logs.output))  # không ghi chi tiết lỗi của cổng vào log
        [pending] = self.txs(self.order, "Refund")
        self.assertEqual(pending.Status, "Pending")  # đã commit ở bước 1, không bị mất
        self.assertEqual(self.order.PaymentStatus, "Paid")
        # Yêu cầu hoàn tiếp khi đang có Refund Pending không được vượt số đã thanh toán.
        with self.assertRaises(BusinessRuleError) as again:
            self.refund()
        self.assertEqual(again.exception.code, "refund_pending")
        self.assertEqual(len(self.gateway.refund_calls), 1)
        resolved = resolve_refund(self.svc, self.f.actor(self.admin), pending.PaymentTransactionId, evidence="RF-MANUAL")
        # Đợt 5.11: mã do Admin nhập là bằng chứng thủ công, không ghi vào dữ liệu của cổng.
        self.assertEqual((resolved.Status, resolved.GatewayTransactionCode, resolved.EvidenceReference,
                          resolved.ResolutionSource), ("Success", None, "RF-MANUAL", "Manual"))
        self.assertEqual(self.order.PaymentStatus, "Refunded")
        with self.assertRaises(BusinessRuleError) as twice:
            resolve_refund(self.svc, self.f.actor(self.admin), pending.PaymentTransactionId, success=False)
        self.assertEqual(twice.exception.code, "refund_not_pending")

    def test_partial_refunds_never_exceed_paid(self):
        first = self.refund(amount=Decimal("50000.00"))
        self.assertEqual((first.Status, self.order.PaymentStatus), ("Success", "Paid"))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.refund(amount=Decimal("80000.01"))
        self.assertEqual(ctx.exception.code, "refund_exceeds_paid")
        self.refund()
        self.assertEqual(self.order.PaymentStatus, "Refunded")
        self.assertEqual(sum(t.Amount for t in self.txs(self.order, "Refund") if t.Status == "Success"), Decimal("130000.00"))
        self.assertEqual(len(self.gateway.refund_calls), 2)

    def test_refund_rules(self):
        with self.assertRaises(PermissionDeniedError):
            self.refund(by=self.customer)
        with self.assertRaises(BusinessRuleError):
            self.refund(amount=Decimal("0"))
        with self.assertRaises(BusinessRuleError):
            self.refund(amount=Decimal("1.005"))
        active = self.f.order(self.customer, self.qr, status="Processing", payment_status="Paid")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.refund_order(self.f.actor(self.staff), active.OrderId)
        self.assertEqual(ctx.exception.code, "refund_not_allowed")
        self.assertEqual(self.gateway.refund_calls, [])
        self.assertEqual(self.txs(self.order, "Refund"), [])

    def test_refund_inside_another_use_case_is_rejected(self):
        with self.assertRaises(BusinessRuleError) as ctx:
            with self.svc.transaction():
                self.refund()
        self.assertEqual(ctx.exception.code, "refund_requires_own_transaction")
        self.assertEqual(self.gateway.refund_calls, [])

    def test_refund_without_gateway_payment_waits_for_another_admin(self):
        cod_order = self.f.order(self.customer, self.cod, status="Cancelled", payment_status="Paid", total="90000.00")
        self.f.payment(cod_order, status="Success", gateway_code=None)
        result = self.svc.refund_order(self.f.actor(self.admin), cod_order.OrderId)
        self.assertEqual((result.Status, result.CreatedByUserId), ("Pending", self.admin.UserId))  # đợt 5.11
        self.assertEqual((cod_order.PaymentStatus, self.gateway.refund_calls), ("Paid", []))
        with self.assertRaises(BusinessRuleError) as own:
            resolve_refund(self.svc, self.f.actor(self.admin), result.PaymentTransactionId)
        self.assertEqual(own.exception.code, "refund_self_confirmation_not_allowed")
        done = resolve_refund(self.svc, self.f.actor(self.f.user("Admin")), result.PaymentTransactionId)
        self.assertEqual((done.Status, cod_order.PaymentStatus), ("Success", "Refunded"))


class CodRecordTest(PaymentTestBase):
    def test_record_cod_payment_is_idempotent_and_needs_staff(self):
        order = self.f.order(self.customer, self.cod, status="Delivered", payment_status="Paid", total="90000.00")
        with self.assertRaises(PermissionDeniedError):
            self.svc.record_cod_payment(self.f.actor(self.customer), order.OrderId)
        first = self.svc.record_cod_payment(self.f.actor(self.staff), order.OrderId)
        second = self.svc.record_cod_payment(self.f.actor(self.staff), order.OrderId)
        self.assertEqual(first.PaymentTransactionId, second.PaymentTransactionId)
        self.assertEqual(len(self.txs(order)), 1)

    def test_record_cod_payment_does_not_mark_unpaid_order_paid(self):
        order = self.f.order(self.customer, self.cod, status="Delivered", payment_status="Pending")
        with self.assertRaises(BusinessRuleError):
            self.svc.record_cod_payment(self.f.actor(self.staff), order.OrderId)
        self.assertEqual((order.PaymentStatus, self.txs(order)), ("Pending", []))


if __name__ == "__main__":
    unittest.main()
