"""Vòng chạy chung của tác vụ nội bộ (run_job) và hai tác vụ: hết hạn QR, xử lý lại webhook.

Mỗi bản ghi một transaction: bản ghi lỗi được rollback, đếm và ghi log theo loại; các bản ghi sau vẫn chạy; bản ghi lỗi
giữ nguyên trạng thái để lần chạy sau thử lại. Fake trong bộ nhớ: rollback là khôi phục ảnh chụp của fake, timeout
SET LOCAL chỉ kiểm tra câu lệnh được gửi; không chứng minh hành vi PostgreSQL thật.
"""

import logging
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models import OrderStatusHistory, PaymentTransaction
from app.services import BusinessRuleError, ConflictError, NotFoundError
from app.services.base import BaseService
from app.services.internal_jobs import (
    JOB_LOCK_TIMEOUT_MS,
    JOB_STATEMENT_TIMEOUT_MS,
    JobRun,
    JobSelectionError,
    run_job,
    set_job_timeouts,
)

from tests.fakes import NOW, FakeSession, Factory, InMemoryDB, order_service
from tests.test_payment import PaymentTestBase
from tests.test_payment_webhook import CODE, WebhookTestBase


def database_error(sqlstate="55P03"):
    """Lỗi driver như PostgreSQL trả (hết thời gian chờ khóa), nội dung chứa dữ liệu không được ghi log."""
    orig = Exception("could not obtain lock; params private-value")
    orig.sqlstate = sqlstate
    return OperationalError("UPDATE secret_table SET x = %(p)s", {"p": "private-value"}, orig)


def integrity_error(sqlstate):
    """Vi phạm ràng buộc như PostgreSQL trả; transaction() đổi loại nó nhận ra thành ConflictError/BusinessRuleError."""
    orig = Exception("duplicate key value violates unique constraint; Key (Email)=(private-value)")
    orig.sqlstate = sqlstate
    orig.diag = SimpleNamespace(constraint_name="UQ_Demo")
    return IntegrityError("INSERT INTO secret_table VALUES (%(p)s)", {"p": "private-value"}, orig)


def job_logs(records):
    return [r for r in records if r.name == "app.jobs"]


def failed_records(records):
    return [(r.error_kind, r.error_code) for r in job_logs(records) if getattr(r, "job_event", "") == "record_failed"]


class RunJobTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.service = BaseService(self.session)
        f = Factory(self.db)
        self.rows = {name: f.variant(stock=10) for name in ("a", "b", "c")}
        self.ids = [self.rows[name].ProductVariantId for name in ("a", "b", "c")]

    def handle_failing_on(self, failing_id, error):
        """Đổi dữ liệu của bản ghi rồi lỗi ở bản ghi ``failing_id`` (sau khi đã thay đổi)."""
        def handle(record_id):
            row = self.db.get(type(self.rows["a"]), record_id)
            row.StockQuantity -= 1
            if record_id == failing_id:
                raise error
            return True
        return handle

    def test_a_failing_record_is_rolled_back_and_the_next_records_still_run(self):
        with self.assertLogs("app.jobs", level="INFO") as logs:
            run = run_job(self.service, "demo", select=lambda: self.ids,
                          handle=self.handle_failing_on(self.ids[1], RuntimeError("boom private-value")))
        self.assertEqual(run, JobRun("demo", selected=3, processed=2, skipped=0, failed=1))
        self.assertEqual([self.rows[name].StockQuantity for name in ("a", "b", "c")], [9, 10, 9])  # b rolled back
        self.assertEqual(self.session.rollbacks, 1)
        failed = [r for r in job_logs(logs.records) if getattr(r, "job_event", "") == "record_failed"]
        self.assertEqual([(r.record_id, r.error_kind, r.error_code) for r in failed],
                         [(str(self.ids[1]), "unexpected", "RuntimeError")])
        self.assertNotIn("private-value", "\n".join(logs.output))

    def test_error_kinds_are_told_apart_without_logging_their_text(self):
        errors = [database_error(), BusinessRuleError("Chi tiết nội bộ private-value", code="some_rule"), KeyError("x")]
        handles = iter(errors)

        def handle(record_id):
            raise next(handles)

        with self.assertLogs("app.jobs", level="INFO") as logs:
            run = run_job(self.service, "demo", select=lambda: self.ids, handle=handle)
        self.assertEqual((run.selected, run.processed, run.failed), (3, 0, 3))
        failed = [r for r in job_logs(logs.records) if getattr(r, "job_event", "") == "record_failed"]
        self.assertEqual([(r.error_kind, r.error_code) for r in failed],
                         [("database", "55P03"), ("business", "some_rule"), ("unexpected", "KeyError")])
        for leaked in ("private-value", "secret_table", "Chi tiết nội bộ"):
            self.assertNotIn(leaked, "\n".join(logs.output))

    def test_a_constraint_violation_is_a_database_error_even_once_the_transaction_has_mapped_it(self):
        # Unique and check violations are mapped by transaction() to ConflictError/BusinessRuleError; an unknown one is not.
        errors = iter([integrity_error("23505"), integrity_error("23514"), integrity_error(None)])

        def handle(record_id):
            self.db.get(type(self.rows["a"]), record_id).StockQuantity -= 1
            raise next(errors)

        with self.assertLogs("app.jobs", level="INFO") as logs:
            run = run_job(self.service, "demo", select=lambda: self.ids, handle=handle)
        self.assertEqual(run, JobRun("demo", selected=3, processed=0, skipped=0, failed=3))
        self.assertEqual([self.rows[name].StockQuantity for name in ("a", "b", "c")], [10, 10, 10])  # all rolled back
        self.assertEqual(self.session.rollbacks, 3)
        self.assertEqual(failed_records(logs.records),
                         [("database", "23505"), ("database", "23514"), ("database", "IntegrityError")])
        for leaked in ("private-value", "secret_table", "Email"):
            self.assertNotIn(leaked, "\n".join(logs.output))

    def test_business_errors_stay_business_even_when_raised_from_another_error(self):
        def from_value_error():
            try:
                raise ValueError("internal private-value")
            except ValueError as exc:
                raise BusinessRuleError("Vi phạm quy tắc", code="rule_from_value") from exc

        def conflict():
            raise ConflictError("Đã tồn tại", code="already_there")

        def not_found():
            raise NotFoundError("Không tìm thấy", code="missing_thing")

        actions = iter([from_value_error, conflict, not_found])
        with self.assertLogs("app.jobs", level="INFO") as logs:
            run = run_job(self.service, "demo", select=lambda: self.ids, handle=lambda record_id: next(actions)())
        self.assertEqual((run.selected, run.failed), (3, 3))
        self.assertEqual(failed_records(logs.records),
                         [("business", "rule_from_value"), ("business", "already_there"), ("business", "missing_thing")])

    def test_each_run_logs_its_start_and_end_with_counts_and_duration(self):
        with self.assertLogs("app.jobs", level="INFO") as logs:
            run_job(self.service, "demo", select=lambda: self.ids, handle=lambda record_id: record_id != self.ids[0])
        started, finished = job_logs(logs.records)
        self.assertEqual((started.job_event, started.levelno), ("started", logging.INFO))
        self.assertEqual((finished.job_event, finished.levelno), ("finished", logging.INFO))
        self.assertEqual((finished.selected, finished.processed, finished.skipped, finished.failed), (3, 2, 1, 0))
        self.assertGreaterEqual(finished.duration_ms, 0)

    def test_a_run_with_failures_ends_with_a_warning(self):
        with self.assertLogs("app.jobs", level="INFO") as logs:
            run_job(self.service, "demo", select=lambda: self.ids, handle=self.handle_failing_on(self.ids[0], database_error()))
        finished = job_logs(logs.records)[-1]
        self.assertEqual((finished.job_event, finished.levelno, finished.failed), ("finished", logging.WARNING, 1))

    def test_a_failed_selection_is_logged_and_raised_before_any_record(self):
        handle = mock.Mock()

        def select():
            raise database_error("57014")

        with self.assertLogs("app.jobs", level="INFO") as logs, self.assertRaises(OperationalError):
            run_job(self.service, "demo", select=select, handle=handle)
        handle.assert_not_called()
        self.assertEqual(job_logs(logs.records)[-1].job_event, "selection_failed")
        self.assertIn("sqlstate=57014", logs.output[-1])
        self.assertNotIn("private-value", "\n".join(logs.output))

    def test_an_unexpected_selection_error_becomes_a_job_selection_error_without_its_text(self):
        handle = mock.Mock()

        def select():
            raise KeyError("internal private-value")

        with self.assertLogs("app.jobs", level="INFO") as logs, self.assertRaises(JobSelectionError) as ctx:
            run_job(self.service, "demo", select=select, handle=handle)
        handle.assert_not_called()
        self.assertIsInstance(ctx.exception.__cause__, KeyError)
        self.assertEqual(ctx.exception.code, "job_selection_failed")
        self.assertNotIn("private-value", ctx.exception.message)
        self.assertIn("error=KeyError", logs.output[-1])
        self.assertNotIn("private-value", "\n".join(logs.output))

    def test_a_business_error_at_selection_keeps_its_own_code(self):
        def select():
            raise BusinessRuleError("limit phải lớn hơn 0", code="invalid_limit")

        with self.assertLogs("app.jobs", level="INFO"), self.assertRaises(BusinessRuleError) as ctx:
            run_job(self.service, "demo", select=select, handle=mock.Mock())
        self.assertEqual(ctx.exception.code, "invalid_limit")
        self.assertNotIsInstance(ctx.exception, JobSelectionError)


class JobTimeoutTest(unittest.TestCase):
    def session(self, dialect):
        session = mock.create_autospec(Session, instance=True)
        session.get_bind.return_value.dialect.name = dialect
        return session

    def test_postgresql_transactions_get_job_scoped_lock_and_statement_timeouts(self):
        session = self.session("postgresql")
        set_job_timeouts(session)
        statements = [str(call.args[0]) for call in session.execute.call_args_list]
        self.assertEqual(statements, [f"SET LOCAL lock_timeout = {JOB_LOCK_TIMEOUT_MS}",
                                      f"SET LOCAL statement_timeout = {JOB_STATEMENT_TIMEOUT_MS}"])
        self.assertEqual((JOB_LOCK_TIMEOUT_MS, JOB_STATEMENT_TIMEOUT_MS), (5_000, 30_000))

    def test_other_databases_and_test_fakes_are_left_alone(self):
        sqlite = self.session("sqlite")
        set_job_timeouts(sqlite)
        sqlite.execute.assert_not_called()
        set_job_timeouts(FakeSession(InMemoryDB()))  # the fake raises on any database access

    def test_every_record_transaction_sets_the_timeouts_first(self):
        session = FakeSession(InMemoryDB())
        calls = []
        with mock.patch("app.services.internal_jobs.set_job_timeouts", side_effect=lambda s: calls.append("timeouts")):
            run_job(BaseService(session), "demo", select=lambda: ["r1", "r2"], handle=lambda r: calls.append(r) or True)
        self.assertEqual(calls, ["timeouts", "timeouts", "r1", "timeouts", "r2"])


class ExpiryJobTest(PaymentTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.orders = order_service(self.db, self.session)
        self.coupon = self.f.coupon(self.admin, used=3)
        self.variants, self.expired = [], []
        for minutes in (40, 30, 20):  # oldest first
            variant = self.f.variant(stock=5)
            order = self.f.order(self.customer, self.qr, total="100000.00", lines=((variant, 1),), coupon=self.coupon,
                                 ordered_at=NOW)
            tx = self.db.get(PaymentTransaction,
                             self.svc.create_qr_payment(self.f.actor(self.customer), order.OrderId).PaymentTransactionId)
            order.OrderedAt = NOW - timedelta(minutes=minutes)
            self.variants.append(variant)
            self.expired.append((order, tx))

    def fail_cancelling(self, order, error):
        """Lỗi ở cuối việc hủy ``order`` (sau khi đã hoàn tồn kho, trả coupon, hủy QR, đổi trạng thái, ghi lịch sử)."""
        original = self.orders._notify_status

        def notify(target):
            if target.OrderId == order.OrderId:
                raise error
            return original(target)

        self.orders._notify_status = notify
        return lambda: setattr(self.orders, "_notify_status", original)

    def test_a_failing_order_is_rolled_back_and_the_orders_after_it_are_still_cancelled(self):
        for error in (BusinessRuleError("x", code="some_rule"), database_error()):
            with self.subTest(error=type(error).__name__):
                self.setUp()
                (first, _), (middle, middle_tx), (last, _) = self.expired
                restore = self.fail_cancelling(middle, error)

                run = self.orders.expire_unpaid_qr_orders()
                self.assertEqual(run, JobRun("expire_unpaid_qr_orders", selected=3, processed=2, skipped=0, failed=1))
                self.assertEqual((first.OrderStatus, last.OrderStatus), ("Cancelled", "Cancelled"))
                # Nothing of the failed cancellation is kept.
                self.assertEqual((middle.OrderStatus, middle.PaymentStatus, middle.CancelledAt, middle.CancelReason),
                                 ("Pending", "Pending", None, None))
                self.assertEqual((middle_tx.Status, self.variants[1].StockQuantity), ("Pending", 5))
                self.assertEqual([v.StockQuantity for v in (self.variants[0], self.variants[2])], [6, 6])
                self.assertEqual(self.coupon.UsedCount, 1)  # released by the two cancelled orders only
                # The stored history row is gone (the fake does not reset the in-memory relationship list).
                self.assertEqual(len([h for h in self.db.rows(OrderStatusHistory) if h.OrderId == middle.OrderId]), 0)

                # The failed order is selected again and cancelled once the error is gone.
                restore()
                self.assertEqual(self.orders.expire_unpaid_qr_orders(),
                                 JobRun("expire_unpaid_qr_orders", selected=1, processed=1))
                self.assertEqual((middle.OrderStatus, self.variants[1].StockQuantity, self.coupon.UsedCount),
                                 ("Cancelled", 6, 0))

    def test_the_oldest_orders_go_first_within_the_limit(self):
        run = self.orders.expire_unpaid_qr_orders(limit=2)
        self.assertEqual((run.selected, run.processed), (2, 2))
        self.assertEqual([order.OrderStatus for order, _ in self.expired], ["Cancelled", "Cancelled", "Pending"])
        self.assertEqual(self.orders.expire_unpaid_qr_orders(limit=2), JobRun("expire_unpaid_qr_orders", 1, 1))

    def test_an_order_paid_after_selection_is_counted_as_skipped(self):
        paid_order = self.expired[0][0]
        original = self.orders.orders.get_by_id_for_update

        def lock(order_id):
            locked = original(order_id)
            if order_id == paid_order.OrderId:
                locked.PaymentStatus = "Paid"  # the webhook committed between the selection and the lock
            return locked

        self.orders.orders.get_by_id_for_update = lock
        run = self.orders.expire_unpaid_qr_orders()
        self.assertEqual((run.selected, run.processed, run.skipped, run.failed), (3, 2, 1, 0))
        self.assertEqual(paid_order.OrderStatus, "Pending")

    def test_running_again_changes_nothing(self):
        self.assertEqual(self.orders.expire_unpaid_qr_orders().processed, 3)
        self.assertEqual(self.orders.expire_unpaid_qr_orders(), JobRun("expire_unpaid_qr_orders"))
        self.assertEqual(([v.StockQuantity for v in self.variants], self.coupon.UsedCount), ([6, 6, 6], 0))


class WebhookRetryJobTest(WebhookTestBase):
    CODE2 = "VTPAYZYXWVUTSRQ"

    def setUp(self) -> None:
        super().setUp()
        self.order2 = self.f.order(self.customer, self.qr, total="130000.00", lines=((self.variant, 1),))
        self.tx2 = self.f.payment(self.order2, status="Pending", gateway_code=self.CODE2)
        # Both first deliveries fail after being stored: the events wait as Received.
        original = self.svc.payments.apply_bank_transfer
        self.svc.payments.apply_bank_transfer = lambda transfer: (_ for _ in ()).throw(RuntimeError("down"))
        for sepay_id, code in ((1001, CODE), (1002, self.CODE2)):
            with self.assertRaises(RuntimeError):
                self.receive(sepay_id, 130000, code=code)
        self.svc.payments.apply_bank_transfer = original
        self.first, self.second = sorted(self.events(), key=lambda e: e.ProviderTransactionId)
        self.first.ReceivedAt = NOW - timedelta(minutes=20)  # oldest first
        self.second.ReceivedAt = NOW - timedelta(minutes=10)

    def fail_for(self, code):
        original = self.svc.payments.apply_bank_transfer

        def apply(transfer):
            if transfer.payment_code == code:
                raise database_error()
            return original(transfer)

        self.svc.payments.apply_bank_transfer = apply
        return lambda: setattr(self.svc.payments, "apply_bank_transfer", original)

    def test_a_failing_event_stays_received_for_the_next_run_and_the_next_events_are_processed(self):
        restore = self.fail_for(CODE)
        with self.assertLogs("app.jobs", level="INFO") as logs:
            run = self.svc.process_unprocessed()
        self.assertEqual(run, JobRun("process_unprocessed_webhooks", selected=2, processed=1, skipped=0, failed=1))
        self.assertEqual((self.first.Status, self.first.ProcessedAt, self.first.ProcessingNote), ("Received", None, None))
        self.assertEqual((self.tx.Status, self.order.PaymentStatus), ("Pending", "Pending"))
        self.assertEqual((self.second.Status, self.order2.PaymentStatus), ("Processed", "Paid"))
        failed = [r for r in job_logs(logs.records) if getattr(r, "job_event", "") == "record_failed"]
        self.assertEqual([(r.record_id, r.error_kind) for r in failed], [(str(self.first.PaymentWebhookEventId), "database")])
        for leaked in (CODE, "130000", "0123456789", "NGUYEN VAN A", "private-value"):
            self.assertNotIn(leaked, "\n".join(logs.output))

        restore()
        self.assertEqual(self.svc.process_unprocessed(), JobRun("process_unprocessed_webhooks", selected=1, processed=1))
        self.assertEqual((self.first.Status, self.order.PaymentStatus), ("Processed", "Paid"))

    def test_the_oldest_events_go_first_within_the_limit_and_recent_ones_wait(self):
        self.second.ReceivedAt = NOW - timedelta(minutes=2)  # newer than older_than (5 minutes)
        self.assertEqual(self.svc.process_unprocessed(limit=1), JobRun("process_unprocessed_webhooks", 1, 1))
        self.assertEqual((self.first.Status, self.second.Status), ("Processed", "Received"))
        self.assertEqual(self.svc.process_unprocessed(), JobRun("process_unprocessed_webhooks"))
        self.assertEqual(self.svc.process_unprocessed(older_than=timedelta(minutes=1)).processed, 1)

    def test_an_event_processed_meanwhile_is_skipped_not_processed_twice(self):
        original = self.svc.events.list_unprocessed_ids

        def listed(**kwargs):
            ids = original(**kwargs)
            self.svc.process_event(self.first.PaymentWebhookEventId)  # SePay's retry got there first
            return ids

        self.svc.events.list_unprocessed_ids = listed
        run = self.svc.process_unprocessed()
        self.assertEqual((run.selected, run.processed, run.skipped, run.failed), (2, 1, 1, 0))
        self.assertEqual(len([t for t in self.db.rows(PaymentTransaction) if t.OrderId == self.order.OrderId]), 1)
