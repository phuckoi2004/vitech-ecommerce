"""HTTP + real repositories/transactions on isolated SQLite; never use DATABASE_URL.

Exercises the full coupon/order workflow, but does not substitute for PostgreSQL row-lock tests.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import Base, Coupon, Promotion, ProductVariant, Cart, CartItem
from app.routers.dependencies import get_coupon_service, get_promotion_service, get_order_service
from app.routers.promotions import admin_router, router
from app.routers.orders import router as orders_router
from app.routers.errors import service_error_handler
from app.services import ServiceError
from app.services.order import OrderService
from app.services.promotion import CouponService, PromotionService
from tests.fakes import Factory, InMemoryDB


@pytest.fixture
def shop():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    now = {"value": datetime(2026, 10, 17, 8, tzinfo=timezone.utc)}

    @event.listens_for(engine, "connect")
    def functions(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("now", 0, lambda: now["value"].isoformat(" "))
        connection.create_function("num_nonnulls", -1, lambda *values: sum(v is not None for v in values))
        connection.create_function("btrim", 1, lambda value: value.strip() if value is not None else None)

    metadata = MetaData()
    for table in Base.metadata.tables.values():
        copy = table.to_metadata(metadata)
        for column in copy.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
    metadata.create_all(engine)
    db = InMemoryDB(); factory = Factory(db)
    admin, customer = factory.user("Admin"), factory.user()
    variant = factory.variant(stock=10, price="100000.00")
    other = factory.variant(stock=10)
    shipping, payment = factory.shipping_method(), factory.payment_method("COD")
    with engine.begin() as connection:
        for model, objects in db.tables.items():
            for obj in objects.values():
                connection.execute(metadata.tables[model.__tablename__].insert().values(
                    **{c.key: getattr(obj, c.key) for c in model.__table__.columns}))

    current = {"actor": factory.actor(admin)}
    app = FastAPI(); app.include_router(admin_router); app.include_router(router); app.include_router(orders_router)
    app.add_exception_handler(ServiceError, service_error_handler)
    app.dependency_overrides[get_current_actor] = lambda: current["actor"]

    def dependency(service):
        def provide():
            with Session(engine) as session:
                yield service(session, clock=lambda: now["value"])
        return provide

    app.dependency_overrides[get_promotion_service] = dependency(PromotionService)
    app.dependency_overrides[get_coupon_service] = dependency(CouponService)
    app.dependency_overrides[get_order_service] = dependency(OrderService)
    with TestClient(app) as client:
        yield dict(client=client, engine=engine, now=now, current=current, admin=admin,
                   customer=customer, factory=factory, variant=variant, other=other,
                   shipping=shipping, payment=payment)
    engine.dispose()


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def create(shop, *, status="Scheduled", start=None, end=None, limit=1, products=()):
    now = shop["now"]["value"]
    client = shop["client"]
    program = ok(client.post("/admin/promotions", json={
        "Name": "CT thử nghiệm", "Status": status, "DiscountType": "Percentage", "DiscountValue": "10",
        "MinOrderValue": "0", "StartDate": (start or now + timedelta(hours=1)).isoformat(),
        "EndDate": (end or now + timedelta(days=1)).isoformat(), "ProductIds": list(products),
    }), 201)
    code = ok(client.post("/admin/coupons", json={"PromotionId": program["PromotionId"],
        "Name": "Mã thử nghiệm", "Code": "TEST10", "UsageLimit": limit}), 201)
    return program, code


def test_parent_and_coupon_follow_server_time_without_changing_computer_clock(shop):
    client, now = shop["client"], shop["now"]
    parent, code = create(shop)
    assert (code["Status"], code["IsActive"]) == ("Upcoming", False)
    now["value"] += timedelta(hours=1)  # inclusive start
    rows = ok(client.get("/admin/promotions", params={"status": "Active"}))
    assert rows["Total"] == 1 and rows["Items"][0]["Status"] == "Active"
    active = ok(client.get("/admin/coupons/" + code["CouponId"]))
    assert (active["Status"], active["IsActive"]) == ("Active", True)
    assert active["CreatedByName"] == shop["admin"].FullName
    assert rows["Items"][0]["CreatedByName"] == shop["admin"].FullName
    now["value"] = datetime.fromisoformat(parent["EndDate"])
    assert ok(client.get("/admin/coupons/" + code["CouponId"]))["IsActive"] is True
    now["value"] += timedelta(microseconds=1)
    assert ok(client.get("/admin/promotions/" + parent["PromotionId"]))["Status"] == "Expired"
    expired = ok(client.get("/admin/coupons/" + code["CouponId"]))
    assert (expired["Status"], expired["IsActive"]) == ("Ended", False)
    assert ok(client.get(f"/admin/promotions/{parent['PromotionId']}/coupons", params={"is_active": True})) == []
    with Session(shop["engine"]) as session:
        assert session.get(Coupon, uuid.UUID(code["CouponId"])).IsActive is False


def test_atomic_patch_saves_name_and_scope_together_and_rolls_back_on_late_failure(shop):
    parent, _ = create(shop, products=[str(shop["variant"].ProductId)])
    path = "/admin/promotions/" + parent["PromotionId"]
    body = {"Name": "Tên mới", "ProductIds": [str(shop["other"].ProductId)], "CategoryIds": []}
    # Fail AFTER both mutations/flushes; transaction must undo metadata and association rows.
    with patch("app.repositories.promotion.CouponRepository.synchronize", side_effect=ServiceError("Lỗi lưu")):
        response = shop["client"].patch(path, json=body)
    assert response.status_code >= 400
    unchanged = ok(shop["client"].get(path))
    assert unchanged["Name"] == parent["Name"]
    assert unchanged["Products"] == parent["Products"]
    saved = ok(shop["client"].patch(path, json=body))
    assert saved["Name"] == body["Name"]
    assert saved["Products"] == [{"ProductId": str(shop["other"].ProductId)}]


def test_invalid_scope_keeps_name_and_targets_unchanged(shop):
    parent, _ = create(shop)
    path = "/admin/promotions/" + parent["PromotionId"]
    assert shop["client"].patch(path, json={"Name": "Không lưu", "ProductIds": [str(uuid.uuid4())]}).status_code == 404
    unchanged = ok(shop["client"].get(path))
    assert unchanged["Name"] == parent["Name"] and unchanged["Products"] == []


def test_no_manual_pause_and_zero_limit_is_exhausted_and_ending_overrides_it(shop):
    parent, code = create(shop, start=shop["now"]["value"], limit=0)
    path = "/admin/coupons/" + code["CouponId"]
    assert (code["Status"], code["IsActive"]) == ("Exhausted", False)
    # Increasing quota reopens a code automatically. Legacy IsActive is never an admin override.
    edited = ok(shop["client"].patch(path, json={"UsageLimit": 2, "IsActive": False}))
    assert (edited["Status"], edited["IsActive"]) == ("Active", True)
    ok(shop["client"].post("/admin/promotions/" + parent["PromotionId"] + "/cancel"))
    ended = ok(shop["client"].get(path))
    assert (ended["Status"], ended["IsActive"]) == ("Ended", False)


def test_parent_already_started_locks_scope_even_if_old_client_thinks_it_is_scheduled(shop):
    parent, _ = create(shop)
    shop["now"]["value"] += timedelta(hours=2)
    path = "/admin/promotions/" + parent["PromotionId"]
    response = shop["client"].patch(path, json={"Name": "Không lưu", "ProductIds": [str(shop["other"].ProductId)]})
    assert response.status_code == 400 and response.json()["code"] == "promotion_active_locked"
    assert ok(shop["client"].get(path))["Name"] == parent["Name"]


def test_coupon_checkout_consumes_last_use_and_order_cancel_reopens_it(shop):
    client = shop["client"]
    parent, code = create(shop)
    # No admin visit after the clock crosses start: checkout must still allow the scheduled program.
    shop["now"]["value"] += timedelta(hours=2)
    shop["current"]["actor"] = shop["factory"].actor(shop["customer"])
    with Session(shop["engine"]) as session:
        cart = Cart(UserId=shop["customer"].UserId); session.add(cart); session.flush()
        session.add(CartItem(CartId=cart.CartId, ProductVariantId=shop["variant"].ProductVariantId,
                             Quantity=2, UnitPrice=Decimal("100000"), IsSelected=True))
        session.commit()
    assert Decimal(ok(client.get("/cart/coupon-preview", params={"code": code["Code"]}))["DiscountAmount"]) == Decimal("20000")
    payload = {"ShippingMethodId": str(shop["shipping"].ShippingMethodId),
        "PaymentMethodId": str(shop["payment"].PaymentMethodId), "CouponCode": code["Code"],
        "ReceiverName": "Khách", "ReceiverPhone": "0900000000", "ShippingAddress": "1 Đường A"}
    order = ok(client.post("/orders", json=payload), 201)
    assert Decimal(order["DiscountAmount"]) == Decimal("20000")
    with Session(shop["engine"]) as session:
        coupon = session.get(Coupon, uuid.UUID(code["CouponId"]))
        assert (coupon.UsedCount, coupon.IsActive) == (1, False)
        assert session.get(ProductVariant, shop["variant"].ProductVariantId).StockQuantity == 8
    ok(client.post("/orders/" + order["OrderId"] + "/cancel", json={"CancelReason": "Thử hủy"}))
    with Session(shop["engine"]) as session:
        coupon = session.get(Coupon, uuid.UUID(code["CouponId"]))
        assert (coupon.UsedCount, coupon.IsActive) == (0, True)
        assert session.get(ProductVariant, shop["variant"].ProductVariantId).StockQuantity == 10
