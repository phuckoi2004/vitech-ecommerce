"""Two-request address workflows using SQLite and a deterministic user-row lock simulator.

SQLite does not implement FOR UPDATE. The simulator waits only when the real
SQLAlchemy statement requests a Users row lock, and releases it on transaction
end. Address reads/writes still use real repositories and separate SQLAlchemy
identity maps. This verifies application serialization, not live PostgreSQL locks.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Lock
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from app.core.errors import AuthError
from app.models import Address, User
from app.repositories.user import UserRepository
from app.schemas.account import DefaultAddressUpdate
from app.schemas.user import AddressCreate, AddressUpdate
from app.services import Actor, NotFoundError, PermissionDeniedError
from app.services.user import AddressService, UserService


class RequestSession(Session):
    pass


@pytest.fixture
def address_database():
    # A named in-memory database lets separate connections share test rows without filesystem state.
    engine = create_engine(
        f"sqlite+pysqlite:///file:addresses_{uuid.uuid4().hex}?mode=memory&cache=shared&uri=true",
        poolclass=QueuePool, connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def defaults(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    User.__table__.create(engine)
    Address.__table__.create(engine)
    owner_id = uuid.uuid4()
    with Session(engine) as db:
        db.add(User(UserId=owner_id, Email=f"{owner_id.hex}@example.com", PhoneNumber="0912345678",
                    FullName="Address owner", PasswordHash="test-only", Role="Customer",
                    AccountStatus="Active", IsDeleted=False))
        db.commit()
    yield engine, owner_id
    engine.dispose()


def address_payload(detail):
    return AddressCreate(ReceiverName="Owner", ReceiverPhone="0912345678", Province="Hà Nội",
                         Ward="Hoàn Kiếm", DetailAddress=detail, IsDefault=True)


def save(api, db, owner_id, detail):
    if api == "profile":
        owner = db.get(User, owner_id)
        return UserService(db, SimpleNamespace()).save_default_address(owner, DefaultAddressUpdate(
            Province="Hà Nội", Ward="Hoàn Kiếm", DetailAddress=detail))
    return AddressService(db).create_address(Actor(owner_id, "Customer"), address_payload(detail))


def two_requests(engine, first, second, *, second_preload=()):
    """Hold request 1's owner lock until request 2 attempts that same lock."""
    owner_lock = Lock()
    first_locked, second_waiting, release_first = Event(), Event(), Event()

    def before_read(state):
        label = state.session.info.get("request")
        if label is None:
            return
        mapper = state.bind_mapper
        if mapper is not None and mapper.class_ is User and state.statement._for_update_arg is not None:
            if not (state.session.info.get("owner_locked") or state.session.info.get("holds_owner_lock")):
                if label == "second":
                    second_waiting.set()
                assert owner_lock.acquire(timeout=5), "Owner lock was never released"
                state.session.info["owner_locked"] = True
                if label == "first":
                    first_locked.set()
                    assert release_first.wait(5), "Second request never attempted the owner lock"
        elif mapper is not None and mapper.class_ is Address:
            assert (state.session.info.get("owner_locked") or state.session.info.get("preloading")
                    or state.session.info.get("committed")), "Address read happened before locking its owner"

    def after_commit(db):
        db.info["committed"] = True

    def end_transaction(db, transaction):
        # PostgreSQL releases the row lock at commit. Here it is released when the request's session closes
        # (see run): in SQLite shared-cache mode a post-commit read (save_default_address refreshes the
        # address) holds a table lock that would make the other request's write fail with "table is locked".
        if transaction.parent is None and db.info.pop("owner_locked", False):
            db.info["holds_owner_lock"] = True

    def run(label, action):
        db = RequestSession(engine, autoflush=False, expire_on_commit=False)
        try:
            with db:
                db.info["request"] = label
                # Authentication and earlier reads can leave stale objects in the identity map.
                owner = db.scalar(select(User))
                db.info["preloading"] = True
                preloaded = [db.get(Address, key) for key in second_preload] if label == "second" else []
                db.info["preloading"] = False
                result = action(db, owner.UserId)
                # Keep strong references until after the use case; SQLAlchemy's identity map uses weak refs.
                assert owner is not None and all(item is not None for item in preloaded)
                return result
        finally:
            if db.info.pop("holds_owner_lock", False):
                owner_lock.release()

    event.listen(RequestSession, "do_orm_execute", before_read)
    event.listen(RequestSession, "after_commit", after_commit)
    event.listen(RequestSession, "after_transaction_end", end_transaction)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_task = executor.submit(run, "first", first)
            try:
                assert first_locked.wait(5), "First mutation did not lock the owner"
                second_task = executor.submit(run, "second", second)
                assert second_waiting.wait(5), "Second mutation did not use the shared owner lock"
            finally:
                release_first.set()
            return first_task.result(timeout=5), second_task.result(timeout=5)
    finally:
        event.remove(RequestSession, "do_orm_execute", before_read)
        event.remove(RequestSession, "after_commit", after_commit)
        event.remove(RequestSession, "after_transaction_end", end_transaction)


@pytest.mark.parametrize("first_api", ["profile", "book"])
@pytest.mark.parametrize("second_api", ["profile", "book"])
def test_two_requests_and_cross_api_saves_keep_one_default(address_database, first_api, second_api):
    engine, _ = address_database
    two_requests(engine,
                 lambda db, owner: save(first_api, db, owner, "First request"),
                 lambda db, owner: save(second_api, db, owner, "Second request"))
    with Session(engine) as db:
        rows = db.scalars(select(Address).where(Address.IsDeleted.is_(False))).all()
        assert len(rows) == (2 if second_api == "book" else 1)
        defaults = [row for row in rows if row.IsDefault]
        assert len(defaults) == 1
        assert defaults[0].DetailAddress == "Second request"


def seed_addresses(engine, owner, count=1):
    with Session(engine, expire_on_commit=False) as db:
        rows = [Address(AddressId=uuid.uuid4(), UserId=owner, ReceiverName="Owner", ReceiverPhone="0912345678",
                        Province="Hà Nội", Ward="Hoàn Kiếm", DetailAddress=f"Initial {i}",
                        IsDefault=i == 0, IsDeleted=False) for i in range(count)]
        db.add_all(rows)
        db.commit()
        return [row.AddressId for row in rows]


def test_delete_then_profile_save_creates_new_default_instead_of_editing_deleted_row(address_database):
    engine, owner = address_database
    [original] = seed_addresses(engine, owner)
    _, saved = two_requests(engine,
                           lambda db, key: AddressService(db).delete_address(Actor(key, "Customer"), original),
                           lambda db, key: save("profile", db, key, "Replacement"), second_preload=[original])
    assert saved.AddressId != original and saved.IsDefault
    with Session(engine) as db:
        old = db.get(Address, original)
        assert old.IsDeleted and not old.IsDefault and old.DetailAddress == "Initial 0"
        defaults = db.scalars(select(Address).where(Address.IsDefault.is_(True), Address.IsDeleted.is_(False))).all()
        assert [row.AddressId for row in defaults] == [saved.AddressId]


def test_profile_save_then_delete_leaves_no_active_default(address_database):
    engine, owner = address_database
    [original] = seed_addresses(engine, owner)
    two_requests(engine, lambda db, key: save("profile", db, key, "Saved before deletion"),
                 lambda db, key: AddressService(db).delete_address(Actor(key, "Customer"), original),
                 second_preload=[original])
    with Session(engine) as db:
        old = db.get(Address, original)
        assert old.IsDeleted and not old.IsDefault and old.DetailAddress == "Saved before deletion"
        assert db.scalars(select(Address).where(Address.IsDeleted.is_(False))).all() == []


def test_waiting_update_rejects_address_deleted_after_its_earlier_read(address_database):
    engine, owner = address_database
    [original] = seed_addresses(engine, owner)
    with pytest.raises(NotFoundError):
        two_requests(engine,
                     lambda db, key: AddressService(db).delete_address(Actor(key, "Customer"), original),
                     lambda db, key: AddressService(db).update_address(
                         Actor(key, "Customer"), original, AddressUpdate(DetailAddress="Must not be saved")),
                     second_preload=[original])
    with Session(engine) as db:
        old = db.get(Address, original)
        assert old.IsDeleted and not old.IsDefault and old.DetailAddress == "Initial 0"


@pytest.mark.parametrize("second_api", ["profile", "book"])
def test_waiting_save_refreshes_an_address_that_became_default(address_database, second_api):
    engine, owner = address_database
    original, promoted = seed_addresses(engine, owner, count=2)
    _, saved = two_requests(engine,
                           lambda db, key: AddressService(db).update_address(
                               Actor(key, "Customer"), promoted, AddressUpdate(IsDefault=True)),
                           lambda db, key: save(second_api, db, key, "Latest request"), second_preload=[promoted])
    assert saved.IsDefault
    if second_api == "profile":
        assert saved.AddressId == promoted
    with Session(engine) as db:
        rows = db.scalars(select(Address)).all()
        assert [row.AddressId for row in rows if row.IsDefault and not row.IsDeleted] == [saved.AddressId]
        assert not db.get(Address, original).IsDefault


@pytest.mark.parametrize("api", ["profile", "book"])
@pytest.mark.parametrize("change", [{"AccountStatus": "Locked"}, {"IsDeleted": True}])
def test_waiting_mutation_rechecks_account_after_admin_lock_or_delete(address_database, api, change):
    engine, _ = address_database

    def administration(db, key):
        owner = UserRepository(db).get_by_id_for_update(key)
        for name, value in change.items():
            setattr(owner, name, value)
        db.commit()

    expected = AuthError if api == "profile" else PermissionDeniedError
    with pytest.raises(expected):
        two_requests(engine, administration, lambda db, owner: save(api, db, owner, "Must not be created"))
    with Session(engine) as db:
        assert db.scalars(select(Address)).all() == []
