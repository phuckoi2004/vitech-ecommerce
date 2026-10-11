"""API tests — Return requests: customer request, Staff receives/inspects, Admin approves the refund amount."""

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


def request_return(api, person, order_item_id, quantity=1, request_type="Return"):
    return api.client.post("/return-requests", headers=person.headers, json={
        "OrderItemId": order_item_id, "RequestType": request_type, "Quantity": quantity, "Reason": "Không ưng ý"})


def step(api, person, request_id, action, body=None, status=200, code=None):
    return expect(api.client.post(f"/admin/return-requests/{request_id}/{action}", headers=person.headers,
                                  json=body), status, code)


def inspected(api, staff, request_id, restocked=1, damaged=0):
    step(api, staff, request_id, "accept")
    step(api, staff, request_id, "start-receiving")
    step(api, staff, request_id, "receive", {})
    return step(api, staff, request_id, "inspect", {"RestockedQuantity": restocked, "DamagedQuantity": damaged})


def test_success_return_refund_and_restock(api, admin, staff, customer):
    shop = api.shop(stock=5, price="100000.00")
    line = api.delivered_line(customer, staff, shop, quantity=2)
    request_id = expect(request_return(api, customer, line["order_item_id"]), 201)["ReturnRequestId"]
    amount = inspected(api, staff, request_id)["CompensationAmount"]
    assert Decimal(amount) == Decimal("100000")
    step(api, admin, request_id, "approve", {"CompensationAmount": amount})
    assert api.scalar('select "StockQuantity" from "ProductVariants" where "ProductVariantId" = :id',
                      id=shop["variant_id"]) == 4  # 5 - 2 sold + 1 restocked
    refund_id = step(api, staff, request_id, "refund")["RefundPaymentTransactionId"]
    expect(api.client.post(f"/admin/refunds/{refund_id}/resolve", headers=admin.headers, json={
        "Success": True, "EvidenceReference": "UNC-0001", "ResolutionNote": "Đã chuyển khoản"}), 200)
    assert step(api, staff, request_id, "confirm-refund")["Status"] == "Completed"
    mine = expect(api.client.get("/return-requests", headers=customer.headers), 200)
    assert [(r["ReturnRequestId"], r["Status"]) for r in mine["Items"]] == [(request_id, "Completed")]


def test_401_without_token(api):
    expect_unauthorized(api.client.post("/return-requests", json={
        "OrderItemId": random_id(), "RequestType": "Return", "Quantity": 1, "Reason": "x"}))
    expect_unauthorized(api.client.get("/return-requests"))
    expect_unauthorized(api.client.get("/admin/return-requests"))


def test_403_roles(api, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    request_id = expect(request_return(api, customer, line["order_item_id"]), 201)["ReturnRequestId"]
    expect_forbidden(request_return(api, staff, line["order_item_id"]))  # requests come from customers
    expect_forbidden(api.client.get("/admin/return-requests", headers=customer.headers))
    amount = inspected(api, staff, request_id)["CompensationAmount"]
    expect_forbidden(api.client.post(f"/admin/return-requests/{request_id}/approve", headers=staff.headers,
                                     json={"CompensationAmount": amount}))  # approving money is Admin's


def test_404_unknown_or_foreign(api, staff, customer, other_customer):
    foreign = api.delivered_line(other_customer, staff, api.shop())
    foreign_request = expect(request_return(api, other_customer, foreign["order_item_id"]), 201)
    expect(request_return(api, customer, random_id()), 404, "order_item_not_found")
    expect(request_return(api, customer, foreign["order_item_id"]), 404, "order_item_not_found")
    expect(api.client.get(f"/return-requests/{foreign_request['ReturnRequestId']}", headers=customer.headers), 404)
    expect(api.client.post(f"/admin/return-requests/{random_id()}/accept", headers=staff.headers), 404)


def test_409_item_with_an_open_warranty_request(api, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    expect(api.client.post("/warranty-requests", headers=customer.headers, json={
        "OrderItemId": line["order_item_id"], "IssueDescription": "Lỗi loa"}), 201)
    expect(request_return(api, customer, line["order_item_id"]), 409, "item_has_open_warranty")


def test_422_validation(api, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    expect_validation(request_return(api, customer, line["order_item_id"], request_type="Refund"), "RequestType")
    expect_validation(api.client.post("/return-requests", headers=customer.headers, json={
        "OrderItemId": line["order_item_id"], "RequestType": "Return"}), "Reason")
    request_id = expect(request_return(api, customer, line["order_item_id"]), 201)["ReturnRequestId"]
    expect_validation(api.client.post(f"/admin/return-requests/{request_id}/inspect", headers=staff.headers,
                                      json={"RestockedQuantity": 1}), "DamagedQuantity")


def test_business_rules_return_window_quantity_workflow_and_amount(api, admin, staff, customer):
    shop = api.shop()
    pending = api.place_order(customer, shop)
    expect(request_return(api, customer, pending["Items"][0]["OrderItemId"]), 400, "return_order_not_delivered")
    line = api.delivered_line(customer, staff, shop)
    expect(request_return(api, customer, line["order_item_id"], quantity=2), 400, "return_quantity_exceeded")
    request_id = expect(request_return(api, customer, line["order_item_id"]), 201)["ReturnRequestId"]
    step(api, staff, request_id, "receive", {}, status=400, code="invalid_return_transition")  # must be accepted and collected first
    inspected(api, staff, request_id)
    expect(api.client.post(f"/admin/return-requests/{request_id}/approve", headers=admin.headers,
                           json={"CompensationAmount": "1.00"}), 400, "compensation_amount_mismatch")

    late = api.delivered_line(customer, staff, shop)
    api.execute('update "Orders" set "DeliveredAt" = now() - interval \'400 days\' where "OrderId" = :id',
                id=late["order_id"])
    expect(request_return(api, customer, late["order_item_id"]), 400, "return_window_expired")
