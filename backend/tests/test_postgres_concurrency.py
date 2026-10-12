"""Opt-in PostgreSQL regressions for overlapping checkout and default-address writes.

Uses the dedicated-database safeguards and destructive setup/cleanup of
test_postgres_integration. Never runs unless RUN_POSTGRES_TESTS=1; no production
database or external gateway is used. Offline suites skip these tests explicitly.
"""

import threading
import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.models import User
from app.schemas import AddressCreate, OrderCreate
from app.schemas.account import DefaultAddressUpdate
from app.services import Actor
from app.services.exceptions import ServiceError
from app.services.order import OrderService
from app.services.user import AddressService, UserService
from tests.postgres_safety import POSTGRES_TESTS_ENABLED

from tests.test_postgres_integration import (
    fill_cart,
    methods as methods,
    new_customer,
    pg as pg,
    stock_of,
    stocked_variant,
    team as team,
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_TESTS_ENABLED,
    reason="opt-in concurrency tests require the protected TEST_DATABASE_URL",
)


def overlapping_calls(engine, first_call, second_call, *, lock_table):
    """Pause A after its read, start B, then let A commit before B continues.

    With the fix, B blocks at the shared row lock and reads A's committed state.
    Before the fix, B reaches its mutation with the old read instead; the second
    hook waits for A's commit, recreating the reported race deterministically.
    The hooks retain the real SQL/transactions and never fake a lock or result.
    """
    first_read = threading.Event()
    release_first = threading.Event()
    first_finished = threading.Event()
    second_reached = threading.Event()
    local = threading.local()
    results = {}
    timeout = 15

    def first_step(operation, *args, **kwargs):
        first_read.set()
        assert release_first.wait(timeout), "first request was not released"
        return operation(*args, **kwargs)

    def second_step(operation, *args, **kwargs):
        second_reached.set()
        assert first_finished.wait(timeout), "first request did not finish"
        return operation(*args, **kwargs)

    def before_execute(conn, cursor, statement, parameters, context, executemany):
        if (getattr(local, "request", None) == "second"
                and f'"{lock_table}"' in statement and "FOR UPDATE" in statement):
            second_reached.set()

    def run(name, operation, step):
        local.request = name
        try:
            with Session(engine, autoflush=False) as session:
                session.execute(text("SET LOCAL lock_timeout = '15s'"))
                session.execute(text("SET LOCAL statement_timeout = '20s'"))
                results[name] = ("ok", operation(session, step))
        except ServiceError as error:
            results[name] = ("refused", error.code)
        except Exception as error:
            # Retain the failure type without printing connection credentials.
            results[name] = ("error", type(error).__name__)
        finally:
            if name == "first":
                first_finished.set()

    first = threading.Thread(target=run, args=("first", first_call, first_step), daemon=True)
    second = threading.Thread(target=run, args=("second", second_call, second_step), daemon=True)
    event.listen(engine, "before_cursor_execute", before_execute)
    try:
        first.start()
        assert first_read.wait(timeout), results
        second.start()
        assert second_reached.wait(timeout), results
        release_first.set()
        first.join(timeout + 5)
        second.join(timeout + 5)
        assert not first.is_alive() and not second.is_alive(), "concurrent requests did not finish"
        assert set(results) == {"first", "second"}, results
        return results
    finally:
        release_first.set()
        first.join(timeout + 5)
        if second.ident is not None:
            second.join(timeout + 5)
        event.remove(engine, "before_cursor_execute", before_execute)


def test_two_checkouts_of_the_same_cart_create_one_order_even_with_spare_stock(pg, team, methods):
    item = stocked_variant(pg, team, quantity=5)
    customer, headers = new_customer(pg)
    fill_cart(pg, headers, item, 1)
    actor = Actor(uuid.UUID(customer["id"]), "Customer")
    payload = OrderCreate(
        ShippingMethodId=methods["shipping"], PaymentMethodId=methods["cod"],
        ReceiverName="Khách", ReceiverPhone="0900000000", ShippingAddress="1 Đường A",
    )

    def checkout(session, step):
        service = OrderService(session)
        original = service.variants.get_many_by_ids_for_update
        service.variants.get_many_by_ids_for_update = lambda ids: step(original, ids)
        return service.create_order(actor, payload).OrderId

    results = overlapping_calls(pg.engine, checkout, checkout, lock_table="Carts")
    assert results["first"][0] == "ok", results
    assert results["second"] == ("refused", "cart_empty"), results
    assert stock_of(pg, item) == 4
    assert pg.scalar('SELECT count(*) FROM "Orders" WHERE "CustomerId" = :id',
                     id=customer["id"]) == 1
    assert pg.scalar('SELECT count(*) FROM "CartItems" i JOIN "Carts" c USING ("CartId") '
                     'WHERE c."UserId" = :id', id=customer["id"]) == 0


@pytest.mark.parametrize("second_api", ["address_book", "profile_default"])
def test_overlapping_address_apis_keep_one_active_default(pg, second_api):
    customer, _ = new_customer(pg)
    owner = uuid.UUID(customer["id"])
    actor = Actor(owner, "Customer")

    def address_payload(detail):
        return AddressCreate(ReceiverName="Khách", ReceiverPhone="0900000000",
                             Province="Hà Nội", Ward="Hoàn Kiếm",
                             DetailAddress=detail, IsDefault=True)

    def first_address(session, step):
        service = AddressService(session)
        original = service.addresses.create
        service.addresses.create = lambda values: step(original, values)
        return service.create_address(actor, address_payload("Địa chỉ A")).AddressId

    def second_address(session, step):
        if second_api == "address_book":
            service = AddressService(session)
            original = service.addresses.create
            service.addresses.create = lambda values: step(original, values)
            return service.create_address(actor, address_payload("Địa chỉ B")).AddressId
        service = UserService(session, runtime=None)
        original = service.addresses.create
        service.addresses.create = lambda values: step(original, values)
        return service.save_default_address(
            session.get(User, owner),
            DefaultAddressUpdate(Province="Hà Nội", Ward="Hoàn Kiếm", DetailAddress="Địa chỉ B"),
        ).AddressId

    results = overlapping_calls(pg.engine, first_address, second_address, lock_table="Users")
    assert results["first"][0] == results["second"][0] == "ok", results
    assert pg.scalar('SELECT count(*) FROM "Addresses" WHERE "UserId" = :id '
                     'AND "IsDefault" AND NOT "IsDeleted"', id=owner) == 1
    assert pg.scalar('SELECT "DetailAddress" FROM "Addresses" WHERE "UserId" = :id '
                     'AND "IsDefault" AND NOT "IsDeleted"', id=owner) == "Địa chỉ B"
    if second_api == "profile_default":
        assert results["first"][1] == results["second"][1], results
