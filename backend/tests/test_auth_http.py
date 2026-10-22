"""HTTP contracts using isolated SQLite, memory state and a capturing email adapter."""

import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth_state import MemoryStateStore
from app.core.config import AuthSettings
from app.core.dependencies import AuthRuntime, get_runtime
from app.core.security import hash_password
from app.core.sessions import SessionManager
from app.database import get_db
from app.main import app
from app.models import Address, User


PASSWORD = "Password1!"


class CapturingMailer:
    def __init__(self):
        self.messages = []

    def send_otp(self, email, code, purpose, ttl):
        self.messages.append({"email": email, "code": code, "purpose": purpose, "ttl": ttl})


@pytest.fixture
def http_context():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def sqlite_defaults(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    User.__table__.create(engine)
    settings = AuthSettings(jwt_secret="test" * 16, app_env="test")
    state = MemoryStateStore()
    mailer = CapturingMailer()
    runtime = AuthRuntime(settings, state, mailer, SessionManager(state, settings),
                          hash_password("NotAnAccount1!"))

    def isolated_db():
        with Session(engine, autoflush=False) as db:
            yield db

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = isolated_db
    app.dependency_overrides[get_runtime] = lambda: runtime
    try:
        with TestClient(app) as client:
            yield client, engine, mailer
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()


def seed_user(engine, role, *, email=None, phone=None, verified=True):
    identity = uuid.uuid4()
    with Session(engine) as db:
        user = User(UserId=identity, Email=email or f"{identity.hex}@example.com",
                    PhoneNumber=phone or f"09{str(identity.int)[-8:]}", FullName=f"Test {role}",
                    PasswordHash=hash_password(PASSWORD), Role=role, AccountStatus="Active",
                    IsEmailVerified=verified, IsDeleted=False)
        db.add(user)
        db.commit()
        return {"id": str(identity), "email": user.Email, "phone": user.PhoneNumber}


def login(client, identifier, portal="customer"):
    response = client.post("/auth/login", json={"Identifier": identifier, "Password": PASSWORD,
                                               "Portal": portal})
    assert response.status_code == 200, response.json()
    return response


def authorization(token):
    return {"Authorization": f"Bearer {token}"}


def user_count(engine):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(User))


def assert_safe_public_user(data):
    for private_field in ("PasswordHash", "Password", "ConfirmPassword", "OtpCode", "OtpExpiredAt"):
        assert private_field not in data


def test_registration_creates_user_only_after_email_otp_and_both_login_identifiers_work(http_context):
    client, engine, mailer = http_context
    response = client.post("/auth/register", json={
        "Email": "CUSTOMER@example.com", "PhoneNumber": "+84 912 345 678", "FullName": " Test Customer ",
        "Password": PASSWORD, "ConfirmPassword": PASSWORD,
    })
    assert response.status_code == 202
    challenge = response.json()
    assert set(challenge) == {"message", "challenge_id", "expires_in", "resend_after"}
    assert challenge["expires_in"] == 90
    assert user_count(engine) == 0
    assert mailer.messages[-1]["purpose"] == "signup"
    assert mailer.messages[-1]["email"] == "customer@example.com"
    assert len(mailer.messages[-1]["code"]) == 6
    response = client.post("/auth/register/verify", json={
        "ChallengeId": challenge["challenge_id"], "Code": mailer.messages[-1]["code"],
    })
    assert response.status_code == 201
    assert user_count(engine) == 1
    response = login(client, "CUSTOMER@example.com")
    tokens = response.json()
    assert tokens["user"]["Role"] == "Customer"
    assert tokens["user"]["FullName"] == "Test Customer"
    assert tokens["user"]["IsEmailVerified"] is True
    assert tokens["csrf_token"] == client.cookies.get("vietech_csrf")
    assert_safe_public_user(tokens["user"])
    refresh_cookie = next(value for value in response.headers.get_list("set-cookie")
                          if value.startswith("vietech_refresh="))
    assert "httponly" in refresh_cookie.lower()
    assert "path=/auth" in refresh_cookie.lower()
    assert response.headers["cache-control"] == "no-store"
    headers = authorization(tokens["access_token"])
    assert client.get("/auth/me", headers=headers).status_code == 200
    assert client.get("/users/me", headers=headers).status_code == 200
    updated = client.patch("/users/me", headers=headers, json={"FullName": "Updated Name"})
    assert updated.status_code == 200
    assert updated.json()["FullName"] == "Updated Name"
    assert_safe_public_user(updated.json())
    assert login(client, "0912345678").json()["user"]["Email"] == "customer@example.com"


def test_unauthenticated_access_and_validation_never_echo_secrets_or_accept_signup_role(http_context):
    client, engine, _ = http_context
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    weak_password = "privateweakpassword"
    payload = {"Email": "customer@example.com", "PhoneNumber": "0912345678", "FullName": "Customer",
               "Password": weak_password, "ConfirmPassword": weak_password}
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422
    assert weak_password not in response.text
    assert all("input" not in detail and "ctx" not in detail for detail in response.json()["detail"])
    response = client.post("/auth/register", json={**payload, "Password": PASSWORD,
                                                  "ConfirmPassword": PASSWORD, "Role": "Admin"})
    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert user_count(engine) == 0


def test_refresh_checks_csrf_rotates_tokens_and_replay_revokes_session(http_context):
    client, engine, _ = http_context
    user = seed_user(engine, "Customer")
    original = login(client, user["email"]).json()
    old_refresh, old_csrf = client.cookies.get("vietech_refresh"), client.cookies.get("vietech_csrf")
    assert client.post("/auth/refresh").status_code == 403
    assert client.post("/auth/refresh", headers={"X-CSRF-Token": "mismatch"}).status_code == 403
    forged_csrf = "forged.signature"
    forged = {"Cookie": f"vietech_refresh={old_refresh}; vietech_csrf={forged_csrf}",
              "X-CSRF-Token": forged_csrf}
    assert client.post("/auth/refresh", headers=forged).status_code == 403
    response = client.post("/auth/refresh", headers={"X-CSRF-Token": old_csrf})
    assert response.status_code == 200
    rotated = response.json()
    assert client.cookies.get("vietech_refresh") != old_refresh
    assert rotated["csrf_token"] == client.cookies.get("vietech_csrf")
    assert client.get("/auth/me", headers=authorization(rotated["access_token"])).status_code == 200
    replay = {"Cookie": f"vietech_refresh={old_refresh}; vietech_csrf={old_csrf}", "X-CSRF-Token": old_csrf}
    assert client.post("/auth/refresh", headers=replay).status_code == 401
    assert client.get("/auth/me", headers=authorization(rotated["access_token"])).status_code == 401
    assert client.get("/auth/me", headers=authorization(original["access_token"])).status_code == 401


def test_logout_revokes_bearer_and_removes_refresh_cookies(http_context):
    client, engine, _ = http_context
    user = seed_user(engine, "Customer")
    tokens = login(client, user["email"]).json()
    headers = {**authorization(tokens["access_token"]), "X-CSRF-Token": tokens["csrf_token"]}
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.cookies.get("vietech_refresh") is None
    assert client.cookies.get("vietech_csrf") is None
    assert client.get("/auth/me", headers=authorization(tokens["access_token"])).status_code == 401


def test_refresh_finishes_database_reads_before_rotating_the_cookie(http_context, monkeypatch):
    """A database outage after rotation must not lose a user's only refresh credential."""
    from sqlalchemy.exc import OperationalError

    client, engine, _ = http_context
    user = seed_user(engine, "Customer")
    original = login(client, user["email"]).json()
    rotated = {"done": False}
    refresh = SessionManager.refresh

    def track_rotation(self, *args, **kwargs):
        result = refresh(self, *args, **kwargs)
        rotated["done"] = True
        return result

    def reject_reads_after_rotation(_connection, _cursor, statement, _parameters, _context, _executemany):
        if rotated["done"] and statement.lstrip().upper().startswith("SELECT"):
            raise OperationalError("SELECT", {}, Exception("private-connection-error"))

    monkeypatch.setattr(SessionManager, "refresh", track_rotation)
    event.listen(engine, "before_cursor_execute", reject_reads_after_rotation)
    try:
        response = client.post("/auth/refresh", headers={"X-CSRF-Token": original["csrf_token"]})
        assert response.status_code == 200, response.text
        renewed = response.json()
        assert renewed["user"]["UserId"] == user["id"]
    finally:
        event.remove(engine, "before_cursor_execute", reject_reads_after_rotation)
    assert client.get("/auth/me", headers=authorization(renewed["access_token"])).status_code == 200


def test_refresh_database_failure_does_not_rotate_cookie_and_can_be_retried(http_context):
    from sqlalchemy.exc import OperationalError

    client, engine, _ = http_context
    user = seed_user(engine, "Customer")
    original = login(client, user["email"]).json()
    cookie = client.cookies.get("vietech_refresh")

    def unavailable(*_args):
        raise OperationalError("SELECT", {}, Exception("private-connection-error"))

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = client.post("/auth/refresh", headers={"X-CSRF-Token": original["csrf_token"]})
        assert response.status_code == 503
        assert response.json()["code"] == "database_unavailable"
        assert "private-connection-error" not in response.text
        assert client.cookies.get("vietech_refresh") == cookie
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert client.post("/auth/refresh", headers={"X-CSRF-Token": original["csrf_token"]}).status_code == 200


def test_portals_and_account_admin_permissions_reject_cross_role_and_peer_actions(http_context):
    client, engine, _ = http_context
    customer, staff, admin, peer = [seed_user(engine, role) for role in ("Customer", "Staff", "Admin", "Admin")]
    assert client.post("/auth/login", json={"Identifier": customer["email"], "Password": PASSWORD,
                                           "Portal": "admin"}).status_code == 403
    assert client.post("/auth/login", json={"Identifier": staff["email"], "Password": PASSWORD,
                                           "Portal": "customer"}).status_code == 403
    for user, portal in ((customer, "customer"), (staff, "admin")):
        token = login(client, user["email"], portal).json()["access_token"]
        assert client.get("/admin/users", headers=authorization(token)).status_code == 403
    tokens = login(client, admin["email"], "admin").json()
    headers = authorization(tokens["access_token"])
    response = client.get("/admin/users?page_size=2", headers=headers)
    assert response.status_code == 200
    assert response.json()["Total"] == 2
    assert len(response.json()["Items"]) == 2
    assert {user["Role"] for user in response.json()["Items"]} == {"Customer", "Staff"}
    assert client.get("/admin/users?role=Admin", headers=headers).status_code == 403
    for user in (admin, peer):
        assert client.patch(f"/admin/users/{user['id']}", headers=headers,
                            json={"FullName": "Forbidden Change"}).status_code == 403
        assert client.delete(f"/admin/users/{user['id']}", headers=headers).status_code == 403
    assert client.patch(f"/admin/users/{staff['id']}", headers=headers, json={"Role": "Admin"}).status_code == 403
    assert client.patch("/users/me", headers=headers, json={"Role": "Admin"}).status_code == 422


def test_staff_created_by_admin_can_sign_in_without_email_otp(http_context):
    client, engine, mailer = http_context
    admin = seed_user(engine, "Admin")
    tokens = login(client, admin["email"], "admin").json()
    payload = {"Email": "newstaff@example.com", "PhoneNumber": "0987654321", "FullName": "New Staff",
               "Password": PASSWORD, "ConfirmPassword": PASSWORD, "Role": "Staff"}
    assert client.post("/admin/users", headers=authorization(tokens["access_token"]),
                       json={**payload, "Role": "Admin"}).status_code == 422
    response = client.post("/admin/users", headers=authorization(tokens["access_token"]), json=payload)
    assert response.status_code == 201
    assert response.json()["Role"] == "Staff"
    assert response.json()["IsEmailVerified"] is True
    assert_safe_public_user(response.json())
    # No email OTP: the new staff member signs in at once with email or phone.
    assert login(client, payload["Email"], "admin").json()["user"]["Role"] == "Staff"
    assert login(client, payload["PhoneNumber"], "admin").status_code == 200
    assert mailer.messages == []
    # The verification endpoints no longer exist; OTP remains for password reset.
    assert client.post("/auth/email-verification", json={"Identifier": payload["Email"]}).status_code == 404
    assert client.post("/auth/forgot-password", json={"Identifier": payload["Email"]}).status_code == 202
    assert mailer.messages[-1]["purpose"] == "password_reset"


def test_admin_user_detail_endpoint_is_admin_only_and_hides_secrets(http_context):
    client, engine, _ = http_context
    customer, staff, admin = [seed_user(engine, role) for role in ("Customer", "Staff", "Admin")]
    admin_token = login(client, admin["email"], "admin").json()["access_token"]
    response = client.get(f"/admin/users/{customer['id']}", headers=authorization(admin_token))
    assert response.status_code == 200
    assert response.json()["UserId"] == customer["id"]
    assert_safe_public_user(response.json())
    assert client.get(f"/admin/users/{admin['id']}", headers=authorization(admin_token)).status_code == 404
    staff_token = login(client, staff["email"], "admin").json()["access_token"]
    assert client.get(f"/admin/users/{customer['id']}", headers=authorization(staff_token)).status_code == 403


def test_admin_reads_a_customer_default_address_and_other_roles_cannot(http_context):
    client, engine, _ = http_context
    Address.__table__.create(engine)
    customer, other, staff, admin = [seed_user(engine, role) for role in ("Customer", "Customer", "Staff", "Admin")]
    customer_headers = authorization(login(client, customer["email"]).json()["access_token"])
    saved = client.put("/users/me/default-address", headers=customer_headers,
                       json={"Province": "Hà Nội", "Ward": "Phường Cầu Giấy", "DetailAddress": "12 Trần Thái Tông"})
    assert saved.status_code == 200, saved.json()

    admin_headers = authorization(login(client, admin["email"], "admin").json()["access_token"])
    response = client.get(f"/admin/users/{customer['id']}/default-address", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["UserId"] == customer["id"]
    assert (response.json()["Province"], response.json()["Ward"], response.json()["DetailAddress"]) == (
        "Hà Nội", "Phường Cầu Giấy", "12 Trần Thái Tông")
    # A customer without a saved address returns null rather than an error.
    no_address = client.get(f"/admin/users/{other['id']}/default-address", headers=admin_headers)
    assert no_address.status_code == 200 and no_address.json() is None
    # Staff accounts have no address book (Phase 4 rule): saving is refused, reading returns null.
    staff_headers = authorization(login(client, staff["email"], "admin").json()["access_token"])
    assert client.get("/users/me/default-address", headers=staff_headers).status_code == 403
    assert client.put("/users/me/default-address", headers=staff_headers, json={
        "Province": "Hà Nội", "Ward": "Phường A", "DetailAddress": "1"}).status_code == 403
    assert client.get("/users/me/default-address", headers=admin_headers).status_code == 403
    staff_address = client.get(f"/admin/users/{staff['id']}/default-address", headers=admin_headers)
    assert staff_address.status_code == 200 and staff_address.json() is None
    # Admin accounts stay outside the managed scope, like the detail endpoint.
    assert client.get(f"/admin/users/{admin['id']}/default-address", headers=admin_headers).status_code == 404
    assert client.get(f"/admin/users/{uuid.uuid4()}/default-address", headers=admin_headers).status_code == 404
    # The detail dialog also opens deleted accounts, so their address stays readable.
    assert client.delete(f"/admin/users/{customer['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/admin/users/{customer['id']}/default-address", headers=admin_headers).json()["Province"] == "Hà Nội"

    other_headers = authorization(login(client, other["email"]).json()["access_token"])
    for headers in (staff_headers, other_headers):
        assert client.get(f"/admin/users/{customer['id']}/default-address", headers=headers).status_code == 403
    assert client.get(f"/admin/users/{customer['id']}/default-address").status_code == 401


def test_startup_fails_when_auth_runtime_is_misconfigured():
    from app.core.errors import AuthConfigurationError

    def broken_runtime():
        raise AuthConfigurationError()

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_runtime] = broken_runtime
    try:
        with pytest.raises(AuthConfigurationError):
            with TestClient(app):
                pass
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def test_unverified_staff_account_still_signs_in(http_context):
    """Accounts created before staff verification was dropped must not be locked out."""
    client, engine, mailer = http_context
    staff = seed_user(engine, "Staff", verified=False)
    tokens = login(client, staff["email"], "admin").json()
    assert client.get("/auth/me", headers=authorization(tokens["access_token"])).status_code == 200
    assert login(client, staff["phone"], "admin").status_code == 200
    assert mailer.messages == []


def test_permissions_are_fixed_and_cannot_be_changed_through_the_api(http_context):
    client, engine, _ = http_context
    staff, admin = [seed_user(engine, role) for role in ("Staff", "Admin")]
    admin_headers = authorization(login(client, admin["email"], "admin").json()["access_token"])
    staff_permissions = login(client, staff["email"], "admin").json()["permissions"]
    assert "products:view" in staff_permissions and "products:create" not in staff_permissions
    assert client.get("/admin/roles", headers=admin_headers).status_code == 404
    assert client.put("/admin/roles/Staff", headers=admin_headers, json={"Permissions": []}).status_code == 404
