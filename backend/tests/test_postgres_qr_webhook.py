"""Opt-in PostgreSQL QR payment and SePay webhook flows over HTTP with real JWTs (payment tests, group A).

Uses the protected, fixture-owned database from test_postgres_integration; its setup and teardown truncate the
dedicated test database. SePay is never contacted: every SEPAY_* setting is replaced with a fake value for each
test, SePayQrGateway builds the QR URL locally (it makes no network call) and webhooks are signed here with the
fake secret, then posted to the in-process app. The webhook route opens its own session through
app.database.SessionLocal, which the pg fixture points at the test database. SQL only reads persisted results.
"""

import json
import string
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import text

from app.integrations.sepay import (
    DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
    FAILURE_BODY,
    SIGNATURE_HEADER,
    SUCCESS_BODY,
    TIMESTAMP_HEADER,
    SePayQrGateway,
    SePaySettings,
    compute_signature,
)
from app.main import app
from app.routers import dependencies as deps
from tests.postgres_safety import POSTGRES_TESTS_ENABLED

from tests.test_postgres_integration import (
    VN,
    fill_cart,
    methods as methods,
    new_customer,
    ok,
    pg as pg,
    stocked_variant,
    team as team,
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_TESTS_ENABLED,
    reason="opt-in QR/webhook tests require the protected TEST_DATABASE_URL",
)

# Fake SePay settings: none of these is a real account, bank or secret.
SECRET = "postgres-qr-webhook-test-secret-not-a-sepay-key"
ACCOUNT = "0000111122223333"
OTHER_ACCOUNT = "9999888877776666"
BANK = "TESTBANK"
QR_IMAGE_URL = "https://qr.example.invalid/img"  # stored in the QR URL only; never fetched (.invalid never resolves)
PREFIX = "VTTEST"
CODE_LENGTH = 10
SEPAY_ENV = {
    "SEPAY_WEBHOOK_SECRET": SECRET,
    "SEPAY_ACCOUNT_NUMBER": ACCOUNT,
    "SEPAY_BANK": BANK,
    "SEPAY_QR_IMAGE_URL": QR_IMAGE_URL,
    "SEPAY_PAYMENT_CODE_PREFIX": PREFIX,
    "SEPAY_PAYMENT_CODE_LENGTH": str(CODE_LENGTH),
}
QR_TTL = timedelta(minutes=15)


@pytest.fixture
def sepay(pg, monkeypatch):
    """Fake SePay settings for one test and a QR gateway built from them; both are restored after the test."""
    for name, value in SEPAY_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setitem(app.dependency_overrides, deps.get_payment_gateway,
                        lambda: SePayQrGateway(SePaySettings.from_env()))


@pytest.fixture(scope="module")
def item(pg, team):
    return stocked_variant(pg, team, quantity=30)


# ------------------------------------------------------------------------------------------------- arrangement


def qr_order(pg, methods, item):
    """A new customer's BANK_QR order for one unit: Pending and unpaid. Returns (customer id, headers, order)."""
    customer, headers = new_customer(pg)
    fill_cart(pg, headers, item, 1)
    order = ok(pg.client.post("/orders", headers=headers, json={
        "ShippingMethodId": methods["shipping"], "PaymentMethodId": methods["qr"], "ReceiverName": "Khách",
        "ReceiverPhone": "0900000000", "ShippingAddress": "1 Đường A"}), 201)
    assert (order["OrderStatus"], order["PaymentStatus"]) == ("Pending", "Pending")
    return customer["id"], headers, order


def request_qr(pg, headers, order):
    return ok(pg.client.post(f"/orders/{order['OrderId']}/payments/qr", headers=headers), 201)


def transfer(code, amount, *, transfer_type="in", account=ACCOUNT):
    """A SePay webhook body with the documented fields and a new SePay transaction id."""
    return {
        "id": uuid.uuid4().int % 2**31, "gateway": BANK,
        "transactionDate": datetime.now(VN).strftime("%Y-%m-%d %H:%M:%S"), "accountNumber": account,
        "subAccount": None, "code": code, "content": f"{code or ''} chuyen khoan".strip(),
        "transferType": transfer_type, "description": "Giao dich thu nghiem", "transferAmount": amount,
        "accumulated": None, "referenceCode": f"FT{uuid.uuid4().hex[:10].upper()}",
    }


def signed_headers(raw, *, secret=SECRET, timestamp=None):
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    return {"Content-Type": "application/json", TIMESTAMP_HEADER: stamp,
            SIGNATURE_HEADER: compute_signature(secret, stamp, raw)}


def post_webhook(pg, body):
    """Sign ``body`` with the fake secret and post it as SePay would."""
    raw = json.dumps(body).encode("utf-8")
    return pg.client.post("/webhooks/sepay", content=raw, headers=signed_headers(raw))


def sepay_key(body):
    """Reconciliation key of a SePay transfer (PaymentReconciliations.GatewayTransactionCode)."""
    return f"sepay:{body['accountNumber']}:{body['id']}"


# ------------------------------------------------------------------------------------------------- read-back


def rows(pg, sql, **params):
    with pg.engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(sql), params).mappings()]


def webhook_event(pg, body):
    [event] = rows(pg, 'select "PaymentWebhookEventId", "Status", "ProcessingNote", "PaymentTransactionId", '
                       '"ProcessedAt", "TransferType", "TransferAmount", "PaymentCode" from "PaymentWebhookEvents" '
                       'where "Provider" = \'SePay\' and "AccountNumber" = :account and "ProviderTransactionId" = :id',
                   account=body["accountNumber"], id=str(body["id"]))
    return event


def payments(pg, order):
    return rows(pg, 'select "PaymentTransactionId", "Status", "Amount", "GatewayTransactionCode", "QrData", "PaidAt" '
                    'from "PaymentTransactions" where "OrderId" = :id and "TransactionType" = \'Payment\'',
                id=order["OrderId"])


def order_state(pg, order):
    [row] = rows(pg, 'select "OrderStatus", "PaymentStatus" from "Orders" where "OrderId" = :id', id=order["OrderId"])
    return row["OrderStatus"], row["PaymentStatus"]


def reconciliations(pg, body):
    return rows(pg, 'select "OrderId", "PaymentTransactionId", "PaymentWebhookEventId", "IssueType", "Status", '
                    '"ExpectedAmount", "ReceivedAmount" from "PaymentReconciliations" '
                    'where "GatewayTransactionCode" = :key', key=sepay_key(body))


def notified(pg, reference_type, reference_id, title):
    """Recipients of the payment notifications with ``title`` about one record."""
    return {str(row["UserId"]) for row in rows(
        pg, 'select "UserId" from "Notifications" where "NotificationType" = \'Payment\' '
            'and "ReferenceType" = :type and "ReferenceId" = :id and "Title" = :title',
        type=reference_type, id=reference_id, title=title)}


def staff_ids(team):
    return {team["admin_id"], team["staff_id"]}


# ------------------------------------------------------------------------------------------------- QR


def test_customer_creates_a_qr_payment_once_and_a_repeat_call_returns_it(pg, sepay, methods, item):
    _, customer, order = qr_order(pg, methods, item)
    total = Decimal(order["TotalAmount"])

    first = request_qr(pg, customer, order)
    code = first["TransferContent"]
    assert (first["OrderId"], first["TransactionType"], first["Status"], first["PaidAt"]) == (
        order["OrderId"], "Payment", "Pending", None)
    assert Decimal(first["Amount"]) == total and first["TransferAmount"] == int(total)
    assert code.startswith(PREFIX) and len(code) == len(PREFIX) + CODE_LENGTH
    assert set(code[len(PREFIX):]) <= set(string.ascii_uppercase + string.digits)
    assert (first["Bank"], first["AccountNumber"]) == (BANK, ACCOUNT)
    assert datetime.fromisoformat(first["ExpiresAt"]) == datetime.fromisoformat(order["OrderedAt"]) + QR_TTL
    qr = urlsplit(first["QrData"])
    assert f"{qr.scheme}://{qr.netloc}{qr.path}" == QR_IMAGE_URL
    assert parse_qs(qr.query) == {"acc": [ACCOUNT], "bank": [BANK], "amount": [str(int(total))], "des": [code]}

    # Calling again returns the stored request instead of creating a second transaction or code.
    again = request_qr(pg, customer, order)
    fields = ("PaymentTransactionId", "Status", "TransferContent", "QrData", "TransferAmount", "ExpiresAt")
    assert {key: again[key] for key in fields} == {key: first[key] for key in fields}
    [stored] = payments(pg, order)
    assert (str(stored["PaymentTransactionId"]), stored["Status"], stored["GatewayTransactionCode"],
            stored["QrData"]) == (first["PaymentTransactionId"], "Pending", code, first["QrData"])
    assert order_state(pg, order) == ("Pending", "Pending")


# ------------------------------------------------------------------------------------------------- webhook


def test_signed_webhook_with_the_exact_amount_marks_the_order_paid(pg, sepay, methods, item):
    customer_id, customer, order = qr_order(pg, methods, item)
    qr = request_qr(pg, customer, order)
    body = transfer(qr["TransferContent"], qr["TransferAmount"])

    response = post_webhook(pg, body)
    assert (response.status_code, response.json()) == (200, SUCCESS_BODY)

    event = webhook_event(pg, body)
    assert (event["Status"], event["ProcessingNote"], str(event["PaymentTransactionId"])) == (
        "Processed", "paid", qr["PaymentTransactionId"])
    assert (event["TransferType"], event["PaymentCode"], Decimal(event["TransferAmount"])) == (
        "in", qr["TransferContent"], Decimal(qr["TransferAmount"]))
    assert event["ProcessedAt"] is not None
    [payment] = payments(pg, order)
    assert payment["Status"] == "Success" and payment["PaidAt"] is not None
    # Paid, still awaiting Staff confirmation (see the last test).
    assert order_state(pg, order) == ("Pending", "Paid")
    assert ok(pg.client.get(f"/orders/{order['OrderId']}", headers=customer))["PaymentStatus"] == "Paid"
    assert notified(pg, "Order", order["OrderId"], "Thanh toán thành công") == {customer_id}
    assert reconciliations(pg, body) == []


def test_unsigned_tampered_stale_or_unconfigured_webhooks_store_nothing(pg, sepay, monkeypatch, methods, item):
    _, customer, order = qr_order(pg, methods, item)
    qr = request_qr(pg, customer, order)
    body = transfer(qr["TransferContent"], qr["TransferAmount"])
    raw = json.dumps(body).encode("utf-8")
    now, beyond_tolerance = int(time.time()), DEFAULT_TIMESTAMP_TOLERANCE_SECONDS + 300
    events_before = pg.scalar('select count(*) from "PaymentWebhookEvents"')

    def send(content, headers):
        return pg.client.post("/webhooks/sepay", content=content, headers=headers)

    def signed_without(header):
        headers = signed_headers(raw)
        del headers[header]
        return headers

    tampered = json.dumps({**body, "transferAmount": body["transferAmount"] + 1}).encode("utf-8")
    unauthenticated = {
        "wrong secret": send(raw, signed_headers(raw, secret="not-the-configured-secret")),
        "tampered body": send(tampered, signed_headers(raw)),
        "no signature header": send(raw, signed_without(SIGNATURE_HEADER)),
        "no timestamp header": send(raw, signed_without(TIMESTAMP_HEADER)),
        "stale timestamp": send(raw, signed_headers(raw, timestamp=now - beyond_tolerance)),
        "future timestamp": send(raw, signed_headers(raw, timestamp=now + beyond_tolerance)),
    }
    for case, response in unauthenticated.items():
        assert (response.status_code, response.json()) == (401, FAILURE_BODY), case

    # Correctly signed, but not a valid SePay body.
    for content in (b"not json", json.dumps([body]).encode("utf-8"),
                    json.dumps({**body, "transferAmount": str(body["transferAmount"])}).encode("utf-8")):
        response = send(content, signed_headers(content))
        assert (response.status_code, response.json()) == (400, FAILURE_BODY), content

    # Incomplete webhook configuration: refused before verification or processing, even when correctly signed.
    monkeypatch.delenv("SEPAY_WEBHOOK_SECRET")
    response = send(raw, signed_headers(raw))
    assert (response.status_code, response.json()) == (503, FAILURE_BODY)
    monkeypatch.setenv("SEPAY_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("SEPAY_ACCOUNT_NUMBER", "   ")
    response = send(raw, signed_headers(raw))
    assert (response.status_code, response.json()) == (503, FAILURE_BODY)

    assert pg.scalar('select count(*) from "PaymentWebhookEvents"') == events_before
    [payment] = payments(pg, order)
    assert (payment["Status"], payment["PaidAt"]) == ("Pending", None)
    assert order_state(pg, order) == ("Pending", "Pending")


def test_webhook_with_a_wrong_amount_is_reconciled_and_the_order_stays_unpaid(pg, sepay, team, methods, item):
    _, customer, order = qr_order(pg, methods, item)
    qr = request_qr(pg, customer, order)
    received = qr["TransferAmount"] - 1000
    body = transfer(qr["TransferContent"], received)

    # Stored and reconciled, so it is acknowledged: SePay must not resend it.
    response = post_webhook(pg, body)
    assert (response.status_code, response.json()) == (200, SUCCESS_BODY)

    event = webhook_event(pg, body)
    assert (event["Status"], event["ProcessingNote"], str(event["PaymentTransactionId"])) == (
        "Processed", "amount_mismatch", qr["PaymentTransactionId"])
    [issue] = reconciliations(pg, body)
    assert (issue["IssueType"], issue["Status"], str(issue["OrderId"]), str(issue["PaymentTransactionId"]),
            issue["PaymentWebhookEventId"]) == (
        "AmountMismatch", "Open", order["OrderId"], qr["PaymentTransactionId"], event["PaymentWebhookEventId"])
    assert (Decimal(issue["ExpectedAmount"]), Decimal(issue["ReceivedAmount"])) == (
        Decimal(order["TotalAmount"]), Decimal(received))
    [payment] = payments(pg, order)
    assert (payment["Status"], payment["PaidAt"]) == ("Pending", None)
    assert order_state(pg, order) == ("Pending", "Pending")
    assert notified(pg, "Order", order["OrderId"], "Thanh toán sai số tiền") == staff_ids(team)
    assert notified(pg, "Order", order["OrderId"], "Thanh toán thành công") == set()


def test_unmatched_outgoing_and_other_account_transfers_are_recorded_without_touching_orders(
        pg, sepay, team, methods, item):
    _, customer, order = qr_order(pg, methods, item)
    qr = request_qr(pg, customer, order)
    code, amount = qr["TransferContent"], qr["TransferAmount"]

    # A code that no QR request carries, or no code at all: reconciled without choosing an order.
    for unknown in (f"{PREFIX}NOMATCH{uuid.uuid4().hex[:6].upper()}", None):
        body = transfer(unknown, amount)
        response = post_webhook(pg, body)
        assert (response.status_code, response.json()) == (200, SUCCESS_BODY), unknown
        event = webhook_event(pg, body)
        assert (event["Status"], event["ProcessingNote"], event["PaymentTransactionId"]) == (
            "Processed", "unmatched", None)
        [issue] = reconciliations(pg, body)
        assert (issue["IssueType"], issue["Status"], issue["OrderId"], issue["PaymentTransactionId"],
                issue["ExpectedAmount"]) == ("UnmatchedPayment", "Open", None, None, None)
        assert issue["PaymentWebhookEventId"] == event["PaymentWebhookEventId"]
        assert Decimal(issue["ReceivedAmount"]) == Decimal(amount)
        assert notified(pg, "PaymentWebhookEvent", event["PaymentWebhookEventId"],
                        "Tiền vào chưa xác định đơn hàng") == staff_ids(team)

    # Money leaving the account, or arriving at another account, never pays the order, even with its code and amount.
    for body, note in ((transfer(code, amount, transfer_type="out"), "ignored_transfer_out"),
                       (transfer(code, amount, account=OTHER_ACCOUNT), "ignored_other_account")):
        response = post_webhook(pg, body)
        assert (response.status_code, response.json()) == (200, SUCCESS_BODY), note
        event = webhook_event(pg, body)
        assert (event["Status"], event["ProcessingNote"], event["PaymentTransactionId"]) == ("Ignored", note, None)
        assert reconciliations(pg, body) == []

    [payment] = payments(pg, order)
    assert (payment["Status"], payment["PaidAt"]) == ("Pending", None)
    assert order_state(pg, order) == ("Pending", "Pending")


# ------------------------------------------------------------------------------------------------- confirmation


def test_staff_can_confirm_a_transfer_order_only_after_the_webhook_marks_it_paid(pg, sepay, team, methods, item):
    _, customer, order = qr_order(pg, methods, item)
    qr = request_qr(pg, customer, order)
    history = 'select count(*) from "OrderStatusHistories" where "OrderId" = :id'
    recorded = pg.scalar(history, id=order["OrderId"])

    def confirm():
        return pg.client.post(f"/admin/orders/{order['OrderId']}/status", headers=team["staff"],
                              json={"OrderStatus": "Confirmed"})

    refused = confirm()
    assert refused.status_code == 400 and refused.json()["code"] == "order_not_paid"
    assert order_state(pg, order) == ("Pending", "Pending")
    assert pg.scalar(history, id=order["OrderId"]) == recorded

    response = post_webhook(pg, transfer(qr["TransferContent"], qr["TransferAmount"]))
    assert (response.status_code, response.json()) == (200, SUCCESS_BODY)
    confirmed = ok(confirm())
    assert (confirmed["OrderStatus"], confirmed["PaymentStatus"]) == ("Confirmed", "Paid")
    assert order_state(pg, order) == ("Confirmed", "Paid")
    assert pg.scalar(history, id=order["OrderId"]) == recorded + 1
