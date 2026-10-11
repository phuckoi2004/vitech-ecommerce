"""Bridge for Stage 6 routers: Actor built from Stage 5 auth, Stage 4 ServiceError mapped to HTTP."""

import asyncio
import json
import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_actor, get_optional_actor
from app.core.errors import AuthError
from app.main import app, auth_error_handler
from app.routers.errors import service_error_handler, service_error_status
from app.services import ADMIN_ONLY, Actor, require_role
from app.services.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PaymentGatewayError,
    PermissionDeniedError,
    ServiceError,
    TooManyRequestsError,
)

from tests.test_auth_http import authorization, http_context, login, seed_user  # noqa: F401  (fixture)


def build_probe() -> FastAPI:
    probe = FastAPI()
    probe.add_exception_handler(AuthError, auth_error_handler)
    probe.add_exception_handler(ServiceError, service_error_handler)

    @probe.get("/actor")
    def current(actor: Actor = Depends(get_current_actor)):
        return {"user_id": str(actor.user_id), "role": actor.role}

    @probe.get("/optional")
    def optional(actor: Actor | None = Depends(get_optional_actor)):
        return {"role": actor.role if actor else None}

    @probe.get("/admin-only")
    def admin_only(actor: Actor = Depends(get_current_actor)):
        require_role(actor, *ADMIN_ONLY)
        return {"ok": True}

    @probe.get("/anonymous-use-case")
    def anonymous_use_case():
        require_role(None, *ADMIN_ONLY)

    @probe.get("/missing")
    def missing():
        raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")

    return probe


@pytest.fixture
def probe_client(http_context):  # noqa: F811
    client, engine, _ = http_context
    probe = build_probe()
    # Same isolated database and auth runtime the fixture installed on the real app.
    probe.dependency_overrides.update(app.dependency_overrides)
    with TestClient(probe) as probe_client:
        yield client, probe_client, engine


def test_actor_comes_from_the_authenticated_user(probe_client):
    client, probe, engine = probe_client
    staff = seed_user(engine, "Staff")
    token = login(client, staff["email"], "admin").json()["access_token"]
    response = probe.get("/actor", headers=authorization(token))
    assert response.status_code == 200
    assert response.json() == {"user_id": staff["id"], "role": "Staff"}


def test_actor_requires_a_valid_token(probe_client):
    _, probe, _ = probe_client
    assert probe.get("/actor").status_code == 401
    assert probe.get("/actor", headers=authorization("not-a-token")).status_code == 401


def test_optional_actor_is_none_without_token_but_rejects_a_bad_token(probe_client):
    client, probe, engine = probe_client
    assert probe.get("/optional").json() == {"role": None}
    assert probe.get("/optional", headers=authorization("not-a-token")).status_code == 401
    customer = seed_user(engine, "Customer")
    token = login(client, customer["email"]).json()["access_token"]
    assert probe.get("/optional", headers=authorization(token)).json() == {"role": "Customer"}


def test_service_role_check_becomes_403_and_missing_actor_401(probe_client):
    client, probe, engine = probe_client
    customer = seed_user(engine, "Customer")
    token = login(client, customer["email"]).json()["access_token"]
    denied = probe.get("/admin-only", headers=authorization(token))
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"
    anonymous = probe.get("/anonymous-use-case")
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "authentication_required"
    assert anonymous.headers["WWW-Authenticate"] == "Bearer"


def test_service_error_body_keeps_message_and_code(probe_client):
    _, probe, _ = probe_client
    response = probe.get("/missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "Không tìm thấy đơn hàng", "code": "order_not_found"}


def test_status_mapping():
    cases = [
        (NotFoundError("x"), 404),
        (ConflictError("x"), 409),
        (PermissionDeniedError("x"), 403),
        (PermissionDeniedError("x", code="authentication_required"), 401),
        (BusinessRuleError("x", code="invalid_order_status"), 400),
        (PaymentGatewayError("x"), 502),
        (TooManyRequestsError("x"), 429),
        (ServiceError("x"), 400),
    ]
    for error, status in cases:
        assert service_error_status(error) == status, type(error).__name__


def test_too_many_requests_sets_retry_after():
    response = asyncio.run(service_error_handler(None, TooManyRequestsError("Thử lại sau", retry_after_seconds=42)))
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"
    assert json.loads(response.body) == {"detail": "Thử lại sau", "code": "too_many_requests"}


def test_main_app_registers_the_service_error_handler():
    assert app.exception_handlers.get(ServiceError) is service_error_handler


def test_actor_ids_are_uuid():
    actor = get_current_actor(type("U", (), {"UserId": uuid.uuid4(), "Role": "Admin"})())
    assert isinstance(actor.user_id, uuid.UUID) and actor.role == "Admin"
