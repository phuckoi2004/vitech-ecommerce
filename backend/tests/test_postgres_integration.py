"""Write-API flows on a real PostgreSQL database, over HTTP with real JWT logins (Stage 6).

Opt-in: runs only with RUN_POSTGRES_TESTS=1 and a TEST_DATABASE_URL (process environment or backend/.env) that
points at a dedicated, migrated test database. The module refuses to run against the DATABASE_URL database, and
TRUNCATEs every table except alembic_version before and after it runs: never point it at data worth keeping.

    RUN_POSTGRES_TESTS=1 python -m pytest tests/test_postgres_integration.py -v

What the in-memory fakes cannot show: real constraints, row locks under concurrency, server defaults, timestamps,
and SQL aggregates. Email is captured in memory and the payment gateway is disabled: nothing leaves the machine
except queries to the test database.
"""

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import app.database as database
from app.core.auth_state import MemoryStateStore
from app.core.config import AuthSettings
from app.core.dependencies import AuthRuntime, get_runtime
from app.core.security import hash_password
from app.core.sessions import SessionManager
from app.main import app
from app.models import User
from app.routers import dependencies as deps
from app.routers import internal
from app.schemas import OrderCreate
from app.services.actor import Actor
from app.services.exceptions import ServiceError
from app.services.order import OrderService
from tests.postgres_safety import (
    POSTGRES_TESTS_ENABLED,
    UnsafePostgresTestDatabase,
    require_test_database_target,
)

BACKEND = Path(__file__).resolve().parents[1]
PASSWORD = "Password1!"
CRON_SECRET = "postgres-integration-cron-secret-0123456789"
VN = timezone(timedelta(hours=7))

pytestmark = pytest.mark.skipif(not POSTGRES_TESTS_ENABLED,
                                reason="set RUN_POSTGRES_TESTS=1 to run against TEST_DATABASE_URL")


def _setting(name):
    return (os.getenv(name) or dotenv_values(BACKEND / ".env").get(name) or "").strip()


class CapturingMailer:
    def __init__(self):
        self.messages = []

    def send_otp(self, email, code, purpose, ttl):
        self.messages.append({"email": email, "code": code, "purpose": purpose})


class Context:
    def __init__(self, client, engine, mailer):
        self.client, self.engine, self.mailer = client, engine, mailer

    def scalar(self, sql, **params):
        with self.engine.connect() as conn:
            return conn.execute(text(sql), params).scalar()

    def execute(self, sql, **params):
        with self.engine.begin() as conn:
            conn.execute(text(sql), params)

    def seed_user(self, role):
        identity = uuid.uuid4()
        email = f"{role.lower()}-{identity.hex[:12]}@example.com"
        with Session(self.engine) as db:
            db.add(User(UserId=identity, Email=email, PhoneNumber=f"09{identity.int % 10**8:08d}",
                        FullName=f"Test {role}", PasswordHash=hash_password(PASSWORD), Role=role,
                        AccountStatus="Active", IsEmailVerified=True, IsDeleted=False))
            db.commit()
        return {"id": str(identity), "email": email, "role": role}

    def login(self, user):
        portal = "customer" if user["role"] == "Customer" else "admin"
        response = self.client.post("/auth/login",
                                    json={"Identifier": user["email"], "Password": PASSWORD, "Portal": portal})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _truncate(engine):
    with engine.begin() as conn:
        tables = conn.execute(text("select tablename from pg_tables where schemaname = 'public' "
                                   "and tablename <> 'alembic_version'")).scalars().all()
        if tables:
            preparer = engine.dialect.identifier_preparer
            public = preparer.quote_identifier("public")
            qualified = [f"{public}.{preparer.quote_identifier(table)}" for table in tables]
            conn.execute(text("TRUNCATE TABLE " + ", ".join(qualified) + " RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="module")
def pg(request):
    if not POSTGRES_TESTS_ENABLED:
        pytest.skip("set RUN_POSTGRES_TESTS=1 to run against TEST_DATABASE_URL")
    test_url, main_url = _setting("TEST_DATABASE_URL"), _setting("DATABASE_URL")
    try:
        require_test_database_target(test_url, main_url, expected_project=_setting("TEST_DATABASE_PROJECT_REF"),
                                     environ=os.environ)
    except UnsafePostgresTestDatabase as error:
        pytest.fail(str(error), pytrace=False)
    request.getfixturevalue("postgres_test_lock")  # one PostgreSQL test run at a time on this database
    engine = create_engine(test_url, pool_pre_ping=True)
    head = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini"))).get_current_head()
    with engine.connect() as conn:
        version = conn.execute(text("select version_num from alembic_version")).scalar()
    if version != head:
        engine.dispose()
        pytest.fail(f"test database is at {version}, expected {head}: run alembic upgrade head on it first",
                    pytrace=False)
    _truncate(engine)

    settings = AuthSettings(jwt_secret="integration" * 6, app_env="test")
    state, mailer = MemoryStateStore(), CapturingMailer()
    runtime = AuthRuntime(settings, state, mailer, SessionManager(state, settings), hash_password("NotAnAccount1!"))
    test_sessions = sessionmaker(bind=engine, autoflush=False)

    def test_db():
        with test_sessions() as db:
            yield db

    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update({database.get_db: test_db, get_runtime: lambda: runtime,
                                     deps.get_payment_gateway: lambda: None})
    with pytest.MonkeyPatch.context() as patch:
        # Anything that bypasses get_db (webhook sessions, health check) also lands on the test database.
        patch.setattr(database, "engine", engine)
        patch.setattr(database, "SessionLocal", test_sessions)
        patch.setenv(internal.INTERNAL_SECRET_ENV, CRON_SECRET)
        try:
            with TestClient(app) as client:
                yield Context(client, engine, mailer)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
            _truncate(engine)
            engine.dispose()


@pytest.fixture(scope="module")
def team(pg):
    admin, staff = pg.seed_user("Admin"), pg.seed_user("Staff")
    return {"admin": pg.login(admin), "staff": pg.login(staff), "admin_id": admin["id"], "staff_id": staff["id"]}


@pytest.fixture(scope="module")
def methods(pg, team):
    tag = uuid.uuid4().hex[:6].upper()
    shipping = ok(pg.client.post("/admin/shipping-methods", headers=team["admin"], json={
        "Code": f"STD-{tag}", "Name": "Giao tiêu chuẩn", "BaseFee": "30000.00", "EstimatedDays": 3}), 201)
    cod = ok(pg.client.post("/admin/payment-methods", headers=team["admin"], json={
        "Code": "COD", "Name": "Thanh toán khi nhận hàng"}), 201)
    qr = ok(pg.client.post("/admin/payment-methods", headers=team["admin"], json={
        "Code": "BANK_QR", "Name": "Chuyển khoản QR"}), 201)
    return {"shipping": shipping["ShippingMethodId"], "cod": cod["PaymentMethodId"], "qr": qr["PaymentMethodId"]}


def ok(response, status=200):
    assert response.status_code == status, f"{response.status_code}: {response.text}"
    return response.json()


def stocked_variant(pg, team, *, quantity, price="100000.00", cost="70000.00"):
    """Catalog + purchasing through the admin APIs, with the Stage 4 roles: Admin owns the catalog and suppliers;
    Staff creates and receives the purchase order; Admin approves it."""
    client, staff, admin = pg.client, team["staff"], team["admin"]
    tag = uuid.uuid4().hex[:8]
    category = ok(client.post("/admin/categories", headers=admin, json={"Name": f"Điện thoại {tag}",
                                                                       "Slug": f"dien-thoai-{tag}"}), 201)
    brand = ok(client.post("/admin/brands", headers=admin, json={"Name": f"Hãng {tag}", "Slug": f"hang-{tag}"}), 201)
    product = ok(client.post("/admin/products", headers=admin, json={
        "CategoryId": category["CategoryId"], "BrandId": brand["BrandId"], "Name": f"Điện thoại {tag}",
        "Slug": f"dt-{tag}", "WarrantyMonths": 12, "Status": "Active"}), 201)
    variant = ok(client.post("/admin/variants", headers=admin, json={
        "ProductId": product["ProductId"], "Sku": f"SKU-{tag.upper()}", "VariantName": "8GB/128GB",
        "Price": price}), 201)
    supplier = ok(client.post("/admin/suppliers", headers=admin, json={
        "SupplierCode": f"NCC-{tag.upper()}", "Name": "Nhà cung cấp A", "PhoneNumber": "0281234567",
        "Address": "1 Lê Lợi, TP.HCM"}), 201)
    po = ok(client.post("/admin/purchase-orders", headers=staff, json={
        "SupplierId": supplier["SupplierId"],
        "Items": [{"ProductVariantId": variant["ProductVariantId"], "OrderedQuantity": quantity, "UnitPrice": cost}]}), 201)
    po_id = po["PurchaseOrderId"]
    assert ok(client.post(f"/admin/purchase-orders/{po_id}/decision", headers=admin,
                          json={"Status": "Approved"}))["Status"] == "Approved"
    received = ok(client.post(f"/admin/purchase-orders/{po_id}/receive", headers=staff, json={
        "Items": [{"PurchaseOrderItemId": po["Items"][0]["PurchaseOrderItemId"], "Quantity": quantity}]}))
    assert received["Status"] == "Completed"
    return {"product": product, "variant": variant, "category": category, "purchase_order": received}


def stock_of(pg, variant):
    return pg.scalar('select "StockQuantity" from "ProductVariants" where "ProductVariantId" = :id',
                     id=variant["variant"]["ProductVariantId"])


def new_customer(pg):
    customer = pg.seed_user("Customer")
    return customer, pg.login(customer)


def fill_cart(pg, headers, variant, quantity):
    ok(pg.client.post("/cart/items", headers=headers,
                      json={"ProductVariantId": variant["variant"]["ProductVariantId"], "Quantity": quantity}))


# ---------------------------------------------------------------------------------------------------- accounts


def test_customer_registers_with_email_otp_and_logs_in(pg):
    tag = uuid.uuid4().hex[:10]
    email = f"KHACH-{tag}@Example.com"
    challenge = ok(pg.client.post("/auth/register", json={
        "Email": email, "PhoneNumber": f"09{int(tag, 16) % 10**8:08d}", "FullName": " Khách Hàng ",
        "Password": PASSWORD, "ConfirmPassword": PASSWORD}), 202)
    assert pg.scalar('select count(*) from "Users" where "Email" = :e', e=email.lower()) == 0
    code = pg.mailer.messages[-1]["code"]
    ok(pg.client.post("/auth/register/verify", json={"ChallengeId": challenge["challenge_id"], "Code": code}), 201)

    with pg.engine.connect() as conn:
        row = conn.execute(text('select "Role", "AccountStatus", "IsEmailVerified", "FullName", "PasswordHash", '
                                '"CreatedAt" from "Users" where "Email" = :e'), {"e": email.lower()}).one()
    assert (row.Role, row.AccountStatus, row.IsEmailVerified, row.FullName) == ("Customer", "Active", True,
                                                                                "Khách Hàng")
    assert row.PasswordHash and PASSWORD not in row.PasswordHash and row.CreatedAt is not None
    token = pg.login({"email": email, "role": "Customer"})
    assert ok(pg.client.get("/auth/me", headers=token))["user"]["Email"] == email.lower()
    # The same email again is refused by the existing row, not by a database error.
    again = pg.client.post("/auth/register", json={
        "Email": email, "PhoneNumber": "0911111111", "FullName": "Khác", "Password": PASSWORD,
        "ConfirmPassword": PASSWORD})
    assert again.status_code in (202, 409) and pg.scalar('select count(*) from "Users" where "Email" = :e',
                                                         e=email.lower()) == 1


# ---------------------------------------------------------------------------------------------- catalog/stock


def test_purchase_receipt_sets_stock_and_cost_and_duplicates_are_conflicts(pg, team):
    item = stocked_variant(pg, team, quantity=10, cost="70000.00")
    assert stock_of(pg, item) == 10
    assert pg.scalar('select "CostPrice" from "ProductVariants" where "ProductVariantId" = :id',
                     id=item["variant"]["ProductVariantId"]) == Decimal("70000.00")
    assert pg.scalar('select count(*) from "PurchaseReceipts" where "PurchaseOrderId" = :id',
                     id=item["purchase_order"]["PurchaseOrderId"]) == 1
    public = ok(pg.client.get(f"/products/{item['product']['ProductId']}"))
    assert public["ProductId"] == item["product"]["ProductId"]

    duplicate = pg.client.post("/admin/categories", headers=team["admin"],
                               json={"Name": "Trùng", "Slug": item["category"]["Slug"]})
    assert duplicate.status_code == 409, duplicate.text
    # Stage 4 roles: Staff reads the catalog but cannot change it.
    assert pg.client.post("/admin/categories", headers=team["staff"],
                          json={"Name": "Staff", "Slug": f"staff-{uuid.uuid4().hex[:8]}"}).status_code == 403
    # Staff cannot approve its own purchase orders: Admin only.
    supplier_id = item["purchase_order"]["SupplierId"]
    po = ok(pg.client.post("/admin/purchase-orders", headers=team["staff"], json={
        "SupplierId": supplier_id, "Items": [{"ProductVariantId": item["variant"]["ProductVariantId"],
                                              "OrderedQuantity": 1, "UnitPrice": "1.00"}]}), 201)
    assert pg.client.post(f"/admin/purchase-orders/{po['PurchaseOrderId']}/decision", headers=team["staff"],
                          json={"Status": "Approved"}).status_code == 403


# ---------------------------------------------------------------------------------------------- order lifecycle


def test_cod_order_delivery_review_return_refund_and_statistics(pg, team, methods):
    client, staff, admin = pg.client, team["staff"], team["admin"]
    item = stocked_variant(pg, team, quantity=10, price="100000.00", cost="70000.00")
    _, customer = new_customer(pg)

    address = ok(client.post("/users/me/addresses", headers=customer, json={
        "ReceiverName": "Nguyễn Văn A", "ReceiverPhone": "0900000000", "Province": "TP. Hồ Chí Minh",
        "Ward": "Phường Bến Nghé", "DetailAddress": "1 Lê Lợi", "IsDefault": True}), 201)
    fill_cart(pg, customer, item, 2)
    order = ok(client.post("/orders", headers=customer, json={
        "ShippingMethodId": methods["shipping"], "PaymentMethodId": methods["cod"],
        "AddressId": address["AddressId"]}), 201)
    order_id, line = order["OrderId"], order["Items"][0]
    assert (Decimal(order["Subtotal"]), Decimal(order["ShippingFee"]), Decimal(order["TotalAmount"])) == (
        Decimal("200000"), Decimal("30000"), Decimal("230000"))
    assert order["ReceiverName"] == "Nguyễn Văn A" and order["OrderStatus"] == "Pending"
    assert stock_of(pg, item) == 8
    assert pg.scalar('select count(*) from "CartItems" ci join "Carts" c on c."CartId" = ci."CartId" '
                     'join "Users" u on u."UserId" = c."UserId" where u."Role" = \'Customer\' '
                     'and ci."ProductVariantId" = :v', v=item["variant"]["ProductVariantId"]) == 0

    for target in ("Confirmed", "Processing", "Shipping"):
        moved = ok(client.post(f"/admin/orders/{order_id}/status", headers=staff, json={"OrderStatus": target}))
        assert moved["OrderStatus"] == target
    # COD cannot be marked Delivered without recording the collection.
    assert client.post(f"/admin/orders/{order_id}/status", headers=staff,
                       json={"OrderStatus": "Delivered"}).status_code == 400
    delivered = ok(client.post(f"/admin/orders/{order_id}/confirm-cod-delivery", headers=staff, json={}))
    assert (delivered["OrderStatus"], delivered["PaymentStatus"]) == ("Delivered", "Paid")
    payments = ok(client.get(f"/admin/orders/{order_id}/payments", headers=staff))
    assert [(p["TransactionType"], p["Status"], Decimal(p["Amount"])) for p in payments] == [
        ("Payment", "Success", Decimal("230000"))]
    # Confirming twice must not create a second payment.
    assert client.post(f"/admin/orders/{order_id}/confirm-cod-delivery", headers=staff, json={}).status_code == 400
    assert Decimal(ok(client.get(f"/admin/orders/{order_id}/cogs", headers=admin))["Cogs"]) == Decimal("140000")
    history = ok(client.get(f"/orders/{order_id}/history", headers=customer))
    assert len(history) >= 5

    review = ok(client.post("/reviews", headers=customer, json={
        "OrderItemId": line["OrderItemId"], "Rating": 5, "Content": "Máy chạy tốt"}), 201)
    reviews = ok(client.get(f"/products/{item['product']['ProductId']}/reviews"))
    assert [r["ReviewId"] for r in reviews["Items"]] == [review["ReviewId"]]
    assert client.post("/reviews", headers=customer, json={
        "OrderItemId": line["OrderItemId"], "Rating": 4, "Content": "Lần hai"}).status_code == 409

    # Return one of the two units: Staff handles the goods, Admin approves the amount, refund is confirmed manually.
    request = ok(client.post("/return-requests", headers=customer, json={
        "OrderItemId": line["OrderItemId"], "RequestType": "Return", "Quantity": 1, "Reason": "Không ưng ý"}), 201)
    request_id = request["ReturnRequestId"]
    ok(client.post(f"/admin/return-requests/{request_id}/accept", headers=staff))
    ok(client.post(f"/admin/return-requests/{request_id}/start-receiving", headers=staff))
    ok(client.post(f"/admin/return-requests/{request_id}/receive", headers=staff, json={}))
    inspected = ok(client.post(f"/admin/return-requests/{request_id}/inspect", headers=staff,
                               json={"RestockedQuantity": 1, "DamagedQuantity": 0}))
    assert Decimal(inspected["CompensationAmount"]) == Decimal("100000")
    assert client.post(f"/admin/return-requests/{request_id}/approve", headers=staff,
                       json={"CompensationAmount": "100000.00"}).status_code == 403
    approved = ok(client.post(f"/admin/return-requests/{request_id}/approve", headers=admin,
                              json={"CompensationAmount": "100000.00"}))
    assert approved["CompensationApprovedByUserId"] == team["admin_id"]
    assert stock_of(pg, item) == 9  # the accepted unit is back in stock exactly once

    refunding = ok(client.post(f"/admin/return-requests/{request_id}/refund", headers=staff))
    refund_id = refunding["RefundPaymentTransactionId"]
    assert refunding["Status"] == "Processing"
    resolved = ok(client.post(f"/admin/refunds/{refund_id}/resolve", headers=admin, json={
        "Success": True, "EvidenceReference": "UNC-0001", "ResolutionNote": "Đã chuyển khoản hoàn tiền"}))
    assert (resolved["Status"], Decimal(resolved["Amount"])) == ("Success", Decimal("100000"))
    completed_request = ok(client.post(f"/admin/return-requests/{request_id}/confirm-refund", headers=staff))
    assert completed_request["Status"] == "Completed"

    completed = ok(client.post(f"/admin/orders/{order_id}/status", headers=staff, json={"OrderStatus": "Completed"}))
    assert completed["OrderStatus"] == "Completed" and completed["CompletedAt"]

    today = datetime.now(VN).date()
    period = {"date_from": (today - timedelta(days=1)).isoformat(), "date_to": today.isoformat()}
    revenue = ok(client.get("/admin/statistics/revenue", headers=staff, params=period))
    assert revenue["OrderCount"] == 1
    assert {key: Decimal(revenue[key]) for key in ("OrderValue", "ShippingFee", "CollectedAmount", "RefundedAmount",
                                                   "NetRevenue", "PendingRefundAmount")} == {
        "OrderValue": Decimal("230000"), "ShippingFee": Decimal("30000"), "CollectedAmount": Decimal("230000"),
        "RefundedAmount": Decimal("100000"), "NetRevenue": Decimal("130000"), "PendingRefundAmount": Decimal("0")}
    orders = ok(client.get("/admin/statistics/orders", headers=staff, params=period))
    assert orders["Completed"] >= 1
    notifications = ok(client.get("/users/me/notifications/unread-count", headers=customer))
    assert notifications["Count"] > 0


# ---------------------------------------------------------------------------------------------- concurrency


def test_statistics_minimum_date_returns_business_error_with_real_auth(pg, team):
    for role in ("staff", "admin"):
        for report in ("orders", "revenue", "cogs", "top-products"):
            response = pg.client.get(f"/admin/statistics/{report}", headers=team[role],
                                     params={"date_from": "0001-01-01", "date_to": "2026-10-31"})
            assert response.status_code == 400, response.text
            assert response.json()["code"] == "invalid_statistics_period"


def test_last_unit_is_sold_once_when_two_customers_check_out_together(pg, team, methods):
    item = stocked_variant(pg, team, quantity=1)
    buyers = []
    for _ in range(2):
        user, headers = new_customer(pg)
        fill_cart(pg, headers, item, 1)
        buyers.append(Actor(user_id=uuid.UUID(user["id"]), role="Customer"))
    payload = OrderCreate(ShippingMethodId=methods["shipping"], PaymentMethodId=methods["cod"],
                          ReceiverName="Khách", ReceiverPhone="0900000000", ShippingAddress="1 Đường A")
    start, results = threading.Barrier(len(buyers)), []

    def checkout(actor):
        with Session(pg.engine, autoflush=False) as session:
            start.wait()
            try:
                results.append(("ok", OrderService(session).create_order(actor, payload).OrderId))
            except ServiceError as error:
                results.append(("refused", error.code))

    threads = [threading.Thread(target=checkout, args=(actor,)) for actor in buyers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    # The row lock serialises the two checkouts: the loser is refused for stock, not by a database error.
    assert sorted(results, key=lambda r: r[0])[1] == ("refused", "insufficient_stock"), results
    assert sorted(kind for kind, _ in results) == ["ok", "refused"], results
    assert stock_of(pg, item) == 0
    assert pg.scalar('select count(*) from "OrderItems" where "ProductVariantId" = :v',
                     v=item["variant"]["ProductVariantId"]) == 1


# ---------------------------------------------------------------------------------------------- cron


def test_cron_cancels_expired_qr_order_and_restores_stock_once(pg, team, methods):
    item = stocked_variant(pg, team, quantity=3)
    _, customer = new_customer(pg)
    fill_cart(pg, customer, item, 2)
    order = ok(pg.client.post("/orders", headers=customer, json={
        "ShippingMethodId": methods["shipping"], "PaymentMethodId": methods["qr"], "ReceiverName": "Khách",
        "ReceiverPhone": "0900000000", "ShippingAddress": "1 Đường A"}), 201)
    assert stock_of(pg, item) == 1
    secret = {"X-Internal-Secret": CRON_SECRET}

    def run_job():
        run = ok(pg.client.post("/internal/orders/expire-unpaid-qr", headers=secret))
        return run["Processed"], run["Failed"]

    # Not yet 15 minutes old: the job leaves it alone.
    assert run_job() == (0, 0)
    pg.execute('update "Orders" set "OrderedAt" = now() - interval \'20 minutes\' where "OrderId" = :id',
               id=order["OrderId"])
    assert run_job() == (1, 0)
    assert run_job() == (0, 0)

    detail = ok(pg.client.get(f"/orders/{order['OrderId']}", headers=customer))
    assert detail["OrderStatus"] == "Cancelled" and detail["CancelledAt"]
    assert stock_of(pg, item) == 3
    assert pg.client.post("/internal/orders/expire-unpaid-qr").status_code == 401
