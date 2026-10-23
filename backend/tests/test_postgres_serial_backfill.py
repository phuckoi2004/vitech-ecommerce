"""Sample Serial/IMEI backfill on real PostgreSQL: row locks, aggregates and the order confirmation that follows.

Opt-in like test_postgres_integration (whose fixtures it reuses): RUN_POSTGRES_TESTS=1 and a dedicated, migrated
TEST_DATABASE_URL. Every table except alembic_version is TRUNCATEd before and after.

    RUN_POSTGRES_TESTS=1 python -m pytest tests/test_postgres_serial_backfill.py -v
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.services.inventory import InventoryService
from scripts.backfill_sample_serials import run as backfill_serials
from tests.postgres_safety import POSTGRES_TESTS_ENABLED
from tests.test_postgres_integration import (  # noqa: F401
    fill_cart, methods, new_customer, ok, pg, stock_of, team,
)

pytestmark = pytest.mark.skipif(not POSTGRES_TESTS_ENABLED,
                                reason="set RUN_POSTGRES_TESTS=1 to run against TEST_DATABASE_URL")


def untracked_variant(pg, team, *, quantity):
    """A SKU like the sample catalog: created without Serial/IMEI tracking, stocked by an Opening declaration."""
    client, admin = pg.client, team["admin"]
    tag = uuid.uuid4().hex[:8]
    category = ok(client.post("/admin/categories", headers=admin, json={"Name": f"Tai nghe {tag}",
                                                                       "Slug": f"tai-nghe-{tag}"}), 201)
    brand = ok(client.post("/admin/brands", headers=admin, json={"Name": f"Hãng {tag}", "Slug": f"hang-{tag}"}), 201)
    product = ok(client.post("/admin/products", headers=admin, json={
        "CategoryId": category["CategoryId"], "BrandId": brand["BrandId"], "Name": f"Tai nghe {tag}",
        "Slug": f"tn-{tag}", "WarrantyMonths": 12, "Status": "Active"}), 201)
    variant = ok(client.post("/admin/variants", headers=admin, json={
        "ProductId": product["ProductId"], "Sku": f"VT-DEMO-{tag.upper()}", "VariantName": "Mặc định",
        "Price": "100000.00", "IsSerialTracked": False}), 201)
    ok(client.post(f"/admin/variants/{variant['ProductVariantId']}/stock-opening", headers=admin, json={
        "Quantity": quantity, "UnitCost": "80000.00", "Reason": "Tồn mẫu kiểm thử"}), 201)
    return {"product": product, "variant": variant}


def test_backfill_numbers_stock_and_pending_units_then_confirmation_reserves_them(pg, team, methods):
    item = untracked_variant(pg, team, quantity=10)
    variant_id, sku = item["variant"]["ProductVariantId"], item["variant"]["Sku"]
    _, customer = new_customer(pg)
    fill_cart(pg, customer, item, 2)
    order = ok(pg.client.post("/orders", headers=customer, json={
        "ShippingMethodId": methods["shipping"], "PaymentMethodId": methods["cod"], "ReceiverName": "Khách",
        "ReceiverPhone": "0900000000", "ShippingAddress": "1 Đường A"}), 201)
    assert stock_of(pg, item) == 8

    with Session(pg.engine) as session:
        preview, planned = backfill_serials(InventoryService(session), apply=False)
    assert pg.scalar('select count(*) from "ProductSerials"') == 0
    with Session(pg.engine) as session:
        report, applied = backfill_serials(InventoryService(session), apply=True)
    assert applied == planned and report["Serials"] == preview["Serials"]
    assert [number for owner, number in applied if owner == sku] == [f"VT-SN-{sku}-{n:03d}" for n in range(1, 11)]
    assert report["MismatchedAfterApply"] == []
    assert pg.scalar('select "IsSerialTracked" from "ProductVariants" where "ProductVariantId" = :id',
                     id=variant_id) is True
    assert stock_of(pg, item) == 8

    moved = ok(pg.client.post(f"/admin/orders/{order['OrderId']}/status", headers=team["staff"],
                              json={"OrderStatus": "Confirmed"}))
    assert moved["OrderStatus"] == "Confirmed"
    count = 'select count(*) from "ProductSerials" where "ProductVariantId" = :id and "Status" = :status'
    assert pg.scalar(count, id=variant_id, status="Reserved") == 2
    assert pg.scalar(count, id=variant_id, status="Available") == 8

    with Session(pg.engine) as session:
        rerun, _ = backfill_serials(InventoryService(session), apply=True)
    assert rerun["Variants"] == 0
