"""Opt-in coupon workflows over HTTP/JWT and a protected, migrated PostgreSQL test database.

The shared pg fixture truncates the dedicated test database before/after this module.
No payment gateway, webhook or cron endpoint is used. UsageLimit is global; usage
per customer is derived from Orders, since there is no separate per-user quota.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.postgres_safety import POSTGRES_TESTS_ENABLED
from tests.test_postgres_integration import (
    fill_cart,
    methods as methods,
    new_customer,
    ok,
    pg as pg,
    stocked_variant,
    team as team,
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_TESTS_ENABLED,
    reason="opt-in coupon tests require the protected TEST_DATABASE_URL",
)


def create_coupon(pg, team, *, minimum="0.00", discount_type="Percentage", discount="10.00",
                  maximum=None, usage_limit=2, product_ids=()):
    tag = uuid.uuid4().hex[:16].upper()
    now = datetime.now(timezone.utc)
    promotion = ok(pg.client.post("/admin/promotions", headers=team["admin"], json={
        "Name": f"Coupon integration {tag}", "DiscountType": discount_type, "DiscountValue": discount,
        "MinOrderValue": minimum, "MaxDiscountAmount": maximum,
        "StartDate": (now - timedelta(days=1)).isoformat(), "EndDate": (now + timedelta(days=1)).isoformat(),
        "Status": "Active", "ProductIds": list(product_ids),
    }), 201)
    coupon = ok(pg.client.post("/admin/coupons", headers=team["admin"], json={
        "PromotionId": promotion["PromotionId"], "Code": f"PGCOUPON{tag}", "Name": f"Coupon {tag}",
        "UsageLimit": usage_limit, "IsActive": True,
    }), 201)
    assert coupon["CreatedByUserId"] == team["admin_id"]
    assert (coupon["UsedCount"], coupon["UsageLimit"]) == (0, usage_limit)
    return coupon


def order_payload(methods, coupon):
    return {
        "ShippingMethodId": methods["shipping"], "PaymentMethodId": methods["cod"],
        "ReceiverName": "Khách coupon", "ReceiverPhone": "0900000000", "ShippingAddress": "1 Đường A",
        "CouponCode": coupon["Code"].lower(),
    }


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


def assert_usage(pg, coupon, expected, *, by_customer=None):
    coupon_id = coupon["CouponId"]
    assert pg.scalar('SELECT "UsedCount" FROM "Coupons" WHERE "CouponId" = :id', id=coupon_id) == expected
    assert pg.scalar('SELECT count(*) FROM "Orders" WHERE "CouponId" = :id '
                     'AND "OrderStatus" <> \'Cancelled\'', id=coupon_id) == expected
    for customer_id, count in (by_customer or {}).items():
        assert pg.scalar('SELECT count(*) FROM "Orders" WHERE "CouponId" = :coupon '
                         'AND "CustomerId" = :customer AND "OrderStatus" <> \'Cancelled\'',
                         coupon=coupon_id, customer=customer_id) == count


def stock(pg, item):
    return pg.scalar('SELECT "StockQuantity" FROM "ProductVariants" WHERE "ProductVariantId" = :id',
                     id=item["variant"]["ProductVariantId"])


def test_coupon_minimum_preview_reprices_checkout_and_cancellation_releases_once(pg, team, methods):
    eligible = stocked_variant(pg, team, quantity=8)
    other = stocked_variant(pg, team, quantity=8, price="30000.00", cost="20000.00")
    customer, headers = new_customer(pg)
    coupon = create_coupon(pg, team, minimum="200000.00", discount="25.00", maximum="40000.00",
                           product_ids=(eligible["product"]["ProductId"],))
    payload = order_payload(methods, coupon)
    fill_cart(pg, headers, eligible, 1)
    fill_cart(pg, headers, other, 1)

    # Selected subtotal 130k does not qualify; rejection leaves cart, stock and usage unchanged.
    assert_error(pg.client.get("/cart/coupon-preview", headers=headers, params={"code": coupon["Code"].lower()}),
                 400, "coupon_min_order_value")
    assert_error(pg.client.post("/orders", headers=headers, json=payload), 400, "coupon_min_order_value")
    assert_usage(pg, coupon, 0)
    assert (stock(pg, eligible), stock(pg, other)) == (8, 8)
    assert pg.scalar('SELECT count(*) FROM "Orders" WHERE "CustomerId" = :id', id=customer["id"]) == 0
    assert len(ok(pg.client.get("/cart", headers=headers))["Items"]) == 2

    fill_cart(pg, headers, eligible, 1)  # subtotal 230k, eligible subtotal 200k
    preview = ok(pg.client.get("/cart/coupon-preview", headers=headers,
                               params={"code": coupon["Code"].lower()}))
    assert preview["Code"] == coupon["Code"]
    assert tuple(Decimal(preview[key]) for key in ("Subtotal", "EligibleSubtotal", "DiscountAmount")) == (
        Decimal("230000.00"), Decimal("200000.00"), Decimal("40000.00"))
    assert_usage(pg, coupon, 0)  # previews do not reserve coupon uses

    # Catalog price changes after preview. Checkout recomputes price rather than trusting cart UnitPrice.
    ok(pg.client.patch(f"/admin/variants/{eligible['variant']['ProductVariantId']}", headers=team["admin"],
                       json={"Price": "120000.00"}))
    assert pg.scalar('SELECT i."UnitPrice" FROM "CartItems" i JOIN "Carts" c USING ("CartId") '
                     'WHERE c."UserId" = :owner AND i."ProductVariantId" = :variant',
                     owner=customer["id"], variant=eligible["variant"]["ProductVariantId"]) == Decimal("100000.00")
    order = ok(pg.client.post("/orders", headers=headers, json=payload), 201)
    assert order["CouponId"] == coupon["CouponId"]
    assert tuple(Decimal(order[key]) for key in ("Subtotal", "DiscountAmount", "ShippingFee", "TotalAmount")) == (
        Decimal("270000.00"), Decimal("40000.00"), Decimal("30000.00"), Decimal("260000.00"))
    lines = {line["ProductVariantId"]: line for line in order["Items"]}
    eligible_line = lines[eligible["variant"]["ProductVariantId"]]
    other_line = lines[other["variant"]["ProductVariantId"]]
    assert (eligible_line["Quantity"], Decimal(eligible_line["UnitPrice"]),
            Decimal(eligible_line["DiscountAmount"]), Decimal(eligible_line["LineTotal"])) == (
        2, Decimal("120000.00"), Decimal("40000.00"), Decimal("200000.00"))
    assert (Decimal(other_line["DiscountAmount"]), Decimal(other_line["LineTotal"])) == (
        Decimal("0.00"), Decimal("30000.00"))
    assert pg.scalar('SELECT "TotalAmount" FROM "Orders" WHERE "OrderId" = :id',
                     id=order["OrderId"]) == Decimal("260000.00")
    assert pg.scalar('SELECT sum("DiscountAmount") FROM "OrderItems" WHERE "OrderId" = :id',
                     id=order["OrderId"]) == Decimal("40000.00")
    assert_usage(pg, coupon, 1, by_customer={customer["id"]: 1})
    assert (stock(pg, eligible), stock(pg, other)) == (6, 7)
    assert ok(pg.client.get("/cart", headers=headers))["Items"] == []

    cancelled = ok(pg.client.post(f"/orders/{order['OrderId']}/cancel", headers=headers,
                                 json={"CancelReason": "Đặt lại đơn"}))
    assert (cancelled["OrderStatus"], cancelled["PaymentStatus"]) == ("Cancelled", "Cancelled")
    assert_usage(pg, coupon, 0, by_customer={customer["id"]: 0})
    assert (stock(pg, eligible), stock(pg, other)) == (8, 8)
    assert_error(pg.client.post(f"/orders/{order['OrderId']}/cancel", headers=headers,
                               json={"CancelReason": "Gửi lại yêu cầu hủy"}), 400, "order_not_cancellable")
    assert_usage(pg, coupon, 0)
    assert (stock(pg, eligible), stock(pg, other)) == (8, 8)

    fill_cart(pg, headers, eligible, 2)
    fill_cart(pg, headers, other, 1)
    retry = ok(pg.client.post("/orders", headers=headers, json=payload), 201)
    assert retry["OrderId"] != order["OrderId"]
    assert Decimal(retry["TotalAmount"]) == Decimal("260000.00")
    assert_usage(pg, coupon, 1, by_customer={customer["id"]: 1})
    assert pg.scalar('SELECT count(*) FROM "Orders" WHERE "CouponId" = :id', id=coupon["CouponId"]) == 2
    assert (stock(pg, eligible), stock(pg, other)) == (6, 7)


def test_coupon_global_limit_across_customers_rolls_back_and_released_use_can_be_retried(pg, team, methods):
    item = stocked_variant(pg, team, quantity=6)
    first_customer, first_headers = new_customer(pg)
    second_customer, second_headers = new_customer(pg)
    coupon = create_coupon(pg, team, discount_type="FixedAmount", discount="15000.00", usage_limit=2)
    payload = order_payload(methods, coupon)

    def checkout(headers):
        fill_cart(pg, headers, item, 1)
        return ok(pg.client.post("/orders", headers=headers, json=payload), 201)

    first_order, second_order = checkout(first_headers), checkout(second_headers)
    assert Decimal(first_order["TotalAmount"]) == Decimal(second_order["TotalAmount"]) == Decimal("115000.00")
    assert_usage(pg, coupon, 2, by_customer={first_customer["id"]: 1, second_customer["id"]: 1})
    assert stock(pg, item) == 4

    fill_cart(pg, first_headers, item, 1)
    assert_error(pg.client.get("/cart/coupon-preview", headers=first_headers, params={"code": coupon["Code"]}),
                 400, "coupon_usage_exceeded")
    assert_error(pg.client.post("/orders", headers=first_headers, json=payload), 400, "coupon_usage_exceeded")
    assert_usage(pg, coupon, 2)
    assert stock(pg, item) == 4
    cart = ok(pg.client.get("/cart", headers=first_headers))
    assert len(cart["Items"]) == 1 and cart["Items"][0]["Quantity"] == 1

    # Another user's failed cancellation must not release the globally exhausted coupon.
    cancel_url = f"/orders/{second_order['OrderId']}/cancel"
    assert_error(pg.client.post(cancel_url, headers=first_headers, json={"CancelReason": "Không sở hữu"}),
                 404, "order_not_found")
    assert_usage(pg, coupon, 2)
    cancelled = ok(pg.client.post(cancel_url, headers=second_headers, json={"CancelReason": "Nhường lượt dùng"}))
    assert cancelled["OrderStatus"] == "Cancelled"
    assert_usage(pg, coupon, 1, by_customer={first_customer["id"]: 1, second_customer["id"]: 0})
    assert stock(pg, item) == 5

    # Retry consumes the cart preserved by the failed checkout; there is no independent per-user quota.
    retry = ok(pg.client.post("/orders", headers=first_headers, json=payload), 201)
    assert retry["OrderId"] != first_order["OrderId"]
    assert_usage(pg, coupon, 2, by_customer={first_customer["id"]: 2, second_customer["id"]: 0})
    assert pg.scalar('SELECT count(*) FROM "Orders" WHERE "CouponId" = :id', id=coupon["CouponId"]) == 3
    assert pg.scalar('SELECT count(*) FROM "Orders" WHERE "CouponId" = :coupon AND "CustomerId" = :owner',
                     coupon=coupon["CouponId"], owner=second_customer["id"]) == 1  # cancellation history retained
    assert stock(pg, item) == 4
    assert ok(pg.client.get("/cart", headers=first_headers))["Items"] == []
