"""Opt-in PostgreSQL warranty workflows over HTTP with real JWTs and SQL invariants.

Uses the protected, fixture-owned database from test_postgres_integration. All
catalog, purchase, order and warranty writes go through APIs; SQL only reads
their persisted results. The payment gateway remains disabled.
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


def processing_request(pg, team, request):
    base = f"/admin/warranty-requests/{request['WarrantyRequestId']}"
    received = ok(pg.client.post(f"{base}/receive", headers=team["staff"], json={
        "Note": "Đã nhận máy", "InternalNote": "Technician-only diagnostic"}))
    assert received["AssignedStaffId"] == team["staff_id"] and received["ReceivedAt"]
    inspected = ok(pg.client.post(f"{base}/inspect", headers=team["staff"],
                                  json={"EligibilityStatus": "Eligible"}))
    assert inspected["EligibilityStatus"] == "Eligible"
    handed = ok(pg.client.post(f"{base}/hand-over", headers=team["staff"], json={
        "ServiceCenter": "Trung tâm bảo hành thử nghiệm", "HandoverCode": f"BH-{uuid.uuid4().hex[:8]}"}))
    assert handed["Status"] == "HandedOver" and handed["HandedOverAt"]
    processing = ok(pg.client.post(f"{base}/start-processing", headers=team["staff"]))
    assert processing["Status"] == "Processing"
    return base


def history_count(pg, request_id):
    return pg.scalar('select count(*) from "ServiceRequestHistories" where "WarrantyRequestId" = :id',
                     id=request_id)


def serial_state(pg, serial_id):
    with pg.engine.connect() as connection:
        return dict(connection.execute(text(
            'select "Status", "OrderItemId", "WarrantyStartDate", "WarrantyEndDate" '
            'from "ProductSerials" where "ProductSerialId" = :id'), {"id": serial_id}).mappings().one())


def test_repaired_warranty_full_http_lifecycle_ownership_roles_and_privacy(pg, team, methods):
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
    error(client.post("/warranty-requests", headers=staff, json=payload), 403, "permission_denied")
    error(client.post("/warranty-requests", headers=customer, json=payload), 409, "warranty_request_open")
    assert history_count(pg, request_id) == 1
    assert pg.scalar('select count(*) from "WarrantyRequests" where "OrderItemId" = :id',
                     id=sale["line"]["OrderItemId"]) == 1

    processing_request(pg, team, request)
    proposed = ok(client.post(f"{base}/propose-result", headers=staff,
                              json={"ResultType": "Repaired", "ResultNote": "Thay chân nguồn, thử máy đạt"}))
    assert proposed["ResultProposedByUserId"] == team["staff_id"] and proposed["ResultProposedAt"]
    pending = ok(client.get(f"/warranty-requests/{request_id}", headers=customer))
    assert pending["ResultType"] is None and pending["ResultNote"] is None
    assert "Technician-only diagnostic" not in str(pending)
    assert all("InternalNote" not in row and "IsInternal" not in row for row in pending["Histories"])
    count = history_count(pg, request_id)
    error(client.post(f"{base}/approve-result", headers=staff), 403, "permission_denied")
    error(client.post(f"{base}/complete", headers=staff), 400, "warranty_result_not_approved")
    assert history_count(pg, request_id) == count and stock_of(pg, sale["item"]) == stock

    approved = ok(client.post(f"{base}/approve-result", headers=admin))
    assert approved["ResultApprovedByUserId"] == team["admin_id"] and approved["ResultApprovedAt"]
    completed = ok(client.post(f"{base}/complete", headers=staff, json={"Note": "Đã trả máy cho khách"}))
    assert completed["Status"] == "Completed" and completed["CompletedAt"]
    public = ok(client.get(f"/warranty-requests/{request_id}", headers=customer))
    assert public["ResultType"] == "Repaired" and public["ResultNote"] == proposed["ResultNote"]
    assert "Technician-only diagnostic" not in str(public)
    assert len(completed["Histories"]) == 8 and len(public["Histories"]) == 7
    assert pg.scalar('select count(*) from "ServiceRequestHistories" '
                     'where "WarrantyRequestId" = :id and "IsInternal"', id=request_id) == 1
    assert pg.scalar('select count(*) from "Notifications" where "ReferenceType" = \'WarrantyRequest\' '
                     'and "ReferenceId" = :id and "UserId" = :owner and "Title" = \'Bảo hành đã hoàn tất\'',
                     id=request_id, owner=sale["owner"]["id"]) == 1
    assert pg.scalar('select count(*) from "Notifications" where "ReferenceId" = :id '
                     'and "UserId" = :admin and "Title" = \'Kết quả bảo hành chờ duyệt\'',
                     id=request_id, admin=team["admin_id"]) == 1
    error(client.post(f"{base}/complete", headers=staff), 400, "invalid_warranty_transition")
    assert history_count(pg, request_id) == 8 and stock_of(pg, sale["item"]) == stock
    assert pg.scalar('select "ResultApprovedByUserId" <> "ResultProposedByUserId" '
                     'and "CompletedAt" >= "ResultApprovedAt" and "Status" = \'Completed\' '
                     'from "WarrantyRequests" where "WarrantyRequestId" = :id', id=request_id) is True


def test_serial_replacement_changes_stock_once_preserves_original_and_starts_new_warranty(pg, team, methods):
    sale = delivered_sale(pg, team, methods, serial=True)
    client, customer, staff, admin = pg.client, sale["customer"], team["staff"], team["admin"]
    original, replacement = sale["item"]["serial_ids"]
    original_before = serial_state(pg, original)
    assert original_before["Status"] == "Sold" and str(original_before["OrderItemId"]) == sale["line"]["OrderItemId"]
    assert serial_state(pg, replacement)["Status"] == "Available"
    assert stock_of(pg, sale["item"]) == 1
    request = ok(client.post("/warranty-requests", headers=customer, json=request_payload(sale)), 201)
    request_id = request["WarrantyRequestId"]
    base = processing_request(pg, team, request)
    assert serial_state(pg, original)["Status"] == "Warranty"
    ok(client.post(f"{base}/propose-result", headers=staff,
                   json={"ResultType": "ProductReplaced", "ResultNote": "Máy lỗi bo mạch, đề nghị đổi máy"}))
    ok(client.post(f"{base}/approve-result", headers=admin))
    count = history_count(pg, request_id)
    error(client.post(f"{base}/complete", headers=staff), 400, "replacement_serial_required")
    error(client.post(f"{base}/complete", headers=staff, json={"ReplacementProductSerialId": original}),
          400, "replacement_same_serial")
    assert history_count(pg, request_id) == count and stock_of(pg, sale["item"]) == 1
    complete_payload = {"ReplacementProductSerialId": replacement, "Note": "Đã giao máy thay thế"}
    completed = ok(client.post(f"{base}/complete", headers=staff, json=complete_payload))
    assert completed["Status"] == "Completed"
    assert completed["ReplacementProductSerialId"] == replacement and completed["ReplacementHandedOverAt"]
    assert completed["ReplacementHandedOverByUserId"] == team["staff_id"]
    old, new = serial_state(pg, original), serial_state(pg, replacement)
    assert old["Status"] == "Returned" and old["OrderItemId"] == original_before["OrderItemId"]
    assert (old["WarrantyStartDate"], old["WarrantyEndDate"]) == (
        original_before["WarrantyStartDate"], original_before["WarrantyEndDate"])
    assert new["Status"] == "Sold" and str(new["OrderItemId"]) == sale["line"]["OrderItemId"]
    assert stock_of(pg, sale["item"]) == 0
    assert pg.scalar('select s."WarrantyStartDate" = (w."ReplacementHandedOverAt" '
                     'at time zone \'Asia/Ho_Chi_Minh\')::date and s."WarrantyEndDate" = '
                     '(s."WarrantyStartDate" + make_interval(months => i."WarrantyMonths") - interval \'1 day\')::date '
                     'from "WarrantyRequests" w join "OrderItems" i on i."OrderItemId" = w."OrderItemId" '
                     'join "ProductSerials" s on s."ProductSerialId" = w."ReplacementProductSerialId" '
                     'where w."WarrantyRequestId" = :id', id=request_id) is True
    error(client.post(f"{base}/complete", headers=staff, json=complete_payload),
          400, "invalid_warranty_transition")
    assert stock_of(pg, sale["item"]) == 0 and history_count(pg, request_id) == count + 1
    assert serial_state(pg, original) == old and serial_state(pg, replacement) == new
    # A replacement remains owned by the customer and is eligible for its newly recorded warranty.
    next_payload = {**request_payload(sale), "ProductSerialId": replacement, "IssueDescription": "Kiểm tra máy thay thế"}
    following = ok(client.post("/warranty-requests", headers=customer, json=next_payload), 201)
    assert following["Status"] == "New" and following["ProductSerialId"] == replacement
    error(client.post("/warranty-requests", headers=customer, json=next_payload), 409, "warranty_request_open")
    error(client.post("/warranty-requests", headers=customer, json=request_payload(sale)),
          400, "serial_not_with_customer")
    assert stock_of(pg, sale["item"]) == 0


def test_admin_cannot_review_own_proposal_and_rejected_proposal_can_be_resubmitted(pg, team, methods):
    sale = delivered_sale(pg, team, methods)
    client, customer, staff, admin = pg.client, sale["customer"], team["staff"], team["admin"]
    reviewer_user = pg.seed_user("Admin")
    reviewer = pg.login(reviewer_user)
    request = ok(client.post("/warranty-requests", headers=customer, json=request_payload(sale)), 201)
    request_id = request["WarrantyRequestId"]
    base = processing_request(pg, team, request)
    ok(client.post(f"{base}/propose-result", headers=admin,
                   json={"ResultType": "Repaired", "ResultNote": "Chưa kiểm chứng đầy đủ"}))
    count = history_count(pg, request_id)
    error(client.post(f"{base}/approve-result", headers=admin), 400, "warranty_self_review_not_allowed")
    error(client.post(f"{base}/reject-result", headers=admin, json={"Reason": "Tự từ chối"}),
          400, "warranty_self_review_not_allowed")
    assert history_count(pg, request_id) == count
    rejected = ok(client.post(f"{base}/reject-result", headers=reviewer,
                              json={"Reason": "Reviewer-only rejection evidence"}))
    assert rejected["Status"] == "Processing"
    assert rejected["ResultType"] is None and rejected["ResultNote"] is None
    assert rejected["ResultProposedByUserId"] is None and rejected["ResultApprovedAt"] is None
    public = ok(client.get(f"/warranty-requests/{request_id}", headers=customer))
    assert "Reviewer-only rejection evidence" not in str(public)
    assert pg.scalar('select count(*) from "ServiceRequestHistories" '
                     'where "WarrantyRequestId" = :id and "IsInternal"', id=request_id) == 2
    error(client.post(f"{base}/complete", headers=staff), 400, "warranty_result_not_approved")
    ok(client.post(f"{base}/propose-result", headers=staff,
                   json={"ResultType": "PartReplaced", "ResultNote": "Đã thay linh kiện và kiểm tra đạt"}))
    approved = ok(client.post(f"{base}/approve-result", headers=reviewer))
    assert approved["ResultProposedByUserId"] == team["staff_id"]
    assert approved["ResultApprovedByUserId"] == reviewer_user["id"]
    assert ok(client.post(f"{base}/complete", headers=staff))["Status"] == "Completed"
    assert stock_of(pg, sale["item"]) == 2
