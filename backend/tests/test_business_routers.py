"""Stage 6 business routers: wiring to Services, the /admin guard and parameter passing.

Services are replaced by a recorder, so no database is needed: every Service call is recorded and answered
with a NotFoundError carrying the code "probe" (HTTP 404). Business rules are covered by the Service tests.
"""

import importlib
import inspect
import re
import uuid
from datetime import date

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_actor, get_optional_actor
from app.core.storage import get_avatar_storage
from app.database import get_db
from app.main import app
from app.routers import dependencies as deps
from app.routers.statistics import get_report_service
from app.services import Actor
from app.services.exceptions import NotFoundError

SERVICE_PROVIDERS = [value for name, value in vars(deps).items()
                     if name.startswith("get_") and name.endswith("_service")] + [get_report_service]
BUSINESS_MODULES = ("catalog", "wishlist_cart", "orders", "payments", "promotions", "purchasing", "reviews",
                    "chat", "service_requests", "content", "statistics")
STAGE5_ACCOUNT_PATHS = ("/auth", "/users/me/avatar", "/users/me/default-address", "/admin/users")
# This endpoint streams raw bytes to a storage helper instead of an injected
# business service. Its upload contract is covered in test_product_media.py.
RAW_UPLOAD_PATHS = {"/admin/product-image-uploads"}
PAUSED_WORKFLOW_PATHS = {
    f"/admin/{resource}/{{request_id}}/{action}"
    for resource, actions in (
        ("warranty-requests", ("inspect", "hand-over", "start-processing", "propose-result",
                               "approve-result", "reject-result", "complete")),
        ("return-requests", ("inspect", "approve", "refund", "confirm-refund")),
    )
    for action in actions
}


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            raise NotFoundError("probe", code="probe")

        return call


def business_routes():
    """Routes of the Stage 6 routers (FastAPI wraps included routers, so read them from the modules)."""
    for name in BUSINESS_MODULES + ("users",):
        module = importlib.import_module(f"app.routers.{name}")
        for router in (getattr(module, "router", None), getattr(module, "admin_router", None)):
            for route in getattr(router, "routes", []):
                if not isinstance(route, APIRoute):
                    continue
                if name == "users" and (route.path.startswith(STAGE5_ACCOUNT_PATHS) or route.path == "/users/me"):
                    continue
                yield route


def expected_method(route):
    source = inspect.getsource(route.endpoint)
    names = re.findall(r"service\.(\w+)\(", source)
    if route.path in PAUSED_WORKFLOW_PATHS:
        assert names == [] and "return paused_service_workflow()" in source, route.path
        return None
    assert len(names) == 1, (route.path, names)
    return names[0]


def sample_url(route):
    path = route.path
    for param in re.findall(r"{(\w+)}", path):
        value = "SN-1" if param in ("serial_number",) else ("demo-slug" if param == "slug" else str(uuid.uuid4()))
        path = path.replace("{" + param + "}", value)
    query = {}
    for param in route.dependant.query_params:
        if param.field_info.is_required():
            annotation = param.field_info.annotation
            query[param.alias] = "2026-10-01" if annotation is date else "x"
    return path, query


def has_required_body(route):
    body = route.dependant.body_params
    return bool(body) and any(param.field_info.is_required() for param in body)


def unexpected_database_dependency():
    raise AssertionError("Router wiring tests must replace every database-backed service.")


@pytest.fixture
def harness():
    recorder = Recorder()
    state = {"actor": Actor(uuid.uuid4(), "Admin")}
    previous = app.dependency_overrides.copy()
    for provider in SERVICE_PROVIDERS:
        app.dependency_overrides[provider] = lambda: recorder
    app.dependency_overrides[get_current_actor] = lambda: state["actor"]
    app.dependency_overrides[get_optional_actor] = lambda: state["actor"]
    app.dependency_overrides[get_avatar_storage] = lambda: None
    app.dependency_overrides[get_db] = unexpected_database_dependency
    try:
        with TestClient(app) as client:
            yield client, recorder, state
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def call(client, route, *, json=None):
    path, query = sample_url(route)
    method = sorted(route.methods)[0]
    return client.request(method, path, params=query, json=json)


def test_every_business_service_method_is_reachable_through_one_route():
    routes = list(business_routes())
    assert len(routes) > 180
    assert {route.path for route in routes} >= RAW_UPLOAD_PATHS | PAUSED_WORKFLOW_PATHS
    for route in routes:
        if route.path in RAW_UPLOAD_PATHS:
            continue
        expected_method(route)  # Active endpoints delegate; paused endpoints cannot call a service.


def test_routes_without_required_body_call_their_service_method(harness):
    client, recorder, _ = harness
    checked = 0
    for route in business_routes():
        if has_required_body(route) or route.path in RAW_UPLOAD_PATHS:
            continue
        recorder.calls.clear()
        response = call(client, route)
        method = expected_method(route)
        if method is None:
            assert response.status_code == 400, (route.path, response.status_code, response.text)
            assert response.json()["code"] == "service_workflow_paused", route.path
            assert recorder.calls == [], route.path
            continue
        assert response.status_code == 404, (route.path, response.status_code, response.text)
        assert response.json()["code"] == "probe", route.path
        assert [name for name, _, _ in recorder.calls] == [method], route.path
        checked += 1
    assert checked > 100


def test_routes_with_body_validate_input_before_reaching_the_service(harness):
    client, recorder, _ = harness
    for route in business_routes():
        if not has_required_body(route):
            continue
        recorder.calls.clear()
        response = call(client, route, json={"UnknownField": 1})
        assert response.status_code == 422, (route.path, response.status_code)
        assert recorder.calls == [], route.path


def test_admin_routes_refuse_customers_before_any_service_call(harness):
    client, recorder, state = harness
    state["actor"] = Actor(uuid.uuid4(), "Customer")
    admin_routes = [route for route in business_routes() if route.path.startswith("/admin/")]
    assert len(admin_routes) > 100
    for route in admin_routes:
        recorder.calls.clear()
        response = call(client, route, json={})
        assert response.status_code == 403, (route.path, response.status_code)
        assert response.json()["code"] == "permission_denied"
        assert recorder.calls == [], route.path


@pytest.mark.parametrize("role", ["Staff", "Admin"])
def test_admin_guard_lets_staff_and_admin_through(harness, role):
    client, recorder, state = harness
    state["actor"] = Actor(uuid.uuid4(), role)
    response = client.get("/admin/orders")
    assert response.status_code == 404 and response.json()["code"] == "probe"
    assert recorder.calls[0][0] == "admin_list_orders"


def test_protected_routes_require_a_token():
    previous = app.dependency_overrides.copy()
    recorder = Recorder()
    for provider in SERVICE_PROVIDERS:
        app.dependency_overrides[provider] = lambda: recorder
    try:
        with TestClient(app) as client:
            for path in ("/cart", "/orders", "/wishlist", "/users/me/addresses", "/admin/orders",
                         "/admin/statistics/inventory", "/warranty-requests", "/conversations"):
                assert client.get(path).status_code == 401, path
            assert recorder.calls == []
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_public_reads_pass_no_actor_when_signed_out(harness):
    client, recorder, state = harness
    state["actor"] = None
    assert client.get("/categories").status_code == 404
    assert recorder.calls[-1] == ("list_categories", (), {"actor": None, "active_only": True, "parent_id": None,
                                                          "roots_only": False})
    assert client.get("/products", params={"keyword": "iphone", "page": 2}).status_code == 404
    assert recorder.calls[-1][2] == {"keyword": "iphone", "category_id": None, "brand_id": None, "include_descendants": False, "min_price": None, "max_price": None,
                                     "sort": None, "in_stock": False, "new_arrivals": False, "specs": None, "page": 2,
                                     "page_size": 20}


def test_actor_and_body_reach_the_service(harness):
    client, recorder, state = harness
    customer = Actor(uuid.uuid4(), "Customer")
    state["actor"] = customer
    order_id = uuid.uuid4()
    response = client.post(f"/orders/{order_id}/cancel", json={"CancelReason": "Đổi ý"})
    assert response.status_code == 404
    name, args, _ = recorder.calls[-1]
    assert name == "cancel_customer_order"
    assert args[0] is customer and args[1] == order_id and args[2].CancelReason == "Đổi ý"

    client.put("/cart/selection", json={"IsSelected": False})
    assert recorder.calls[-1][:2] == ("set_all_selected", (customer, False))

    client.get("/cart/coupon-preview", params={"code": "SALE10"})
    assert recorder.calls[-1][:2] == ("preview_cart_coupon", (customer, "SALE10"))


def test_admin_parameters_reach_the_service(harness):
    client, recorder, state = harness
    staff = Actor(uuid.uuid4(), "Staff")
    state["actor"] = staff
    order_id, source_id = uuid.uuid4(), uuid.uuid4()
    client.post(f"/admin/orders/{order_id}/refunds", json={"Amount": "150000.00", "PaymentTransactionId": str(source_id)})
    name, args, kwargs = recorder.calls[-1]
    assert (name, args) == ("refund_order", (staff, order_id))
    assert str(kwargs["amount"]) == "150000.00" and kwargs["payment_transaction_id"] == source_id

    client.post(f"/admin/orders/{order_id}/confirm-cod-delivery", json={"Note": "Đã thu tiền"})
    assert recorder.calls[-1] == ("confirm_cod_delivery", (staff, order_id), {"note": "Đã thu tiền"})

    client.get("/admin/orders", params={"order_status": "Pending", "page_size": 5})
    assert recorder.calls[-1][2]["order_status"] == "Pending" and recorder.calls[-1][2]["page_size"] == 5

    client.get("/admin/statistics/top-products", params={"date_from": "2026-10-01", "date_to": "2026-10-31",
                                                         "rank_by": "revenue"})
    assert recorder.calls[-1] == ("top_products", (staff, date(2026, 10, 1), date(2026, 10, 31)),
                                  {"rank_by": "revenue", "limit": 10})


def test_optional_note_bodies_may_be_omitted(harness):
    client, recorder, _ = harness
    request_id = uuid.uuid4()
    assert client.post(f"/admin/warranty-requests/{request_id}/receive").status_code == 404
    name, args, _ = recorder.calls[-1]
    assert name == "advance_status" and args[1] == request_id and args[2].ExpectedStage == "New"
    # The legacy receive endpoint now only advances the stage; a note body is accepted but ignored.
    client.post(f"/admin/warranty-requests/{request_id}/receive", json={"Note": "Đã nhận máy"})
    assert recorder.calls[-1][0] == "advance_status" and recorder.calls[-1][1][2].ExpectedStage == "New"


def test_page_size_is_bounded(harness):
    client, recorder, _ = harness
    assert client.get("/products", params={"page_size": 500}).status_code == 422
    assert client.get("/products", params={"page": 0}).status_code == 422
    assert recorder.calls == []
