"""PaymentWebhookService + PaymentService.apply_bank_transfer (SePay) với fake trong bộ nhớ.

Không chứng minh concurrency thật của PostgreSQL: UNIQUE/khóa dòng được giả lập trong fake.
"""

import json
import unittest
from datetime import timedelta
from decimal import Decimal

from app.integrations.sepay import SePayQrGateway, SePaySettings, SePayWebhookPayload, compute_signature, handle_sepay_webhook
from app.models import Notification, PaymentReconciliation, PaymentTransaction, PaymentWebhookEvent
from app.services import BusinessRuleError
from app.services.payment import BankTransfer

from tests.fakes import NOW, FakeSession, Factory, InMemoryDB, payment_webhook_service, resolve_refund

ACCOUNT = "0123456789"
CODE = "VTPAYABCDEFGHJK"


def payload(sepay_id, amount, *, code=CODE, transfer_type="in", account=ACCOUNT):
    raw = {
        "id": sepay_id, "gateway": "Vietcombank", "transactionDate": "2026-10-09 15:00:00", "accountNumber": account,
        "subAccount": "", "code": code, "content": f"{code} NGUYEN VAN A chuyen tien", "transferType": transfer_type,
        "description": "NGUYEN VAN A chuyen tien", "transferAmount": amount, "accumulated": 0, "referenceCode": "FT1",
    }
    return SePayWebhookPayload.model_validate(raw), raw


class WebhookTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = payment_webhook_service(self.db, self.session)
        self.customer = self.f.user()
        self.staff = self.f.user("Staff")
        self.admin = self.f.user("Admin")
        self.qr = self.f.payment_method("QR")
        self.variant = self.f.variant(stock=3)
        self.order = self.f.order(self.customer, self.qr, total="130000.00", lines=((self.variant, 1),))
        self.tx = self.f.payment(self.order, status="Pending", gateway_code=CODE)
        self.tx.QrData = "https://qr.example.test/img?des=" + CODE

    def receive(self, sepay_id, amount, **kwargs):
        return self.svc.receive_sepay(*payload(sepay_id, amount, **kwargs))

    def events(self):
        return self.db.rows(PaymentWebhookEvent)

    def reconciliations(self, issue_type=None):
        return [r for r in self.db.rows(PaymentReconciliation) if issue_type is None or r.IssueType == issue_type]

    def staff_alerts(self):
        return [n for n in self.db.rows(Notification) if n.UserId in (self.staff.UserId, self.admin.UserId)]


class MatchingTest(WebhookTestBase):
    def test_exact_amount_marks_paid_and_records_event(self):
        self.assertEqual(self.receive(1001, 130000), "paid")
        self.assertEqual((self.tx.Status, self.order.PaymentStatus), ("Success", "Paid"))
        self.assertEqual(self.tx.ResponseData["sepay_id"], 1001)
        self.assertNotIn("content", self.tx.ResponseData)  # không sao chép tên/nội dung chuyển khoản
        [event] = self.events()
        self.assertEqual((event.Status, event.ProcessingNote, event.PaymentTransactionId), ("Processed", "paid", self.tx.PaymentTransactionId))
        self.assertEqual((event.ProviderTransactionId, event.TransferAmount, event.PaymentCode), ("1001", Decimal("130000"), CODE))
        self.assertEqual(event.ProcessedAt, NOW)
        self.assertEqual(self.session.commits, 2)  # bước 1 lưu sự kiện, bước 2 xử lý

    def test_repeated_delivery_is_not_processed_twice(self):
        self.receive(1001, 130000)
        notifications = len(self.db.rows(Notification))
        self.assertEqual(self.receive(1001, 130000), "duplicate")
        self.assertEqual(self.receive(1001, 130000), "duplicate")
        self.assertEqual((len(self.events()), len(self.db.rows(Notification))), (1, notifications))
        self.assertEqual(len([t for t in self.db.rows(PaymentTransaction) if t.Status == "Success"]), 1)

    def test_amount_mismatch_is_reconciled_and_not_paid(self):
        self.assertEqual(self.receive(1001, 100000), "amount_mismatch")
        self.assertEqual((self.tx.Status, self.order.PaymentStatus), ("Pending", "Pending"))
        [record] = self.reconciliations("AmountMismatch")
        self.assertEqual(
            (record.ExpectedAmount, record.ReceivedAmount, record.GatewayTransactionCode, record.Status),
            (Decimal("130000.00"), Decimal("100000"), f"sepay:{ACCOUNT}:1001", "Open"),
        )
        self.assertEqual(record.PaymentWebhookEventId, self.events()[0].PaymentWebhookEventId)
        alerts = len(self.staff_alerts())
        self.assertEqual(self.receive(1001, 100000), "duplicate")  # SePay gửi lại
        self.assertEqual((len(self.reconciliations()), len(self.staff_alerts())), (1, alerts))
        self.assertEqual(self.receive(1002, 120000), "amount_mismatch")  # một chuyển khoản sai khác
        self.assertEqual(len(self.reconciliations("AmountMismatch")), 2)
        self.assertEqual(self.receive(1003, 130000), "paid")  # khách chuyển đúng sau đó
        self.assertEqual(self.order.PaymentStatus, "Paid")

    def test_second_real_transfer_is_recorded_separately(self):
        self.receive(1001, 130000)
        paid_at, response = self.tx.PaidAt, dict(self.tx.ResponseData)
        self.assertEqual(self.receive(1002, 130000), "duplicate_payment")
        self.assertEqual((self.tx.PaidAt, self.tx.ResponseData), (paid_at, response))  # không ghi đè khoản trước
        extra = [t for t in self.db.rows(PaymentTransaction) if t is not self.tx]
        self.assertEqual(len(extra), 1)
        self.assertEqual((extra[0].Status, extra[0].Amount, extra[0].GatewayTransactionCode), ("Success", Decimal("130000"), None))
        [record] = self.reconciliations("DuplicatePayment")
        self.assertEqual((record.PaymentTransactionId, record.GatewayTransactionCode), (extra[0].PaymentTransactionId, f"sepay:{ACCOUNT}:1002"))
        self.assertEqual(self.order.PaymentStatus, "Paid")
        self.assertFalse([t for t in self.db.rows(PaymentTransaction) if t.TransactionType == "Refund"])

    def test_payment_after_expiry_or_cancellation(self):
        self.order.OrderStatus, self.order.PaymentStatus, self.tx.Status = "Cancelled", "Cancelled", "Cancelled"
        self.assertEqual(self.receive(1001, 130000), "payment_after_cancellation")
        self.assertEqual((self.tx.Status, self.order.OrderStatus, self.order.PaymentStatus), ("Success", "Cancelled", "Paid"))
        [record] = self.reconciliations("PaymentAfterCancellation")
        self.assertEqual(record.Status, "Open")
        self.assertEqual(self.variant.StockQuantity, 3)  # không khôi phục đơn/không trừ lại tồn kho

    def test_extra_transfer_after_paid_order_was_cancelled(self):
        self.receive(1001, 130000)
        self.order.OrderStatus = "Cancelled"
        self.assertEqual(self.receive(1002, 130000), "payment_after_cancellation")
        [extra] = [t for t in self.db.rows(PaymentTransaction) if t is not self.tx]
        [record] = self.reconciliations("PaymentAfterCancellation")
        self.assertEqual((record.PaymentTransactionId, record.GatewayTransactionCode), (extra.PaymentTransactionId, f"sepay:{ACCOUNT}:1002"))
        self.assertEqual(self.reconciliations("DuplicatePayment"), [])

    def test_processing_an_already_processed_event_again_is_a_no_op(self):
        self.receive(1001, 130000)
        [event] = self.events()
        before = (event.ProcessingNote, event.ProcessedAt, event.PaymentTransactionId)
        self.assertEqual(self.svc.process_event(event.PaymentWebhookEventId), "duplicate")  # tác vụ nội bộ/đồng thời
        self.assertEqual((event.ProcessingNote, event.ProcessedAt, event.PaymentTransactionId), before)
        self.assertEqual((len(self.db.rows(PaymentTransaction)), self.reconciliations()), (1, []))

    def test_unmatched_transfer_is_recorded_once_per_bank_transaction(self):
        transfer = BankTransfer(reconciliation_key=f"sepay:{ACCOUNT}:4001", payment_code=None, amount=Decimal("1000"),
                                response_data={"provider": "SePay", "sepay_id": 4001})
        for _ in range(2):
            with self.svc.payments.transaction():
                self.assertEqual(self.svc.payments.apply_bank_transfer(transfer), ("unmatched", None))
        self.assertEqual((len(self.reconciliations("UnmatchedPayment")), len(self.staff_alerts())), (1, 2))  # 1 bản ghi, báo Staff+Admin 1 lần

    def test_outgoing_and_other_account_are_ignored(self):
        self.assertEqual(self.receive(2001, 130000, transfer_type="out"), "ignored_transfer_out")
        self.assertEqual(self.receive(2002, 130000, account="9999999999"), "ignored_other_account")
        self.assertTrue(all(e.Status == "Ignored" for e in self.events()))
        self.assertEqual((self.tx.Status, self.reconciliations()), ("Pending", []))

    def test_unidentifiable_order_goes_to_reconciliation(self):
        self.f.payment(self.f.order(self.customer, self.qr), status="Pending", gateway_code="VTPAYDUPLICATE1")
        self.f.payment(self.f.order(self.customer, self.qr), status="Pending", gateway_code="VTPAYDUPLICATE1")
        for sepay_id, code in ((3001, None), (3002, "VTPAYUNKNOWN"), (3003, "VTPAYDUPLICATE1")):
            with self.subTest(code=code):
                self.assertEqual(self.receive(sepay_id, 130000, code=code), "unmatched")
        records = self.reconciliations("UnmatchedPayment")
        self.assertEqual(len(records), 3)
        self.assertTrue(all(r.OrderId is None and r.PaymentTransactionId is None and r.ExpectedAmount is None for r in records))
        self.assertTrue(all(t.Status == "Pending" for t in self.db.rows(PaymentTransaction)))  # không tự chọn đơn
        refs = {n.ReferenceType for n in self.staff_alerts()}
        self.assertEqual(refs, {"PaymentWebhookEvent"})


class DurabilityTest(WebhookTestBase):
    def test_processing_failure_keeps_event_for_retry(self):
        original = self.svc.payments.apply_bank_transfer

        def broken(transfer):
            raise RuntimeError("database unavailable")

        self.svc.payments.apply_bank_transfer = broken
        with self.assertRaises(RuntimeError):
            self.receive(1001, 130000)
        [event] = self.events()
        self.assertEqual((event.Status, event.ProcessedAt), ("Received", None))  # đã lưu bền vững ở bước 1
        self.assertEqual((self.tx.Status, self.order.PaymentStatus), ("Pending", "Pending"))
        self.svc.payments.apply_bank_transfer = original
        self.assertEqual(self.receive(1001, 130000), "paid")  # SePay gửi lại → xử lý tiếp sự kiện đã lưu
        self.assertEqual(len(self.events()), 1)

    def test_unprocessed_events_can_be_reprocessed_by_internal_job(self):
        original = self.svc.payments.apply_bank_transfer
        self.svc.payments.apply_bank_transfer = lambda transfer: (_ for _ in ()).throw(RuntimeError("down"))
        with self.assertRaises(RuntimeError):
            self.receive(1001, 130000)
        self.svc.payments.apply_bank_transfer = original
        self.events()[0].ReceivedAt = NOW - timedelta(minutes=10)
        self.assertEqual(self.svc.process_unprocessed(), 1)
        self.assertEqual(self.order.PaymentStatus, "Paid")
        self.assertEqual(self.svc.process_unprocessed(), 0)

    def test_concurrent_store_uses_existing_event(self):
        """Request khác vừa lưu cùng sự kiện giữa lúc kiểm tra và ghi: UNIQUE (giả lập) → dùng bản ghi đã có."""
        events = self.svc.events
        original_get = events.get_by_key
        calls = {"n": 0}

        def race(*key):
            calls["n"] += 1
            if calls["n"] == 1:
                found = original_get(*key)
                p, raw = payload(1001, 130000)
                events.db.add(PaymentWebhookEvent(Provider="SePay", ProviderTransactionId="1001", AccountNumber=ACCOUNT,
                                                  TransferType="in", TransferAmount=Decimal("130000"), PaymentCode=CODE,
                                                  Payload=raw, Status="Received", ReceivedAt=NOW))
                self.session._snapshot = self.db.snapshot()  # bản ghi do session khác đã commit: rollback không xóa
                return found  # None: lần kiểm tra đầu chưa thấy
            return original_get(*key)

        events.get_by_key = race
        self.assertEqual(self.receive(1001, 130000), "paid")
        self.assertEqual(self.session.rollbacks, 1)  # INSERT vi phạm UNIQUE → rollback → đọc lại bản ghi đã có
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.order.PaymentStatus, "Paid")

    def test_events_cannot_be_deleted_and_must_run_standalone(self):
        self.receive(1001, 130000)
        with self.assertRaises(PermissionError):
            self.svc.events.delete(self.events()[0])
        with self.assertRaises(BusinessRuleError):
            with self.svc.transaction():
                self.receive(1002, 130000)


class EndToEndTest(WebhookTestBase):
    """handle_sepay_webhook (chữ ký thật) → PaymentWebhookService (fake database)."""

    def settings(self):
        return SePaySettings(webhook_secret="test-secret-not-real", account_number=ACCOUNT, bank="Vietcombank",
                             qr_image_url="https://qr.example.test/img", payment_code_prefix="VTPAY", payment_code_length=10)

    def deliver(self, body: bytes, process=None):
        headers = {"X-SePay-Signature": compute_signature("test-secret-not-real", "1700000000", body),
                   "X-SePay-Timestamp": "1700000000"}
        return handle_sepay_webhook(
            body, headers, settings_loader=self.settings, now=lambda: 1700000000,
            process=process or (lambda p, raw, cfg: self.svc.receive_sepay(p, raw)),
        )

    def test_signed_webhook_marks_order_paid_and_acknowledges(self):
        _, raw = payload(1001, 130000)
        body = json.dumps(raw, ensure_ascii=False).encode()
        with self.assertLogs("app.integrations.sepay", level="INFO"):
            self.assertEqual(self.deliver(body), (200, {"success": True}))
            self.assertEqual(self.deliver(body), (200, {"success": True}))  # gửi lại: vẫn xác nhận, không xử lý lại
        self.assertEqual((self.order.PaymentStatus, len(self.events())), ("Paid", 1))

    def test_mismatch_is_acknowledged_after_being_persisted_but_not_paid(self):
        _, raw = payload(1001, 1000)
        with self.assertLogs("app.integrations.sepay", level="INFO"):
            self.assertEqual(self.deliver(json.dumps(raw).encode()), (200, {"success": True}))
        self.assertEqual(self.order.PaymentStatus, "Pending")
        self.assertEqual(len(self.reconciliations("AmountMismatch")), 1)

    def test_database_failure_is_not_acknowledged(self):
        _, raw = payload(1001, 130000)

        def db_down(p, raw_payload, cfg):
            raise ConnectionError("could not connect to server")

        with self.assertLogs("app.integrations.sepay", level="ERROR"):
            self.assertEqual(self.deliver(json.dumps(raw).encode(), db_down), (500, {"success": False}))
        self.assertEqual(self.events(), [])


class SePayQrAndRefundTest(WebhookTestBase):
    def setUp(self) -> None:
        super().setUp()
        cfg = SePaySettings(webhook_secret="s", account_number=ACCOUNT, bank="Vietcombank",
                            qr_image_url="https://qr.example.test/img", payment_code_prefix="VTPAY", payment_code_length=10)
        self.gateway = SePayQrGateway(cfg)
        self.svc = payment_webhook_service(self.db, self.session, gateway=self.gateway)

    def test_qr_created_through_existing_flow_then_paid_by_webhook(self):
        order = self.f.order(self.customer, self.qr, total="250000.00")
        created = self.svc.payments.create_qr_payment(self.f.actor(self.customer), order.OrderId)
        tx = self.db.get(PaymentTransaction, created.PaymentTransactionId)
        self.assertTrue(tx.GatewayTransactionCode.startswith("VTPAY"))
        self.assertIn(f"des={tx.GatewayTransactionCode}", created.QrData)
        self.assertEqual(self.svc.receive_sepay(*payload(5001, 250000, code=tx.GatewayTransactionCode)), "paid")
        self.assertEqual(order.PaymentStatus, "Paid")

    def test_fractional_total_cannot_get_qr(self):
        order = self.f.order(self.customer, self.qr, total="250000.50")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.payments.create_qr_payment(self.f.actor(self.customer), order.OrderId)
        self.assertEqual(ctx.exception.code, "qr_amount_not_supported")
        self.assertFalse([t for t in self.db.rows(PaymentTransaction) if t.OrderId == order.OrderId])

    def test_payment_code_collision_is_rejected(self):
        order = self.f.order(self.customer, self.qr, total="250000.00")
        self.gateway._choice = lambda alphabet: "A"  # ép sinh cùng một mã
        taken = self.f.payment(self.f.order(self.customer, self.qr), status="Pending", gateway_code="VTPAY" + "A" * 10)
        with self.assertRaises(Exception) as ctx:
            self.svc.payments.create_qr_payment(self.f.actor(self.customer), order.OrderId)
        self.assertEqual(ctx.exception.code, "payment_code_collision")
        [mine] = [t for t in self.db.rows(PaymentTransaction) if t.OrderId == order.OrderId]
        self.assertEqual((mine.Status, mine.GatewayTransactionCode, mine.QrData), ("Cancelled", None, None))
        self.assertEqual(taken.Status, "Pending")

    def test_manual_refund_is_recorded_pending_without_calling_any_api(self):
        self.receive(1001, 130000)
        self.order.OrderStatus = "Cancelled"
        refund = self.svc.payments.refund_order(self.f.actor(self.staff), self.order.OrderId)
        self.assertEqual((refund.Status, refund.TransactionType), ("Pending", "Refund"))
        self.assertEqual(self.order.PaymentStatus, "Paid")
        with self.assertRaises(BusinessRuleError) as ctx:  # không tạo yêu cầu hoàn trùng
            self.svc.payments.refund_order(self.f.actor(self.staff), self.order.OrderId)
        self.assertEqual(ctx.exception.code, "refund_pending")
        done = resolve_refund(self.svc.payments, self.f.actor(self.admin), refund.PaymentTransactionId,
                              evidence="FT-REFUND-1")
        self.assertEqual((done.Status, self.order.PaymentStatus), ("Success", "Refunded"))
        self.assertEqual((done.ResolutionSource, done.EvidenceReference, done.GatewayTransactionCode),
                         ("Manual", "FT-REFUND-1", None))  # đợt 5.11: không ghi vào dữ liệu của cổng


if __name__ == "__main__":
    unittest.main()
