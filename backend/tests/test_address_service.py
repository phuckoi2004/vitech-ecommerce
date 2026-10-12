"""Sổ địa chỉ theo quyền giai đoạn 4: chỉ Customer, mỗi người chỉ thấy địa chỉ của mình; SQLite only."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.models import Address, User
from app.schemas.user import AddressCreate, AddressUpdate
from app.services import Actor, AddressService, NotFoundError, PermissionDeniedError


@pytest.fixture
def address_context():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def defaults(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    User.__table__.create(engine)
    Address.__table__.create(engine)
    with Session(engine, autoflush=False) as db:
        yield db, AddressService(db)
    engine.dispose()


def add_actor(db, role):
    key = uuid.uuid4()
    user = User(UserId=key, Email=f"{key.hex}@example.com", PhoneNumber=key.hex[:20],
                FullName="Address owner", PasswordHash="test-only", Role=role,
                AccountStatus="Active", IsDeleted=False)
    db.add(user)
    db.commit()
    return Actor(user.UserId, role)


def new_address(detail="First", *, default=False):
    return AddressCreate(ReceiverName="Owner", ReceiverPhone="0912345678",
                         Province="Hà Nội", Ward="Hoàn Kiếm", DetailAddress=detail,
                         IsDefault=default)


def test_customer_manages_own_addresses_and_switches_the_default(address_context):
    db, service = address_context
    owner = add_actor(db, "Customer")
    first = service.create_address(owner, new_address(default=True))
    second = service.create_address(owner, new_address("Second", default=True))
    addresses = service.list_addresses(owner)
    assert {address.AddressId for address in addresses} == {first.AddressId, second.AddressId}
    assert [address.AddressId for address in addresses if address.IsDefault] == [second.AddressId]
    updated = service.update_address(owner, first.AddressId,
                                     AddressUpdate(DetailAddress="Updated", IsDefault=True))
    assert updated.DetailAddress == "Updated"
    assert service.get_address(owner, first.AddressId).IsDefault
    assert not service.get_address(owner, second.AddressId).IsDefault
    service.delete_address(owner, first.AddressId)
    assert [address.AddressId for address in service.list_addresses(owner)] == [second.AddressId]
    assert db.get(Address, first.AddressId).IsDeleted


def test_switch_flushes_old_default_before_inserting_or_promoting_another(address_context):
    db, service = address_context
    # Test-only uniqueness makes write ordering observable; production uses the shared owner lock.
    db.execute(text('CREATE UNIQUE INDEX "UX_Test_Address_Default" ON "Addresses" ("UserId") '
                    'WHERE "IsDefault" = 1 AND "IsDeleted" = 0'))
    db.commit()
    owner = add_actor(db, "Customer")
    first = service.create_address(owner, new_address(default=True))
    second = service.create_address(owner, new_address("Second", default=True))
    service.update_address(owner, first.AddressId, AddressUpdate(IsDefault=True))
    addresses = service.list_addresses(owner)
    assert [address.AddressId for address in addresses if address.IsDefault] == [first.AddressId]
    assert not service.get_address(owner, second.AddressId).IsDefault


def test_customer_cannot_read_change_or_delete_someone_elses_address(address_context):
    db, service = address_context
    owner = add_actor(db, "Customer")
    intruder = add_actor(db, "Customer")
    address = service.create_address(owner, new_address(default=True))
    assert service.list_addresses(intruder) == []
    for action in (
        lambda: service.get_address(intruder, address.AddressId),
        lambda: service.update_address(intruder, address.AddressId, AddressUpdate(DetailAddress="Hijacked")),
        lambda: service.delete_address(intruder, address.AddressId),
    ):
        with pytest.raises(NotFoundError):
            action()
    saved = service.get_address(owner, address.AddressId)
    assert saved.DetailAddress == "First" and saved.IsDefault


def test_address_book_rejects_anonymous_access(address_context):
    _, service = address_context
    with pytest.raises(PermissionDeniedError):
        service.create_address(None, new_address())


@pytest.mark.parametrize("role", ["Staff", "Admin"])
def test_internal_roles_have_no_address_book(address_context, role):
    db, service = address_context
    actor = add_actor(db, role)
    with pytest.raises(PermissionDeniedError):
        service.create_address(actor, new_address())
    with pytest.raises(PermissionDeniedError):
        service.list_addresses(actor)
    assert db.query(Address).count() == 0
