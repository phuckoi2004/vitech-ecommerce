"""API tests — Promotions and coupons (Admin only), coupon preview and use at checkout (Customer)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .support import (
    expect,
    expect_forbidden,
    expect_unauthorized,
    expect_validation,
    random_id,
    requires_postgres,
)

pytestmark = requires_postgres


def when(days=0):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def promotion_payload(**overrides):
    return {"Name": "Giảm 10%", "DiscountType": "Percentage", "DiscountValue": "10", "MinOrderValue": "0",
            "MaxDiscountAmount": "50000", "StartDate": when(-1), "EndDate": when(30), "Status": "Active", **overrides}


def promotion_with_coupon(api, admin, code="GIAM10", usage_limit=None, **promotion):
    created = expect(api.client.post("/admin/promotions", headers=admin.headers,
                                     json=promotion_payload(**promotion)), 201)
    coupon = {"PromotionId": created["PromotionId"], "Code": code, "Name": "Mã giảm 10%"}
    if usage_limit is not None:
        coupon["UsageLimit"] = usage_limit
    return created, expect(api.client.post("/admin/coupons", headers=admin.headers, json=coupon), 201)


def fill_cart(api, customer, shop, quantity=2):
    expect(api.client.post("/cart/items", headers=customer.headers,
                           json={"ProductVariantId": shop["variant_id"], "Quantity": quantity}), 200)


def preview(api, customer, code):
    return api.client.get("/cart/coupon-preview", headers=customer.headers, params={"code": code})


def test_success_preview_and_checkout_with_coupon(api, admin, customer):
    shop = api.shop(price="100000.00")
    _, coupon = promotion_with_coupon(api, admin)
    fill_cart(api, customer, shop)
    previewed = expect(preview(api, customer, "giam10"), 200)  # codes are case-insensitive
    assert (Decimal(previewed["Subtotal"]), Decimal(previewed["DiscountAmount"])) == (Decimal("200000"),
                                                                                       Decimal("20000"))
    order = expect(api.client.post("/orders", headers=customer.headers, json={
        "ShippingMethodId": shop["shipping_id"], "PaymentMethodId": shop["cod_id"], "CouponCode": "GIAM10",
        "ReceiverName": "A", "ReceiverPhone": "0900000000", "ShippingAddress": "1 Lê Lợi"}), 201)
    assert (Decimal(order["DiscountAmount"]), Decimal(order["TotalAmount"])) == (Decimal("20000"), Decimal("210000"))
    assert api.scalar('select "UsedCount" from "Coupons" where "CouponId" = :id', id=coupon["CouponId"]) == 1


def test_401_without_token(api):
    expect_unauthorized(api.client.get("/cart/coupon-preview", params={"code": "GIAM10"}))
    expect_unauthorized(api.client.post("/admin/promotions", json=promotion_payload()))
    expect_unauthorized(api.client.get("/admin/coupons/" + random_id()))


def test_403_promotions_are_admin_only(api, admin, staff, customer):
    created, coupon = promotion_with_coupon(api, admin)
    expect_forbidden(api.client.get("/admin/promotions", headers=staff.headers))
    expect_forbidden(api.client.post("/admin/promotions", headers=staff.headers, json=promotion_payload()))
    expect_forbidden(api.client.patch(f"/admin/coupons/{coupon['CouponId']}", headers=staff.headers,
                                      json={"IsActive": False}))
    expect_forbidden(api.client.get(f"/admin/promotions/{created['PromotionId']}", headers=customer.headers))
    expect_forbidden(preview(api, staff, "GIAM10"))  # preview works on a customer's own cart


def test_404_unknown_promotions_and_coupons(api, admin):
    expect(api.client.get(f"/admin/coupons/{random_id()}", headers=admin.headers), 404, "coupon_not_found")
    expect(api.client.get(f"/admin/promotions/{random_id()}", headers=admin.headers), 404)
    expect(api.client.patch(f"/admin/promotions/{random_id()}", headers=admin.headers, json={"Name": "x"}), 404)
    expect(api.client.post("/admin/coupons", headers=admin.headers, json={
        "PromotionId": random_id(), "Code": "MOI", "Name": "x"}), 404)


def test_409_coupon_code_is_unique_ignoring_case(api, admin):
    created, _ = promotion_with_coupon(api, admin, code="TET2027")
    expect(api.client.post("/admin/coupons", headers=admin.headers, json={
        "PromotionId": created["PromotionId"], "Code": "tet2027", "Name": "Trùng"}), 409, "coupon_code_exists")


def test_422_validation(api, admin):
    post = lambda body: api.client.post("/admin/promotions", headers=admin.headers, json=body)  # noqa: E731
    expect_validation(post(promotion_payload(DiscountType="BuyOneGetOne")), "DiscountType")
    expect_validation(post(promotion_payload(DiscountValue="-1")), "DiscountValue")
    expect_validation(post(promotion_payload(DiscountValue="150")))  # a percentage above 100
    expect_validation(post({key: value for key, value in promotion_payload().items() if key != "StartDate"}),
                      "StartDate")
    expect_validation(api.client.post("/admin/coupons", headers=admin.headers, json={
        "PromotionId": random_id(), "Code": "X" * 51, "Name": "x"}), "Code")


def test_business_rules_promotions_and_coupons(api, admin, customer, other_customer):
    client = api.client
    draft = expect(client.post("/admin/promotions", headers=admin.headers,
                               json=promotion_payload(Status="Draft", StartDate=when(1))), 201)
    expect(client.patch(f"/admin/promotions/{draft['PromotionId']}", headers=admin.headers,
                        json={"EndDate": when(-1)}), 400, "invalid_promotion_period")
    shop = api.shop(price="100000.00")
    promotion_with_coupon(api, admin, code="TOITHIEU", MinOrderValue="1000000")
    promotion_with_coupon(api, admin, code="HETHAN", StartDate=when(-10), EndDate=when(-5), Status="Expired")
    promotion_with_coupon(api, admin, code="MOTLAN", usage_limit=1)
    fill_cart(api, customer, shop, quantity=1)
    # An unknown code is "invalid" (400), not "not found": the preview does not reveal which codes exist.
    expect(preview(api, customer, "KHONGCO"), 400, "coupon_invalid")
    expect(preview(api, customer, "TOITHIEU"), 400, "coupon_min_order_value")
    expect(preview(api, customer, "HETHAN"), 400, "coupon_expired")
    expect(client.post("/orders", headers=customer.headers, json={
        "ShippingMethodId": shop["shipping_id"], "PaymentMethodId": shop["cod_id"], "CouponCode": "MOTLAN",
        "ReceiverName": "A", "ReceiverPhone": "0900000000", "ShippingAddress": "1 Lê Lợi"}), 201)
    fill_cart(api, other_customer, shop, quantity=1)
    expect(preview(api, other_customer, "MOTLAN"), 400, "coupon_usage_exceeded")
