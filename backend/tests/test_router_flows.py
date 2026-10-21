"""End-to-end HTTP flows through the Stage 6 routers with the real Services on the in-memory fakes.

Unlike test_business_routers (recorded calls), these flows return real Service results, so FastAPI validates
them against each route's response_model, including the chat routes that narrow internal schemas.
"""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_actor, get_optional_actor
from app.main import app
from app.models import Message
from app.routers import dependencies as deps

from tests.fakes import (
    Factory,
    FakeSession,
    InMemoryDB,
    chat_service,
    content_service,
    notification_service,
    order_service,
    statistics_service,
    purchase_order_service,
)


@pytest.fixture
def flow():
    db = InMemoryDB()
    session = FakeSession(db)
    factory = Factory(db)
    state = {"actor": None}
    overrides = {
        deps.get_chat_service: lambda: chat_service(db, session),
        deps.get_order_service: lambda: order_service(db, session),
        deps.get_content_service: lambda: content_service(db, session),
        deps.get_statistics_service: lambda: statistics_service(db, session),
        deps.get_notification_service: lambda: notification_service(db, session),
        deps.get_purchase_order_service: lambda: purchase_order_service(db, session),
        get_current_actor: lambda: state["actor"],
        get_optional_actor: lambda: state["actor"],
    }
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            def as_user(user):
                state["actor"] = factory.actor(user)
                return client

            yield client, db, factory, as_user
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def test_purchase_owner_and_admin_deletion_are_enforced_over_http(flow):
    _, db, f, as_user = flow
    staff, other, admin = f.user("Staff"), f.user("Staff"), f.user("Admin")
    supplier, variant = f.supplier(), f.variant(stock=0, cost="0")
    po = ok(as_user(staff).post("/admin/purchase-orders", json={
        "SupplierId": str(supplier.SupplierId), "Items": [{
            "ProductVariantId": str(variant.ProductVariantId), "OrderedQuantity": 1, "UnitPrice": "10.00",
        }],
    }), 201)
    path = "/admin/purchase-orders/" + po["PurchaseOrderId"]
    assert as_user(other).patch(path, json={"Note": "forged"}).status_code == 403
    assert as_user(admin).patch(path, json={"Note": "admin cannot override owner"}).status_code == 403
    assert as_user(staff).delete(path).status_code == 403
    assert as_user(staff).post(path + "/cancel").status_code == 404
    assert as_user(staff).post(path + "/resubmit").status_code == 404
    assert ok(as_user(staff).patch(path, json={"Note": "own draft"}))["Note"] == "own draft"
    assert as_user(admin).post(path + "/decision", json={"Status": "Rejected", "RejectReason": "New purchase required"}).status_code == 200
    assert as_user(staff).patch(path, json={"Note": "cannot reopen"}).status_code == 400
    assert as_user(admin).post(path + "/resubmit").status_code == 404
    rejected = ok(as_user(staff).get(path))
    assert rejected["Status"] == "Rejected" and rejected["RejectReason"] == "New purchase required"
    assert as_user(admin).delete(path).status_code == 204
    assert as_user(staff).get(path).status_code == 404


def test_chat_flow_keeps_customer_and_staff_views_apart(flow):
    _, db, f, as_user = flow
    customer, staff = f.user(), f.user("Staff")

    conversation = ok(as_user(customer).post("/conversations", json={"Mode": "Staff"}), 201)
    conversation_id = conversation["ConversationId"]
    assert "AssignedStaffId" not in conversation

    queue = ok(as_user(staff).get("/admin/conversations/unassigned"))
    assert [c["ConversationId"] for c in queue["Items"]] == [conversation_id]
    claimed = ok(as_user(staff).post(f"/admin/conversations/{conversation_id}/claim"))
    assert claimed["AssignedStaffId"] == str(staff.UserId)
    reply = ok(as_user(staff).post(f"/admin/conversations/{conversation_id}/messages",
                                   json={"MessageType": "Text", "Content": "Chào anh"}), 201)
    assert reply["SenderUserId"] == str(staff.UserId)

    ok(as_user(customer).post(f"/conversations/{conversation_id}/messages",
                              json={"MessageType": "Text", "Content": "Cho tôi hỏi giá"}), 201)
    page = ok(as_user(customer).get(f"/conversations/{conversation_id}/messages"))
    staff_messages = [m for m in page["Items"] if m["SenderType"] == "Staff"]
    assert staff_messages and all(m["SenderUserId"] is None for m in staff_messages)
    assert len(db.rows(Message)) == 2

    # Staff on a customer route gets the customer view (narrowed), not a server error.
    narrowed = ok(as_user(staff).get(f"/conversations/{conversation_id}"))
    assert "AssignedStaffId" not in narrowed
    internal = ok(as_user(staff).get(f"/admin/conversations/{conversation_id}"))
    assert internal["AssignedStaffId"] == str(staff.UserId)
    # A customer never reaches the internal route, even for their own conversation.
    assert as_user(customer).get(f"/admin/conversations/{conversation_id}").status_code == 403

    closed = ok(as_user(staff).post(f"/admin/conversations/{conversation_id}/close"))
    assert closed["Status"] == "Closed"


def test_order_flow_from_cart_to_processing(flow):
    _, _, f, as_user = flow
    customer, staff, admin = f.user(), f.user("Staff"), f.user("Admin")
    variant = f.variant(stock=5, price="100000.00", cost="70000.00")
    f.cart_with(customer, (variant, 2))
    payload = {"ShippingMethodId": str(f.shipping_method("30000.00").ShippingMethodId),
               "PaymentMethodId": str(f.payment_method("COD").PaymentMethodId),
               "ReceiverName": "Nguyễn Văn A", "ReceiverPhone": "0900000000", "ShippingAddress": "1 Đường A"}

    order = ok(as_user(customer).post("/orders", json=payload), 201)
    order_id = order["OrderId"]
    assert order["TotalAmount"] == "230000.00"

    mine = ok(as_user(customer).get("/orders"))
    assert [o["OrderId"] for o in mine["Items"]] == [order_id]
    assert ok(as_user(customer).get(f"/orders/{order_id}"))["OrderId"] == order_id
    assert ok(as_user(customer).get(f"/orders/{order_id}/history"))

    listed = ok(as_user(staff).get("/admin/orders", params={"order_status": "Pending"}))
    assert listed["Total"] == 1
    confirmed = ok(as_user(staff).post(f"/admin/orders/{order_id}/status", json={"OrderStatus": "Confirmed"}))
    assert confirmed["OrderStatus"] == "Confirmed"
    processing = ok(as_user(staff).post(f"/admin/orders/{order_id}/status", json={"OrderStatus": "Processing"}))
    assert processing["OrderStatus"] == "Processing"
    assert confirmed["AssignedStaffId"] == str(staff.UserId)
    cogs = ok(as_user(admin).get(f"/admin/orders/{order_id}/cogs"))
    assert cogs == {"OrderId": order_id, "Cogs": "140000.00"}
    # COGS is Admin-only inside the Service: Staff passes the /admin guard but the Service refuses.
    assert as_user(staff).get(f"/admin/orders/{order_id}/cogs").status_code == 403


def test_order_date_filters_require_a_timezone(flow):
    client, _, f, as_user = flow
    as_user(f.user())
    assert client.get("/orders", params={"ordered_from": "2026-10-01T00:00:00"}).status_code == 422
    assert client.get("/orders", params={"ordered_from": "2026-10-01T00:00:00+07:00"}).status_code == 200


def test_notification_counts_are_wrapped(flow):
    _, db, f, as_user = flow
    customer = f.user()
    service = notification_service(db, FakeSession(db))
    with service.transaction():  # notify() only runs inside an enclosing use case
        for title in ("Đơn hàng mới", "Đã giao"):
            service.notify(customer.UserId, title=title, content="...", notification_type="Order")
    client = as_user(customer)
    assert ok(client.get("/users/me/notifications/unread-count")) == {"Count": 2}
    assert ok(client.get("/users/me/notifications"))["Total"] == 2
    assert ok(client.post("/users/me/notifications/read-all")) == {"Count": 2}
    assert ok(client.get("/users/me/notifications/unread-count")) == {"Count": 0}


def test_banner_management_and_public_display(flow):
    client, _, f, as_user = flow
    admin = f.user("Admin")
    banner = ok(as_user(admin).post("/admin/banners", json={"Title": "Sale", "ImageUrl": "https://cdn.example.com/a.jpg"}),
                201)
    assert ok(as_user(admin).get("/admin/banners"))[0]["BannerId"] == banner["BannerId"]
    public = client.get("/banners")
    assert [b["BannerId"] for b in ok(public)] == [banner["BannerId"]]
    ok(as_user(admin).post(f"/admin/banners/{banner['BannerId']}/deactivate"))
    assert ok(client.get("/banners")) == []


def test_statistics_respond_with_their_schemas(flow):
    _, _, f, as_user = flow
    client = as_user(f.user("Staff"))
    period = {"date_from": date(2026, 10, 1).isoformat(), "date_to": date(2026, 10, 31).isoformat()}
    assert ok(client.get("/admin/statistics/orders", params=period))["TotalOrders"] == 0
    assert ok(client.get("/admin/statistics/revenue", params=period))["OrderCount"] == 0
    assert ok(client.get("/admin/statistics/top-products", params=period)) == []
    assert ok(client.get("/admin/statistics/inventory"))["Total"] == 0
    bad = client.get("/admin/statistics/orders", params={"date_from": "2026-10-31", "date_to": "2026-10-01"})
    assert bad.status_code == 400 and bad.json()["code"] == "invalid_statistics_period"


@pytest.mark.parametrize("role", ["Staff", "Admin"])
@pytest.mark.parametrize("report", ["orders", "revenue", "cogs", "top-products"])
def test_statistics_date_before_utc_minimum_returns_400(flow, role, report):
    client, _, factory, as_user = flow
    as_user(factory.user(role))
    response = client.get(f"/admin/statistics/{report}",
                          params={"date_from": "0001-01-01", "date_to": "2026-10-31"})
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "invalid_statistics_period"


def test_unknown_ids_return_404_with_a_code(flow):
    _, _, f, as_user = flow
    client = as_user(f.user("Admin"))
    response = client.get(f"/admin/orders/{uuid.uuid4()}")
    assert response.status_code == 404 and response.json()["code"]
