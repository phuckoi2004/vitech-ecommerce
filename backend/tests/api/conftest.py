"""Stage 7 API test fixtures: real PostgreSQL, one rolled-back transaction per test, real JWT logins.

Opt-in like the other PostgreSQL suites (RUN_POSTGRES_TESTS=1 in the process environment and TEST_DATABASE_URL
pointing at a separate, migrated test database; tests/postgres_safety refuses the DATABASE_URL database).

Isolation: each test opens one connection and one outer transaction. Every request gets its own Session bound to
that connection with ``join_transaction_mode="create_savepoint"``, so Service commits only release savepoints
and the outer transaction is rolled back after the test. Nothing a test writes survives it, and real PostgreSQL
constraints, defaults, row locks and SQL aggregates still apply.
"""

import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.database as database
from app.core.auth_state import MemoryStateStore
from app.core.config import AuthSettings
from app.core.dependencies import AuthRuntime, get_runtime
from app.core.security import hash_password
from app.core.sessions import SessionManager
from app.main import app
from app.routers import dependencies as deps
from tests.postgres_safety import (
    POSTGRES_TESTS_ENABLED,
    UnsafePostgresTestDatabase,
    require_separate_test_database,
)

from .support import PASSWORD, Person, Seed, expect

BACKEND = Path(__file__).resolve().parents[2]


def _setting(name: str) -> str:
    return (os.getenv(name) or dotenv_values(BACKEND / ".env").get(name) or "").strip()


class CapturingMailer:
    def __init__(self):
        self.messages = []

    def send_otp(self, email, code, purpose, ttl):
        self.messages.append({"email": email, "code": code, "purpose": purpose})


@pytest.fixture(scope="session")
def api_engine(request):
    if not POSTGRES_TESTS_ENABLED:
        pytest.skip("set RUN_POSTGRES_TESTS=1 to run the API tests against TEST_DATABASE_URL")
    test_url = _setting("TEST_DATABASE_URL")
    try:
        require_separate_test_database(test_url, _setting("DATABASE_URL"))
    except UnsafePostgresTestDatabase as error:
        pytest.fail(str(error), pytrace=False)
    request.getfixturevalue("postgres_test_lock")  # one PostgreSQL test run at a time on this database
    engine = create_engine(test_url, pool_pre_ping=True)
    head = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini"))).get_current_head()
    with engine.connect() as conn:
        version = conn.execute(text("select version_num from alembic_version")).scalar()
    if version != head:
        engine.dispose()
        # Opted in but not migrated: a configuration error, not a reason to report success with nothing run.
        pytest.fail(f"test database is at {version}, expected {head}: run alembic upgrade head on it first",
                    pytrace=False)
    # Start from empty tables: the API tests assume no leftover rows (other suites clean up after themselves).
    with engine.begin() as conn:
        preparer = engine.dialect.identifier_preparer
        tables = conn.execute(text("select tablename from pg_tables where schemaname = 'public' "
                                   "and tablename <> 'alembic_version'")).scalars().all()
        if tables:
            qualified = ", ".join(f"{preparer.quote_identifier('public')}.{preparer.quote_identifier(t)}"
                                  for t in tables)
            conn.execute(text(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def password_hash():
    return hash_password(PASSWORD)


class Api:
    """One test's view of the application: HTTP client, seeding and read-back SQL on the test transaction."""

    def __init__(self, client, sessions, mailer, password_hash):
        self.client = client
        self.sessions = sessions
        self.mailer = mailer
        self.seed = Seed(sessions, password_hash)

    # -------------------------------------------------------------------------------------------- reads/writes

    def scalar(self, sql: str, **params):
        with self.sessions() as db:
            return db.execute(text(sql), params).scalar()

    def execute(self, sql: str, **params):
        with self.sessions() as db:
            db.execute(text(sql), params)
            db.commit()

    # -------------------------------------------------------------------------------------------- actors

    def login(self, person: Person) -> Person:
        portal = "customer" if person.role == "Customer" else "admin"
        body = expect(self.client.post("/auth/login", json={
            "Identifier": person.email, "Password": PASSWORD, "Portal": portal}), 200)
        person.headers = {"Authorization": f"Bearer {body['access_token']}"}
        return person

    def person(self, role: str = "Customer") -> Person:
        return self.login(self.seed.user(role))

    # -------------------------------------------------------------------------------------------- flows

    def shop(self, **variant_options) -> dict:
        """A sellable variant plus shipping and COD payment methods."""
        return {**self.seed.variant(**variant_options), "shipping_id": self.seed.shipping_method(),
                "cod_id": self.seed.payment_method("COD")}

    def place_order(self, customer: Person, shop: dict, *, quantity: int = 1, payment_id: str | None = None) -> dict:
        expect(self.client.post("/cart/items", headers=customer.headers,
                                json={"ProductVariantId": shop["variant_id"], "Quantity": quantity}), 200)
        return expect(self.client.post("/orders", headers=customer.headers, json={
            "ShippingMethodId": shop["shipping_id"], "PaymentMethodId": payment_id or shop["cod_id"],
            "ReceiverName": "Nguyễn Văn A", "ReceiverPhone": "0900000000", "ShippingAddress": "1 Lê Lợi"}), 201)

    def ship(self, order_id: str, staff: Person) -> None:
        for status in ("Confirmed", "Processing", "Shipping"):
            expect(self.client.post(f"/admin/orders/{order_id}/status", headers=staff.headers,
                                    json={"OrderStatus": status}), 200)

    def deliver(self, order_id: str, staff: Person) -> dict:
        """COD order from Pending to Delivered (collection recorded)."""
        self.ship(order_id, staff)
        return expect(self.client.post(f"/admin/orders/{order_id}/confirm-cod-delivery", headers=staff.headers,
                                       json={}), 200)

    def delivered_line(self, customer: Person, staff: Person, shop: dict, *, quantity: int = 1) -> dict:
        """Order item of a delivered COD order: the starting point for reviews, warranty and returns."""
        order = self.place_order(customer, shop, quantity=quantity)
        self.deliver(order["OrderId"], staff)
        return {"order_id": order["OrderId"], "order_item_id": order["Items"][0]["OrderItemId"]}


@pytest.fixture
def api(api_engine, password_hash):
    connection = api_engine.connect()
    outer = connection.begin()
    sessions = sessionmaker(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")

    def test_db():
        with sessions() as db:
            yield db

    settings = AuthSettings(jwt_secret="stage7-api-tests" * 4, app_env="test")
    state, mailer = MemoryStateStore(), CapturingMailer()
    runtime = AuthRuntime(settings, state, mailer, SessionManager(state, settings), password_hash)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update({database.get_db: test_db, get_runtime: lambda: runtime,
                                     deps.get_payment_gateway: lambda: None})
    try:
        with pytest.MonkeyPatch.context() as patch:
            # Code that bypasses get_db (webhook sessions) also stays inside the test transaction.
            patch.setattr(database, "SessionLocal", sessions)
            with TestClient(app) as client:
                yield Api(client, sessions, mailer, password_hash)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        outer.rollback()
        connection.close()


@pytest.fixture
def admin(api) -> Person:
    return api.person("Admin")


@pytest.fixture
def staff(api) -> Person:
    return api.person("Staff")


@pytest.fixture
def customer(api) -> Person:
    return api.person("Customer")


@pytest.fixture
def other_customer(api) -> Person:
    return api.person("Customer")
