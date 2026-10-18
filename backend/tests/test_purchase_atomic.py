"""Purchase draft PATCH through HTTP and real transactions on isolated SQLite.

Never connects to or writes to the configured database. PostgreSQL row locking
continues to use the existing service lock; SQLite exercises validation and rollback.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import Base, ProductVariant, Supplier
from app.routers.dependencies import get_purchase_order_service
from app.routers.errors import service_error_handler
from app.routers.purchasing import admin_router
from app.services import ServiceError
from app.services.purchasing import PurchaseOrderService
from tests.fakes import Factory, InMemoryDB


@pytest.fixture
def purchase():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    now = datetime(2026, 10, 17, 8, tzinfo=timezone.utc)

    @event.listens_for(engine, "connect")
    def functions(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("now", 0, lambda: now.isoformat(" "))
        connection.create_function("num_nonnulls", -1, lambda *values: sum(v is not None for v in values))
        connection.create_function("btrim", 1, lambda value: value.strip() if value is not None else None)

    metadata = MetaData()
    for table in Base.metadata.tables.values():
        copied = table.to_metadata(metadata)
        for column in copied.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
    metadata.create_all(engine)
    db = InMemoryDB(); factory = Factory(db)
    staff, admin = factory.user("Staff"), factory.user("Admin")
    supplier, other_supplier = factory.supplier(), factory.supplier()
    variants = [factory.variant(stock=5), factory.variant(stock=7), factory.variant(stock=9)]
    with engine.begin() as connection:
        for model, objects in db.tables.items():
            for obj in objects.values():
                connection.execute(metadata.tables[model.__tablename__].insert().values(
                    **{c.key: getattr(obj, c.key) for c in model.__table__.columns}))

    app = FastAPI(); app.include_router(admin_router)
    app.add_exception_handler(ServiceError, service_error_handler)
    current = {"actor": factory.actor(staff)}
    app.dependency_overrides[get_current_actor] = lambda: current["actor"]

    def service():
        with Session(engine, autoflush=False) as session:
            yield PurchaseOrderService(session, clock=lambda: now)

    app.dependency_overrides[get_purchase_order_service] = service
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/admin/purchase-orders", json={
            "SupplierId": str(supplier.SupplierId), "Note": "Original",
            "Items": [line(variants[0], 2, "10.25"), line(variants[1], 3, "20.00")],
        })
        assert response.status_code == 201, response.text
        original = response.json()
        yield dict(client=client, engine=engine, current=current, factory=factory, staff=staff, admin=admin,
                   supplier=supplier, other_supplier=other_supplier, variants=variants, original=original,
                   path="/admin/purchase-orders/" + original["PurchaseOrderId"])
    engine.dispose()


def line(variant, quantity=1, price="1.00"):
    return dict(ProductVariantId=str(variant.ProductVariantId), OrderedQuantity=quantity,
                UnitPrice=price, Note=None)


def desired(purchase):
    variants = purchase["variants"]
    return dict(SupplierId=str(purchase["other_supplier"].SupplierId), Note="Changed",
                Items=[line(variants[0], 4, "10.10"), line(variants[2], 5, "20.20")])


def unchanged(purchase):
    response = purchase["client"].get(purchase["path"])
    assert response.status_code == 200, response.text
    assert response.json() == purchase["original"]
    with Session(purchase["engine"]) as session:
        assert [session.get(ProductVariant, v.ProductVariantId).StockQuantity for v in purchase["variants"]] == [5, 7, 9]


def test_atomic_patch_changes_header_retains_line_ids_adds_removes_and_retry_is_idempotent(purchase):
    body = desired(purchase)
    response = purchase["client"].patch(purchase["path"], json=body)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["Note"] == body["Note"] and saved["SupplierId"] == body["SupplierId"]
    assert Decimal(saved["TotalAmount"]) == Decimal("141.40")
    rows = {row["ProductVariantId"]: row for row in saved["Items"]}
    original = {row["ProductVariantId"]: row for row in purchase["original"]["Items"]}
    first = str(purchase["variants"][0].ProductVariantId)
    assert rows[first]["PurchaseOrderItemId"] == original[first]["PurchaseOrderItemId"]
    assert set(rows) == {row["ProductVariantId"] for row in body["Items"]}
    assert all(row["ReceivedQuantity"] == 0 for row in rows.values())
    assert saved["CreatedAt"] == purchase["original"]["CreatedAt"] and saved["Status"] == "Pending"
    retried = purchase["client"].patch(purchase["path"], json=body)
    assert retried.status_code == 200 and retried.json() == saved
    with Session(purchase["engine"]) as session:
        assert [session.get(ProductVariant, v.ProductVariantId).StockQuantity for v in purchase["variants"]] == [5, 7, 9]


def test_invalid_later_line_rolls_back_header_and_earlier_line_change(purchase):
    body = desired(purchase)
    body["Items"][-1]["ProductVariantId"] = str(uuid.uuid4())
    response = purchase["client"].patch(purchase["path"], json=body)
    assert response.status_code == 404, response.text
    unchanged(purchase)


def test_failure_after_all_mutations_and_flush_rolls_back_everything_then_retry_succeeds(purchase):
    original_detail = PurchaseOrderService._detail

    def fail_after_flush(service, po):
        original_detail(service, po)
        raise ServiceError("Simulated response failure")

    with patch.object(PurchaseOrderService, "_detail", fail_after_flush):
        response = purchase["client"].patch(purchase["path"], json=desired(purchase))
    assert response.status_code >= 400
    unchanged(purchase)
    assert purchase["client"].patch(purchase["path"], json=desired(purchase)).status_code == 200


def test_commit_failure_rolls_back_all_flushed_changes(purchase):
    with patch.object(Session, "commit", side_effect=RuntimeError("Simulated commit failure")):
        response = purchase["client"].patch(purchase["path"], json=desired(purchase))
    assert response.status_code == 500
    unchanged(purchase)


@pytest.mark.parametrize("invalid", ["empty", "null", "duplicate", "received", "created_at", "zero_quantity", "negative_price"])
def test_invalid_payload_cannot_partially_save(purchase, invalid):
    body = desired(purchase)
    if invalid == "empty": body["Items"] = []
    elif invalid == "null": body["Items"] = None
    elif invalid == "duplicate": body["Items"] = [body["Items"][0]] * 2
    elif invalid == "received": body["Items"][0]["ReceivedQuantity"] = 99
    elif invalid == "created_at": body["CreatedAt"] = "2026-01-01T00:00:00Z"
    elif invalid == "zero_quantity": body["Items"][0]["OrderedQuantity"] = 0
    else: body["Items"][0]["UnitPrice"] = "-1"
    assert purchase["client"].patch(purchase["path"], json=body).status_code >= 400
    unchanged(purchase)


def test_header_only_patch_remains_compatible(purchase):
    response = purchase["client"].patch(purchase["path"], json={"Note": None})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["Note"] is None
    assert saved["Items"] == purchase["original"]["Items"]
    assert saved["TotalAmount"] == purchase["original"]["TotalAmount"]


def test_linked_inactive_supplier_can_be_kept_but_new_inactive_supplier_is_rejected(purchase):
    with Session(purchase["engine"]) as session:
        for supplier in [purchase["supplier"], purchase["other_supplier"]]:
            session.get(Supplier, supplier.SupplierId).IsActive = False
        session.commit()
    body = desired(purchase)
    rejected = purchase["client"].patch(purchase["path"], json=body)
    assert rejected.status_code == 404, rejected.text
    unchanged(purchase)
    body["SupplierId"] = str(purchase["supplier"].SupplierId)
    accepted = purchase["client"].patch(purchase["path"], json=body)
    assert accepted.status_code == 200, accepted.text


def test_status_changed_after_form_load_blocks_all_draft_changes(purchase):
    purchase["current"]["actor"] = purchase["factory"].actor(purchase["admin"])
    approved = purchase["client"].post(purchase["path"] + "/decision", json={"Status": "Approved"})
    assert approved.status_code == 200, approved.text
    response = purchase["client"].patch(purchase["path"], json=desired(purchase))
    assert response.status_code >= 400
    current = purchase["client"].get(purchase["path"]).json()
    assert current["Note"] == "Original" and current["Items"] == purchase["original"]["Items"]
