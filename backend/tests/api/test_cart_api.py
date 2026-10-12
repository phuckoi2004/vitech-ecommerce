"""API tests — Cart and wishlist (Customer only; each customer sees only their own items)."""

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


def add(api, person, variant_id, quantity=1):
    return api.client.post("/cart/items", headers=person.headers,
                           json={"ProductVariantId": variant_id, "Quantity": quantity})


def test_success_cart_and_wishlist(api, customer):
    shop = api.seed.variant(stock=10, price="250000.00")
    client = api.client
    cart = expect(add(api, customer, shop["variant_id"], 2), 200)
    cart = expect(add(api, customer, shop["variant_id"], 1), 200)  # same variant merges into one line
    assert [(i["Quantity"], Decimal(i["LineTotal"])) for i in cart["Items"]] == [(3, Decimal("750000"))]
    item_id = cart["Items"][0]["CartItemId"]
    assert expect(client.patch(f"/cart/items/{item_id}", headers=customer.headers, json={"Quantity": 1}),
                  200)["SelectedQuantity"] == 1
    assert expect(client.put("/cart/selection", headers=customer.headers, json={"IsSelected": False}),
                  200)["SelectedQuantity"] == 0
    assert expect(client.delete(f"/cart/items/{item_id}", headers=customer.headers), 200)["Items"] == []

    added = expect(client.post("/wishlist/items", headers=customer.headers, json={"ProductId": shop["product_id"]}),
                   201)
    assert [i["ProductId"] for i in expect(client.get("/wishlist", headers=customer.headers), 200)["Items"]] == [
        shop["product_id"]]
    expect(client.delete(f"/wishlist/items/{added['WishlistItemId']}", headers=customer.headers), 204)


def test_401_without_token(api):
    expect_unauthorized(api.client.get("/cart"))
    expect_unauthorized(api.client.post("/cart/items", json={"ProductVariantId": random_id(), "Quantity": 1}))
    expect_unauthorized(api.client.get("/wishlist"))


def test_403_cart_is_customer_only(api, staff, admin):
    shop = api.seed.variant()
    expect_forbidden(add(api, staff, shop["variant_id"]))
    expect_forbidden(api.client.get("/cart", headers=admin.headers))
    expect_forbidden(api.client.post("/wishlist/items", headers=staff.headers, json={"ProductId": shop["product_id"]}))


def test_404_unknown_or_foreign_items(api, customer, other_customer):
    shop = api.seed.variant()
    hidden = api.seed.variant(status="Draft")
    expect(add(api, customer, random_id()), 404, "variant_not_available")
    expect(add(api, customer, hidden["variant_id"]), 404, "variant_not_available")  # not for sale
    foreign = expect(add(api, other_customer, shop["variant_id"]), 200)["Items"][0]["CartItemId"]
    # Another customer's cart line looks absent.
    expect(api.client.patch(f"/cart/items/{foreign}", headers=customer.headers, json={"Quantity": 2}), 404,
           "cart_item_not_found")
    expect(api.client.delete(f"/cart/items/{random_id()}", headers=customer.headers), 404, "cart_item_not_found")
    expect(api.client.post("/wishlist/items", headers=customer.headers, json={"ProductId": random_id()}), 404)


def test_409_product_already_in_wishlist(api, customer):
    shop = api.seed.variant()
    expect(api.client.post("/wishlist/items", headers=customer.headers, json={"ProductId": shop["product_id"]}), 201)
    expect(api.client.post("/wishlist/items", headers=customer.headers, json={"ProductId": shop["product_id"]}), 409,
           "wishlist_item_exists")


def test_422_validation(api, customer):
    shop = api.seed.variant()
    expect_validation(add(api, customer, shop["variant_id"], 0), "Quantity")
    expect_validation(add(api, customer, "not-a-uuid"), "ProductVariantId")
    expect_validation(api.client.post("/cart/items", headers=customer.headers, json={"Quantity": 1}),
                      "ProductVariantId")
    expect_validation(api.client.put("/cart/selection", headers=customer.headers, json={}), "IsSelected")


def test_business_rule_quantity_cannot_exceed_stock(api, customer):
    shop = api.seed.variant(stock=3)
    expect(add(api, customer, shop["variant_id"], 4), 400, "insufficient_stock")
    cart = expect(add(api, customer, shop["variant_id"], 3), 200)
    expect(add(api, customer, shop["variant_id"], 1), 400, "insufficient_stock")  # 3 already in the cart
    expect(api.client.patch(f"/cart/items/{cart['Items'][0]['CartItemId']}", headers=customer.headers,
                            json={"Quantity": 5}), 400, "insufficient_stock")
