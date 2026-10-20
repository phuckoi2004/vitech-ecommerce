"""Opt-in PostgreSQL concurrency and timeout checks for SePay webhooks and the retry job (payment tests, group C).

Uses the protected, fixture-owned database from test_postgres_integration (its setup and teardown truncate the
dedicated test database) and the fake SePay settings and helpers of groups A and B; SePay is never contacted.
Contention is real: worker threads use their own sessions, and a test only proceeds once PostgreSQL reports, through
pg_blocking_pids on a separate monitor connection, that the waiting backend is blocked by the expected one. Backend
pids come from pg_backend_pid() on the test's own sessions. Every wait is bounded; Concurrency.close releases events
and row locks and joins the threads; it never cancels a backend: a thread still running is reported and fails the test.
Final state is read in separate transactions after every thread finished. No SQL here writes data.
"""

import json
import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.integrations.sepay import FAILURE_BODY, SUCCESS_BODY, SePaySettings, handle_sepay_webhook
from app.repositories import PaymentWebhookEventRepository
from app.routers.webhooks import _process_with_database_session
from app.services.base import BaseService
from app.services.internal_jobs import JOB_LOCK_TIMEOUT_MS, JOB_STATEMENT_TIMEOUT_MS, JobRun, run_job
from app.services.payment import PaymentService
from app.services.payment_webhook import PaymentWebhookService
from tests.postgres_safety import POSTGRES_TESTS_ENABLED

from tests.test_postgres_integration import (
    methods as methods,
    pg as pg,
    team as team,
)
from tests.test_postgres_qr_webhook import (
    ACCOUNT,
    item as item,
    notified,
    order_state,
    payments,
    post_webhook,
    sepay as sepay,
    signed_headers,
    transfer,
)
from tests.test_postgres_webhook_retry import (
    PAID_TITLE,
    InjectedFailure,
    age,
    assert_paid_once,
    assert_received_untouched,
    counts,
    failures as failures,
    notification_count,
    qr_sale,
    received_events,
    stored_but_unprocessed,
)
from tests.test_postgres_webhook_retry import run_job as call_retry_job

pytestmark = pytest.mark.skipif(
    not POSTGRES_TESTS_ENABLED,
    reason="opt-in payment concurrency tests require the protected TEST_DATABASE_URL",
)

WAIT = 15  # seconds: upper bound of every synchronisation wait in this module
POLL = 0.05
RETRY_JOB = "process_unprocessed_webhooks"
SHOW_TIMEOUTS = "select current_setting('lock_timeout'), current_setting('statement_timeout')"


def shown(milliseconds):
    """How PostgreSQL prints a millisecond setting such as lock_timeout (largest unit that divides it)."""
    for unit, size in (("h", 3_600_000), ("min", 60_000), ("s", 1000)):
        if milliseconds % size == 0:
            return f"{milliseconds // size}{unit}"
    return f"{milliseconds}ms"


def backend_pid(executor):
    return executor.execute(text("select pg_backend_pid()")).scalar()


class Concurrency:
    """Threads, events, row locks and backend pids of one test; ``close`` always releases and joins them.

    ``results[name]`` is ("ok", value) or ("error", exception type, SQLSTATE). ``sqlstates[thread]`` lists the
    SQLSTATE of every database error raised on the test engine, from any thread, except failed pool pre-pings.
    """

    def __init__(self, pg):
        self.pg = pg
        self.monitor = pg.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        self.pids, self.results, self.outcomes, self.sqlstates = {}, {}, {}, {}
        self._events, self._threads = [], {}
        self._holder = self._holder_transaction = None
        self._listener = self._on_error
        event.listen(pg.engine, "handle_error", self._listener)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def _on_error(self, context):
        if context.is_pre_ping:
            # A pooled connection the pooler dropped while idle, found on checkout and replaced by the pool:
            # not an error of the statements under test.
            return
        sqlstate = getattr(context.original_exception, "sqlstate", None)
        self.sqlstates.setdefault(threading.current_thread().name, []).append(sqlstate)

    def event(self):
        flag = threading.Event()
        self._events.append(flag)
        return flag

    def start(self, name, call):
        def run():
            try:
                self.results[name] = ("ok", call())
            except Exception as error:  # reported by type and SQLSTATE only, never by message
                self.results[name] = ("error", type(error).__name__,
                                      getattr(getattr(error, "orig", None), "sqlstate", None))

        thread = threading.Thread(target=run, name=name, daemon=True)
        self._threads[name] = thread
        thread.start()

    def record_pid(self, session, name=None):
        """Backend pid of the connection ``session`` is using now (first value per name is kept)."""
        name = name or threading.current_thread().name
        if name not in self.pids:
            self.pids[name] = backend_pid(session)

    def wait_for_pid(self, name):
        deadline = time.monotonic() + WAIT
        while name not in self.pids:
            assert time.monotonic() < deadline, f"no backend pid recorded for {name}"
            time.sleep(POLL)
        return self.pids[name]

    def wait_blocked(self, waiter, *, by):
        """Until PostgreSQL reports that ``waiter``'s backend is blocked by ``by`` (a name or a pid)."""
        waiter_pid = self.wait_for_pid(waiter)
        blocker_pid = by if isinstance(by, int) else self.wait_for_pid(by)
        deadline = time.monotonic() + WAIT
        while not self.monitor.execute(text("select :blocker = any(pg_blocking_pids(:waiter))"),
                                       {"blocker": blocker_pid, "waiter": waiter_pid}).scalar():
            assert time.monotonic() < deadline, f"{waiter} was not blocked by {by}"
            time.sleep(POLL)
        return True

    def hold_row_lock(self, sql, **params):
        """Another session locks a row (SELECT ... FOR UPDATE) and keeps its transaction open."""
        self._holder = self.pg.engine.connect()
        self._holder_transaction = self._holder.begin()
        self.pids["holder"] = backend_pid(self._holder)
        assert self._holder.execute(text(sql), params).scalar() == 1
        return self.pids["holder"]

    def release_row_lock(self):
        if self._holder is not None:
            try:
                self._holder_transaction.rollback()
            finally:
                self._holder.close()
                self._holder = self._holder_transaction = None

    def join(self, *names):
        for name in names or tuple(self._threads):
            self._threads[name].join(WAIT)
        return [name for name, thread in self._threads.items() if thread.is_alive()]

    def close(self):
        """Release the events and the row lock, join the threads, detach the listener and close the monitor.

        No backend is ever cancelled. A thread still running after the bounded join, or a row lock that could not be
        released, fails the test with the thread names, their recorded backend pids and the cleanup state, so that a
        person decides how to handle those sessions before PostgreSQL tests run again.
        """
        for flag in self._events:
            flag.set()
        lock_error = None
        try:
            try:
                self.release_row_lock()
            except Exception as error:  # still join the threads, then report: never claim the lock was released
                lock_error = error
            stuck = self.join()
        finally:
            event.remove(self.pg.engine, "handle_error", self._listener)
            self.monitor.close()
        if stuck or lock_error is not None:
            threads = ", ".join(f"{name} (backend pid {self.pids.get(name, 'not recorded')})" for name in stuck)
            lock = "released" if lock_error is None else f"release failed ({type(lock_error).__name__}), state unknown"
            raise AssertionError(
                f"cleanup incomplete: threads still running after a {WAIT}s join: {threads or 'none'}; "
                f"row lock: {lock}; events set, listener removed, monitor closed. No backend was cancelled: their "
                "sessions and statements may still be active. Stop and decide how to handle them before running "
                "PostgreSQL tests again.")


# ------------------------------------------------------------------------------------------------- hooks


def watch_processing(monkeypatch, run):
    """Record each thread's backend pid before process_event locks the event, and its outcome."""
    original = PaymentWebhookService.process_event

    def process_event(service, event_id):
        run.record_pid(service.session)
        outcome = original(service, event_id)
        run.outcomes.setdefault(threading.current_thread().name, []).append(outcome)
        return outcome

    monkeypatch.setattr(PaymentWebhookService, "process_event", process_event)


def pause_after_apply(monkeypatch, thread_name, holding, release):
    """In ``thread_name``, stop once the transfer was applied: the event, order and payment rows stay locked."""
    original = PaymentService.apply_bank_transfer

    def apply_bank_transfer(service, transfer):
        result = original(service, transfer)
        if threading.current_thread().name == thread_name and not holding.is_set():
            holding.set()
            assert release.wait(WAIT), f"{thread_name} was not released"
        return result

    monkeypatch.setattr(PaymentService, "apply_bank_transfer", apply_bank_transfer)


def retry_job(engine):
    """The retry job in this thread's own session on the protected test engine, as the internal endpoint runs it."""
    with Session(engine, autoflush=False) as session:
        return PaymentWebhookService(session, account_number=ACCOUNT).process_unprocessed(
            older_than=timedelta(minutes=5))


def deliver(raw):
    """One SePay delivery through the production handler and session factory, outside the HTTP client."""
    return handle_sepay_webhook(raw, signed_headers(raw), settings_loader=SePaySettings.from_env,
                                process=_process_with_database_session, now=time.time)


def aged_received_event(pg, failures, methods, item):
    """An order with a QR request whose webhook was stored, failed processing and is now 10 minutes old."""
    assert received_events(pg) == 0  # job counts below cover this test's event only
    customer_id, order, qr = qr_sale(pg, methods, item)
    body = transfer(qr["TransferContent"], qr["TransferAmount"])
    [stored] = stored_but_unprocessed(pg, failures, body)
    age(pg, stored, 10)
    return customer_id, order, qr, body


# ------------------------------------------------------------------------------------------------- C1


def test_job_transactions_set_local_timeouts_that_end_with_each_transaction(pg):
    expected = (shown(JOB_LOCK_TIMEOUT_MS), shown(JOB_STATEMENT_TIMEOUT_MS))
    seen = {}
    with pg.engine.connect() as connection:  # one physical connection for before, during and after
        before_pid, before = backend_pid(connection), tuple(connection.execute(text(SHOW_TIMEOUTS)).one())
        connection.commit()  # the Session below must begin its own transactions on this connection
        assert before != expected, "the role defaults equal the job timeouts: the check would prove nothing"

        with Session(bind=connection, autoflush=False) as session:
            def select():
                seen["selection"] = (backend_pid(session), tuple(session.execute(text(SHOW_TIMEOUTS)).one()))
                return ["probe"]

            def handle(record_id):
                seen["record"] = (backend_pid(session), tuple(session.execute(text(SHOW_TIMEOUTS)).one()))
                return True

            run = run_job(BaseService(session), "timeout_probe", select=select, handle=handle)

        after_pid, after = backend_pid(connection), tuple(connection.execute(text(SHOW_TIMEOUTS)).one())
        connection.rollback()

    assert run == JobRun("timeout_probe", selected=1, processed=1)
    assert seen == {"selection": (before_pid, expected), "record": (before_pid, expected)}
    assert (after_pid, after) == (before_pid, before)  # SET LOCAL ended with each job transaction


# ------------------------------------------------------------------------------------------------- C2


def test_the_retry_job_gives_up_on_a_locked_order_after_the_lock_timeout_and_retries_later(
        pg, sepay, failures, monkeypatch, caplog, methods, item):
    customer_id, order, qr, body = aged_received_event(pg, failures, methods, item)

    with Concurrency(pg) as run:
        armed = [True]
        original = PaymentService._lock_order

        def lock_order(service, order_id):
            if armed and str(order_id) == order["OrderId"]:
                run.record_pid(service.session, name="job")
            return original(service, order_id)

        monkeypatch.setattr(PaymentService, "_lock_order", lock_order)
        holder = run.hold_row_lock('select 1 from "Orders" where "OrderId" = :id for update', id=order["OrderId"])
        run.start("observer", lambda: run.wait_blocked("job", by=holder))

        caplog.clear()
        started = time.monotonic()
        with caplog.at_level("INFO", logger="app.jobs"):
            assert call_retry_job(pg, 500, older_than_minutes=5) == counts(selected=1, failed=1)
        elapsed = time.monotonic() - started
        armed.clear()
        assert run.join("observer") == []
        assert run.results["observer"] == ("ok", True)  # PostgreSQL showed the job waiting on the holder

        # Read while the order is still locked: the attempt was rolled back, the event waits for the next run.
        assert_received_untouched(pg, body)
        [payment] = payments(pg, order)
        assert (payment["Status"], payment["PaidAt"]) == ("Pending", None)
        assert order_state(pg, order) == ("Pending", "Pending")
        assert notification_count(pg, order) == 0
        run.release_row_lock()

    assert JOB_LOCK_TIMEOUT_MS / 1000 <= elapsed < JOB_STATEMENT_TIMEOUT_MS / 1000
    assert [state for states in run.sqlstates.values() for state in states] == ["55P03"]
    [failed] = [r for r in caplog.records if r.name == "app.jobs" and getattr(r, "job_event", None) == "record_failed"]
    assert (failed.job, failed.error_kind, failed.error_code) == (RETRY_JOB, "database", "55P03")

    assert call_retry_job(pg, older_than_minutes=5) == counts(processed=1, selected=1)
    assert_paid_once(pg, order, body, qr)
    assert notified(pg, "Order", order["OrderId"], PAID_TITLE) == {customer_id}
    assert received_events(pg) == 0


# ------------------------------------------------------------------------------------------------- C3


def test_two_simultaneous_deliveries_of_one_webhook_store_one_event_and_pay_once(
        pg, sepay, monkeypatch, methods, item):
    customer_id, order, qr = qr_sale(pg, methods, item)
    body = transfer(qr["TransferContent"], qr["TransferAmount"])
    raw = json.dumps(body).encode("utf-8")

    with Concurrency(pg) as run:
        inserted, release_first = run.event(), run.event()
        original_get, original_flush = PaymentWebhookEventRepository.get_by_key, PaymentWebhookEventRepository.flush
        original_receive = PaymentWebhookService.receive_sepay

        def get_by_key(repository, *key):
            run.record_pid(repository.session)  # the connection of this delivery's storing transaction
            return original_get(repository, *key)

        def flush(repository, objects=None):
            original_flush(repository, objects)
            if threading.current_thread().name == "first" and not inserted.is_set():
                inserted.set()  # the first INSERT is flushed, not committed
                assert release_first.wait(WAIT), "the first delivery was not released"

        def receive_sepay(service, payload, raw_body):
            outcome = original_receive(service, payload, raw_body)
            run.outcomes[threading.current_thread().name] = outcome
            return outcome

        monkeypatch.setattr(PaymentWebhookEventRepository, "get_by_key", get_by_key)
        monkeypatch.setattr(PaymentWebhookEventRepository, "flush", flush)
        monkeypatch.setattr(PaymentWebhookService, "receive_sepay", receive_sepay)

        run.start("first", lambda: deliver(raw))
        assert inserted.wait(WAIT), "the first delivery did not insert its event"
        run.start("second", lambda: deliver(raw))  # sees no committed event, inserts the same key
        run.wait_blocked("second", by="first")  # its INSERT waits on the first one's unique key
        release_first.set()
        assert run.join() == []

    assert run.results == {"first": ("ok", (200, SUCCESS_BODY)), "second": ("ok", (200, SUCCESS_BODY))}
    assert run.sqlstates == {"second": ["23505"]}  # the unique violation, then the ConflictError path
    assert sorted(run.outcomes.values()) == ["duplicate", "paid"]
    assert_paid_once(pg, order, body, qr)
    assert pg.scalar('select count(*) from "PaymentWebhookEvents" where "ProviderTransactionId" = :id',
                     id=str(body["id"])) == 1
    assert notified(pg, "Order", order["OrderId"], PAID_TITLE) == {customer_id}


# ------------------------------------------------------------------------------------------------- C4


def test_two_retry_jobs_on_one_event_process_it_once_and_skip_it_once(
        pg, sepay, failures, monkeypatch, methods, item):
    customer_id, order, qr, body = aged_received_event(pg, failures, methods, item)

    with Concurrency(pg) as run:
        holding, release = run.event(), run.event()
        watch_processing(monkeypatch, run)
        pause_after_apply(monkeypatch, "first", holding, release)

        run.start("first", lambda: retry_job(pg.engine))
        assert holding.wait(WAIT), "the first job did not apply the transfer"
        run.start("second", lambda: retry_job(pg.engine))  # selects the same Received event (selection takes no lock)
        run.wait_blocked("second", by="first")  # its SELECT ... FOR UPDATE waits on the event row
        release.set()
        assert run.join() == []

    assert run.results == {"first": ("ok", JobRun(RETRY_JOB, selected=1, processed=1)),
                           "second": ("ok", JobRun(RETRY_JOB, selected=1, skipped=1))}
    assert run.outcomes == {"first": ["paid"], "second": ["duplicate"]}
    assert run.sqlstates == {}  # neither a lock timeout nor a deadlock
    assert_paid_once(pg, order, body, qr)
    assert notified(pg, "Order", order["OrderId"], PAID_TITLE) == {customer_id}
    assert received_events(pg) == 0


# ------------------------------------------------------------------------------------------------- C5


def test_a_resend_arriving_while_the_retry_job_holds_the_event_waits_and_changes_nothing(
        pg, sepay, failures, monkeypatch, methods, item):
    customer_id, order, qr, body = aged_received_event(pg, failures, methods, item)
    raw = json.dumps(body).encode("utf-8")

    with Concurrency(pg) as run:
        holding, release = run.event(), run.event()
        watch_processing(monkeypatch, run)
        pause_after_apply(monkeypatch, "job", holding, release)

        run.start("job", lambda: retry_job(pg.engine))
        assert holding.wait(WAIT), "the job did not apply the transfer"
        run.start("resend", lambda: deliver(raw))  # finds the event still Received and processes it
        run.wait_blocked("resend", by="job")  # its SELECT ... FOR UPDATE waits on the event row
        release.set()
        assert run.join() == []

    assert run.results == {"job": ("ok", JobRun(RETRY_JOB, selected=1, processed=1)),
                           "resend": ("ok", (200, SUCCESS_BODY))}
    assert run.outcomes == {"job": ["paid"], "resend": ["duplicate"]}
    assert run.sqlstates == {}
    assert_paid_once(pg, order, body, qr)
    assert notified(pg, "Order", order["OrderId"], PAID_TITLE) == {customer_id}
    assert received_events(pg) == 0


# ------------------------------------------------------------------------------------------------- C6


def test_a_failure_after_the_event_insert_keeps_nothing_and_a_resend_stores_and_pays_once(
        pg, sepay, monkeypatch, methods, item):
    _, order, qr = qr_sale(pg, methods, item)
    body = transfer(qr["TransferContent"], qr["TransferAmount"])
    stored = 'select count(*) from "PaymentWebhookEvents" where "ProviderTransactionId" = :id'
    before = (payments(pg, order), order_state(pg, order))
    seen = []
    original = PaymentWebhookEventRepository.flush

    def flush_then_fail(repository, objects=None):
        original(repository, objects)
        if not seen:  # the first flush is the storing transaction's INSERT
            seen.append(repository.session.execute(text(stored), {"id": str(body["id"])}).scalar())
            raise InjectedFailure("injected after the event INSERT was flushed")

    monkeypatch.setattr(PaymentWebhookEventRepository, "flush", flush_then_fail)

    response = post_webhook(pg, body)
    assert (response.status_code, response.json()) == (500, FAILURE_BODY)
    assert seen == [1]  # the INSERT was visible inside its own transaction...
    assert pg.scalar(stored, id=str(body["id"])) == 0  # ...and was rolled back: nothing was stored
    assert (payments(pg, order), order_state(pg, order)) == before
    assert notification_count(pg, order) == 0

    response = post_webhook(pg, body)  # SePay retries an unacknowledged delivery
    assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    assert pg.scalar(stored, id=str(body["id"])) == 1
    assert_paid_once(pg, order, body, qr)
