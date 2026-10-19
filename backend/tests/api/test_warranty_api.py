"""API tests — Warranty requests: customer request and the active forward-only workflow (15/10/2026).

Staff/Admin receive the device, start processing, publish the actual result directly and close the request, or reject
it; no serial, stock or financial operation runs and no separate reviewer exists. The repair-centre and
proposal/approval endpoints are paused (400 service_workflow_paused).
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


def request_warranty(api, person, order_item_id, description="Màn hình chập chờn"):
    return api.client.post("/warranty-requests", headers=person.headers,
                           json={"OrderItemId": order_item_id, "IssueDescription": description})


def step(api, person, request_id, action, body=None, status=200, code=None):
    return expect(api.client.post(f"/admin/warranty-requests/{request_id}/{action}", headers=person.headers,
                                  json=body), status, code)


PAUSED_STEPS = (("inspect", {"EligibilityStatus": "Eligible"}), ("hand-over", {"ServiceCenter": "Trung tâm hãng"}),
                ("start-processing", None), ("propose-result", {"ResultType": "Repaired", "ResultNote": "Đã sửa"}),
                ("approve-result", None), ("complete", None))


def test_success_status_only_warranty_workflow(api, admin, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    created = expect(request_warranty(api, customer, line["order_item_id"]), 201)
    request_id = created["WarrantyRequestId"]
    assert created["Status"] == "New"
    received = step(api, staff, request_id, "receive", {"Note": "Máy trầy nhẹ góc", "InternalNote": "Kệ B2"})
    assert received["Status"] == "New" and received["ReceivedAt"] is not None
    assert step(api, staff, request_id, "advance", {"ExpectedStage": "Inspecting"})["Status"] == "Processing"
    for action, body in PAUSED_STEPS:  # the repair-centre and review steps change nothing
        step(api, admin, request_id, action, body, status=400, code="service_workflow_paused")
    published = step(api, staff, request_id, "advance", {"ExpectedStage": "Repairing", "ResultType": "Repaired",
                                                         "ResultNote": "Thay cáp màn hình"})
    assert published["ResultType"] == "Repaired" and published["ResultApprovedAt"] is not None
    assert step(api, admin, request_id, "advance", {"ExpectedStage": "Finished"})["Status"] == "Completed"
    mine = expect(api.client.get(f"/warranty-requests/{request_id}", headers=customer.headers), 200)
    assert mine["Status"] == "Completed" and mine["ResultNote"] == "Thay cáp màn hình"
    assert "Máy trầy nhẹ góc" in str(mine["Histories"])
    assert "InternalNote" not in str(mine) and "Kệ B2" not in str(mine)  # customers never see internal notes


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
    for action, body in (("advance", {"ExpectedStage": "New"}), ("receive", None), ("reject", {"Reason": "x"}),
                         ("approve-result", None)):
        expect_forbidden(api.client.post(f"/admin/warranty-requests/{request_id}/{action}", headers=customer.headers,
                                         json=body))
    mine = expect(api.client.get(f"/warranty-requests/{request_id}", headers=customer.headers), 200)
    assert mine["Status"] == "New" and mine["ReceivedAt"] is None  # nothing changed
    assert step(api, staff, request_id, "receive")["ReceivedAt"] is not None  # Staff drives the active workflow
    step(api, staff, request_id, "approve-result", status=400,
         code="service_workflow_paused")  # no separate reviewer: result approval is paused for every role


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
    step(api, staff, request_id, "advance", {"ExpectedStage": "Inspecting"}, status=409,
         code="service_request_stale")  # must be received first
    step(api, staff, request_id, "start-processing", status=400, code="service_workflow_paused")  # legacy step
    step(api, staff, request_id, "receive")
    step(api, staff, request_id, "receive", status=409, code="service_request_stale")  # a repeated click is refused
    expect(api.client.post(f"/warranty-requests/{request_id}/cancel", headers=customer.headers), 400,
           "warranty_not_cancellable")  # the device is already with the store
    step(api, staff, request_id, "advance",
         {"ExpectedStage": "Inspecting", "ResultType": "Repaired", "ResultNote": "x"},
         status=400, code="warranty_result_not_applicable")  # a result belongs to the end of processing
    step(api, staff, request_id, "advance", {"ExpectedStage": "Inspecting"})
    step(api, staff, request_id, "advance", {"ExpectedStage": "Repairing"}, status=400, code="warranty_result_required")
    step(api, staff, request_id, "advance",
         {"ExpectedStage": "Repairing", "ResultType": "Repaired", "ResultNote": "   "},
         status=400, code="result_note_required")
    expect_validation(api.client.post(f"/admin/warranty-requests/{request_id}/advance", headers=staff.headers, json={
        "ExpectedStage": "Repairing", "ResultType": "ProductReplaced", "ResultNote": "Đổi máy"}), "ResultType")
    # One operator publishes the actual result directly (the proposer/reviewer split was removed on 15/10/2026).
    step(api, admin, request_id, "advance",
         {"ExpectedStage": "Repairing", "ResultType": "Repaired", "ResultNote": "Đã sửa"})
    assert step(api, admin, request_id, "advance", {"ExpectedStage": "Finished"})["Status"] == "Completed"
    step(api, staff, request_id, "reject", {"Reason": "Không được mở lại"}, status=400, code="service_request_closed")
