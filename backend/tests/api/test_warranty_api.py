"""API tests — Warranty requests: customer request, Staff handling, Admin approval of the proposed result."""

from .support import (
    expect,
    expect_forbidden,
    expect_unauthorized,
    expect_validation,
    random_id,
    requires_postgres,
)

pytestmark = requires_postgres


def request_warranty(api, person, order_item_id, description="Màn hình chập chờn"):
    return api.client.post("/warranty-requests", headers=person.headers,
                           json={"OrderItemId": order_item_id, "IssueDescription": description})


def step(api, person, request_id, action, body=None, status=200, code=None):
    return expect(api.client.post(f"/admin/warranty-requests/{request_id}/{action}", headers=person.headers,
                                  json=body), status, code)


def to_processing(api, staff, request_id):
    step(api, staff, request_id, "receive")
    step(api, staff, request_id, "inspect", {"EligibilityStatus": "Eligible"})
    step(api, staff, request_id, "hand-over", {"ServiceCenter": "Trung tâm bảo hành hãng"})
    return step(api, staff, request_id, "start-processing")


def test_success_full_repair_workflow(api, admin, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    created = expect(request_warranty(api, customer, line["order_item_id"]), 201)
    request_id = created["WarrantyRequestId"]
    assert created["Status"] == "New"
    assert to_processing(api, staff, request_id)["Status"] == "Processing"
    step(api, staff, request_id, "propose-result", {"ResultType": "Repaired", "ResultNote": "Thay cáp màn hình"})
    step(api, admin, request_id, "approve-result")
    assert step(api, staff, request_id, "complete")["Status"] == "Completed"
    mine = expect(api.client.get(f"/warranty-requests/{request_id}", headers=customer.headers), 200)
    assert mine["Status"] == "Completed"
    assert "InternalNote" not in str(mine)  # customers never see internal notes


def test_401_without_token(api):
    expect_unauthorized(api.client.post("/warranty-requests",
                                        json={"OrderItemId": random_id(), "IssueDescription": "x"}))
    expect_unauthorized(api.client.get("/warranty-requests"))
    expect_unauthorized(api.client.get("/admin/warranty-requests"))


def test_403_roles(api, admin, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    request_id = expect(request_warranty(api, customer, line["order_item_id"]), 201)["WarrantyRequestId"]
    expect_forbidden(request_warranty(api, staff, line["order_item_id"]))  # requests come from customers
    expect_forbidden(api.client.get("/admin/warranty-requests", headers=customer.headers))
    to_processing(api, staff, request_id)
    step(api, staff, request_id, "propose-result", {"ResultType": "Repaired", "ResultNote": "Đã sửa"})
    expect_forbidden(api.client.post(f"/admin/warranty-requests/{request_id}/approve-result",
                                     headers=staff.headers))  # approving the result is Admin's


def test_404_unknown_or_foreign(api, admin, staff, customer, other_customer):
    foreign = api.delivered_line(other_customer, staff, api.shop())
    foreign_request = expect(request_warranty(api, other_customer, foreign["order_item_id"]), 201)
    expect(request_warranty(api, customer, random_id()), 404)
    expect(request_warranty(api, customer, foreign["order_item_id"]), 404)
    expect(api.client.get(f"/warranty-requests/{foreign_request['WarrantyRequestId']}", headers=customer.headers),
           404)
    expect(api.client.post(f"/admin/warranty-requests/{random_id()}/receive", headers=staff.headers), 404)


def test_409_one_open_request_per_item(api, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    expect(request_warranty(api, customer, line["order_item_id"]), 201)
    expect(request_warranty(api, customer, line["order_item_id"], "Lỗi khác"), 409, "warranty_request_open")


def test_422_validation(api, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    expect_validation(api.client.post("/warranty-requests", headers=customer.headers,
                                      json={"OrderItemId": line["order_item_id"]}), "IssueDescription")
    request_id = expect(request_warranty(api, customer, line["order_item_id"]), 201)["WarrantyRequestId"]
    expect_validation(api.client.post(f"/admin/warranty-requests/{request_id}/inspect", headers=staff.headers,
                                      json={"EligibilityStatus": "Maybe"}), "EligibilityStatus")
    expect_validation(api.client.post(f"/admin/warranty-requests/{request_id}/propose-result", headers=staff.headers,
                                      json={"ResultType": "Refunded", "ResultNote": "x"}), "ResultType")


def test_business_rules_warranty_workflow(api, admin, staff, customer):
    shop = api.shop()
    pending = api.place_order(customer, shop)
    expect(request_warranty(api, customer, pending["Items"][0]["OrderItemId"]), 400, "warranty_order_not_delivered")
    line = api.delivered_line(customer, staff, shop)
    request_id = expect(request_warranty(api, customer, line["order_item_id"]), 201)["WarrantyRequestId"]
    step(api, staff, request_id, "start-processing", status=400, code="invalid_warranty_transition")  # must be inspected and handed over first
    step(api, staff, request_id, "receive")
    expect(api.client.post(f"/warranty-requests/{request_id}/cancel", headers=customer.headers), 400,
           "warranty_not_cancellable")  # the device is already with the store
    step(api, staff, request_id, "inspect", {"EligibilityStatus": "Eligible"})
    step(api, staff, request_id, "hand-over", {"ServiceCenter": "Trung tâm bảo hành hãng"})
    step(api, staff, request_id, "start-processing")
    step(api, admin, request_id, "propose-result", {"ResultType": "Repaired", "ResultNote": "Đã sửa"})
    expect(api.client.post(f"/admin/warranty-requests/{request_id}/approve-result", headers=admin.headers), 400,
           "warranty_self_review_not_allowed")  # the proposer cannot approve their own result
