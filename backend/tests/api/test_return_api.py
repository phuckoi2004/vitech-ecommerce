"""API tests — Return requests: customer request and the active status-only workflow (15/10/2026).

Staff/Admin move a request Pending → Approved → Receiving → Processing → Completed or reject it; no refund, stock or
serial operation runs. The inspection/approval/refund endpoints are paused (400 service_workflow_paused).
"""

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


PAUSED_STEPS = (("inspect", {"RestockedQuantity": 1, "DamagedQuantity": 0}),
                ("approve", {"CompensationAmount": "100000.00"}), ("refund", None), ("confirm-refund", None))


def test_success_status_only_return_flow_without_money_or_stock_effects(api, admin, staff, customer):
    shop = api.shop(stock=5, price="100000.00")
    line = api.delivered_line(customer, staff, shop, quantity=2)
    request_id = expect(request_return(api, customer, line["order_item_id"]), 201)["ReturnRequestId"]
    step(api, staff, request_id, "accept", {"Note": "Đã liên hệ hẹn nhận hàng", "InternalNote": "Khách gọi lúc 9h"})
    step(api, staff, request_id, "start-receiving")
    received = step(api, staff, request_id, "receive", {})
    assert received["Status"] == "Processing" and received["ReceivedAt"] is not None
    for action, body in PAUSED_STEPS:  # the deferred inspection/approval/refund steps change nothing
        step(api, admin, request_id, action, body, status=400, code="service_workflow_paused")
    done = step(api, admin, request_id, "advance", {"ExpectedStatus": "Processing"})
    assert done["Status"] == "Completed" and done["CompletedAt"] is not None
    assert done["CompensationAmount"] is None and done["RefundPaymentTransactionId"] is None  # Completed is no refund
    assert api.scalar('select "StockQuantity" from "ProductVariants" where "ProductVariantId" = :id',
                      id=shop["variant_id"]) == 3  # 5 - 2 sold; nothing restocked
    assert api.scalar('select count(*) from "PaymentTransactions" where "TransactionType" = \'Refund\'') == 0
    mine = expect(api.client.get("/return-requests", headers=customer.headers), 200)
    assert [(r["ReturnRequestId"], r["Status"]) for r in mine["Items"]] == [(request_id, "Completed")]
    detail = expect(api.client.get(f"/return-requests/{request_id}", headers=customer.headers), 200)
    assert "Đã liên hệ hẹn nhận hàng" in str(detail["Histories"]) and "Khách gọi lúc 9h" not in str(detail)


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
    for action, body in (("advance", {"ExpectedStatus": "Pending"}), ("accept", None), ("reject", {"Reason": "x"}),
                         ("approve", {"CompensationAmount": "0"})):
        expect_forbidden(api.client.post(f"/admin/return-requests/{request_id}/{action}", headers=customer.headers,
                                         json=body))
    mine = expect(api.client.get(f"/return-requests/{request_id}", headers=customer.headers), 200)
    assert mine["Status"] == "Pending"  # nothing changed
    assert step(api, staff, request_id, "accept")["Status"] == "Approved"  # Staff drives the active workflow
    step(api, staff, request_id, "approve", {"CompensationAmount": "0"}, status=400,
         code="service_workflow_paused")  # money approval is deferred for every role


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


def test_business_rules_return_window_quantity_and_workflow(api, admin, staff, customer):
    shop = api.shop()
    pending = api.place_order(customer, shop)
    expect(request_return(api, customer, pending["Items"][0]["OrderItemId"]), 400, "return_order_not_delivered")
    line = api.delivered_line(customer, staff, shop)
    expect(request_return(api, customer, line["order_item_id"], quantity=2), 400, "return_quantity_exceeded")
    request_id = expect(request_return(api, customer, line["order_item_id"]), 201)["ReturnRequestId"]
    # Must be accepted and collected first; a step never skips one.
    step(api, staff, request_id, "receive", {}, status=409, code="service_request_stale")
    step(api, staff, request_id, "advance", {"ExpectedStatus": "Approved"}, status=409, code="service_request_stale")
    step(api, staff, request_id, "accept")
    step(api, staff, request_id, "accept", status=409, code="service_request_stale")  # a repeated click changes nothing
    assert step(api, staff, request_id, "reject", {"Reason": "Không đúng mô tả"})["Status"] == "Rejected"
    step(api, staff, request_id, "advance", {"ExpectedStatus": "Rejected"}, status=400, code="service_request_closed")
    step(api, admin, request_id, "approve", {"CompensationAmount": "1.00"}, status=400, code="service_workflow_paused")

    late = api.delivered_line(customer, staff, shop)
    api.execute('update "Orders" set "DeliveredAt" = now() - interval \'400 days\' where "OrderId" = :id',
                id=late["order_id"])
    expect(request_return(api, customer, late["order_item_id"]), 400, "return_window_expired")
