"""API tests — Reviews: customers review delivered items once; Admin moderates; the public reads visible reviews."""

from .support import (
    expect,
    expect_forbidden,
    expect_unauthorized,
    expect_validation,
    random_id,
    requires_postgres,
)

pytestmark = requires_postgres


def review(api, person, order_item_id, rating=5, content="Máy chạy tốt"):
    return api.client.post("/reviews", headers=person.headers,
                           json={"OrderItemId": order_item_id, "Rating": rating, "Content": content})


def test_success_review_edit_and_moderation(api, admin, staff, customer):
    shop = api.shop()
    line = api.delivered_line(customer, staff, shop)
    created = expect(review(api, customer, line["order_item_id"]), 201)
    public = expect(api.client.get(f"/products/{shop['product_id']}/reviews"), 200)
    assert [r["ReviewId"] for r in public["Items"]] == [created["ReviewId"]]
    edited = expect(api.client.patch(f"/reviews/{created['ReviewId']}", headers=customer.headers,
                                     json={"Rating": 4, "Content": "Pin hơi yếu"}), 200)
    assert (edited["Rating"], edited["Content"]) == (4, "Pin hơi yếu")
    assert [r["ReviewId"] for r in expect(api.client.get("/reviews/mine", headers=customer.headers), 200)["Items"]] \
        == [created["ReviewId"]]
    expect(api.client.post(f"/admin/reviews/{created['ReviewId']}/hide", headers=admin.headers,
                           json={"DeleteReason": "Ngôn từ không phù hợp"}), 200)
    assert expect(api.client.get(f"/products/{shop['product_id']}/reviews"), 200)["Items"] == []


def test_401_without_token(api):
    expect_unauthorized(api.client.post("/reviews", json={"OrderItemId": random_id(), "Rating": 5, "Content": "x"}))
    expect_unauthorized(api.client.patch(f"/reviews/{random_id()}", json={"Rating": 4}))
    expect_unauthorized(api.client.get("/reviews/mine"))


def test_403_roles(api, admin, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    created = expect(review(api, customer, line["order_item_id"]), 201)
    expect_forbidden(review(api, staff, line["order_item_id"]))  # only customers write reviews
    expect_forbidden(api.client.post(f"/admin/reviews/{created['ReviewId']}/hide", headers=staff.headers,
                                     json={"DeleteReason": "x"}))  # Staff has no review moderation (Stage 4)
    expect_forbidden(api.client.post(f"/admin/reviews/{created['ReviewId']}/hide", headers=customer.headers,
                                     json={"DeleteReason": "x"}))
    expect_forbidden(api.client.get(f"/admin/reviews/{created['ReviewId']}", headers=staff.headers))


def test_404_unknown_or_foreign(api, admin, staff, customer, other_customer):
    foreign_line = api.delivered_line(other_customer, staff, api.shop())
    foreign_review = expect(review(api, other_customer, foreign_line["order_item_id"]), 201)
    expect(review(api, customer, random_id()), 404, "order_item_not_found")
    expect(review(api, customer, foreign_line["order_item_id"]), 404, "order_item_not_found")  # not revealed
    expect(api.client.patch(f"/reviews/{foreign_review['ReviewId']}", headers=customer.headers, json={"Rating": 1}),
           404)
    expect(api.client.post(f"/admin/reviews/{random_id()}/hide", headers=admin.headers, json={"DeleteReason": "x"}),
           404)


def test_409_one_review_per_order_line(api, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    expect(review(api, customer, line["order_item_id"]), 201)
    expect(review(api, customer, line["order_item_id"], rating=1, content="Lần hai"), 409, "review_exists")


def test_422_validation(api, customer):
    expect_validation(review(api, customer, random_id(), rating=6), "Rating")
    expect_validation(review(api, customer, random_id(), rating=0), "Rating")
    expect_validation(api.client.post("/reviews", headers=customer.headers,
                                      json={"OrderItemId": random_id(), "Rating": 5}), "Content")
    expect_validation(review(api, customer, "not-a-uuid"), "OrderItemId")


def test_business_rules_reviews(api, admin, staff, customer):
    shop = api.shop()
    pending = api.place_order(customer, shop)
    expect(review(api, customer, pending["Items"][0]["OrderItemId"]), 400, "review_order_not_delivered")
    line = api.delivered_line(customer, staff, shop)
    created = expect(review(api, customer, line["order_item_id"]), 201)
    expect(api.client.post(f"/admin/reviews/{created['ReviewId']}/hide", headers=admin.headers,
                           json={"DeleteReason": "Spam"}), 200)
    expect(api.client.post(f"/admin/reviews/{created['ReviewId']}/hide", headers=admin.headers,
                           json={"DeleteReason": "Spam"}), 400, "review_already_hidden")
