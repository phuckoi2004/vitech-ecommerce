"""Opt-in PostgreSQL warranty workflows over HTTP with real JWTs and SQL invariants.

Uses the protected, fixture-owned database from test_postgres_integration. All
catalog, purchase, order and warranty writes go through APIs; SQL only reads
their persisted results. The payment gateway remains disabled.

Active workflow (15/10/2026): Staff/Admin receive the device, advance it through
processing, publish the actual result directly and close the request, or reject
it. No serial, stock or financial operation runs and there is no separate
reviewer; the repair-centre, proposal/review and replacement endpoints are paused.
"""

import uuid

import pytest
from sqlalchemy import text

from tests.postgres_safety import POSTGRES_TESTS_ENABLED
from tests.test_postgres_integration import (
    fill_cart,
    methods as methods,
    new_customer,
    ok,
    pg as pg,
    stock_of,
    stocked_variant,
    team as team,
)


pytestmark = pytest.mark.skipif(
    not POSTGRES_TESTS_ENABLED,
    reason="opt-in warranty workflows require the protected TEST_DATABASE_URL",
)


def error(response, status, code=None):
    assert response.status_code == status, response.text
    if code is not None:
        assert response.json()["code"] == code, response.text


def stocked_serial_variant(pg, team):
    """Create two tracked devices via purchasing: one sold device and one replacement."""
    client, admin, staff = pg.client, team["admin"], team["staff"]
    tag = uuid.uuid4().hex[:10]
    category = ok(client.post("/admin/categories", headers=admin,
                              json={"Name": f"Bảo hành {tag}", "Slug": f"bh-{tag}"}), 201)
    brand = ok(client.post("/admin/brands", headers=admin,
                           json={"Name": f"Hãng {tag}", "Slug": f"bh-brand-{tag}"}), 201)
    product = ok(client.post("/admin/products", headers=admin, json={
        "CategoryId": category["CategoryId"], "BrandId": brand["BrandId"], "Name": f"Máy {tag}",
        "Slug": f"bh-device-{tag}", "WarrantyMonths": 12, "Status": "Active"}), 201)
    variant = ok(client.post("/admin/variants", headers=admin, json={
        "ProductId": product["ProductId"], "Sku": f"BH-{tag.upper()}", "VariantName": "Thiết bị có serial",
        "Price": "100000.00", "IsSerialTracked": True}), 201)
    supplier = ok(client.post("/admin/suppliers", headers=admin, json={
        "SupplierCode": f"BH-{tag.upper()}", "Name": "Nhà cung cấp bảo hành", "PhoneNumber": "0281234567",
        "Address": "1 Lê Lợi, TP.HCM"}), 201)
    purchase = ok(client.post("/admin/purchase-orders", headers=staff, json={
        "SupplierId": supplier["SupplierId"], "Items": [{"ProductVariantId": variant["ProductVariantId"],
                                                        "OrderedQuantity": 2, "UnitPrice": "70000.00"}]}), 201)
    base = f"/admin/purchase-orders/{purchase['PurchaseOrderId']}"
    ok(client.post(f"{base}/decision", headers=admin, json={"Status": "Approved"}))
    numbers = [f"BH-{tag}-ORIGINAL", f"BH-{tag}-REPLACEMENT"]
    received = ok(client.post(f"{base}/receive", headers=staff, json={"Items": [{
        "PurchaseOrderItemId": purchase["Items"][0]["PurchaseOrderItemId"], "Quantity": 2,
        "SerialNumbers": numbers}]}))
    assert received["Status"] == "Completed"
    serial_ids = [str(pg.scalar('select "ProductSerialId" from "ProductSerials" where "SerialNumber" = :number',
                                number=number)) for number in numbers]
    result = {"product": product, "variant": variant, "serial_numbers": numbers, "serial_ids": serial_ids}
    assert stock_of(pg, result) == 2
    return result


def delivered_sale(pg, team, methods, *, serial=False):
    item = stocked_serial_variant(pg, team) if serial else stocked_variant(pg, team, quantity=3)
    owner, customer = new_customer(pg)
    fill_cart(pg, customer, item, 1)
    order = ok(pg.client.post("/orders", headers=customer, json={
        "ShippingMethodId": methods["shipping"], "PaymentMethodId": methods["cod"],
        "ReceiverName": "Khách bảo hành", "ReceiverPhone": "0900000000", "ShippingAddress": "1 Đường A"}), 201)
    base = f"/admin/orders/{order['OrderId']}"
    for target in ("Confirmed", "Processing"):
        ok(pg.client.post(f"{base}/status", headers=team["staff"], json={"OrderStatus": target}))
    if serial:
        ok(pg.client.post(f"{base}/serials", headers=team["staff"], json={"Items": [{
            "OrderItemId": order["Items"][0]["OrderItemId"], "SerialNumbers": [item["serial_numbers"][0]]}]}))
    ok(pg.client.post(f"{base}/status", headers=team["staff"], json={"OrderStatus": "Shipping"}))
    delivered = ok(pg.client.post(f"{base}/confirm-cod-delivery", headers=team["staff"], json={}))
    assert delivered["OrderStatus"] == "Delivered" and delivered["PaymentStatus"] == "Paid"
    assert delivered["DeliveredAt"]
    assert delivered["Items"][0]["WarrantyMonths"] == 12
    return {"item": item, "owner": owner, "customer": customer,
            "order": delivered, "line": order["Items"][0]}


def request_payload(sale):
    payload = {"OrderItemId": sale["line"]["OrderItemId"], "IssueDescription": "Máy tự khởi động lại"}
    if "serial_ids" in sale["item"]:
        payload["ProductSerialId"] = sale["item"]["serial_ids"][0]
    return payload


PAUSED_STEPS = (
    ("inspect", {"EligibilityStatus": "Eligible"}),
    ("hand-over", {"ServiceCenter": "Trung tâm bảo hành thử nghiệm"}),
    ("start-processing", None),
    ("propose-result", {"ResultType": "Repaired", "ResultNote": "Đề xuất theo luồng cũ"}),
    ("approve-result", None),
    ("reject-result", {"Reason": "Từ chối theo luồng cũ"}),
    ("complete", None),
)


def processing_request(pg, team, request):
    """Receive the device (with a customer note and an internal note) and start processing: the active workflow."""
    base = f"/admin/warranty-requests/{request['WarrantyRequestId']}"
    received = ok(pg.client.post(f"{base}/receive", headers=team["staff"], json={
        "Note": "Đã nhận máy", "InternalNote": "Technician-only diagnostic"}))
    assert received["AssignedStaffId"] == team["staff_id"] and received["ReceivedAt"]
    assert received["Status"] == "New"
    processing = ok(pg.client.post(f"{base}/advance", headers=team["staff"], json={"ExpectedStage": "Inspecting"}))
    assert (processing["Status"], processing["EligibilityStatus"]) == ("Processing", "Eligible")
    return base


def history_count(pg, request_id):
    return pg.scalar('select count(*) from "ServiceRequestHistories" where "WarrantyRequestId" = :id',
                     id=request_id)


def serial_state(pg, serial_id):
    with pg.engine.connect() as connection:
        return dict(connection.execute(text(
            'select "Status", "OrderItemId", "WarrantyStartDate", "WarrantyEndDate" '
            'from "ProductSerials" where "ProductSerialId" = :id'), {"id": serial_id}).mappings().one())


def test_warranty_active_workflow_http_lifecycle_ownership_roles_and_privacy(pg, team, methods):
    sale = delivered_sale(pg, team, methods)
    client, customer, staff, admin = pg.client, sale["customer"], team["staff"], team["admin"]
    payload = request_payload(sale)
    payload["Attachments"] = [{"FileUrl": "https://example.com/warranty-proof.jpg", "FileType": "Image"}]
    error(client.post("/warranty-requests", json=payload), 401)
    request = ok(client.post("/warranty-requests", headers=customer, json=payload), 201)
    request_id = request["WarrantyRequestId"]
    base = f"/admin/warranty-requests/{request_id}"
    assert (request["Status"], request["EligibilityStatus"]) == ("New", "Pending")
    assert len(request["Attachments"]) == 1
    assert pg.scalar('select count(*) from "ServiceRequestAttachments" where "WarrantyRequestId" = :id',
                     id=request_id) == 1
    stock = stock_of(pg, sale["item"])

    _, intruder = new_customer(pg)
    error(client.get(f"/warranty-requests/{request_id}", headers=intruder), 404, "warranty_request_not_found")
    error(client.post("/warranty-requests", headers=intruder, json=payload), 404, "order_item_not_found")
    assert ok(client.get("/warranty-requests", headers=intruder))["Items"] == []
    error(client.post(f"{base}/receive", headers=customer), 403, "permission_denied")
    error(client.post(f"{base}/advance", headers=customer, json={"ExpectedStage": "New"}), 403, "permission_denied")
    error(client.post("/warranty-requests", headers=staff, json=payload), 403, "permission_denied")
    error(client.post("/warranty-requests", headers=customer, json=payload), 409, "warranty_request_open")
    assert history_count(pg, request_id) == 1
    assert pg.scalar('select count(*) from "WarrantyRequests" where "OrderItemId" = :id',
                     id=sale["line"]["OrderItemId"]) == 1

    processing_request(pg, team, request)
    count = history_count(pg, request_id)
    for action, body in PAUSED_STEPS:  # the repair-centre, proposal/review and completion forms change nothing
        error(client.post(f"{base}/{action}", headers=admin, json=body), 400, "service_workflow_paused")
    assert history_count(pg, request_id) == count and stock_of(pg, sale["item"]) == stock
    published = ok(client.post(f"{base}/advance", headers=staff, json={
        "ExpectedStage": "Repairing", "ResultType": "Repaired", "ResultNote": "Thay chân nguồn, thử máy đạt"}))
    # One operator publishes the actual result directly: proposer and approver are the same person.
    assert published["ResultProposedByUserId"] == published["ResultApprovedByUserId"] == team["staff_id"]
    public = ok(client.get(f"/warranty-requests/{request_id}", headers=customer))
    assert public["ResultType"] == "Repaired" and public["ResultNote"] == "Thay chân nguồn, thử máy đạt"
    assert "Đã nhận máy" in str(public["Histories"]) and "Technician-only diagnostic" not in str(public)
    assert all("InternalNote" not in row and "IsInternal" not in row for row in public["Histories"])

    completed = ok(client.post(f"{base}/advance", headers=staff, json={"ExpectedStage": "Finished"}))
    assert completed["Status"] == "Completed" and completed["CompletedAt"]
    error(client.post(f"{base}/advance", headers=staff, json={"ExpectedStage": "Finished"}),
          409, "service_request_stale")
    assert history_count(pg, request_id) == count + 2 and stock_of(pg, sale["item"]) == stock
    assert pg.scalar('select count(*) from "Notifications" where "ReferenceType" = \'WarrantyRequest\' '
                     'and "ReferenceId" = :id and "UserId" = :owner and "Title" = \'Cập nhật yêu cầu bảo hành\'',
                     id=request_id, owner=sale["owner"]["id"]) == 4  # receive, processing, result, completion
    assert pg.scalar('select count(*) from "Notifications" where "ReferenceId" = :id '
                     'and "Content" like \'%Technician-only%\'', id=request_id) == 0
    assert pg.scalar('select "ResultApprovedByUserId" = "ResultProposedByUserId" '
                     'and "CompletedAt" >= "ResultApprovedAt" and "Status" = \'Completed\' '
                     'from "WarrantyRequests" where "WarrantyRequestId" = :id', id=request_id) is True


def test_serial_tracked_warranty_moves_no_serial_or_stock_and_replacement_stays_paused(pg, team, methods):
    sale = delivered_sale(pg, team, methods, serial=True)
    client, customer, staff, admin = pg.client, sale["customer"], team["staff"], team["admin"]
    original, replacement = sale["item"]["serial_ids"]
    original_before, replacement_before = serial_state(pg, original), serial_state(pg, replacement)
    assert original_before["Status"] == "Sold" and str(original_before["OrderItemId"]) == sale["line"]["OrderItemId"]
    assert replacement_before["Status"] == "Available"
    assert stock_of(pg, sale["item"]) == 1
    request = ok(client.post("/warranty-requests", headers=customer, json=request_payload(sale)), 201)
    request_id = request["WarrantyRequestId"]
    base = processing_request(pg, team, request)
    assert serial_state(pg, original) == original_before  # receiving the device moves no serial
    count = history_count(pg, request_id)
    # Replacing the device is not offered: the active step refuses it and the former replacement steps are paused.
    error(client.post(f"{base}/advance", headers=staff, json={
        "ExpectedStage": "Repairing", "ResultType": "ProductReplaced", "ResultNote": "Đề nghị đổi máy"}), 422)
    error(client.post(f"{base}/propose-result", headers=staff, json={
        "ResultType": "ProductReplaced", "ResultNote": "Đề nghị đổi máy"}), 400, "service_workflow_paused")
    error(client.post(f"{base}/complete", headers=staff, json={"ReplacementProductSerialId": replacement}),
          400, "service_workflow_paused")
    assert history_count(pg, request_id) == count and stock_of(pg, sale["item"]) == 1
    ok(client.post(f"{base}/advance", headers=staff, json={
        "ExpectedStage": "Repairing", "ResultType": "PartReplaced", "ResultNote": "Đã thay linh kiện và kiểm tra đạt"}))
    finished = ok(client.post(f"{base}/advance", headers=staff, json={"ExpectedStage": "Finished"}))
    assert finished["Status"] == "Completed"
    assert serial_state(pg, original) == original_before and serial_state(pg, replacement) == replacement_before
    assert stock_of(pg, sale["item"]) == 1
    # The device stays with the customer, so it can be brought in again once this request is closed.
    following = ok(client.post("/warranty-requests", headers=customer, json={
        **request_payload(sale), "IssueDescription": "Máy lại tự khởi động lại"}), 201)
    assert following["Status"] == "New" and following["ProductSerialId"] == original
    error(client.post("/warranty-requests", headers=customer, json=request_payload(sale)), 409, "warranty_request_open")
    assert stock_of(pg, sale["item"]) == 1


def test_paused_review_endpoints_change_nothing_and_rejection_note_stays_internal(pg, team, methods):
    sale = delivered_sale(pg, team, methods)
    client, customer, staff, admin = pg.client, sale["customer"], team["staff"], team["admin"]
    reviewer = pg.login(pg.seed_user("Admin"))
    request = ok(client.post("/warranty-requests", headers=customer, json=request_payload(sale)), 201)
    request_id = request["WarrantyRequestId"]
    base = processing_request(pg, team, request)
    count = history_count(pg, request_id)
    for headers in (staff, admin, reviewer):  # no role can use the former proposal/review steps
        error(client.post(f"{base}/propose-result", headers=headers,
                          json={"ResultType": "Repaired", "ResultNote": "Chưa kiểm chứng"}),
              400, "service_workflow_paused")
        error(client.post(f"{base}/approve-result", headers=headers), 400, "service_workflow_paused")
        error(client.post(f"{base}/reject-result", headers=headers, json={"Reason": "Tự từ chối"}),
              400, "service_workflow_paused")
    detail = ok(client.get(base, headers=admin))
    assert detail["ResultType"] is None and detail["ResultProposedByUserId"] is None
    assert history_count(pg, request_id) == count

    rejected = ok(client.post(f"{base}/reject", headers=reviewer, json={
        "Reason": "Không thuộc diện bảo hành", "InternalNote": "Reviewer-only rejection evidence"}))
    assert (rejected["Status"], rejected["EligibilityStatus"]) == ("Rejected", "Ineligible")
    [line] = [row for row in rejected["Histories"] if row["NewStatus"] == "Rejected"]
    assert line["InternalNote"] == "Reviewer-only rejection evidence" and "Không thuộc diện bảo hành" in line["Note"]
    public = ok(client.get(f"/warranty-requests/{request_id}", headers=customer))
    assert public["Status"] == "Rejected" and public["EligibilityReason"] == "Không thuộc diện bảo hành"
    assert "Reviewer-only rejection evidence" not in str(public)
    assert pg.scalar('select count(*) from "Notifications" where "ReferenceId" = :id '
                     'and "Content" like \'%Reviewer-only%\'', id=request_id) == 0
    error(client.post(f"{base}/reject", headers=staff, json={"Reason": "Lần hai"}), 400, "service_request_closed")
    error(client.post(f"{base}/advance", headers=staff, json={
        "ExpectedStage": "Repairing", "ResultType": "Repaired", "ResultNote": "Không được mở lại"}),
          409, "service_request_stale")
    assert history_count(pg, request_id) == count + 1 and stock_of(pg, sale["item"]) == 2
