"""API tests — Payments: payment methods, COD collection records, QR payment requests and refunds."""

from decimal import Decimal

import pytest

from app.main import app
from app.routers import dependencies as deps

from .support import (
    expect,
    expect_forbidden,
    expect_unauthorized,
    expect_validation,
    random_id,
    requires_postgres,
)

pytestmark = requires_postgres


class UnreachableGateway:
    """Stands in for SePay when a test needs a configured gateway; failing checks must stop before any call."""

    def create_qr_payment(self, **_):
        raise AssertionError("the gateway must not be called")


@pytest.fixture
def gateway(api):
    app.dependency_overrides[deps.get_payment_gateway] = lambda: UnreachableGateway()


def test_success_methods_and_cod_collection_records(api, admin, staff, customer):
    client = api.client
    shop = api.shop(price="100000.00")
    created = expect(client.post("/admin/payment-methods", headers=admin.headers,
                                 json={"Code": "BANK_QR", "Name": "Chuyển khoản QR", "DisplayOrder": 2}), 201)
    expect(client.patch(f"/admin/payment-methods/{created['PaymentMethodId']}", headers=admin.headers,
                        json={"Name": "Chuyển khoản ngân hàng"}), 200)
    codes = {m["Code"] for m in expect(client.get("/payment-methods"), 200)}
    assert {"COD", "BANK_QR"} <= codes

    line = api.delivered_line(customer, staff, shop)
    mine = expect(client.get(f"/orders/{line['order_id']}/payments", headers=customer.headers), 200)
    assert [(p["TransactionType"], p["Status"], Decimal(p["Amount"])) for p in mine] == [
        ("Payment", "Success", Decimal("130000"))]
    internal = expect(client.get(f"/admin/orders/{line['order_id']}/payments", headers=staff.headers), 200)
    assert internal[0]["PaymentTransactionId"] == mine[0]["PaymentTransactionId"]


def test_401_without_token(api):
    order_id = random_id()
    expect_unauthorized(api.client.post(f"/orders/{order_id}/payments/qr"))
    expect_unauthorized(api.client.get(f"/orders/{order_id}/payments"))
    expect_unauthorized(api.client.post("/admin/payment-methods", json={"Code": "X", "Name": "X"}))
    expect_unauthorized(api.client.post(f"/admin/orders/{order_id}/refunds", json={"Amount": "1.00"}))


def test_403_roles(api, staff, customer):
    order_id = api.place_order(customer, api.shop())["OrderId"]
    expect_forbidden(api.client.post("/admin/payment-methods", headers=staff.headers,
                                     json={"Code": "STAFF", "Name": "x"}))  # Staff only views methods
    expect_forbidden(api.client.get(f"/admin/orders/{order_id}/payments", headers=customer.headers))
    expect_forbidden(api.client.post(f"/orders/{order_id}/payments/qr", headers=staff.headers))  # Customer only
    expect_forbidden(api.client.post(f"/admin/refunds/{random_id()}/resolve", headers=staff.headers, json={
        "Success": True, "EvidenceReference": "UNC-1", "ResolutionNote": "x"}))  # manual confirmation is Admin's


def test_404_unknown_or_foreign(api, gateway, admin, customer, other_customer):
    foreign = api.place_order(other_customer, api.shop())["OrderId"]
    expect(api.client.get(f"/payment-methods/{random_id()}"), 404)
    expect(api.client.patch(f"/admin/payment-methods/{random_id()}", headers=admin.headers, json={"Name": "x"}), 404,
           "payment_method_not_found")
    expect(api.client.get(f"/orders/{foreign}/payments", headers=customer.headers), 404)
    expect(api.client.post(f"/orders/{foreign}/payments/qr", headers=customer.headers), 404, "order_not_found")
    expect(api.client.post(f"/orders/{random_id()}/payments/qr", headers=customer.headers), 404, "order_not_found")
    expect(api.client.post(f"/admin/refunds/{random_id()}/resolve", headers=admin.headers, json={
        "Success": True, "EvidenceReference": "UNC-1", "ResolutionNote": "x"}), 404, "refund_transaction_not_found")


def test_409_duplicate_payment_method_code(api, admin):
    expect(api.client.post("/admin/payment-methods", headers=admin.headers, json={"Code": "MOMO", "Name": "MoMo"}),
           201)
    expect(api.client.post("/admin/payment-methods", headers=admin.headers, json={"Code": "MOMO", "Name": "Khác"}),
           409, "payment_method_code_exists")


def test_422_validation(api, admin, staff, customer):
    line = api.delivered_line(customer, staff, api.shop())
    expect_validation(api.client.post("/admin/payment-methods", headers=admin.headers, json={"Code": "X"}), "Name")
    expect_validation(api.client.post(f"/admin/orders/{line['order_id']}/refunds", headers=staff.headers,
                                      json={"Amount": "-5"}), "Amount")
    expect_validation(api.client.post(f"/admin/refunds/{random_id()}/resolve", headers=admin.headers,
                                      json={"Success": True}), "EvidenceReference", "ResolutionNote")


def test_business_rules_payments(api, gateway, admin, staff, customer):
    client = api.client
    shop = api.shop()
    pending = api.place_order(customer, shop)["OrderId"]
    expect(client.post(f"/orders/{pending}/payments/qr", headers=customer.headers), 400, "payment_method_is_cod")
    app.dependency_overrides[deps.get_payment_gateway] = lambda: None
    expect(client.post(f"/orders/{pending}/payments/qr", headers=customer.headers), 400,
           "payment_gateway_not_configured")
    # A delivered, not cancelled order only refunds overpayment; ordinary refunds go through return requests.
    line = api.delivered_line(customer, staff, shop)
    expect(client.post(f"/admin/orders/{line['order_id']}/refunds", headers=staff.headers,
                       json={"Amount": "10000.00"}), 400, "refund_not_allowed")
    expect(client.post(f"/admin/orders/{pending}/payments/cod", headers=staff.headers), 400, "cod_not_paid")
    expect(client.delete(f"/admin/payment-methods/{shop['cod_id']}", headers=admin.headers), 400,
           "payment_method_in_use")
