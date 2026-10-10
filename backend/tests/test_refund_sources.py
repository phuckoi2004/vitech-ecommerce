"""Hoàn tiền theo từng khoản Payment gốc (RefundOfPaymentTransactionId).

Bảo vệ: mỗi Refund trỏ tới một Payment thành công cùng đơn; số còn có thể hoàn tính theo từng khoản
(Amount − Refund Success − Refund Pending); Refund Failed/Cancelled không giữ tiền; Refund không làm nguồn.
Fake trong bộ nhớ: khóa dòng chỉ được ghi lại (db.locks), không chứng minh concurrency thật của PostgreSQL.
"""

import unittest
import uuid
from decimal import Decimal

from app.models import PaymentTransaction
from app.services import (
    BusinessRuleError,
    GatewayRefundResult,
    NotFoundError,
    PermissionDeniedError,
)

from tests.fakes import payment_service, resolve_refund
from tests.test_payment import FakeGateway, PaymentTestBase


class HookedGateway(FakeGateway):
    """Cổng giả cho phép chạy một yêu cầu khác ĐANG giữa bước 1 (Refund Pending đã commit) và bước 3."""

    def __init__(self, session) -> None:
        super().__init__(session)
        self.on_refund = None

    def refund(self, *, gateway_transaction_code, amount):
        hook, self.on_refund = self.on_refund, None
        if hook is not None:
            hook()
        return super().refund(gateway_transaction_code=gateway_transaction_code, amount=amount)


class ManualRefundGateway(FakeGateway):
    """Cổng không có API hoàn tiền: Refund giữ Pending đến khi Staff/Admin xác nhận chuyển khoản thủ công."""

    supports_refund = False


class RefundSourceTestBase(PaymentTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.gateway = HookedGateway(self.session)
        self.svc = payment_service(self.db, self.session, gateway=self.gateway)
        self.order = self.f.order(self.customer, self.qr, status="Cancelled", payment_status="Paid", total="150000.00")
        self.a = self.f.payment(self.order, status="Success", amount="100000.00", gateway_code="GW-A")
        self.b = self.f.payment(self.order, status="Success", amount="50000.00", gateway_code="GW-B")

    def refund(self, amount=None, source=None, *, order=None):
        return self.svc.refund_order(
            self.f.actor(self.staff),
            (order or self.order).OrderId,
            amount=Decimal(amount) if amount is not None else None,
            payment_transaction_id=source.PaymentTransactionId if source is not None else None,
        )

    def refunds(self, status=None):
        return [t for t in self.txs(self.order, "Refund") if status is None or t.Status == status]

    def remaining(self):
        return {s.PaymentTransactionId: s.RefundableAmount for s in self.svc.list_refund_sources(self.f.actor(self.staff), self.order.OrderId)}

    def assert_rejected(self, code, *args, **kwargs):
        calls, rows = len(self.gateway.refund_calls), len(self.refunds())
        with self.assertRaises(BusinessRuleError) as ctx:
            self.refund(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code)
        self.assertEqual((len(self.gateway.refund_calls), len(self.refunds())), (calls, rows))  # không gọi cổng, không ghi


class PartialAndFullRefundTest(RefundSourceTestBase):
    def test_partial_refund_links_source_and_keeps_payment_history(self):
        result = self.refund("40000.00", self.a)
        self.assertEqual((result.Status, result.RefundOfPaymentTransactionId), ("Success", self.a.PaymentTransactionId))
        self.assertEqual(self.gateway.refund_calls[0]["code"], "GW-A")
        self.assertEqual(self.a.Status, "Success")  # khoản thu đã xảy ra; trạng thái hoàn suy ra từ các Refund
        self.assertEqual(self.order.PaymentStatus, "Paid")
        self.assertEqual(self.remaining(), {self.a.PaymentTransactionId: Decimal("60000.00"),
                                            self.b.PaymentTransactionId: Decimal("50000.00")})

    def test_full_refund_of_every_source(self):
        self.refund("100000.00", self.a)
        self.assertEqual(self.order.PaymentStatus, "Paid")  # mới hoàn một khoản
        self.refund("50000.00", self.b)
        self.assertEqual(self.order.PaymentStatus, "Refunded")
        self.assertEqual(set(self.remaining().values()), {Decimal("0.00")})
        self.assertEqual({r.RefundOfPaymentTransactionId for r in self.refunds("Success")},
                         {self.a.PaymentTransactionId, self.b.PaymentTransactionId})
        self.assertEqual((self.a.Status, self.b.Status), ("Success", "Success"))
        detail = {s.PaymentTransactionId: s for s in self.svc.list_refund_sources(self.f.actor(self.admin), self.order.OrderId)}
        self.assertEqual((detail[self.a.PaymentTransactionId].RefundedAmount,
                          detail[self.a.PaymentTransactionId].PendingRefundAmount), (Decimal("100000.00"), Decimal("0")))

    def test_fully_refunded_source_is_rejected(self):
        self.refund("100000.00", self.a)
        self.assert_rejected("source_payment_fully_refunded", "1.00", self.a)
        self.refund("50000.00", self.b)  # khoản khác vẫn hoàn được

    def test_cannot_exceed_remaining_of_the_source(self):
        self.refund("70000.00", self.a)
        self.assert_rejected("refund_exceeds_source_payment", "30000.01", self.a)  # theo đơn vẫn còn 80000
        self.refund("30000.00", self.a)
        self.assertEqual(sum(r.Amount for r in self.refunds("Success") if r.RefundOfPaymentTransactionId == self.a.PaymentTransactionId),
                         Decimal("100000.00"))

    def test_cannot_exceed_order_refundable(self):
        self.assert_rejected("refund_exceeds_paid", "150000.01")
        self.assert_rejected("refund_exceeds_source_payment", "60000.00", self.b)


class MultipleSourcesTest(RefundSourceTestBase):
    def test_default_source_never_reuses_an_exhausted_payment(self):
        """Lỗi audit: hai khoản bằng nhau, lần hoàn mặc định thứ hai từng chọn lại khoản đầu tiên."""
        order = self.f.order(self.customer, self.qr, status="Cancelled", payment_status="Paid", total="100000.00")
        first = self.f.payment(order, status="Success", amount="100000.00", gateway_code="GW-1")
        second = self.f.payment(order, status="Success", amount="100000.00", gateway_code="GW-2")
        self.refund("100000.00", order=order)
        self.refund("100000.00", order=order)
        self.assertEqual([c["code"] for c in self.gateway.refund_calls], ["GW-1", "GW-2"])
        linked = [t.RefundOfPaymentTransactionId for t in self.txs(order, "Refund")]
        self.assertEqual(sorted(map(str, linked)), sorted([str(first.PaymentTransactionId), str(second.PaymentTransactionId)]))
        self.assertEqual(order.PaymentStatus, "Refunded")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.refund("1.00", order=order)
        self.assertEqual(ctx.exception.code, "refund_not_allowed")  # đơn đã Refunded

    def test_default_picks_first_source_with_enough_remaining(self):
        self.refund("60000.00")  # A
        self.refund("50000.00")  # A còn 40000 < 50000 → B
        self.refund()  # mặc định phần còn lại của đơn (40000) → A
        self.assertEqual([c["code"] for c in self.gateway.refund_calls], ["GW-A", "GW-B", "GW-A"])
        self.assertEqual(self.order.PaymentStatus, "Refunded")

    def test_amount_larger_than_every_single_source_requires_split(self):
        self.assert_rejected("refund_requires_source_payment", "120000.00")


class ConcurrencyTest(RefundSourceTestBase):
    def test_second_request_while_first_is_at_gateway_sees_pending_amount(self):
        outcome = {}

        def second_request():
            for key, args in (("same_source", ("1.00", self.a)), ("other_source", ("50000.00", self.b))):
                try:
                    outcome[key] = self.refund(*args).Status
                except BusinessRuleError as exc:
                    outcome[key] = exc.code

        self.gateway.on_refund = second_request
        self.refund("100000.00", self.a)
        self.assertEqual(outcome, {"same_source": "source_payment_fully_refunded", "other_source": "Success"})
        self.assertEqual(sorted(r.Amount for r in self.refunds("Success")), [Decimal("50000.00"), Decimal("100000.00")])
        self.assertEqual(self.order.PaymentStatus, "Refunded")

    def test_order_is_locked_before_source_payment(self):
        self.db.locks.clear()
        self.refund("10000.00", self.b)
        order_lock = self.db.locks.index(("Order", self.order.OrderId))
        source_lock = self.db.locks.index(("PaymentTransaction", self.b.PaymentTransactionId))
        self.assertLess(order_lock, source_lock)

    def test_error_inside_transaction_leaves_no_refund(self):
        cod_order = self.f.order(self.customer, self.cod, status="Cancelled", payment_status="Paid", total="90000.00")
        self.f.payment(cod_order, status="Success", gateway_code=None)

        def broken(*args, **kwargs):
            raise RuntimeError("database write failed")

        self.svc.transactions.flush = broken  # lỗi ngay sau khi ghi giao dịch Refund
        with self.assertRaises(RuntimeError):
            self.refund(order=cod_order)
        self.assertEqual((self.txs(cod_order, "Refund"), cod_order.PaymentStatus), ([], "Paid"))


class PendingFailedCancelledTest(RefundSourceTestBase):
    def test_failed_refund_does_not_hold_amount(self):
        self.gateway.refund_result = GatewayRefundResult(success=False, response_data={"result": "declined"})
        failed = self.refund("100000.00", self.a)
        self.assertEqual(failed.Status, "Failed")
        self.assertEqual(self.remaining()[self.a.PaymentTransactionId], Decimal("100000.00"))
        self.gateway.refund_result = GatewayRefundResult(success=True, response_data={}, gateway_transaction_code="RF-2")
        self.assertEqual(self.refund("100000.00", self.a).Status, "Success")

    def test_manual_pending_refund_holds_amount_until_resolved(self):
        self.svc = payment_service(self.db, self.session, gateway=ManualRefundGateway(self.session))
        pending = self.refund("100000.00", self.a)
        self.assertEqual(pending.Status, "Pending")
        self.assert_rejected("source_payment_fully_refunded", "1.00", self.a)
        [source] = [s for s in self.svc.list_refund_sources(self.f.actor(self.staff), self.order.OrderId)
                    if s.PaymentTransactionId == self.a.PaymentTransactionId]
        self.assertEqual((source.PendingRefundAmount, source.RefundableAmount), (Decimal("100000.00"), Decimal("0")))
        resolve_refund(self.svc, self.f.actor(self.admin), pending.PaymentTransactionId, success=False)
        self.assertEqual(self.remaining()[self.a.PaymentTransactionId], Decimal("100000.00"))  # thất bại → nhả số tiền
        retry = self.refund("100000.00", self.a)
        resolve_refund(self.svc, self.f.actor(self.admin), retry.PaymentTransactionId, evidence="FT-1")
        self.assertEqual(self.order.PaymentStatus, "Paid")  # khoản B chưa hoàn
        self.assertEqual([r.Status for r in sorted(self.refunds(), key=lambda r: r.Status)], ["Failed", "Success"])

    def test_cancelled_refund_does_not_hold_amount(self):
        """Cancelled thuộc tập trạng thái giao dịch; hiện chưa có use case tạo Refund Cancelled nhưng phép tính phải đúng."""
        self.f.payment(self.order, status="Cancelled", amount="100000.00", gateway_code=None, tx_type="Refund", refund_of=self.a)
        self.assertEqual(self.remaining()[self.a.PaymentTransactionId], Decimal("100000.00"))
        self.assertEqual(self.refund("100000.00", self.a).Status, "Success")


class InvalidSourceTest(RefundSourceTestBase):
    def test_refund_transaction_cannot_be_a_source(self):
        refund = self.refund("40000.00", self.a)
        self.assert_rejected("invalid_refund_source", "1.00", self.db.get(PaymentTransaction, refund.PaymentTransactionId))

    def test_source_must_be_successful_payment_of_this_order(self):
        waiting = self.f.payment(self.order, status="Pending", amount="10000.00", gateway_code="GW-P")
        self.assert_rejected("invalid_refund_source", "1.00", waiting)
        elsewhere = self.f.payment(self.f.order(self.customer, self.qr, status="Cancelled", payment_status="Paid"))
        with self.assertRaises(NotFoundError):
            self.refund("1.00", elsewhere)
        with self.assertRaises(NotFoundError):
            self.svc.refund_order(self.f.actor(self.staff), self.order.OrderId, payment_transaction_id=uuid.uuid4())
        self.assertEqual(self.gateway.refund_calls, [])

    def test_cod_refund_links_cod_payment(self):
        cod_order = self.f.order(self.customer, self.cod, status="Cancelled", payment_status="Paid", total="90000.00")
        cod_payment = self.f.payment(cod_order, status="Success", gateway_code=None)
        result = self.refund(order=cod_order)
        self.assertEqual((result.Status, result.RefundOfPaymentTransactionId), ("Pending", cod_payment.PaymentTransactionId))
        self.assertEqual((cod_order.PaymentStatus, self.gateway.refund_calls), ("Paid", []))  # chưa xác nhận
        resolve_refund(self.svc, self.f.actor(self.admin), result.PaymentTransactionId)
        self.assertEqual(cod_order.PaymentStatus, "Refunded")

    def test_order_without_successful_payment_has_nothing_to_refund(self):
        """Dữ liệu lệch (Paid nhưng không có Payment thành công): không tạo Refund không có nguồn."""
        legacy = self.f.order(self.customer, self.cod, status="Cancelled", payment_status="Paid", total="90000.00")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.refund(order=legacy)
        self.assertEqual(ctx.exception.code, "nothing_to_refund")
        self.assertEqual(self.txs(legacy, "Refund"), [])

    def test_listing_requires_staff(self):
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_refund_sources(self.f.actor(self.customer), self.order.OrderId)
        with self.assertRaises(NotFoundError):
            self.svc.list_refund_sources(self.f.actor(self.staff), uuid.uuid4())


if __name__ == "__main__":
    unittest.main()
