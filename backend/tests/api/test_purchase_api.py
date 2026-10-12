"""API tests — Purchasing and inventory: suppliers, purchase orders (Staff drafts/receives, Admin decides), stock."""

from .support import (
    expect,
    expect_forbidden,
    expect_unauthorized,
    expect_validation,
    random_id,
    requires_postgres,
)

pytestmark = requires_postgres


def stock(api, variant_id):
    return api.scalar('select "StockQuantity" from "ProductVariants" where "ProductVariantId" = :id', id=variant_id)


def draft_order(api, staff, supplier_id, variant_id, quantity=10, price="70000.00"):
    return expect(api.client.post("/admin/purchase-orders", headers=staff.headers, json={
        "SupplierId": supplier_id, "Items": [{"ProductVariantId": variant_id, "OrderedQuantity": quantity,
                                              "UnitPrice": price}]}), 201)


def receive(api, staff, order, quantity):
    return api.client.post(f"/admin/purchase-orders/{order['PurchaseOrderId']}/receive", headers=staff.headers, json={
        "Items": [{"PurchaseOrderItemId": order["Items"][0]["PurchaseOrderItemId"], "Quantity": quantity}]})


def test_success_supplier_purchase_receipt_and_stock(api, admin, staff):
    client = api.client
    variant_id = api.seed.variant(stock=0)["variant_id"]
    supplier = expect(client.post("/admin/suppliers", headers=admin.headers, json={
        "SupplierCode": "NCC-APPLE", "Name": "Nhà phân phối", "PhoneNumber": "0281234567",
        "Address": "1 Lê Lợi, TP.HCM"}), 201)
    order = draft_order(api, staff, supplier["SupplierId"], variant_id)
    assert order["Status"] == "Pending" and order["TotalAmount"] == "700000.00"
    assert expect(client.post(f"/admin/purchase-orders/{order['PurchaseOrderId']}/decision", headers=admin.headers,
                              json={"Status": "Approved"}), 200)["Status"] == "Approved"
    assert expect(receive(api, staff, order, 6), 200)["Status"] == "Receiving"
    assert expect(receive(api, staff, order, 4), 200)["Status"] == "Completed"
    assert stock(api, variant_id) == 10
    assert len(expect(client.get(f"/admin/purchase-orders/{order['PurchaseOrderId']}/receipts",
                                 headers=staff.headers), 200)) == 2
    adjusted = expect(client.post(f"/admin/variants/{variant_id}/stock-adjustments", headers=admin.headers,
                                  json={"QuantityChange": -1, "Reason": "Hàng mẫu trưng bày"}), 201)
    assert adjusted["QuantityChange"] == -1 and stock(api, variant_id) == 9


def test_401_without_token(api):
    expect_unauthorized(api.client.get("/admin/suppliers"))
    expect_unauthorized(api.client.post("/admin/purchase-orders", json={}))
    expect_unauthorized(api.client.get("/admin/inventory/low-stock"))


def test_403_roles(api, admin, staff, customer):
    supplier = api.seed.supplier()
    variant_id = api.seed.variant()["variant_id"]
    order = draft_order(api, staff, supplier["supplier_id"], variant_id)
    expect_forbidden(api.client.get("/admin/purchase-orders", headers=customer.headers))
    expect_forbidden(api.client.post("/admin/suppliers", headers=staff.headers, json={
        "SupplierCode": "NCC-X", "Name": "x", "PhoneNumber": "0281234567", "Address": "x"}))  # Admin only
    expect_forbidden(api.client.post(f"/admin/purchase-orders/{order['PurchaseOrderId']}/decision",
                                     headers=staff.headers, json={"Status": "Approved"}))  # Admin decides
    expect_forbidden(api.client.post(f"/admin/variants/{variant_id}/stock-adjustments", headers=staff.headers,
                                     json={"QuantityChange": 1, "Reason": "x"}))


def test_404_unknown_resources(api, admin, staff):
    variant_id = api.seed.variant()["variant_id"]
    expect(api.client.get(f"/admin/purchase-orders/{random_id()}", headers=staff.headers), 404)
    expect(api.client.get(f"/admin/suppliers/{random_id()}", headers=staff.headers), 404)
    expect(api.client.post("/admin/purchase-orders", headers=staff.headers, json={
        "SupplierId": random_id(), "Items": [{"ProductVariantId": variant_id, "OrderedQuantity": 1,
                                             "UnitPrice": "1.00"}]}), 404)
    expect(api.client.post(f"/admin/purchase-orders/{random_id()}/decision", headers=admin.headers,
                           json={"Status": "Approved"}), 404)


def test_409_duplicate_supplier_code(api, admin):
    supplier = api.seed.supplier()
    expect(api.client.post("/admin/suppliers", headers=admin.headers, json={
        "SupplierCode": supplier["code"], "Name": "Trùng", "PhoneNumber": "0281234567", "Address": "x"}), 409,
        "supplier_code_exists")


def test_422_validation(api, admin, staff):
    supplier = api.seed.supplier()
    variant_id = api.seed.variant()["variant_id"]
    expect_validation(api.client.post("/admin/purchase-orders", headers=staff.headers,
                                      json={"SupplierId": supplier["supplier_id"], "Items": []}), "Items")
    expect_validation(api.client.post("/admin/purchase-orders", headers=staff.headers, json={
        "SupplierId": supplier["supplier_id"], "Items": [{"ProductVariantId": variant_id, "OrderedQuantity": 0,
                                                         "UnitPrice": "1.00"}]}), "OrderedQuantity")
    order = draft_order(api, staff, supplier["supplier_id"], variant_id)
    expect_validation(api.client.post(f"/admin/purchase-orders/{order['PurchaseOrderId']}/decision",
                                      headers=admin.headers, json={"Status": "Maybe"}), "Status")
    # Rejecting needs a reason (checked by the schema).
    expect_validation(api.client.post(f"/admin/purchase-orders/{order['PurchaseOrderId']}/decision",
                                      headers=admin.headers, json={"Status": "Rejected"}))
    expect_validation(api.client.post("/admin/suppliers", headers=admin.headers,
                                      json={"SupplierCode": "NCC-Y", "Name": "x"}), "PhoneNumber", "Address")


def test_business_rules_purchasing_and_stock(api, admin, staff):
    client = api.client
    supplier = api.seed.supplier()
    variant_id = api.seed.variant(stock=2)["variant_id"]
    order = draft_order(api, staff, supplier["supplier_id"], variant_id, quantity=5)
    expect(receive(api, staff, order, 1), 400, "purchase_order_not_receivable")  # not approved yet
    expect(client.post(f"/admin/purchase-orders/{order['PurchaseOrderId']}/decision", headers=admin.headers,
                       json={"Status": "Approved"}), 200)
    expect(client.post(f"/admin/purchase-orders/{order['PurchaseOrderId']}/items", headers=staff.headers, json={
        "ProductVariantId": variant_id, "OrderedQuantity": 1, "UnitPrice": "1.00"}), 400,
        "purchase_order_not_editable")  # an approved order is frozen
    expect(receive(api, staff, order, 6), 400, "receive_exceeds_ordered")
    expect(client.post(f"/admin/variants/{variant_id}/stock-adjustments", headers=admin.headers,
                       json={"QuantityChange": -3, "Reason": "Kiểm kê"}), 400, "insufficient_stock")
    assert stock(api, variant_id) == 2
