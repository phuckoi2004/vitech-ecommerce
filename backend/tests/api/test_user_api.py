"""API tests — User: profile, address book, notifications and Admin account management."""

from datetime import datetime, timedelta, timezone

from app.core.storage import AVATAR_MAX_BYTES, get_avatar_storage
from app.main import app

from .support import (
    PASSWORD,
    expect,
    expect_forbidden,
    expect_unauthorized,
    expect_validation,
    random_id,
    requires_postgres,
)

pytestmark = requires_postgres

ADDRESS = {"ReceiverName": "Nguyễn Văn A", "ReceiverPhone": "0900000000", "Province": "TP. Hồ Chí Minh",
           "Ward": "Phường Bến Nghé", "DetailAddress": "1 Lê Lợi"}


def staff_payload(email="nhanvien@example.com", phone="0933000111"):
    return {"Email": email, "PhoneNumber": phone, "Password": PASSWORD, "ConfirmPassword": PASSWORD,
            "FullName": "Nhân Viên Mới", "Role": "Staff"}


def test_success_profile_addresses_notifications_and_staff_account(api, admin, staff, customer):
    client = api.client
    assert expect(client.get("/users/me", headers=customer.headers), 200)["Email"] == customer.email
    assert expect(client.patch("/users/me", headers=customer.headers, json={"FullName": "Tên Mới"}),
                  200)["FullName"] == "Tên Mới"

    first = expect(client.post("/users/me/addresses", headers=customer.headers, json={**ADDRESS, "IsDefault": True}),
                   201)
    second = expect(client.post("/users/me/addresses", headers=customer.headers,
                                json={**ADDRESS, "DetailAddress": "2 Lê Lợi", "IsDefault": True}), 201)
    listed = expect(client.get("/users/me/addresses", headers=customer.headers), 200)
    assert [a["AddressId"] for a in listed if a["IsDefault"]] == [second["AddressId"]]  # one default only
    expect(client.patch(f"/users/me/addresses/{first['AddressId']}", headers=customer.headers,
                        json={"DetailAddress": "3 Lê Lợi"}), 200)
    expect(client.delete(f"/users/me/addresses/{first['AddressId']}", headers=customer.headers), 204)
    assert len(expect(client.get("/users/me/addresses", headers=customer.headers), 200)) == 1

    api.place_order(customer, api.shop())  # placing an order notifies the customer
    assert expect(client.get("/users/me/notifications/unread-count", headers=customer.headers), 200)["Count"] >= 1
    assert expect(client.post("/users/me/notifications/read-all", headers=customer.headers), 200)["Count"] >= 1
    assert expect(client.get("/users/me/notifications/unread-count", headers=customer.headers), 200)["Count"] == 0

    created = expect(client.post("/admin/users", headers=admin.headers, json=staff_payload()), 201)
    assert created["Role"] == "Staff"
    assert expect(client.get(f"/admin/users/{created['UserId']}", headers=admin.headers), 200)["Email"] == \
        "nhanvien@example.com"
    assert expect(client.get("/admin/users", headers=admin.headers, params={"role": "Staff"}), 200)["Total"] >= 2


def test_401_without_token(api):
    expect_unauthorized(api.client.get("/users/me"))
    expect_unauthorized(api.client.post("/users/me/addresses", json=ADDRESS))
    expect_unauthorized(api.client.get("/users/me/notifications"))
    expect_unauthorized(api.client.get("/admin/users"))


def test_403_roles_and_self_management(api, admin, staff, customer):
    client = api.client
    expect_forbidden(client.get("/users/me/addresses", headers=staff.headers))  # address book is Customer-only
    expect_forbidden(client.post("/users/me/addresses", headers=admin.headers, json=ADDRESS))
    expect_forbidden(client.get("/admin/users", headers=customer.headers))
    expect_forbidden(client.get("/admin/users", headers=staff.headers))  # account management is Admin-only
    expect_forbidden(client.post("/admin/users", headers=staff.headers, json=staff_payload()))
    expect_forbidden(client.patch(f"/admin/users/{admin.id}", headers=admin.headers,
                                  json={"AccountStatus": "Active"}))  # own account goes through the profile


def test_404_unknown_or_foreign_resources(api, admin, customer, other_customer):
    client = api.client
    foreign = expect(client.post("/users/me/addresses", headers=other_customer.headers, json=ADDRESS), 201)
    # Another customer's address looks absent rather than forbidden.
    expect(client.patch(f"/users/me/addresses/{foreign['AddressId']}", headers=customer.headers,
                        json={"DetailAddress": "x"}), 404, "address_not_found")
    expect(client.delete(f"/users/me/addresses/{random_id()}", headers=customer.headers), 404, "address_not_found")
    expect(client.post(f"/users/me/notifications/{random_id()}/read", headers=customer.headers), 404)
    expect(client.get(f"/admin/users/{random_id()}", headers=admin.headers), 404)
    expect(client.get(f"/admin/users/{admin.id}", headers=admin.headers), 404)  # Admin accounts are out of scope


def test_409_duplicate_email_or_phone(api, admin, customer, other_customer):
    expect(api.client.post("/admin/users", headers=admin.headers,
                           json=staff_payload(email=customer.email)), 409)
    expect(api.client.post("/admin/users", headers=admin.headers,
                           json=staff_payload(phone=customer.phone)), 409)
    expect(api.client.patch("/users/me", headers=customer.headers, json={"PhoneNumber": other_customer.phone}), 409)


def test_422_validation(api, admin, customer):
    client = api.client
    missing_province = {key: value for key, value in ADDRESS.items() if key != "Province"}
    expect_validation(client.post("/users/me/addresses", headers=customer.headers, json=missing_province),
                      "Province")
    expect_validation(client.post("/admin/users", headers=admin.headers,
                                  json={**staff_payload(), "Role": "Admin"}), "Role")
    expect_validation(client.post("/admin/users", headers=admin.headers,
                                  json={**staff_payload(), "Email": "sai-dinh-dang"}), "Email")
    expect_validation(client.get("/admin/users", headers=admin.headers, params={"page_size": 0}), "page_size")
    expect_validation(client.get("/admin/users/not-a-uuid", headers=admin.headers), "user_id")
    # Locking needs a reason and a future deadline (checked by the service, reported as 422).
    expect(client.patch(f"/admin/users/{customer.id}", headers=admin.headers, json={"AccountStatus": "Locked"}),
           422)


def test_business_rule_locking_revokes_sessions_and_blocks_login(api, admin, customer):
    until = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    locked = expect(api.client.patch(f"/admin/users/{customer.id}", headers=admin.headers, json={
        "AccountStatus": "Locked", "LockReason": "Vi phạm chính sách", "LockedUntil": until}), 200)
    assert locked["AccountStatus"] == "Locked"
    # The existing token stops working at once: every request rereads the account from the database.
    blocked = expect_forbidden(api.client.get("/users/me", headers=customer.headers))
    assert blocked["detail"] == "Tài khoản đang bị khóa"
    expect_forbidden(api.client.post("/auth/login", json={
        "Identifier": customer.email, "Password": PASSWORD, "Portal": "customer"}))


class StorageNeverReached:
    """A configured avatar store that rejected uploads must never touch."""

    def __getattr__(self, name):
        raise AssertionError(f"storage.{name} must not be called for a rejected upload")


def test_business_rules_avatar_type_and_size(api, customer):
    app.dependency_overrides[get_avatar_storage] = lambda: StorageNeverReached()
    upload = lambda data: api.client.put("/users/me/avatar", headers=customer.headers, content=data)  # noqa: E731
    expect(upload(b"%PDF-1.7 not an image"), 415)  # the file signature decides the type, not its name
    expect(upload(b"\x89PNG" + b"0" * AVATAR_MAX_BYTES), 413)
    expect(upload(b""), 422)
