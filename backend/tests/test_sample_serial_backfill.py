"""Sample Serial/IMEI backfill: dry-run writes nothing; apply numbers stock and Pending units once, atomically."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import JSON, MetaData, create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base, ProductSerial, ProductVariant
from app.services import ConflictError
from app.services.inventory import InventoryService
from scripts.backfill_sample_serials import run
from tests.fakes import Factory, InMemoryDB


@pytest.fixture
def catalog():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def functions(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("now", 0, lambda: datetime(2026, 10, 23, tzinfo=timezone.utc).isoformat(" "))
        connection.create_function("num_nonnulls", -1, lambda *values: sum(v is not None for v in values))
        connection.create_function("btrim", 1, lambda value: value.strip() if value is not None else None)
        connection.create_function("greatest", -1, lambda *values: max(values))

    metadata = MetaData()
    for table in Base.metadata.tables.values():
        for column in table.to_metadata(metadata).columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
    metadata.create_all(engine)
    db = InMemoryDB(); factory = Factory(db)
    customer, payment = factory.user(), factory.payment_method("COD")
    stocked, empty, tracked = factory.variant(stock=10), factory.variant(stock=0), factory.variant(stock=1, serial_tracked=True)
    deleted = factory.variant(stock=4); deleted.IsDeleted = True
    db.add(ProductSerial(ProductVariantId=tracked.ProductVariantId, SerialNumber="REAL-1", Status="Available"))
    factory.order(customer, payment, status="Pending", lines=((stocked, 2),))
    factory.order(customer, payment, status="Delivered", lines=((stocked, 1),))
    with engine.begin() as connection:
        for model, objects in db.tables.items():
            for obj in objects.values():
                connection.execute(metadata.tables[model.__tablename__].insert().values(
                    **{c.key: getattr(obj, c.key) for c in model.__table__.columns}))
    yield dict(engine=engine, stocked=stocked, empty=empty, tracked=tracked, deleted=deleted)
    engine.dispose()


def serials_of(session, variant):
    return sorted(session.scalars(select(ProductSerial.SerialNumber).where(
        ProductSerial.ProductVariantId == variant.ProductVariantId)))


def tracking_of(session, variant):
    return session.get(ProductVariant, variant.ProductVariantId).IsSerialTracked


def test_dry_run_reports_plan_without_writing(catalog):
    with Session(catalog["engine"]) as session:
        report, serials = run(InventoryService(session), apply=False)
        session.rollback()
        assert (report["Variants"], report["Serials"], report["VariantsWithoutStock"]) == (2, 12, 1)
        assert report["UnnumberedOrderLines"] == {"Delivered": 1}
        sku = catalog["stocked"].Sku
        assert serials[0] == (sku, f"VT-SN-{sku}-001") and serials[-1] == (sku, f"VT-SN-{sku}-012")
        assert session.scalar(select(func.count(ProductSerial.ProductSerialId))) == 1
        assert not tracking_of(session, catalog["stocked"]) and not tracking_of(session, catalog["empty"])


def test_apply_numbers_stock_and_pending_units_then_rerun_skips(catalog):
    stocked, empty, tracked, deleted = (catalog[k] for k in ("stocked", "empty", "tracked", "deleted"))
    with Session(catalog["engine"]) as session:
        report, _ = run(InventoryService(session), apply=True)
        assert (report["Variants"], report["Serials"], report["MismatchedAfterApply"]) == (2, 12, [])
    with Session(catalog["engine"]) as session:
        variant = session.get(ProductVariant, stocked.ProductVariantId)
        assert (variant.IsSerialTracked, variant.StockQuantity) == (True, 10)
        assert serials_of(session, stocked) == [f"VT-SN-{stocked.Sku}-{n:03d}" for n in range(1, 13)]
        assert set(session.scalars(select(ProductSerial.Status).where(
            ProductSerial.ProductVariantId == stocked.ProductVariantId))) == {"Available"}
        assert tracking_of(session, empty) and serials_of(session, empty) == []
        assert serials_of(session, tracked) == ["REAL-1"]
        assert not tracking_of(session, deleted) and serials_of(session, deleted) == []
        report, serials = run(InventoryService(session), apply=True)
        assert (report["Variants"], serials) == (0, [])


def test_existing_code_rolls_back_whole_batch(catalog):
    stocked, empty = catalog["stocked"], catalog["empty"]
    with Session(catalog["engine"]) as session:
        session.add(ProductSerial(ProductVariantId=catalog["tracked"].ProductVariantId,
                                  SerialNumber=f"VT-SN-{stocked.Sku}-005", Status="Sold"))
        session.commit()
        with pytest.raises(ConflictError):
            run(InventoryService(session), apply=True)
    with Session(catalog["engine"]) as session:
        assert not tracking_of(session, stocked) and not tracking_of(session, empty)
        assert serials_of(session, stocked) == []
