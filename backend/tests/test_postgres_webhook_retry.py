"""Opt-in PostgreSQL SePay webhook retry and idempotency over HTTP with real commits (payment tests, group B).

Uses the protected, fixture-owned database from test_postgres_integration (its setup and teardown truncate the
dedicated test database) and the fake SePay settings and helpers of test_postgres_qr_webhook. SePay is never
contacted. Processing failures are injected by wrapping PaymentService.apply_bank_transfer: the real method runs,
its changes are flushed into the processing transaction, then an error is raised, so the rollback is a real one.
Every read-back opens its own connection and transaction, so it only sees committed data. The only SQL write is
AGE_EVENT_SQL, which backdates ReceivedAt of an event this test created and left Received.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.integrations.sepay import FAILURE_BODY, SUCCESS_BODY
from app.repositories import PaymentWebhookEventRepository
from app.services.payment import PaymentService
from app.services.payment_webhook import PaymentWebhookService
from tests.postgres_safety import POSTGRES_TESTS_ENABLED

from tests.test_postgres_integration import (
    CRON_SECRET,
    methods as methods,
    pg as pg,
    team as team,
)
from tests.test_postgres_qr_webhook import (
    ACCOUNT,
    SECRET,
    item as item,
    notified,
    order_state,
    payments,
    post_webhook,
    qr_order,
    reconciliations,
    request_qr,
    rows,
    sepay as sepay,
    staff_ids,
    transfer,
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_TESTS_ENABLED,
    reason="opt-in webhook retry tests require the protected TEST_DATABASE_URL",
)

RETRY_JOB = "/internal/payment-webhooks/process"
PAID_TITLE = "Thanh toán thành công"
# The one write these tests make directly: backdate an event they created and that is still Received.
AGE_EVENT_SQL = ('UPDATE "PaymentWebhookEvents" SET "ReceivedAt" = :received_at '
                 'WHERE "PaymentWebhookEventId" = :event_id AND "Status" = \'Received\'')


class InjectedFailure(RuntimeError):
    """Raised after the payment changes of one transfer were flushed into the processing transaction."""


class Failures:
    """Wraps PaymentService.apply_bank_transfer for the transfers whose payment code is listed.

    The real method runs, the session is flushed, the state visible inside that transaction is recorded in
    ``seen``, then InjectedFailure is raised. ``times`` limits the number of failures (None: every time).
    """

    def __init__(self, monkeypatch):
        self.codes, self.remaining, self.seen = set(), None, []
        original = PaymentService.apply_bank_transfer
        failures = self

        def apply(service, transfer):
            outcome, transaction_id = original(service, transfer)
            if transfer.payment_code in failures.codes and failures.remaining != 0:
                service.session.flush()
                failures.seen.append(_in_transaction(service.session, transfer, transaction_id))
                if failures.remaining is not None:
                    failures.remaining -= 1
                raise InjectedFailure("injected after the payment changes were flushed")
            return outcome, transaction_id

        monkeypatch.setattr(PaymentService, "apply_bank_transfer", apply)

    def fail(self, *codes, times=None):
        self.codes, self.remaining = set(codes), times

    def stop(self):
        self.codes = set()


def _in_transaction(session, transfer, transaction_id):
    """What the failing processing transaction itself sees after its flush (it is rolled back right after)."""
    def scalar(sql, **params):
        return session.execute(text(sql), params).scalar()

    return {
        "payment": scalar('select "Status" from "PaymentTransactions" where "PaymentTransactionId" = :id',
                          id=transaction_id),
        "order_payment": scalar('select o."PaymentStatus" from "Orders" o join "PaymentTransactions" t '
                                'using ("OrderId") where t."PaymentTransactionId" = :id', id=transaction_id),
        "reconciliations": scalar('select count(*) from "PaymentReconciliations" where "GatewayTransactionCode" = :key',
                                  key=transfer.reconciliation_key),
        "notifications": scalar('select count(*) from "Notifications" n join "PaymentTransactions" t '
                                'on n."ReferenceId" = t."OrderId" where t."PaymentTransactionId" = :id '
                                'and n."NotificationType" = \'Payment\' and n."ReferenceType" = \'Order\'',
                                id=transaction_id),
    }


@pytest.fixture
def failures(monkeypatch):
    return Failures(monkeypatch)


# ------------------------------------------------------------------------------------------------- helpers


def qr_sale(pg, methods, item):
    """A customer's BANK_QR order with its QR request. Returns (customer id, order, QR response)."""
    customer_id, headers, order = qr_order(pg, methods, item)
    return customer_id, order, request_qr(pg, headers, order)


def event_detail(pg, body):
    """The stored event of a SePay transfer, read in a separate transaction (committed data only)."""
    [event] = rows(pg, 'select "PaymentWebhookEventId", "Status", "ProcessingNote", "PaymentTransactionId", '
                       '"ProcessedAt", "TransferAmount", "Payload" from "PaymentWebhookEvents" '
                       'where "Provider" = \'SePay\' and "AccountNumber" = :account and "ProviderTransactionId" = :id',
                   account=body["accountNumber"], id=str(body["id"]))
    return event


def assert_received_untouched(pg, body):
    """Stored and committed, still waiting: nothing of a processing attempt was kept."""
    event = event_detail(pg, body)
    assert (event["Status"], event["ProcessedAt"], event["ProcessingNote"], event["PaymentTransactionId"]) == (
        "Received", None, None, None)
    assert event["Payload"] == body
    return event


def notification_count(pg, order, title=None):
    sql = ('select count(*) from "Notifications" where "NotificationType" = \'Payment\' '
           'and "ReferenceType" = \'Order\' and "ReferenceId" = :id')
    if title is None:
        return pg.scalar(sql, id=order["OrderId"])
    return pg.scalar(sql + ' and "Title" = :title', id=order["OrderId"], title=title)


def received_events(pg):
    return pg.scalar('select count(*) from "PaymentWebhookEvents" where "Status" = \'Received\'')


def age(pg, event, minutes):
    """Backdate ReceivedAt of one Received event created by this test (time computed here, like the job's clock)."""
    received_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with pg.engine.begin() as connection:
        changed = connection.execute(text(AGE_EVENT_SQL), {"received_at": received_at,
                                                           "event_id": event["PaymentWebhookEventId"]}).rowcount
    assert changed == 1


def stored_but_unprocessed(pg, failures, *bodies):
    """First deliveries whose processing fails: each answers 500 and leaves its event Received."""
    failures.fail(*(body["code"] for body in bodies))
    for body in bodies:
        response = post_webhook(pg, body)
        assert (response.status_code, response.json()) == (500, FAILURE_BODY)
    failures.stop()
    return [assert_received_untouched(pg, body) for body in bodies]


def run_job(pg, status=200, **params):
    response = pg.client.post(RETRY_JOB, headers={"X-Internal-Secret": CRON_SECRET}, params=params)
    assert response.status_code == status, response.text
    return response.json()


def counts(processed=0, selected=0, skipped=0, failed=0):
    return {"Processed": processed, "Selected": selected, "Skipped": skipped, "Failed": failed}


def assert_paid_once(pg, order, body, qr):
    """The final, committed state of an order paid by one transfer, however many times it was delivered."""
    event = event_detail(pg, body)
    assert (event["Status"], event["ProcessingNote"], str(event["PaymentTransactionId"])) == (
        "Processed", "paid", qr["PaymentTransactionId"])
    assert event["ProcessedAt"] is not None
    [payment] = payments(pg, order)
    assert payment["Status"] == "Success" and payment["PaidAt"] is not None
    assert order_state(pg, order) == ("Pending", "Paid")
    assert notification_count(pg, order, PAID_TITLE) == 1
    assert reconciliations(pg, body) == []
    return event, payment


# ------------------------------------------------------------------------------------------------- resends


def test_the_same_sepay_transaction_delivered_twice_is_applied_once(pg, sepay, methods, item):
    customer_id, order, qr = qr_sale(pg, methods, item)
    body = transfer(qr["TransferContent"], qr["TransferAmount"])
    response = post_webhook(pg, body)
    assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    first_event, first_payment = assert_paid_once(pg, order, body, qr)

    # SePay resends the same transaction (new timestamp and signature each time).
    for _ in range(2):
        response = post_webhook(pg, body)
        assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    # A resend with the same SePay id but another amount: the stored event wins, nothing is reprocessed.
    altered = {**body, "transferAmount": body["transferAmount"] - 1000}
    response = post_webhook(pg, altered)
    assert (response.status_code, response.json()) == (200, SUCCESS_BODY)

    event, payment = assert_paid_once(pg, order, body, qr)
    assert (event["ProcessedAt"], event["Payload"], Decimal(event["TransferAmount"])) == (
        first_event["ProcessedAt"], body, Decimal(body["transferAmount"]))
    assert payment["PaidAt"] == first_payment["PaidAt"]
    assert notified(pg, "Order", order["OrderId"], PAID_TITLE) == {customer_id}


def test_a_second_distinct_transfer_for_a_paid_order_is_recorded_once_as_a_duplicate_payment(
        pg, sepay, team, methods, item):
    _, order, qr = qr_sale(pg, methods, item)
    code, amount = qr["TransferContent"], qr["TransferAmount"]
    assert post_webhook(pg, transfer(code, amount)).status_code == 200
    second = transfer(code, amount)  # another bank transaction carrying the same payment code

    for _ in range(2):  # delivered, then resent by SePay
        response = post_webhook(pg, second)
        assert (response.status_code, response.json()) == (200, SUCCESS_BODY)

    event = event_detail(pg, second)
    assert (event["Status"], event["ProcessingNote"]) == ("Processed", "duplicate_payment")
    extra_id = str(event["PaymentTransactionId"])
    assert extra_id != qr["PaymentTransactionId"]
    recorded = {str(p["PaymentTransactionId"]): p for p in payments(pg, order)}
    assert set(recorded) == {qr["PaymentTransactionId"], extra_id}
    assert all(p["Status"] == "Success" and p["PaidAt"] is not None for p in recorded.values())
    assert Decimal(recorded[extra_id]["Amount"]) == Decimal(amount)
    [issue] = reconciliations(pg, second)
    assert (issue["IssueType"], issue["Status"], str(issue["OrderId"]), str(issue["PaymentTransactionId"]),
            issue["PaymentWebhookEventId"]) == (
        "DuplicatePayment", "Open", order["OrderId"], extra_id, event["PaymentWebhookEventId"])
    assert (Decimal(issue["ExpectedAmount"]), Decimal(issue["ReceivedAmount"])) == (Decimal(amount), Decimal(amount))
    assert notification_count(pg, order, "Thanh toán trùng") == len(staff_ids(team))
    assert notified(pg, "Order", order["OrderId"], "Thanh toán trùng") == staff_ids(team)
    assert notification_count(pg, order, PAID_TITLE) == 1
    assert order_state(pg, order) == ("Pending", "Paid")


# ------------------------------------------------------------------------------------------------- failed processing


def test_a_failed_first_processing_is_rolled_back_and_a_sepay_resend_completes_it_once(pg, sepay, failures,
                                                                                         methods, item):
    _, order, qr = qr_sale(pg, methods, item)
    body = transfer(qr["TransferContent"], qr["TransferAmount"])
    failures.fail(body["code"], times=1)

    response = post_webhook(pg, body)
    assert (response.status_code, response.json()) == (500, FAILURE_BODY)
    # Inside the processing transaction the payment had been applied and flushed...
    assert failures.seen == [{"payment": "Success", "order_payment": "Paid", "reconciliations": 0,
                              "notifications": 1}]
    # ...yet another transaction sees the committed event only: the processing was rolled back.
    assert_received_untouched(pg, body)
    [payment] = payments(pg, order)
    assert (payment["Status"], payment["PaidAt"]) == ("Pending", None)
    assert order_state(pg, order) == ("Pending", "Pending")
    assert notification_count(pg, order) == 0
    assert reconciliations(pg, body) == []

    for _ in range(2):  # SePay's resend completes it; a further resend changes nothing
        response = post_webhook(pg, body)
        assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    assert len(failures.seen) == 1
    assert_paid_once(pg, order, body, qr)
    assert len(rows(pg, 'select 1 from "PaymentWebhookEvents" where "ProviderTransactionId" = :id',
                    id=str(body["id"]))) == 1


def test_a_mismatch_whose_processing_failed_is_reconciled_exactly_once_after_retry(pg, sepay, failures, team,
                                                                                    methods, item):
    _, order, qr = qr_sale(pg, methods, item)
    received = qr["TransferAmount"] - 1000
    body = transfer(qr["TransferContent"], received)
    failures.fail(body["code"], times=1)

    response = post_webhook(pg, body)
    assert (response.status_code, response.json()) == (500, FAILURE_BODY)
    # The reconciliation and the Staff/Admin alerts were written inside the failing transaction...
    assert failures.seen == [{"payment": "Pending", "order_payment": "Pending", "reconciliations": 1,
                              "notifications": len(staff_ids(team))}]
    # ...and none of them was committed.
    assert_received_untouched(pg, body)
    assert reconciliations(pg, body) == []
    assert notification_count(pg, order) == 0

    for _ in range(2):  # SePay's resend reconciles it; a further resend changes nothing
        response = post_webhook(pg, body)
        assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    assert len(failures.seen) == 1
    event = event_detail(pg, body)
    assert (event["Status"], event["ProcessingNote"], str(event["PaymentTransactionId"])) == (
        "Processed", "amount_mismatch", qr["PaymentTransactionId"])
    [issue] = reconciliations(pg, body)
    assert (issue["IssueType"], issue["Status"], issue["PaymentWebhookEventId"]) == (
        "AmountMismatch", "Open", event["PaymentWebhookEventId"])
    assert (Decimal(issue["ExpectedAmount"]), Decimal(issue["ReceivedAmount"])) == (
        Decimal(order["TotalAmount"]), Decimal(received))
    assert notification_count(pg, order, "Thanh toán sai số tiền") == len(staff_ids(team))
    assert notification_count(pg, order) == len(staff_ids(team))
    [payment] = payments(pg, order)
    assert (payment["Status"], payment["PaidAt"]) == ("Pending", None)
    assert order_state(pg, order) == ("Pending", "Pending")


# ------------------------------------------------------------------------------------------------- retry job


def test_the_retry_job_completes_aged_received_events_once_and_leaves_recent_ones(pg, sepay, monkeypatch, failures,
                                                                                  methods, item):
    assert received_events(pg) == 0  # the job's counts below cover this test's events only
    sales = [qr_sale(pg, methods, item) for _ in range(3)]
    bodies = [transfer(qr["TransferContent"], qr["TransferAmount"]) for _, _, qr in sales]
    oldest, older, recent = stored_but_unprocessed(pg, failures, *bodies)
    age(pg, oldest, 40)
    age(pg, older, 30)

    assert pg.client.post(RETRY_JOB).status_code == 401
    assert pg.client.post(RETRY_JOB, headers={"X-Internal-Secret": "wrong-secret"}).status_code == 401
    monkeypatch.delenv("SEPAY_WEBHOOK_SECRET")  # the secret is checked first, then the SePay configuration
    assert run_job(pg, 503) == {"detail": "Webhook thanh toán chưa được cấu hình"}
    monkeypatch.setenv("SEPAY_WEBHOOK_SECRET", SECRET)
    for body in bodies:
        assert_received_untouched(pg, body)

    # Oldest first within the limit; events newer than older_than wait.
    assert run_job(pg, limit=1, older_than_minutes=5) == counts(processed=1, selected=1)
    assert_paid_once(pg, sales[0][1], bodies[0], sales[0][2])
    assert_received_untouched(pg, bodies[1])
    assert run_job(pg, older_than_minutes=5) == counts(processed=1, selected=1)
    assert_paid_once(pg, sales[1][1], bodies[1], sales[1][2])
    assert_received_untouched(pg, bodies[2])
    assert run_job(pg, older_than_minutes=5) == counts()

    # Three minutes old: still too recent for older_than=5, old enough for older_than=1.
    age(pg, recent, 3)
    assert run_job(pg, older_than_minutes=5) == counts()
    assert_received_untouched(pg, bodies[2])
    assert run_job(pg, older_than_minutes=1) == counts(processed=1, selected=1)
    for (_, order, qr), body in zip(sales, bodies):
        assert_paid_once(pg, order, body, qr)
    assert received_events(pg) == 0


def test_a_failing_event_in_the_retry_job_is_rolled_back_counted_and_retried_next_run(pg, sepay, failures, caplog,
                                                                                      methods, item):
    assert received_events(pg) == 0
    (_, first_order, first_qr), (_, second_order, second_qr) = (qr_sale(pg, methods, item) for _ in range(2))
    first = transfer(first_qr["TransferContent"], first_qr["TransferAmount"])
    second = transfer(second_qr["TransferContent"], second_qr["TransferAmount"])
    failing, other = stored_but_unprocessed(pg, failures, first, second)
    age(pg, failing, 20)
    age(pg, other, 10)

    failures.fail(first["code"])
    attempts = len(failures.seen)
    caplog.clear()  # only this job run's records below
    with caplog.at_level("INFO", logger="app.jobs"):
        assert run_job(pg, 500, older_than_minutes=5) == counts(processed=1, selected=2, failed=1)
    assert failures.seen[attempts:] == [{"payment": "Success", "order_payment": "Paid", "reconciliations": 0,
                                         "notifications": 1}]  # applied and flushed in the job, then rolled back
    assert_received_untouched(pg, first)
    [payment] = payments(pg, first_order)
    assert (payment["Status"], payment["PaidAt"]) == ("Pending", None)
    assert order_state(pg, first_order) == ("Pending", "Pending")
    assert notification_count(pg, first_order) == 0
    assert_paid_once(pg, second_order, second, second_qr)

    job_records = [r for r in caplog.records if r.name == "app.jobs"]
    [failed] = [r for r in job_records if getattr(r, "job_event", None) == "record_failed"]
    assert (failed.job, failed.record_id, failed.error_kind, failed.error_code) == (
        "process_unprocessed_webhooks", str(failing["PaymentWebhookEventId"]), "unexpected", "InjectedFailure")
    [finished] = [r for r in job_records if getattr(r, "job_event", None) == "finished"]
    assert (finished.levelname, finished.selected, finished.processed, finished.failed) == ("WARNING", 2, 1, 1)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for private in (first["code"], second["code"], ACCOUNT, SECRET, CRON_SECRET):
        assert private not in logged

    failures.stop()
    assert run_job(pg, older_than_minutes=5) == counts(processed=1, selected=1)
    assert_paid_once(pg, first_order, first, first_qr)
    assert received_events(pg) == 0


def test_an_event_completed_by_a_resend_after_selection_is_skipped_not_paid_twice(pg, sepay, monkeypatch, failures,
                                                                                  methods, item):
    assert received_events(pg) == 0
    customer_id, order, qr = qr_sale(pg, methods, item)
    body = transfer(qr["TransferContent"], qr["TransferAmount"])
    [event] = stored_but_unprocessed(pg, failures, body)
    age(pg, event, 10)
    completed = []
    original = PaymentWebhookEventRepository.list_unprocessed_ids

    def selected_then_resent(repository, **kwargs):
        ids = original(repository, **kwargs)
        if event["PaymentWebhookEventId"] in ids and not completed:
            # SePay's resend gets there between the job's selection and its processing (own session, committed).
            with Session(pg.engine, autoflush=False) as session:
                completed.append(PaymentWebhookService(session, account_number=ACCOUNT)
                                 .process_event(event["PaymentWebhookEventId"]))
        return ids

    monkeypatch.setattr(PaymentWebhookEventRepository, "list_unprocessed_ids", selected_then_resent)
    assert run_job(pg, older_than_minutes=5) == counts(selected=1, skipped=1)
    assert completed == ["paid"]
    assert_paid_once(pg, order, body, qr)
    assert notified(pg, "Order", order["OrderId"], PAID_TITLE) == {customer_id}
    assert received_events(pg) == 0
