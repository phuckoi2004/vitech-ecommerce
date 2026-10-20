"""Opt-in PostgreSQL QR expiry job and late payment checks over HTTP and real contention (payment tests, group D).

Uses the protected, fixture-owned database from test_postgres_integration (its setup and teardown truncate the
dedicated test database), the fake SePay settings and helpers of groups A to C, and the coupon helper of
test_postgres_coupon; SePay is never contacted. Each test creates its own variant, coupon and orders and asserts the
exact stock and coupon usage. The expiry job selects every overdue order in the database, so each test starts and
ends with no expirable order and checks the expirable set before every job run. The only SQL write is AGE_ORDER_SQL,
which backdates OrderedAt of a Pending, unpaid order the test created (always before paying or cancelling it).
Blocking is confirmed with pg_blocking_pids through the Concurrency helper of group C; final state is read in
separate transactions after every thread finished and every lock was released.
"""

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.integrations.sepay import SUCCESS_BODY
from app.services.internal_jobs import JOB_LOCK_TIMEOUT_MS, JOB_STATEMENT_TIMEOUT_MS, JobRun
from app.services.order import QR_EXPIRED_REASON, QR_PAYMENT_TTL, OrderService
from app.services.promotion import CouponService
from tests.postgres_safety import POSTGRES_TESTS_ENABLED

from tests.test_postgres_coupon import create_coupon
from tests.test_postgres_integration import (
    CRON_SECRET,
    fill_cart,
    methods as methods,
    new_customer,
    ok,
    pg as pg,
    stock_of,
    stocked_variant,
    team as team,
)
from tests.test_postgres_payment_concurrency import WAIT, Concurrency, deliver, pause_after_apply, watch_processing
from tests.test_postgres_qr_webhook import (
    notified,
    order_state,
    payments,
    post_webhook,
    reconciliations,
    request_qr,
    rows,
    sepay as sepay,
    staff_ids,
    transfer,
)
from tests.test_postgres_webhook_retry import InjectedFailure, counts, event_detail, notification_count

pytestmark = pytest.mark.skipif(
    not POSTGRES_TESTS_ENABLED,
    reason="opt-in QR expiry tests require the protected TEST_DATABASE_URL",
)

EXPIRY_JOB = "expire_unpaid_qr_orders"
EXPIRY_ENDPOINT = "/internal/orders/expire-unpaid-qr"
EXPIRY_NOTE = "Hệ thống: hết hạn thanh toán QR"
LATE_PAYMENT_TITLE = "Đã nhận thanh toán"
MANUAL_REFUND_TITLE = "Cần hoàn tiền thủ công"
STOCK_SQL = 'select "StockQuantity" from "ProductVariants" where "ProductVariantId" = :id'
# The one write these tests make directly: backdate a Pending, unpaid order they created.
AGE_ORDER_SQL = ('UPDATE "Orders" SET "OrderedAt" = :ordered_at '
                 'WHERE "OrderId" = :order_id AND "OrderStatus" = \'Pending\' AND "PaymentStatus" = \'Pending\'')


@dataclass
class Sale:
    customer_id: str
    headers: dict
    order: dict
    qr: dict | None

    @property
    def id(self):
        return self.order["OrderId"]


# ------------------------------------------------------------------------------------------------- arrangement


def place_order(pg, methods, variant, *, payment, quantity=1, coupon=None):
    customer, headers = new_customer(pg)
    fill_cart(pg, headers, variant, quantity)
    payload = {"ShippingMethodId": methods["shipping"], "PaymentMethodId": methods[payment],
               "ReceiverName": "Khách", "ReceiverPhone": "0900000000", "ShippingAddress": "1 Đường A"}
    if coupon is not None:
        payload["CouponCode"] = coupon["Code"]
    order = ok(pg.client.post("/orders", headers=headers, json=payload), 201)
    assert (order["OrderStatus"], order["PaymentStatus"], order["CouponId"]) == (
        "Pending", "Pending", coupon["CouponId"] if coupon else None)
    return customer["id"], headers, order


def expiring_sale(pg, methods, variant, *, quantity=1, coupon=None):
    """A BANK_QR order with its QR request (requested while the order is new: the deadline is checked)."""
    customer_id, headers, order = place_order(pg, methods, variant, payment="qr", quantity=quantity, coupon=coupon)
    return Sale(customer_id, headers, order, request_qr(pg, headers, order))


def cod_sale(pg, methods, variant):
    return Sale(*place_order(pg, methods, variant, payment="cod"), None)


def age_order(pg, sale, minutes):
    """Backdate OrderedAt of a Pending, unpaid order this test created (time computed here, like the job's clock)."""
    ordered_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with pg.engine.begin() as connection:
        changed = connection.execute(text(AGE_ORDER_SQL), {"ordered_at": ordered_at, "order_id": sale.id}).rowcount
    assert changed == 1


def run_expiry_job(pg, status=200, **params):
    response = pg.client.post(EXPIRY_ENDPOINT, headers={"X-Internal-Secret": CRON_SECRET}, params=params)
    assert response.status_code == status, response.text
    return response.json()


def expiry_job(engine):
    """The expiry job in this thread's own session on the protected test engine, as the internal endpoint runs it."""
    with Session(engine, autoflush=False) as session:
        return OrderService(session).expire_unpaid_qr_orders()


def late_transfer(sale, amount=None):
    """The SePay transfer paying ``sale``'s QR request (or ``amount``), as a body and its raw bytes."""
    body = transfer(sale.qr["TransferContent"], sale.qr["TransferAmount"] if amount is None else amount)
    return body, json.dumps(body).encode("utf-8")


# ------------------------------------------------------------------------------------------------- read-back


def expirable_orders(pg):
    """Ids of the orders the expiry job would select now (its own conditions, read in a separate transaction)."""
    cutoff = datetime.now(timezone.utc) - QR_PAYMENT_TTL
    return {str(row["OrderId"]) for row in rows(
        pg, 'select o."OrderId" from "Orders" o join "PaymentMethods" m on m."PaymentMethodId" = o."PaymentMethodId" '
            'where o."OrderStatus" = \'Pending\' and o."PaymentStatus" in (\'Pending\', \'Failed\') '
            'and m."Code" <> \'COD\' and o."OrderedAt" <= :cutoff', cutoff=cutoff)}


def order_row(pg, sale):
    [row] = rows(pg, 'select "OrderStatus", "PaymentStatus", "CancelReason", "CancelledAt" from "Orders" '
                     'where "OrderId" = :id', id=sale.id)
    return row


def cancellations(pg, sale):
    return rows(pg, 'select "OldStatus", "NewStatus", "ChangedByUserId", "Note" from "OrderStatusHistories" '
                    'where "OrderId" = :id and "NewStatus" = \'Cancelled\'', id=sale.id)


def status_notifications(pg, sale):
    """Order status notifications about ``sale`` ("Cập nhật đơn hàng", type Order)."""
    return pg.scalar('select count(*) from "Notifications" where "NotificationType" = \'Order\' '
                     'and "ReferenceType" = \'Order\' and "ReferenceId" = :id', id=sale.id)


def used_count(pg, coupon):
    return pg.scalar('select "UsedCount" from "Coupons" where "CouponId" = :id', id=coupon["CouponId"])


def awaiting_refund(pg, team):
    page = ok(pg.client.get("/admin/refunds/awaiting-orders", headers=team["staff"], params={"page_size": 100}))
    return {order["OrderId"] for order in page["Items"]}


def assert_cancelled_by_expiry(pg, sale, payment_status="Cancelled"):
    """Cancelled once by the job: reason, history and the QR request kept for reconciliation."""
    row = order_row(pg, sale)
    assert (row["OrderStatus"], row["PaymentStatus"], row["CancelReason"]) == (
        "Cancelled", payment_status, QR_EXPIRED_REASON)
    assert row["CancelledAt"] is not None
    assert cancellations(pg, sale) == [{"OldStatus": "Pending", "NewStatus": "Cancelled", "ChangedByUserId": None,
                                        "Note": EXPIRY_NOTE}]


def assert_qr_request(pg, sale, status):
    [payment] = payments(pg, sale.order)
    assert (str(payment["PaymentTransactionId"]), payment["Status"], payment["GatewayTransactionCode"],
            payment["QrData"]) == (sale.qr["PaymentTransactionId"], status, sale.qr["TransferContent"],
                                   sale.qr["QrData"])
    return payment


# ------------------------------------------------------------------------------------------------- hooks


def watch_expiry(monkeypatch, run):
    """Record each thread's backend pid before _expire_one locks the order, and whether it cancelled it."""
    original = OrderService._expire_one

    def expire_one(service, order_id):
        run.record_pid(service.session)
        cancelled = original(service, order_id)
        run.outcomes.setdefault(threading.current_thread().name, []).append(cancelled)
        return cancelled

    monkeypatch.setattr(OrderService, "_expire_one", expire_one)


def pause_after_cancel(monkeypatch, thread_name, holding, release):
    """In ``thread_name``, stop once the order was cancelled: order, variant, coupon and payment rows stay locked."""
    original = OrderService._cancel

    def cancel(service, order, **kwargs):
        original(service, order, **kwargs)
        if threading.current_thread().name == thread_name and not holding.is_set():
            holding.set()
            assert release.wait(WAIT), f"{thread_name} was not released"

    monkeypatch.setattr(OrderService, "_cancel", cancel)


# ------------------------------------------------------------------------------------------------- D1


def test_expiry_job_cancels_only_expired_unpaid_qr_orders_and_restores_everything_once(pg, sepay, team, methods):
    assert expirable_orders(pg) == set()
    variant = stocked_variant(pg, team, quantity=10)
    coupon = create_coupon(pg, team, usage_limit=1)
    oldest = expiring_sale(pg, methods, variant, quantity=2, coupon=coupon)
    older = expiring_sale(pg, methods, variant)
    fresh = expiring_sale(pg, methods, variant)
    cod = cod_sale(pg, methods, variant)
    paid = expiring_sale(pg, methods, variant)
    cancelled = expiring_sale(pg, methods, variant)
    for sale, minutes in ((oldest, 40), (older, 30), (cod, 60), (paid, 60), (cancelled, 60)):
        age_order(pg, sale, minutes)
    # Old, yet not eligible: paid after its deadline (before any job run), and cancelled by its customer.
    response = post_webhook(pg, late_transfer(paid)[0])
    assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    ok(pg.client.post(f"/orders/{cancelled.id}/cancel", headers=cancelled.headers, json={"CancelReason": "Đổi ý"}))
    reserved = stock_of(pg, variant)
    assert used_count(pg, coupon) == 1
    notices = {sale.id: status_notifications(pg, sale) for sale in (oldest, older)}

    # Oldest first within the limit.
    assert expirable_orders(pg) == {oldest.id, older.id}
    assert run_expiry_job(pg, limit=1) == counts(processed=1, selected=1)
    assert_cancelled_by_expiry(pg, oldest)
    assert_qr_request(pg, oldest, "Cancelled")
    assert (stock_of(pg, variant), used_count(pg, coupon)) == (reserved + 2, 0)
    assert order_state(pg, older.order) == ("Pending", "Pending")

    assert expirable_orders(pg) == {older.id}
    assert run_expiry_job(pg) == counts(processed=1, selected=1)
    assert_cancelled_by_expiry(pg, older)
    assert_qr_request(pg, older, "Cancelled")
    assert expirable_orders(pg) == set()
    assert run_expiry_job(pg) == counts()

    assert (stock_of(pg, variant), used_count(pg, coupon)) == (reserved + 3, 0)  # each order restored once
    assert [status_notifications(pg, sale) - notices[sale.id] for sale in (oldest, older)] == [1, 1]
    assert order_state(pg, fresh.order) == ("Pending", "Pending")
    assert_qr_request(pg, fresh, "Pending")
    assert order_state(pg, cod.order) == ("Pending", "Pending")
    assert order_state(pg, paid.order) == ("Pending", "Paid")
    assert_qr_request(pg, paid, "Success")
    customer_cancel = order_row(pg, cancelled)
    assert (customer_cancel["OrderStatus"], customer_cancel["CancelReason"]) == ("Cancelled", "Đổi ý")

    # The new order would become overdue later: its customer cancels it, leaving no expirable order behind.
    ok(pg.client.post(f"/orders/{fresh.id}/cancel", headers=fresh.headers, json={"CancelReason": "Dọn dẹp"}))
    assert expirable_orders(pg) == set()


# ------------------------------------------------------------------------------------------------- D2


def test_expiry_job_rolls_back_a_failed_cancellation_and_cancels_the_others(pg, sepay, monkeypatch, caplog, team,
                                                                           methods):
    assert expirable_orders(pg) == set()
    variant = stocked_variant(pg, team, quantity=10)
    coupon = create_coupon(pg, team, usage_limit=3)
    first, middle, last = sales = [expiring_sale(pg, methods, variant, coupon=coupon) for _ in range(3)]
    for sale, minutes in zip(sales, (40, 30, 20)):
        age_order(pg, sale, minutes)
    reserved = stock_of(pg, variant)
    assert used_count(pg, coupon) == 3
    middle_notices = status_notifications(pg, middle)

    failing, seen = [True], []
    original = OrderService._notify_status

    def notify_then_fail(service, order):
        original(service, order)
        if failing and str(order.OrderId) == middle.id:
            service.session.flush()

            def scalar(sql, **params):
                return service.session.execute(text(sql), params).scalar()

            seen.append({
                "order": tuple(service.session.execute(text(
                    'select "OrderStatus", "PaymentStatus" from "Orders" where "OrderId" = :id'),
                    {"id": middle.id}).one()),
                "payment": scalar('select "Status" from "PaymentTransactions" where "OrderId" = :id '
                                  'and "TransactionType" = \'Payment\'', id=middle.id),
                "stock": scalar(STOCK_SQL, id=variant["variant"]["ProductVariantId"]),
                "used": scalar('select "UsedCount" from "Coupons" where "CouponId" = :id', id=coupon["CouponId"]),
                "cancellations": scalar('select count(*) from "OrderStatusHistories" where "OrderId" = :id '
                                        'and "NewStatus" = \'Cancelled\'', id=middle.id),
            })
            raise InjectedFailure("injected after the cancellation was flushed")

    monkeypatch.setattr(OrderService, "_notify_status", notify_then_fail)

    assert expirable_orders(pg) == {sale.id for sale in sales}
    caplog.clear()
    with caplog.at_level("INFO", logger="app.jobs"):
        assert run_expiry_job(pg, 500) == counts(processed=2, selected=3, failed=1)
    # Inside the failing transaction the middle order had been cancelled and its stock and coupon restored...
    assert seen == [{"order": ("Cancelled", "Cancelled"), "payment": "Cancelled", "stock": reserved + 2, "used": 1,
                     "cancellations": 1}]
    # ...yet nothing of it was committed, while the orders before and after it were cancelled.
    row = order_row(pg, middle)
    assert (row["OrderStatus"], row["PaymentStatus"], row["CancelReason"], row["CancelledAt"]) == (
        "Pending", "Pending", None, None)
    assert_qr_request(pg, middle, "Pending")
    assert cancellations(pg, middle) == []
    assert status_notifications(pg, middle) == middle_notices
    for sale in (first, last):
        assert_cancelled_by_expiry(pg, sale)
    assert (stock_of(pg, variant), used_count(pg, coupon)) == (reserved + 2, 1)
    [failed] = [r for r in caplog.records if r.name == "app.jobs" and getattr(r, "job_event", None) == "record_failed"]
    assert (failed.job, failed.record_id, failed.error_kind, failed.error_code) == (
        EXPIRY_JOB, middle.id, "unexpected", "InjectedFailure")

    failing.clear()
    assert expirable_orders(pg) == {middle.id}
    assert run_expiry_job(pg) == counts(processed=1, selected=1)
    assert_cancelled_by_expiry(pg, middle)
    assert (stock_of(pg, variant), used_count(pg, coupon)) == (reserved + 3, 0)
    assert expirable_orders(pg) == set()


# ------------------------------------------------------------------------------------------------- D5


def test_payment_after_the_expiry_job_cancelled_the_order_is_kept_for_a_manual_refund(pg, sepay, team, methods):
    assert expirable_orders(pg) == set()
    variant = stocked_variant(pg, team, quantity=5)
    coupon = create_coupon(pg, team, usage_limit=1)
    sale = expiring_sale(pg, methods, variant, coupon=coupon)
    age_order(pg, sale, 30)
    assert expirable_orders(pg) == {sale.id}
    assert run_expiry_job(pg) == counts(processed=1, selected=1)
    assert_cancelled_by_expiry(pg, sale)
    restored = (stock_of(pg, variant), used_count(pg, coupon))
    amount = sale.qr["TransferAmount"]

    body, _ = late_transfer(sale)
    for _ in range(2):  # delivered, then resent by SePay
        response = post_webhook(pg, body)
        assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    event = event_detail(pg, body)
    assert (event["Status"], event["ProcessingNote"], str(event["PaymentTransactionId"])) == (
        "Processed", "payment_after_cancellation", sale.qr["PaymentTransactionId"])
    # The money is recorded on the cancelled QR request; the order is not revived but is now Paid for the refund.
    payment = assert_qr_request(pg, sale, "Success")
    assert payment["PaidAt"] is not None
    assert_cancelled_by_expiry(pg, sale, payment_status="Paid")
    [issue] = reconciliations(pg, body)
    assert (issue["IssueType"], issue["Status"], str(issue["OrderId"]), str(issue["PaymentTransactionId"]),
            issue["PaymentWebhookEventId"]) == (
        "PaymentAfterCancellation", "Open", sale.id, sale.qr["PaymentTransactionId"], event["PaymentWebhookEventId"])
    assert (Decimal(issue["ExpectedAmount"]), Decimal(issue["ReceivedAmount"])) == (Decimal(amount), Decimal(amount))
    assert notification_count(pg, sale.order, LATE_PAYMENT_TITLE) == 1
    assert notified(pg, "Order", sale.id, LATE_PAYMENT_TITLE) == {sale.customer_id}
    assert notification_count(pg, sale.order, MANUAL_REFUND_TITLE) == len(staff_ids(team))
    assert notified(pg, "Order", sale.id, MANUAL_REFUND_TITLE) == staff_ids(team)
    assert (stock_of(pg, variant), used_count(pg, coupon)) == restored  # restored once, by the job
    assert sale.id in awaiting_refund(pg, team)
    refused = pg.client.post(f"/orders/{sale.id}/cancel", headers=sale.headers, json={"CancelReason": "x"})
    assert refused.status_code == 400 and refused.json()["code"] == "order_not_cancellable"

    # Another bank transfer carrying the same code: its own payment and reconciliation (one per transfer).
    second, _ = late_transfer(sale)
    response = post_webhook(pg, second)
    assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    second_event = event_detail(pg, second)
    assert (second_event["Status"], second_event["ProcessingNote"]) == ("Processed", "payment_after_cancellation")
    extra_id = str(second_event["PaymentTransactionId"])
    recorded = {str(p["PaymentTransactionId"]): p for p in payments(pg, sale.order)}
    assert set(recorded) == {sale.qr["PaymentTransactionId"], extra_id}
    assert recorded[extra_id]["Status"] == "Success" and Decimal(recorded[extra_id]["Amount"]) == Decimal(amount)
    [second_issue] = reconciliations(pg, second)
    assert (second_issue["IssueType"], str(second_issue["PaymentTransactionId"])) == (
        "PaymentAfterCancellation", extra_id)
    assert notification_count(pg, sale.order, MANUAL_REFUND_TITLE) == 2 * len(staff_ids(team))
    assert notification_count(pg, sale.order, LATE_PAYMENT_TITLE) == 2
    assert order_state(pg, sale.order) == ("Cancelled", "Paid")
    assert (stock_of(pg, variant), used_count(pg, coupon)) == restored
    assert expirable_orders(pg) == set()


def test_payment_after_the_deadline_but_before_the_expiry_job_is_accepted_and_skipped_by_the_job(
        pg, sepay, team, methods):
    assert expirable_orders(pg) == set()
    variant = stocked_variant(pg, team, quantity=5)
    coupon = create_coupon(pg, team, usage_limit=1)
    sale = expiring_sale(pg, methods, variant, coupon=coupon)
    age_order(pg, sale, 30)
    reserved = stock_of(pg, variant)
    assert used_count(pg, coupon) == 1
    assert expirable_orders(pg) == {sale.id}

    body, _ = late_transfer(sale)
    response = post_webhook(pg, body)
    assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    event = event_detail(pg, body)
    assert (event["Status"], event["ProcessingNote"]) == ("Processed", "paid")
    assert_qr_request(pg, sale, "Success")
    assert order_state(pg, sale.order) == ("Pending", "Paid")
    assert reconciliations(pg, body) == []

    # The job leaves a paid order alone: its stock and coupon stay with it.
    assert expirable_orders(pg) == set()
    assert run_expiry_job(pg) == counts()
    assert (stock_of(pg, variant), used_count(pg, coupon)) == (reserved, 1)
    assert cancellations(pg, sale) == []
    assert sale.id not in awaiting_refund(pg, team)
    confirmed = ok(pg.client.post(f"/admin/orders/{sale.id}/status", headers=team["staff"],
                                  json={"OrderStatus": "Confirmed"}))
    assert (confirmed["OrderStatus"], confirmed["PaymentStatus"]) == ("Confirmed", "Paid")


def test_a_wrong_amount_after_cancellation_is_reconciled_without_marking_the_order_paid(pg, sepay, team, methods):
    assert expirable_orders(pg) == set()
    variant = stocked_variant(pg, team, quantity=5)
    coupon = create_coupon(pg, team, usage_limit=1)
    sale = expiring_sale(pg, methods, variant, coupon=coupon)
    age_order(pg, sale, 30)
    assert expirable_orders(pg) == {sale.id}
    assert run_expiry_job(pg) == counts(processed=1, selected=1)
    restored = (stock_of(pg, variant), used_count(pg, coupon))
    received = sale.qr["TransferAmount"] - 1000

    body, _ = late_transfer(sale, received)
    response = post_webhook(pg, body)
    assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    event = event_detail(pg, body)
    assert (event["Status"], event["ProcessingNote"], str(event["PaymentTransactionId"])) == (
        "Processed", "amount_mismatch", sale.qr["PaymentTransactionId"])
    payment = assert_qr_request(pg, sale, "Cancelled")
    assert payment["PaidAt"] is None
    assert_cancelled_by_expiry(pg, sale)  # still Cancelled / Cancelled: the wrong amount does not pay it
    [issue] = reconciliations(pg, body)
    assert (issue["IssueType"], issue["Status"], str(issue["OrderId"]), str(issue["PaymentTransactionId"])) == (
        "AmountMismatch", "Open", sale.id, sale.qr["PaymentTransactionId"])
    assert (Decimal(issue["ExpectedAmount"]), Decimal(issue["ReceivedAmount"])) == (
        Decimal(sale.order["TotalAmount"]), Decimal(received))
    assert notification_count(pg, sale.order, "Thanh toán sai số tiền") == len(staff_ids(team))
    assert notified(pg, "Order", sale.id, "Thanh toán sai số tiền") == staff_ids(team)
    assert notification_count(pg, sale.order, LATE_PAYMENT_TITLE) == 0
    assert (stock_of(pg, variant), used_count(pg, coupon)) == restored
    assert sale.id not in awaiting_refund(pg, team)
    assert expirable_orders(pg) == set()


# ------------------------------------------------------------------------------------------------- D2/D4


def test_expiry_job_lock_timeout_on_the_coupon_rolls_back_the_restored_stock(pg, sepay, monkeypatch, caplog, team,
                                                                            methods):
    assert expirable_orders(pg) == set()
    variant = stocked_variant(pg, team, quantity=5)
    variant_id = variant["variant"]["ProductVariantId"]
    coupon = create_coupon(pg, team, usage_limit=1)
    sale = expiring_sale(pg, methods, variant, coupon=coupon)
    age_order(pg, sale, 30)
    reserved = stock_of(pg, variant)
    assert used_count(pg, coupon) == 1
    assert expirable_orders(pg) == {sale.id}

    with Concurrency(pg) as run:
        armed, inside, committed = [True], [], []
        original_expire, original_release = OrderService._expire_one, CouponService.release_coupon_usage

        def expire_one(service, order_id):
            if armed and str(order_id) == sale.id:
                run.record_pid(service.session, name="job")
            return original_expire(service, order_id)

        def release_coupon_usage(service, coupon_id):
            if armed and str(coupon_id) == coupon["CouponId"]:
                # change_stock has already updated and flushed the stock in this transaction.
                inside.append(service.session.execute(text(STOCK_SQL), {"id": variant_id}).scalar())
            return original_release(service, coupon_id)

        monkeypatch.setattr(OrderService, "_expire_one", expire_one)
        monkeypatch.setattr(CouponService, "release_coupon_usage", release_coupon_usage)
        holder = run.hold_row_lock('select 1 from "Coupons" where "CouponId" = :id for update', id=coupon["CouponId"])

        def observe():
            run.wait_blocked("job", by=holder)  # the job waits on the coupon row the holder locked
            committed.append(run.monitor.execute(text(STOCK_SQL), {"id": variant_id}).scalar())
            return True

        run.start("observer", observe)
        caplog.clear()
        started = time.monotonic()
        with caplog.at_level("INFO", logger="app.jobs"):
            assert run_expiry_job(pg, 500) == counts(selected=1, failed=1)
        elapsed = time.monotonic() - started
        armed.clear()
        assert run.join("observer") == []
        assert run.results["observer"] == ("ok", True)

        # Read while the coupon is still locked: the whole cancellation was rolled back.
        row = order_row(pg, sale)
        assert (row["OrderStatus"], row["PaymentStatus"], row["CancelledAt"]) == ("Pending", "Pending", None)
        assert_qr_request(pg, sale, "Pending")
        assert cancellations(pg, sale) == []
        assert stock_of(pg, variant) == reserved
        run.release_row_lock()

    assert inside == [reserved + 1]  # restored inside the job transaction...
    assert committed == [reserved]  # ...never committed, not even while the job was waiting
    assert JOB_LOCK_TIMEOUT_MS / 1000 <= elapsed < JOB_STATEMENT_TIMEOUT_MS / 1000
    assert [state for states in run.sqlstates.values() for state in states] == ["55P03"]
    [failed] = [r for r in caplog.records if r.name == "app.jobs" and getattr(r, "job_event", None) == "record_failed"]
    assert (failed.job, failed.record_id, failed.error_kind, failed.error_code) == (
        EXPIRY_JOB, sale.id, "database", "55P03")
    assert used_count(pg, coupon) == 1

    assert expirable_orders(pg) == {sale.id}
    assert run_expiry_job(pg) == counts(processed=1, selected=1)
    assert_cancelled_by_expiry(pg, sale)
    assert (stock_of(pg, variant), used_count(pg, coupon)) == (reserved + 1, 0)
    assert expirable_orders(pg) == set()


# ------------------------------------------------------------------------------------------------- D3


def test_two_expiry_jobs_on_one_order_cancel_it_once_and_skip_it_once(pg, sepay, monkeypatch, team, methods):
    assert expirable_orders(pg) == set()
    variant = stocked_variant(pg, team, quantity=5)
    coupon = create_coupon(pg, team, usage_limit=1)
    sale = expiring_sale(pg, methods, variant, coupon=coupon)
    age_order(pg, sale, 30)
    reserved = stock_of(pg, variant)
    notices = status_notifications(pg, sale)
    assert expirable_orders(pg) == {sale.id}

    with Concurrency(pg) as run:
        holding, release = run.event(), run.event()
        watch_expiry(monkeypatch, run)
        pause_after_cancel(monkeypatch, "first", holding, release)

        run.start("first", lambda: expiry_job(pg.engine))
        assert holding.wait(WAIT), "the first job did not cancel the order"
        run.start("second", lambda: expiry_job(pg.engine))  # selects the same order (selection takes no lock)
        run.wait_blocked("second", by="first")  # its SELECT ... FOR UPDATE waits on the order row
        release.set()
        assert run.join() == []

    assert run.results == {"first": ("ok", JobRun(EXPIRY_JOB, selected=1, processed=1)),
                           "second": ("ok", JobRun(EXPIRY_JOB, selected=1, skipped=1))}
    assert run.outcomes == {"first": [True], "second": [False]}
    assert run.sqlstates == {}  # neither a lock timeout nor a deadlock
    assert_cancelled_by_expiry(pg, sale)
    assert_qr_request(pg, sale, "Cancelled")
    assert (stock_of(pg, variant), used_count(pg, coupon)) == (reserved + 1, 0)
    assert status_notifications(pg, sale) == notices + 1
    assert expirable_orders(pg) == set()


# ------------------------------------------------------------------------------------------------- D6


def test_a_webhook_waiting_on_an_order_the_expiry_job_is_cancelling_records_a_payment_after_cancellation(
        pg, sepay, monkeypatch, team, methods):
    assert expirable_orders(pg) == set()
    variant = stocked_variant(pg, team, quantity=5)
    coupon = create_coupon(pg, team, usage_limit=1)
    sale = expiring_sale(pg, methods, variant, coupon=coupon)
    age_order(pg, sale, 30)
    reserved = stock_of(pg, variant)
    body, raw = late_transfer(sale)
    assert expirable_orders(pg) == {sale.id}

    with Concurrency(pg) as run:
        holding, release = run.event(), run.event()
        watch_expiry(monkeypatch, run)
        watch_processing(monkeypatch, run)
        pause_after_cancel(monkeypatch, "job", holding, release)

        run.start("job", lambda: expiry_job(pg.engine))
        assert holding.wait(WAIT), "the job did not cancel the order"
        run.start("webhook", lambda: deliver(raw))  # stores the event, then waits to lock the order
        run.wait_blocked("webhook", by="job")
        release.set()
        assert run.join() == []

    assert run.results == {"job": ("ok", JobRun(EXPIRY_JOB, selected=1, processed=1)),
                           "webhook": ("ok", (200, SUCCESS_BODY))}
    assert run.outcomes == {"job": [True], "webhook": ["payment_after_cancellation"]}
    assert run.sqlstates == {}
    assert_cancelled_by_expiry(pg, sale, payment_status="Paid")
    payment = assert_qr_request(pg, sale, "Success")
    assert payment["PaidAt"] is not None
    [issue] = reconciliations(pg, body)
    assert (issue["IssueType"], str(issue["PaymentTransactionId"])) == (
        "PaymentAfterCancellation", sale.qr["PaymentTransactionId"])
    assert (stock_of(pg, variant), used_count(pg, coupon)) == (reserved + 1, 0)  # restored once, by the job
    assert notification_count(pg, sale.order, MANUAL_REFUND_TITLE) == len(staff_ids(team))
    assert notified(pg, "Order", sale.id, MANUAL_REFUND_TITLE) == staff_ids(team)
    assert notification_count(pg, sale.order, LATE_PAYMENT_TITLE) == 1
    assert expirable_orders(pg) == set()


def test_the_expiry_job_waiting_on_an_order_being_paid_skips_it(pg, sepay, monkeypatch, team, methods):
    assert expirable_orders(pg) == set()
    variant = stocked_variant(pg, team, quantity=5)
    coupon = create_coupon(pg, team, usage_limit=1)
    sale = expiring_sale(pg, methods, variant, coupon=coupon)
    age_order(pg, sale, 30)
    reserved = stock_of(pg, variant)
    notices = status_notifications(pg, sale)
    body, raw = late_transfer(sale)
    assert expirable_orders(pg) == {sale.id}

    with Concurrency(pg) as run:
        holding, release = run.event(), run.event()
        watch_expiry(monkeypatch, run)
        watch_processing(monkeypatch, run)
        pause_after_apply(monkeypatch, "webhook", holding, release)

        run.start("webhook", lambda: deliver(raw))
        assert holding.wait(WAIT), "the webhook did not apply the transfer"
        run.start("job", lambda: expiry_job(pg.engine))  # still selects it: the payment is not committed yet
        run.wait_blocked("job", by="webhook")  # its SELECT ... FOR UPDATE waits on the order row
        release.set()
        assert run.join() == []

    assert run.results == {"webhook": ("ok", (200, SUCCESS_BODY)),
                           "job": ("ok", JobRun(EXPIRY_JOB, selected=1, skipped=1))}
    assert run.outcomes == {"webhook": ["paid"], "job": [False]}
    assert run.sqlstates == {}
    assert order_state(pg, sale.order) == ("Pending", "Paid")
    assert_qr_request(pg, sale, "Success")
    assert reconciliations(pg, body) == []
    assert cancellations(pg, sale) == []
    assert status_notifications(pg, sale) == notices
    assert (stock_of(pg, variant), used_count(pg, coupon)) == (reserved, 1)  # stock and coupon stay with the order
    assert expirable_orders(pg) == set()
