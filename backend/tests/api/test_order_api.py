"""API tests — Orders: checkout, customer views, staff workflow, cancellation and shipping methods."""

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


def stock(api, shop):
    return api.scalar('select "StockQuantity" from "ProductVariants" where "ProductVariantId" = :id',
                      id=shop["variant_id"])


def test_success_checkout_workflow_and_cancellation(api, admin, staff, customer):
    client = api.client
    shop = api.shop(stock=5, price="100000.00", cost="60000.00")
    order = api.place_order(customer, shop, quantity=2)
    order_id = order["OrderId"]
    assert (order["OrderStatus"], order["PaymentStatus"], Decimal(order["TotalAmount"])) == (
        "Pending", "Pending", Decimal("230000"))
    assert stock(api, shop) == 3
    assert [o["OrderId"] for o in expect(client.get("/orders", headers=customer.headers), 200)["Items"]] == [order_id]
    assert expect(client.get(f"/orders/{order_id}/history", headers=customer.headers), 200)

    pending = expect(client.get("/admin/orders", headers=staff.headers, params={"order_status": "Pending"}), 200)
    assert order_id in [o["OrderId"] for o in pending["Items"]]
    delivered = api.deliver(order_id, staff)
    assert (delivered["OrderStatus"], delivered["PaymentStatus"]) == ("Delivered", "Paid")
    assert Decimal(expect(client.get(f"/admin/orders/{order_id}/cogs", headers=admin.headers), 200)["Cogs"]) == \
        Decimal("120000")

    second = api.place_order(customer, shop, quantity=1)
    cancelled = expect(client.post(f"/orders/{second['OrderId']}/cancel", headers=customer.headers,
                                   json={"CancelReason": "Đổi ý"}), 200)
    assert cancelled["OrderStatus"] == "Cancelled" and stock(api, shop) == 3  # stock returned once

    # Order history: order_status repeats (any matches) and each order lists its lines with the product slug.
    history = expect(client.get("/orders", headers=customer.headers,
                                params=[("order_status", "Delivered"), ("order_status", "Cancelled")]), 200)
    assert {o["OrderId"] for o in history["Items"]} == {order_id, second["OrderId"]}
    lines = next(o for o in history["Items"] if o["OrderId"] == order_id)["Items"]
    assert [line["Quantity"] for line in lines] == [2] and lines[0]["ProductName"] and lines[0]["ProductSlug"]


def test_401_without_token(api):
    expect_unauthorized(api.client.get("/orders"))
    expect_unauthorized(api.client.post("/orders", json={}))
    expect_unauthorized(api.client.get("/admin/orders"))
    expect_unauthorized(api.client.post(f"/admin/orders/{random_id()}/status", json={"OrderStatus": "Confirmed"}))


def test_403_roles(api, staff, customer):
    shop = api.shop()
    order_id = api.place_order(customer, shop)["OrderId"]
    expect_forbidden(api.client.get("/admin/orders", headers=customer.headers))
    expect_forbidden(api.client.post(f"/admin/orders/{order_id}/status", headers=customer.headers,
                                     json={"OrderStatus": "Confirmed"}))
    expect_forbidden(api.client.get(f"/admin/orders/{order_id}/cogs", headers=staff.headers))  # Admin only
    expect_forbidden(api.client.post("/orders", headers=staff.headers, json={
        "ShippingMethodId": shop["shipping_id"], "PaymentMethodId": shop["cod_id"], "ReceiverName": "A",
        "ReceiverPhone": "0900000000", "ShippingAddress": "1 Lê Lợi"}))  # checkout is Customer-only
    expect_forbidden(api.client.post("/admin/shipping-methods", headers=staff.headers, json={
        "Code": "STAFF", "Name": "x", "BaseFee": "1.00", "EstimatedDays": 1}))  # Staff only views methods


def test_404_unknown_or_foreign_orders(api, admin, customer, other_customer):
    shop = api.shop()
    foreign = api.place_order(other_customer, shop)["OrderId"]
    expect(api.client.get(f"/orders/{foreign}", headers=customer.headers), 404)  # not revealed to others
    expect(api.client.get(f"/orders/{random_id()}", headers=customer.headers), 404)
    expect(api.client.get(f"/admin/orders/{random_id()}", headers=admin.headers), 404, "order_not_found")
    expect(api.client.post(f"/admin/orders/{random_id()}/status", headers=admin.headers,
                           json={"OrderStatus": "Confirmed"}), 404, "order_not_found")
    expect(api.client.post("/cart/items", headers=customer.headers,
                           json={"ProductVariantId": shop["variant_id"], "Quantity": 1}), 200)
    expect(api.client.post("/orders", headers=customer.headers, json={
        "ShippingMethodId": random_id(), "PaymentMethodId": shop["cod_id"], "ReceiverName": "A",
        "ReceiverPhone": "0900000000", "ShippingAddress": "1 Lê Lợi"}), 404, "shipping_method_not_available")


def test_409_duplicate_shipping_method_code(api, admin):
    payload = {"Code": "GIAO-NHANH", "Name": "Giao nhanh", "BaseFee": "40000.00", "EstimatedDays": 1}
    expect(api.client.post("/admin/shipping-methods", headers=admin.headers, json=payload), 201)
    expect(api.client.post("/admin/shipping-methods", headers=admin.headers, json=payload), 409,
           "shipping_method_code_exists")


def test_422_validation(api, staff, customer):
    shop = api.shop()
    order_id = api.place_order(customer, shop)["OrderId"]
    expect_validation(api.client.post("/orders", headers=customer.headers,
                                      json={"ShippingMethodId": shop["shipping_id"]}), "PaymentMethodId")
    expect_validation(api.client.post(f"/admin/orders/{order_id}/status", headers=staff.headers,
                                      json={"OrderStatus": "Lost"}), "OrderStatus")
    expect_validation(api.client.get("/orders", headers=customer.headers,
                                     params={"ordered_from": "2026-10-01T00:00:00"}), "ordered_from")  # no timezone
    expect_validation(api.client.get("/orders/not-a-uuid", headers=customer.headers), "order_id")


def test_business_rules_order_workflow(api, staff, customer):
    client = api.client
    shop = api.shop()
    expect(client.post("/orders", headers=customer.headers, json={
        "ShippingMethodId": shop["shipping_id"], "PaymentMethodId": shop["cod_id"], "ReceiverName": "A",
        "ReceiverPhone": "0900000000", "ShippingAddress": "1 Lê Lợi"}), 400, "cart_empty")
    order_id = api.place_order(customer, shop)["OrderId"]
    expect(client.post(f"/admin/orders/{order_id}/status", headers=staff.headers, json={"OrderStatus": "Shipping"}),
           400, "invalid_status_transition")  # steps cannot be skipped
    expect(client.post(f"/admin/orders/{order_id}/status", headers=staff.headers,
                       json={"OrderStatus": "Confirmed", "CancelReason": "x"}), 400, "cancel_reason_not_allowed")
    api.ship(order_id, staff)
    expect(client.post(f"/orders/{order_id}/cancel", headers=customer.headers, json={"CancelReason": "Muộn"}), 400,
           "order_not_cancellable")  # already shipping
    expect(client.post(f"/admin/orders/{order_id}/status", headers=staff.headers, json={"OrderStatus": "Delivered"}),
           400, "cod_delivery_requires_collection")
