"""Real pricing/catalog/admin HTTP on isolated SQLite; no application DB writes."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_optional_actor
from app.database import get_db
from app.models import Coupon, Order, ProductVariant, Promotion
from app.routers.catalog import router as catalog_router
from app.routers.dependencies import get_product_service
from app.schemas.pricing import QuoteItemRequest
from app.services import Actor, BusinessRuleError
from app.services.catalog import ProductService
from app.services.pricing import PricingService
from tests.test_promotion_lifecycle import shop, ok  # noqa: F401


@pytest.fixture
def pricing_shop(shop):
    shop["now"]["value"] = datetime.now(timezone.utc)
    client = shop["client"]
    app = client.app
    app.include_router(catalog_router)
    app.dependency_overrides[get_optional_actor] = lambda: None

    def database():
        with Session(shop["engine"]) as session:
            yield session

    def products():
        with Session(shop["engine"]) as session:
            yield ProductService(session, clock=lambda: shop["now"]["value"])

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_product_service] = products
    with Session(shop["engine"]) as session:
        variant = session.get(ProductVariant, shop["variant"].ProductVariantId)
        variant.Price, variant.CostPrice = Decimal("35000000"), Decimal("31000000")
        other = session.get(ProductVariant, shop["other"].ProductVariantId)
        other.Price, other.CostPrice = Decimal("2000000"), Decimal("1500000")
        session.commit()
    return shop


def program(shop, *, mode="Automatic", amount="2000000", products=None, **extra):
    now = shop["now"]["value"]
    return ok(shop["client"].post("/admin/promotions", json={
        "Name": "Giảm trực tiếp", "ApplyMode": mode, "Status": "Active", "DiscountType": "FixedAmount",
        "DiscountValue": amount, "MinOrderValue": "0", "StartDate": (now - timedelta(hours=1)).isoformat(),
        "EndDate": (now + timedelta(days=3)).isoformat(),
        "ProductIds": products if products is not None else [str(shop["variant"].ProductId)], **extra,
    }), 201)


def coupon(shop, *, amount="300000", limit=100, code="TEST300", **extra):
    promotion = program(shop, mode="Coupon", amount=amount, products=[], **extra)
    return ok(shop["client"].post("/admin/coupons", json={"PromotionId": promotion["PromotionId"],
        "Code": code, "Name": "Ưu đãi công khai", "UsageLimit": limit}), 201)


def preview(shop, code=None, quantity=1):
    return shop["client"].post("/pricing/quote", json={
        "Items": [{"ProductVariantId": str(shop["variant"].ProductVariantId), "Quantity": quantity}],
        "CouponCode": code})


def test_public_detail_same_sku_prices_and_per_unit_discount(pricing_shop):
    s = pricing_shop
    program(s)
    data = ok(s["client"].get(f'/products/{s["variant"].ProductId}'))
    variant = data["Variants"][0]
    assert Decimal(variant["Price"]) == Decimal(variant["OriginalPrice"]) == 35000000
    assert Decimal(variant["SalePrice"]) == 33000000
    assert Decimal(variant["DiscountPercent"]) == Decimal("5.71")
    assert "CostPrice" not in variant and "UnitCost" not in variant
    quote = ok(preview(s, quantity=2))
    assert Decimal(quote["AutomaticDiscount"]) == 4000000
    assert Decimal(quote["Total"]) == 66000000


def test_coupon_stacks_after_automatic_without_consuming_or_creating_orders(pricing_shop):
    s = pricing_shop
    program(s)
    c = coupon(s)
    for _ in range(2):
        quote = ok(preview(s, "test300"))
        assert Decimal(quote["Subtotal"]) == 33000000
        assert Decimal(quote["CouponDiscount"]) == 300000
        assert Decimal(quote["Total"]) == 32700000
        assert quote["PreviewOnly"] is True
    with Session(s["engine"]) as session:
        assert session.get(Coupon, uuid.UUID(c["CouponId"])).UsedCount == 0
        assert session.scalar(select(Order.OrderId).limit(1)) is None
    public = ok(s["client"].get("/coupons"))
    assert public[0]["RemainingUses"] == 100
    assert "CreatedByUserId" not in public[0]


def test_best_automatic_discount_expiry_cancellation_and_cost_changes(pricing_shop):
    s = pricing_shop
    program(s, amount="1000000")
    best = program(s)
    with Session(s["engine"]) as session:
        row = session.get(Promotion, uuid.UUID(best["PromotionId"]))
        row.Status = "Cancelled"
        session.commit()
    detail = ok(s["client"].get(f'/products/{s["variant"].ProductId}'))
    assert Decimal(detail["Variants"][0]["SalePrice"]) == 34000000
    with Session(s["engine"]) as session:
        variant = session.get(ProductVariant, s["variant"].ProductVariantId)
        variant.CostPrice = 34500000
        session.commit()
    detail = ok(s["client"].get(f'/products/{s["variant"].ProductId}'))
    assert Decimal(detail["Variants"][0]["SalePrice"]) == 35000000


def test_admin_rejects_loss_missing_cost_and_coupon_on_automatic(pricing_shop):
    s = pricing_shop
    now = s["now"]["value"]
    body = dict(Name="Lỗ", ApplyMode="Automatic", DiscountType="FixedAmount", DiscountValue="5000000",
                MinOrderValue="0", StartDate=now.isoformat(), EndDate=(now + timedelta(days=1)).isoformat(),
                Status="Active", ProductIds=[str(s["variant"].ProductId)])
    response = s["client"].post("/admin/promotions", json=body)
    assert response.status_code == 400 and response.json()["code"] == "promotion_price_floor"
    valid = program(s)
    response = s["client"].post("/admin/coupons", json={"Name": "Sai", "Code": "WRONG", "PromotionId": valid["PromotionId"]})
    assert response.status_code == 400
    coupon(s, amount="3000000")
    response = preview(s, "TEST300")
    assert response.status_code == 400 and response.json()["code"] == "coupon_price_floor"


def test_effective_price_filter_precedes_pagination(pricing_shop):
    s = pricing_shop
    program(s)
    result = ok(s["client"].get("/products", params={"min_price": 32000000, "max_price": 33000000, "page_size": 1}))
    assert result["Total"] == 1 and result["Items"][0]["ProductId"] == str(s["variant"].ProductId)
    assert ok(s["client"].get("/products", params={"min_price": 34000000}))["Total"] == 0


def test_exhausted_code_hidden_and_rejected_even_if_isactive_stale(pricing_shop):
    s = pricing_shop
    c = coupon(s, limit=1)
    with Session(s["engine"]) as session:
        row = session.get(Coupon, uuid.UUID(c["CouponId"]))
        row.UsedCount, row.IsActive = 1, True
        session.commit()
    assert ok(s["client"].get("/coupons")) == []
    response = preview(s, "TEST300")
    assert response.status_code == 400 and response.json()["code"] == "coupon_usage_exceeded"


def test_percent_coupon_uses_discounted_base_and_cap(pricing_shop):
    s = pricing_shop
    program(s)
    coupon(s, amount="10", DiscountType="Percentage", MaxDiscountAmount="300000")
    assert Decimal(ok(preview(s, "TEST300"))["Total"]) == 32700000


def test_reservation_requires_transaction_and_rolls_back(pricing_shop):
    s = pricing_shop
    c = coupon(s, limit=1)
    actor = Actor(s["customer"].UserId, "Customer")
    items = [QuoteItemRequest(ProductVariantId=s["variant"].ProductVariantId, Quantity=1)]
    with Session(s["engine"]) as session:
        service = PricingService(session)
        with pytest.raises(BusinessRuleError):
            service.reserve_order_quote(actor, items, coupon_code="TEST300")
        with pytest.raises(RuntimeError):
            with service.transaction():
                service.reserve_order_quote(actor, items, coupon_code="TEST300")
                assert session.get(Coupon, uuid.UUID(c["CouponId"])).UsedCount == 1
                raise RuntimeError("Tạo đơn thất bại")
        assert session.get(Coupon, uuid.UUID(c["CouponId"])).UsedCount == 0


def test_one_use_per_account_uses_order_history_and_allows_cancelled_order(pricing_shop):
    s = pricing_shop
    c = coupon(s)
    actor = Actor(s["customer"].UserId, "Customer")
    items = [QuoteItemRequest(ProductVariantId=s["variant"].ProductVariantId, Quantity=1)]
    with Session(s["engine"]) as session:
        order = Order(OrderCode="TEST-ONCE", CustomerId=actor.user_id, CouponId=uuid.UUID(c["CouponId"]),
                      ShippingMethodId=s["shipping"].ShippingMethodId, PaymentMethodId=s["payment"].PaymentMethodId,
                      Subtotal=35000000, ShippingFee=0, DiscountAmount=300000, TotalAmount=34700000,
                      OrderStatus="Pending", PaymentStatus="Pending", ReceiverName="Khách thử", ReceiverPhone="0900000000",
                      ShippingAddress="Địa chỉ thử")
        session.add(order); session.commit()
        with pytest.raises(BusinessRuleError) as error:
            PricingService(session).quote(items, coupon_code="TEST300", actor=actor)
        assert error.value.code == "coupon_customer_limit"
        order.OrderStatus = "Cancelled"; session.commit()
        assert PricingService(session).quote(items, coupon_code="TEST300", actor=actor).CouponDiscount == 300000


def test_admin_profit_preview_is_read_only_and_unknown_cost_fails_closed(pricing_shop):
    s = pricing_shop
    now = s["now"]["value"]
    body = dict(Name="Xem thử", ApplyMode="Automatic", DiscountType="FixedAmount", DiscountValue="2000000",
                MinOrderValue="0", StartDate=now.isoformat(), EndDate=(now + timedelta(days=1)).isoformat(),
                Status="Active", ProductIds=[str(s["variant"].ProductId)])
    data = ok(s["client"].post("/admin/promotions/pricing-preview", json=body))
    assert Decimal(str(data["Items"][0]["EstimatedGrossProfit"])) == 2000000
    with Session(s["engine"]) as session:
        assert session.scalar(select(Promotion.PromotionId).limit(1)) is None
        row = session.get(ProductVariant, s["variant"].ProductVariantId)
        row.CostPrice = 0; session.commit()
    data = ok(s["client"].post("/admin/promotions/pricing-preview", json=body))
    assert data["Items"][0]["IsValid"] is False and data["Items"][0]["EstimatedGrossProfit"] is None
    assert s["client"].post("/admin/promotions", json=body).status_code == 400
    assert preview(s).status_code == 400


def test_future_expired_and_draft_offers_never_change_public_price(pricing_shop):
    s = pricing_shop
    now = s["now"]["value"]
    program(s, StartDate=(now + timedelta(days=1)).isoformat())
    program(s, StartDate=(now - timedelta(days=2)).isoformat(), EndDate=(now - timedelta(days=1)).isoformat())
    program(s, Status="Draft")
    detail = ok(s["client"].get(f'/products/{s["variant"].ProductId}'))
    assert Decimal(detail["Variants"][0]["SalePrice"]) == 35000000


def test_last_redemption_reserved_once_and_persisted_with_order(pricing_shop):
    s = pricing_shop
    c = coupon(s, limit=1)
    actor = Actor(s["customer"].UserId, "Customer")
    items = [QuoteItemRequest(ProductVariantId=s["variant"].ProductVariantId, Quantity=1)]
    with Session(s["engine"]) as session:
        service = PricingService(session)
        with service.transaction():
            quote = service.reserve_order_quote(actor, items, coupon_code="TEST300")
            session.add(Order(OrderCode="TEST-LAST", CustomerId=actor.user_id, CouponId=quote.CouponId,
                              ShippingMethodId=s["shipping"].ShippingMethodId, PaymentMethodId=s["payment"].PaymentMethodId,
                              Subtotal=quote.OriginalSubtotal, ShippingFee=0, DiscountAmount=quote.AutomaticDiscount + quote.CouponDiscount,
                              TotalAmount=quote.Total, OrderStatus="Pending", PaymentStatus="Pending", ReceiverName="Khách thử",
                              ReceiverPhone="0900000000", ShippingAddress="Địa chỉ thử"))
        row = session.get(Coupon, uuid.UUID(c["CouponId"]))
        assert row.UsedCount == 1 and row.IsActive is False
        with pytest.raises(BusinessRuleError) as error:
            with service.transaction():
                service.reserve_order_quote(actor, items, coupon_code="TEST300")
        assert error.value.code == "coupon_usage_exceeded"
