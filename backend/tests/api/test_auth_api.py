"""API tests — Auth: registration with email OTP, login portals, session tokens, password flows."""

from .support import PASSWORD, expect, expect_forbidden, expect_unauthorized, expect_validation, requires_postgres

pytestmark = requires_postgres


def register(api, email, phone, **overrides):
    payload = {"Email": email, "PhoneNumber": phone, "FullName": "Khách Hàng", "Password": PASSWORD,
               "ConfirmPassword": PASSWORD, **overrides}
    return api.client.post("/auth/register", json=payload)


def test_success_register_verify_login_me_logout(api):
    challenge = expect(register(api, "Khach.Moi@Example.com", "0911222333"), 202)
    code = api.mailer.messages[-1]["code"]
    expect(api.client.post("/auth/register/verify", json={"ChallengeId": challenge["challenge_id"], "Code": code}),
           201)
    assert api.scalar('select "Role" from "Users" where "Email" = :e', e="khach.moi@example.com") == "Customer"

    tokens = expect(api.client.post("/auth/login", json={
        "Identifier": "0911222333", "Password": PASSWORD, "Portal": "customer"}), 200)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert expect(api.client.get("/auth/me", headers=headers), 200)["user"]["Email"] == "khach.moi@example.com"
    # Logout changes the cookie session, so it needs the CSRF token as well as the Bearer token.
    expect_forbidden(api.client.post("/auth/logout", headers=headers))
    expect(api.client.post("/auth/logout", headers={**headers, "X-CSRF-Token": tokens["csrf_token"]}), 200)
    expect_unauthorized(api.client.get("/auth/me", headers=headers))  # revoked immediately


def test_401_missing_invalid_token_and_wrong_password(api, customer):
    expect_unauthorized(api.client.get("/auth/me"))
    expect_unauthorized(api.client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"}))
    expect_unauthorized(api.client.post("/auth/login", json={
        "Identifier": customer.email, "Password": "Wrong-password1!", "Portal": "customer"}))
    expect_unauthorized(api.client.post("/auth/change-password", json={
        "CurrentPassword": PASSWORD, "NewPassword": "Another-pass1!", "ConfirmPassword": "Another-pass1!"}))


def test_403_wrong_portal_and_locked_account(api, staff, customer):
    expect_forbidden(api.client.post("/auth/login", json={
        "Identifier": staff.email, "Password": PASSWORD, "Portal": "customer"}))
    expect_forbidden(api.client.post("/auth/login", json={
        "Identifier": customer.email, "Password": PASSWORD, "Portal": "admin"}))
    locked = api.seed.user("Customer", status="Locked")
    expect_forbidden(api.client.post("/auth/login", json={
        "Identifier": locked.email, "Password": PASSWORD, "Portal": "customer"}))


def test_404_password_reset_for_unknown_account(api):
    response = api.client.post("/auth/forgot-password", json={"Identifier": "nobody@example.com"})
    expect(response, 404)
    assert api.mailer.messages == []


def test_409_register_with_used_email_or_phone(api, customer):
    expect(register(api, customer.email.upper(), "0911000111"), 409)
    expect(register(api, "khac@example.com", customer.phone), 409)
    assert api.mailer.messages == []  # no OTP is sent for an existing identity


def test_422_registration_and_login_validation(api):
    expect_validation(register(api, "not-an-email", "0911222333"), "Email")
    expect_validation(register(api, "a@example.com", "0911222333", ConfirmPassword="Different1!"))
    expect_validation(register(api, "a@example.com", "0911222333", Role="Admin"), "Role")  # extra field forbidden
    expect_validation(api.client.post("/auth/login", json={"Identifier": "a@example.com"}), "Password")
    expect_validation(api.client.post("/auth/login", json={
        "Identifier": "a@example.com", "Password": PASSWORD, "Portal": "staff"}), "Portal")


def test_business_rules_wrong_otp_and_reused_password(api, customer):
    challenge = expect(register(api, "otp@example.com", "0911333444"), 202)
    wrong = "000000" if api.mailer.messages[-1]["code"] != "000000" else "111111"
    expect(api.client.post("/auth/register/verify", json={"ChallengeId": challenge["challenge_id"], "Code": wrong}),
           400)
    assert api.scalar('select count(*) from "Users" where "Email" = :e', e="otp@example.com") == 0

    expect(api.client.post("/auth/change-password", headers=customer.headers, json={
        "CurrentPassword": PASSWORD, "NewPassword": PASSWORD, "ConfirmPassword": PASSWORD}), 400)
