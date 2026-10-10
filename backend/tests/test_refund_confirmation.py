"""Đợt 5.11 (phương án D2): người tạo giao dịch Refund, xác nhận thủ công bởi Admin khác người tạo, nguồn kết quả.

- Mọi Refund tạo ở Pending, ghi CreatedByUserId. COD/hoàn trực tiếp không qua cổng chỉ Success sau xác nhận thủ công.
- resolve_pending_refund: chỉ Admin, khác người tạo; bắt buộc mã bằng chứng + ghi chú; ghi ResolutionSource = Manual,
  ResolvedByUserId, ResolvedAt; không ghi GatewayTransactionCode/ResponseData.
- Kết quả cổng: ResolutionSource = Gateway, giữ dữ liệu cổng; không bị xác nhận thủ công ghi đè (và ngược lại).
- Pending/Failed không phải đã hoàn. Giới hạn số tiền theo đơn và khoản nguồn giữ nguyên (đợt 5.1/5.8).
Fake trong bộ nhớ: khóa dòng/đồng thời chỉ được giả lập (thứ tự gọi, db.locks); CHECK constraint được kiểm tra bằng bản
viết lại trong Python (assert_resolution_checks), không phải bởi PostgreSQL thật.
"""

import unittest
import uuid
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError

from app.models import Notification, PaymentTransaction
from app.models.payment import (
    GATEWAY_RESOLUTION_SQL,
    MANUAL_NOT_BY_CREATOR_SQL,
    MANUAL_RESOLUTION_SQL,
    RESOLUTION_CONSISTENT_SQL,
)
from app.schemas import RefundResolution
from app.services import (
    BusinessRuleError,
    GatewayRefundResult,
    NotFoundError,
    PaymentGatewayError,
    PermissionDeniedError,
)

from tests.fakes import payment_service, resolve_refund
from tests.test_payment import PaymentTestBase
from tests.test_refund_sources import ManualRefundGateway
from tests.test_return_service import ReturnTestBase

EVIDENCE = "FT26101100123"
NOTE = "Đã đối chiếu sao kê ngân hàng ngày 11/10"


def bypass(values):
    """Dữ liệu đi vòng qua Schema (ví dụ Router lỗi) để kiểm tra Service tự chặn."""
    return SimpleNamespace(model_dump=lambda exclude_unset=True: dict(values))


def check_violations(t: PaymentTransaction) -> list[str]:
    """Viết lại bằng Python các CHECK của migration a9f4c2e7b513 (CHECK chỉ vi phạm khi biểu thức = FALSE)."""
    def blank(value):
        return value is None or not value.strip()

    fields = (t.ResolvedByUserId, t.ResolvedAt, t.EvidenceReference, t.ResolutionNote)
    problems = []
    if t.ResolutionSource not in (None, "Gateway", "Manual"):
        problems.append("ResolutionSource_Valid")
    unresolved = t.ResolutionSource is None and all(v is None for v in fields)
    resolved = (t.ResolutionSource is not None and t.ResolvedAt is not None and t.TransactionType == "Refund"
                and t.Status in ("Success", "Failed"))
    if not (unresolved or resolved):
        problems.append("Resolution_Consistent")
    if t.ResolutionSource == "Gateway" and not (
            t.ResolvedByUserId is None and t.EvidenceReference is None and t.ResolutionNote is None):
        problems.append("GatewayResolution_NoManualFields")
    if t.ResolutionSource == "Manual" and (t.ResolvedByUserId is None or blank(t.EvidenceReference)
                                           or blank(t.ResolutionNote)):
        problems.append("ManualResolution_Complete")
    if (t.ResolutionSource == "Manual" and t.CreatedByUserId is not None
            and t.ResolvedByUserId == t.CreatedByUserId):
        problems.append("ManualResolution_NotByCreator")
    return problems


class RefundCheckMixin:
    def refunds(self):
        return [t for t in self.db.rows(PaymentTransaction) if t.TransactionType == "Refund"]  # thứ tự ghi

    def assert_resolution_checks(self):
        for t in self.db.rows(PaymentTransaction):
            self.assertEqual(check_violations(t), [], (t.TransactionType, t.Status, t.ResolutionSource))

    def resolution(self, t):
        return (t.Status, t.ResolutionSource, t.ResolvedByUserId, t.EvidenceReference, t.ResolutionNote)

    def assert_code(self, error, code, call):
        with self.assertRaises(error) as ctx:
            call()
        self.assertEqual(ctx.exception.code, code)


class ConfirmationTestBase(RefundCheckMixin, PaymentTestBase):
    """Đơn COD đã hủy khi đã thu 130.000 (không qua cổng): hoàn trực tiếp."""

    def setUp(self) -> None:
        super().setUp()
        self.admin2 = self.f.user("Admin")
        self.order = self.f.order(self.customer, self.cod, status="Cancelled", payment_status="Paid", total="130000.00")
        self.payment = self.f.payment(self.order, status="Success", gateway_code=None)

    def refund(self, by=None, amount=None, order=None, source=None):
        return self.svc.refund_order(self.f.actor(by or self.staff), (order or self.order).OrderId,
                                     amount=Decimal(amount) if amount is not None else None,
                                     payment_transaction_id=source.PaymentTransactionId if source else None)

    def resolve(self, refund_id, by=None, success=True, evidence=EVIDENCE, note=NOTE):
        return resolve_refund(self.svc, self.f.actor(by or self.admin), refund_id, success=success, evidence=evidence,
                              note=note)

    def refunded_notifications(self):
        return [n for n in self.db.rows(Notification) if n.UserId == self.customer.UserId and n.Title == "Hoàn tiền"]


class DirectRefundConfirmationTest(ConfirmationTestBase):
    def test_staff_creates_pending_refund_and_another_admin_confirms(self):
        pending = self.refund()
        self.assertEqual((pending.Status, pending.CreatedByUserId, pending.RefundOfPaymentTransactionId),
                         ("Pending", self.staff.UserId, self.payment.PaymentTransactionId))
        self.assertEqual((pending.ResolutionSource, pending.ResolvedByUserId, pending.ResolvedAt, pending.PaidAt),
                         (None, None, None, None))
        self.assertEqual((self.order.PaymentStatus, self.gateway.refund_calls, self.refunded_notifications()),
                         ("Paid", [], []))  # chưa phải đã hoàn: không đổi PaymentStatus, không báo khách
        queue = self.svc.list_orders_awaiting_refund(self.f.actor(self.staff)).Items
        self.assertEqual([o.OrderId for o in queue], [self.order.OrderId])
        done = self.resolve(pending.PaymentTransactionId)
        self.assertEqual(
            (done.Status, done.ResolutionSource, done.ResolvedByUserId, done.EvidenceReference, done.ResolutionNote),
            ("Success", "Manual", self.admin.UserId, EVIDENCE, NOTE))
        self.assertIsNotNone(done.ResolvedAt)
        self.assertEqual((done.PaidAt, done.CreatedByUserId), (done.ResolvedAt, self.staff.UserId))
        self.assertEqual((done.GatewayTransactionCode, done.ResponseData), (None, None))  # không tạo dữ liệu cổng giả
        self.assertEqual((self.order.PaymentStatus, len(self.refunded_notifications())), ("Refunded", 1))
        self.assertEqual(self.svc.list_orders_awaiting_refund(self.f.actor(self.staff)).Items, [])
        self.assertEqual(self.db.locks[-2:], [("Order", self.order.OrderId),
                                              ("PaymentTransaction", pending.PaymentTransactionId)])
        self.assert_resolution_checks()

    def test_creator_cannot_confirm_own_refund_even_as_admin(self):
        pending = self.refund(by=self.admin)
        self.assert_code(BusinessRuleError, "refund_self_confirmation_not_allowed",
                         lambda: self.resolve(pending.PaymentTransactionId, by=self.admin))
        self.assert_code(BusinessRuleError, "refund_self_confirmation_not_allowed",
                         lambda: self.resolve(pending.PaymentTransactionId, by=self.admin, success=False))
        [refund] = self.refunds()
        self.assertEqual(self.resolution(refund), ("Pending", None, None, None, None))
        self.assertEqual(self.resolve(pending.PaymentTransactionId, by=self.admin2).ResolvedByUserId, self.admin2.UserId)
        self.assert_resolution_checks()

    def test_only_admin_can_confirm(self):
        pending = self.refund()
        for user in (self.staff, self.f.user("Staff"), self.customer):
            with self.subTest(role=user.Role):
                self.assertRaises(PermissionDeniedError, lambda: self.resolve(pending.PaymentTransactionId, by=user))
        self.assertEqual(self.resolution(self.refunds()[0]), ("Pending", None, None, None, None))

    def test_evidence_and_note_are_required_for_success_and_failure(self):
        pending = self.refund()
        for kwargs in ({"EvidenceReference": "   "}, {"ResolutionNote": ""}, {"EvidenceReference": "x" * 256}):
            with self.subTest(kwargs=kwargs):
                self.assertRaises(ValidationError, RefundResolution,
                                  **{"Success": True, "EvidenceReference": EVIDENCE, "ResolutionNote": NOTE, **kwargs})
        self.assertRaises(ValidationError, RefundResolution, Success=False, ResolutionNote=NOTE)
        admin = self.f.actor(self.admin)
        cases = (
            ({"Success": True, "ResolutionNote": NOTE}, "refund_evidence_required"),
            ({"Success": False, "EvidenceReference": "  ", "ResolutionNote": NOTE}, "refund_evidence_required"),
            ({"Success": True, "EvidenceReference": EVIDENCE}, "refund_resolution_note_required"),
            ({"Success": False, "EvidenceReference": EVIDENCE, "ResolutionNote": " "}, "refund_resolution_note_required"),
            ({"Success": "yes", "EvidenceReference": EVIDENCE, "ResolutionNote": NOTE}, "invalid_refund_resolution"),
            ({"EvidenceReference": EVIDENCE, "ResolutionNote": NOTE}, "invalid_refund_resolution"),
            ({"Success": True, "EvidenceReference": "x" * 256, "ResolutionNote": NOTE}, "refund_evidence_too_long"),
            ({"Success": True, "EvidenceReference": EVIDENCE, "ResolutionNote": NOTE, "GatewayTransactionCode": "X"},
             "refund_resolution_field_not_allowed"),
            ({"Success": True, "EvidenceReference": EVIDENCE, "ResolutionNote": NOTE, "ResponseData": {"a": 1}},
             "refund_resolution_field_not_allowed"),
            ({"Success": True, "EvidenceReference": EVIDENCE, "ResolutionNote": NOTE,
              "ResolvedByUserId": self.staff.UserId}, "refund_resolution_field_not_allowed"),
        )
        for values, code in cases:
            with self.subTest(code=code, values=sorted(values)):
                self.assert_code(BusinessRuleError, code,
                                 lambda: self.svc.resolve_pending_refund(admin, pending.PaymentTransactionId,
                                                                         bypass(values)))
        self.assertEqual(self.resolution(self.refunds()[0]), ("Pending", None, None, None, None))
        done = self.resolve(pending.PaymentTransactionId, evidence="  BL-01  ", note="  Biên nhận tiền mặt ")
        self.assertEqual((done.EvidenceReference, done.ResolutionNote), ("BL-01", "Biên nhận tiền mặt"))  # bỏ khoảng trắng

    def test_failed_confirmation_releases_money_and_allows_retry(self):
        pending = self.refund(amount="100000.00")
        self.assert_code(BusinessRuleError, "refund_exceeds_paid", lambda: self.refund(amount="30000.01"))  # Pending giữ
        failed = self.resolve(pending.PaymentTransactionId, success=False, note="Ngân hàng từ chối chuyển khoản")
        self.assertEqual((failed.Status, failed.ResolutionSource, failed.PaidAt), ("Failed", "Manual", None))
        self.assertEqual((self.order.PaymentStatus, self.refunded_notifications()), ("Paid", []))
        [source] = self.svc.list_refund_sources(self.f.actor(self.staff), self.order.OrderId)
        self.assertEqual((source.RefundedAmount, source.PendingRefundAmount, source.RefundableAmount),
                         (Decimal("0"), Decimal("0"), Decimal("130000.00")))  # Failed không giữ tiền
        retry = self.refund()
        self.assertEqual((retry.Amount, retry.Status), (Decimal("130000.00"), "Pending"))
        self.resolve(retry.PaymentTransactionId)
        self.assertEqual(([t.Status for t in self.refunds()], self.order.PaymentStatus),
                         (["Failed", "Success"], "Refunded"))  # thứ tự ghi: lần đầu Failed, lần thử lại Success
        self.assert_resolution_checks()

    def test_duplicate_and_wrong_state_confirmations_are_rejected(self):
        pending = self.refund()
        done = self.resolve(pending.PaymentTransactionId)
        before = self.resolution(self.refunds()[0])
        for by, success in ((self.admin, True), (self.admin2, False), (self.admin2, True)):
            with self.subTest(by=by.UserId, success=success):
                self.assert_code(BusinessRuleError, "refund_not_pending",
                                 lambda: self.resolve(pending.PaymentTransactionId, by=by, success=success,
                                                      evidence="OTHER", note="ghi đè"))
        self.assertEqual(self.resolution(self.refunds()[0]), before)
        self.assertEqual((done.ResolvedAt, len(self.refunded_notifications())), (self.refunds()[0].ResolvedAt, 1))
        self.assert_code(NotFoundError, "refund_transaction_not_found",
                         lambda: self.resolve(self.payment.PaymentTransactionId))  # Payment không phải Refund
        self.assert_code(NotFoundError, "refund_transaction_not_found", lambda: self.resolve(uuid.uuid4()))

    def test_result_committed_while_waiting_for_the_lock_is_seen_after_locking(self):
        """Hai Admin xác nhận đồng thời: yêu cầu sau đọc giao dịch lúc còn Pending, rồi chờ khóa Order; trong lúc chờ,
        yêu cầu kia đã ghi kết quả. Sau khi có khóa, giao dịch được đọc lại (FOR UPDATE) nên yêu cầu sau bị từ chối.
        (Fake: kết quả của "kết nối khác" được giả lập bằng cách sửa trực tiếp dòng ngay trước khi khóa; khi yêu cầu sau
        rollback, fake khôi phục cả thay đổi đó nên không kiểm tra trạng thái cuối.)"""
        pending = self.refund()
        refund = self.db.get(PaymentTransaction, pending.PaymentTransactionId)
        original_lock = self.svc.orders.get_by_id_for_update
        seen = []

        def other_admin_commits_first(order_id):
            seen.append(refund.Status)  # yêu cầu sau đã đọc giao dịch còn Pending trước khi khóa
            refund.Status, refund.ResolutionSource, refund.ResolvedByUserId = "Failed", "Manual", self.admin2.UserId
            return original_lock(order_id)

        self.svc.orders.get_by_id_for_update = other_admin_commits_first
        notifications = len(self.db.rows(Notification))
        self.assert_code(BusinessRuleError, "refund_not_pending", lambda: self.resolve(pending.PaymentTransactionId))
        self.assertEqual(seen, ["Pending"])
        self.assertEqual(self.db.locks[-2:], [("Order", self.order.OrderId),
                                              ("PaymentTransaction", pending.PaymentTransactionId)])
        self.assertEqual(len(self.db.rows(Notification)), notifications)  # không báo "đã hoàn"

    def test_legacy_pending_refund_without_creator_needs_admin_and_evidence(self):
        pending = self.refund()
        legacy = self.db.get(PaymentTransaction, pending.PaymentTransactionId)
        legacy.CreatedByUserId = None  # dữ liệu trước migration a9f4c2e7b513
        self.assertRaises(PermissionDeniedError, lambda: self.resolve(legacy.PaymentTransactionId, by=self.staff))
        self.assert_code(BusinessRuleError, "refund_evidence_required",
                         lambda: self.svc.resolve_pending_refund(self.f.actor(self.admin), legacy.PaymentTransactionId,
                                                                 bypass({"Success": True, "ResolutionNote": NOTE})))
        self.assertEqual(self.resolve(legacy.PaymentTransactionId).Status, "Success")
        self.assert_resolution_checks()


class LimitsAndMultiplePaymentsTest(ConfirmationTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.second = self.f.payment(self.order, status="Success", amount="70000.00", gateway_code=None)  # thu thêm

    def test_multiple_payments_and_refunds_never_exceed_paid(self):
        a = self.refund(amount="100000.00", source=self.payment)
        b = self.refund(amount="30000.00", source=self.payment)
        self.assert_code(BusinessRuleError, "source_payment_fully_refunded",
                         lambda: self.refund(amount="1.00", source=self.payment))  # Pending giữ tiền của khoản A
        c = self.refund(amount="70000.00", source=self.second)
        self.assert_code(BusinessRuleError, "refund_pending", lambda: self.refund())  # mọi số tiền đang chờ
        self.resolve(a.PaymentTransactionId)
        self.resolve(b.PaymentTransactionId, by=self.admin2, success=False)
        self.assertEqual(self.order.PaymentStatus, "Paid")  # 170.000 Success < 200.000 đã thu
        d = self.refund()
        self.assertEqual((d.Amount, d.RefundOfPaymentTransactionId), (Decimal("30000.00"), self.payment.PaymentTransactionId))
        self.resolve(c.PaymentTransactionId)
        self.assertEqual(self.order.PaymentStatus, "Paid")
        self.resolve(d.PaymentTransactionId, by=self.admin2)
        success = sum(t.Amount for t in self.refunds() if t.Status == "Success")
        self.assertEqual((success, self.order.PaymentStatus), (Decimal("200000.00"), "Refunded"))
        self.assert_code(BusinessRuleError, "refund_not_allowed", lambda: self.refund())  # đơn đã Refunded
        self.assert_resolution_checks()

    def test_manual_success_rechecks_limits_against_inconsistent_data(self):
        first = self.refund(amount="100000.00", source=self.payment)
        second = self.refund(amount="70000.00", source=self.second)
        self.resolve(first.PaymentTransactionId)
        # Dữ liệu bất thường dựng tay: Refund đã Success bị tăng số tiền vượt khoản nguồn và tổng đã thu.
        self.db.get(PaymentTransaction, first.PaymentTransactionId).Amount = Decimal("135000.00")
        self.assert_code(BusinessRuleError, "refund_exceeds_paid", lambda: self.resolve(second.PaymentTransactionId))
        self.db.get(PaymentTransaction, first.PaymentTransactionId).Amount = Decimal("100000.00")
        self.db.get(PaymentTransaction, second.PaymentTransactionId).Amount = Decimal("70000.01")  # > khoản nguồn
        self.assert_code(BusinessRuleError, "refund_exceeds_source_payment",
                         lambda: self.resolve(second.PaymentTransactionId))
        self.assertEqual(self.db.get(PaymentTransaction, second.PaymentTransactionId).Status, "Pending")
        self.assertEqual(self.resolve(second.PaymentTransactionId, success=False).Status, "Failed")  # thất bại vẫn ghi được
        self.assert_resolution_checks()


class GatewayResolutionTest(RefundCheckMixin, PaymentTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.order = self.f.order(self.customer, self.qr, status="Cancelled", payment_status="Paid", total="130000.00")
        self.f.payment(self.order, status="Success", gateway_code="GW-PAY")

    def refund(self):
        return self.svc.refund_order(self.f.actor(self.staff), self.order.OrderId)

    def test_gateway_success_keeps_gateway_evidence_and_source(self):
        done = self.refund()
        self.assertEqual((done.Status, done.ResolutionSource, done.CreatedByUserId, done.ResolvedByUserId),
                         ("Success", "Gateway", self.staff.UserId, None))
        self.assertEqual((done.GatewayTransactionCode, done.ResponseData, done.EvidenceReference, done.ResolutionNote),
                         ("RF-1", {"result": "ok"}, None, None))
        self.assertIsNotNone(done.ResolvedAt)
        self.assertEqual(self.order.PaymentStatus, "Refunded")
        self.assert_code(BusinessRuleError, "refund_not_pending",  # xác nhận thủ công không ghi đè kết quả cổng
                         lambda: resolve_refund(self.svc, self.f.actor(self.admin), done.PaymentTransactionId,
                                                success=False))
        [refund] = self.refunds()
        self.assertEqual((refund.Status, refund.ResolutionSource, refund.GatewayTransactionCode, refund.ResponseData),
                         ("Success", "Gateway", "RF-1", {"result": "ok"}))
        self.assert_resolution_checks()

    def test_gateway_failure_is_recorded_as_gateway_result(self):
        self.gateway.refund_result = GatewayRefundResult(success=False, response_data={"code": "DECLINED"})
        failed = self.refund()
        self.assertEqual((failed.Status, failed.ResolutionSource, failed.ResponseData, failed.ResolvedByUserId),
                         ("Failed", "Gateway", {"code": "DECLINED"}, None))
        self.assertEqual(self.order.PaymentStatus, "Paid")
        self.assert_resolution_checks()

    def test_late_gateway_result_does_not_overwrite_manual_confirmation(self):
        self.gateway.refund_error = TimeoutError("cổng không phản hồi")
        self.assert_code(PaymentGatewayError, "refund_pending_reconciliation", self.refund)
        [pending] = self.refunds()
        self.assertEqual((pending.Status, pending.ResolutionSource), ("Pending", None))
        resolve_refund(self.svc, self.f.actor(self.admin), pending.PaymentTransactionId, evidence="RF-PORTAL-9")
        late = self.svc._record_gateway_result(pending.PaymentTransactionId, GatewayRefundResult(
            success=False, response_data={"late": True}, gateway_transaction_code="RF-LATE"))
        self.assertEqual((late.Status, late.ResolutionSource, late.EvidenceReference, late.GatewayTransactionCode,
                          late.ResponseData), ("Success", "Manual", "RF-PORTAL-9", None, None))
        self.assert_resolution_checks()

    def test_manual_gateway_refund_waits_for_admin_confirmation(self):
        self.svc = payment_service(self.db, self.session, gateway=ManualRefundGateway(self.session))
        pending = self.refund()
        self.assertEqual((pending.Status, pending.ResolutionSource, self.order.PaymentStatus), ("Pending", None, "Paid"))
        self.assert_code(BusinessRuleError, "refund_pending", self.refund)  # không tạo yêu cầu trùng
        done = resolve_refund(self.svc, self.f.actor(self.admin), pending.PaymentTransactionId, evidence="FT-SEPAY-1")
        self.assertEqual((done.Status, done.ResolutionSource, done.GatewayTransactionCode, self.order.PaymentStatus),
                         ("Success", "Manual", None, "Refunded"))
        self.assert_resolution_checks()


class ReturnRefundConfirmationTest(RefundCheckMixin, ReturnTestBase):
    """ReturnService phụ thuộc kết quả Refund: chỉ Refund Success (đã xác nhận) mới hoàn tất yêu cầu trả hàng."""

    def test_cod_return_refund_waits_for_admin_and_failure_allows_new_refund(self):
        rid = self.approved()
        self.assertEqual(self.refund(rid).Status, "Processing")
        [first] = self.refunds()
        self.assertEqual((first.Status, first.CreatedByUserId), ("Pending", self.staff.UserId))
        self.assertIn("chờ Admin khác người tạo xác nhận", self.histories(rid)[-1].InternalNote)
        confirm = lambda: self.svc.confirm_return_refund(self.a(self.staff), rid)  # noqa: E731
        self.assert_code(BusinessRuleError, "return_refund_pending", confirm)
        resolve_refund(self.svc.payments, self.a(self.admin), first.PaymentTransactionId, success=False)
        self.assert_code(BusinessRuleError, "return_refund_failed", confirm)
        self.assertEqual(self.request(rid).Status, "Processing")
        self.assertEqual(self.refund(rid, by=self.admin).Status, "Processing")  # tạo lại (Admin lập)
        second = self.refunds()[-1]
        self.assertEqual((self.request(rid).RefundPaymentTransactionId, second.CreatedByUserId),
                         (second.PaymentTransactionId, self.admin.UserId))
        self.assert_code(BusinessRuleError, "refund_self_confirmation_not_allowed",
                         lambda: resolve_refund(self.svc.payments, self.a(self.admin), second.PaymentTransactionId))
        other_admin = self.f.user("Admin")
        resolve_refund(self.svc.payments, self.a(other_admin), second.PaymentTransactionId)
        done = confirm()
        self.assertEqual((done.Status, self.order.PaymentStatus), ("Completed", "Paid"))  # đơn đã giao giữ Paid
        self.assertEqual([t.Status for t in self.refunds()], ["Failed", "Success"])
        self.assert_resolution_checks()

    def test_return_and_overpayment_limits_hold_with_pending_direct_refunds(self):
        """Hồi quy đợt 5.8 với Refund COD còn Pending: Pending giữ tiền nhưng không chặn hoàn phần thu trùng."""
        self.f.payment(self.order, status="Success", amount="190000.00", gateway_code=None)  # thu trùng
        self.assertEqual(self.refund(self.approved()).Status, "Processing")  # trả điện thoại 100.000 (Pending)
        overpay = self.svc.payments.refund_order(self.a(self.staff), self.order.OrderId)
        self.assertEqual((overpay.Amount, overpay.Status), (Decimal("190000.00"), "Pending"))
        self.assert_code(BusinessRuleError, "refund_pending",
                         lambda: self.svc.payments.refund_order(self.a(self.staff), self.order.OrderId))
        held = sum(t.Amount for t in self.refunds() if t.Status in ("Pending", "Success"))
        self.assertLessEqual(held, Decimal("380000.00"))
        resolve_refund(self.svc.payments, self.a(self.admin), overpay.PaymentTransactionId)
        self.assertEqual(self.order.PaymentStatus, "Paid")  # đơn chưa hủy: hoàn phần thu dư không đổi PaymentStatus
        self.assert_resolution_checks()


class ConstraintDefinitionTest(unittest.TestCase):
    def test_model_constraints_match_the_python_rules_and_migration(self):
        # Migration a9f4c2e7b513 được so khớp DDL với model bằng công cụ phát lại offline (không chạy Alembic).
        self.assertIn("\"ResolvedByUserId\" <> \"CreatedByUserId\"", MANUAL_NOT_BY_CREATOR_SQL)
        self.assertIn("length(btrim(\"EvidenceReference\")) > 0", MANUAL_RESOLUTION_SQL)
        self.assertIn("\"EvidenceReference\" IS NOT NULL", MANUAL_RESOLUTION_SQL)  # NULL không lọt qua CHECK
        self.assertIn("\"Status\" IN ('Success', 'Failed')", RESOLUTION_CONSISTENT_SQL)
        self.assertIn("\"ResolvedByUserId\" IS NULL", GATEWAY_RESOLUTION_SQL)
        names = {c.name for c in PaymentTransaction.__table__.constraints if c.name}
        self.assertTrue({"CK_PaymentTransactions_ResolutionSource_Valid", "CK_PaymentTransactions_Resolution_Consistent",
                         "CK_PaymentTransactions_GatewayResolution_NoManualFields",
                         "CK_PaymentTransactions_ManualResolution_Complete",
                         "CK_PaymentTransactions_ManualResolution_NotByCreator",
                         "FK_PaymentTransactions_CreatedByUserId", "FK_PaymentTransactions_ResolvedByUserId"} <= names)

    def test_python_rules_reject_incomplete_manual_resolution(self):
        creator = uuid.uuid4()
        base = dict(TransactionType="Refund", Status="Success", CreatedByUserId=creator, ResolvedByUserId=uuid.uuid4(),
                    ResolvedAt=object(), ResolutionSource="Manual", EvidenceReference="FT-1", ResolutionNote="ok")
        self.assertEqual(check_violations(SimpleNamespace(**base)), [])
        cases = {
            "ManualResolution_Complete": [{"EvidenceReference": None}, {"ResolutionNote": "  "},
                                          {"ResolvedByUserId": None}],
            "ManualResolution_NotByCreator": [{"ResolvedByUserId": creator}],
            "Resolution_Consistent": [{"Status": "Pending"}, {"ResolvedAt": None}, {"TransactionType": "Payment"}],
            "GatewayResolution_NoManualFields": [{"ResolutionSource": "Gateway"}],
            "ResolutionSource_Valid": [{"ResolutionSource": "Staff"}],
        }
        for name, overrides in cases.items():
            for override in overrides:
                with self.subTest(name=name, override=override):
                    self.assertIn(name, check_violations(SimpleNamespace(**{**base, **override})))
        legacy = dict(TransactionType="Refund", Status="Success", CreatedByUserId=None, ResolvedByUserId=None,
                      ResolvedAt=None, ResolutionSource=None, EvidenceReference=None, ResolutionNote=None)
        self.assertEqual(check_violations(SimpleNamespace(**legacy)), [])  # dữ liệu cũ hợp lệ


if __name__ == "__main__":
    unittest.main()
