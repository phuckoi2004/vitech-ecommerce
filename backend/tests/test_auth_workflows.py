import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth_state import MemoryStateStore
from app.core.config import AuthSettings
from app.core.dependencies import AuthRuntime
from app.core.errors import AuthError
from app.core.security import decode_access_token, hash_password, verify_password
from app.core.sessions import SessionManager
from app.models import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    EmailChangeRequest, LoginRequest, PasswordChangeRequest,
    RegistrationRequest, ResetPasswordRequest,
)
from app.services.auth import AuthService, ensure_active_user


class Clock:
    def __init__(self):
        self.value = time.time()

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class CapturingMailer:
    def __init__(self):
        self.messages = []

    def send_otp(self, email, code, purpose, ttl):
        self.messages.append((email, code, purpose, ttl))


@pytest.fixture
def auth():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def functions(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

    User.__table__.create(engine)
    clock = Clock()
    settings = AuthSettings(jwt_secret="isolated-test-key-" * 4, app_env="test")
    state, mailer = MemoryStateStore(clock), CapturingMailer()
    runtime = AuthRuntime(settings, state, mailer, SessionManager(state, settings), hash_password("Dummy7!account"))
    with Session(engine) as db:
        yield AuthService(db, runtime, clock), db, runtime, clock
    engine.dispose()


def signup(service, mailer, email="customer@example.com", phone="0912345678"):
    payload = RegistrationRequest(Email=email, PhoneNumber=phone, FullName="Khách hàng",
                                  Password="Password7!", ConfirmPassword="Password7!")
    challenge = service.register(payload)
    user = service.verify_registration(challenge["challenge_id"], mailer.messages[-1][1])
    return user


def error_status(expected, function, *args):
    with pytest.raises(AuthError) as raised:
        function(*args)
    assert raised.value.status_code == expected
    return raised.value


def test_registration_only_persists_after_verified_otp_and_cannot_replay(auth):
    service, db, runtime, _ = auth
    data = RegistrationRequest(Email="Customer@example.com", PhoneNumber="+84 912 345 678",
                               FullName=" Khách hàng ", Password="Password7!", ConfirmPassword="Password7!")
    challenge = service.register(data)
    assert db.scalar(select(User)) is None
    assert challenge["expires_in"] == 90
    assert "Code" not in challenge and "Password" not in challenge
    code = runtime.mailer.messages[-1][1]
    user = service.verify_registration(challenge["challenge_id"], code)
    assert user.Role == "Customer" and user.AccountStatus == "Active" and user.IsEmailVerified
    assert user.PhoneNumber == "0912345678" and user.FullName == "Khách hàng"
    assert verify_password("Password7!", user.PasswordHash)
    assert user.OtpCode is None and user.OtpExpiredAt is None
    error_status(400, service.verify_registration, challenge["challenge_id"], code)


def test_expired_signup_code_and_resend_invalidate_previous_challenge(auth):
    service, _, runtime, clock = auth
    data = RegistrationRequest(Email="customer@example.com", PhoneNumber="0912345678",
                               FullName="Khách", Password="Password7!", ConfirmPassword="Password7!")
    first = service.register(data)
    first_code = runtime.mailer.messages[-1][1]
    error_status(429, service.resend, first["challenge_id"])
    clock.advance(90)
    error_status(400, service.verify_registration, first["challenge_id"], first_code)
    second = service.resend(first["challenge_id"])
    error_status(400, service.verify_registration, first["challenge_id"], first_code)
    service.verify_registration(second["challenge_id"], runtime.mailer.messages[-1][1])


@pytest.mark.parametrize("delivery_seconds, expected_remaining", [(7.25, 53), (60, 0), (65, 0)])
def test_otp_response_counts_delivery_time_without_extending_expiry(delivery_seconds, expected_remaining):
    clock = Clock()
    started_at = clock()
    settings = AuthSettings(jwt_secret="isolated-test-key-" * 4, app_env="test")
    state = MemoryStateStore(clock)

    class DelayedMailer(CapturingMailer):
        def send_otp(self, email, code, purpose, ttl):
            super().send_otp(email, code, purpose, ttl)
            clock.advance(delivery_seconds)

    mailer = DelayedMailer()
    runtime = SimpleNamespace(settings=settings, state=state, mailer=mailer)
    service = AuthService(None, runtime, clock)
    challenge = service._send("password_reset", "staff@example.com", {}, settings.reset_otp_ttl)
    record = state.get(f"challenge:{challenge['challenge_id']}")

    assert challenge["expires_in"] == expected_remaining
    assert record["expires_at"] == started_at + settings.reset_otp_ttl
    assert challenge["resend_after"] == settings.resend_interval
    cooldown = state.get(f"otp-send:password_reset:{record['identity']}")
    assert cooldown["until"] == clock() + settings.resend_interval
    # Delivery latency changes the reported remaining time, not acceptance of
    # the code at its original deadline. This path never touches a database.
    if delivery_seconds < settings.reset_otp_ttl:
        service._verify(challenge["challenge_id"], mailer.messages[-1][1], "password_reset")
        clock.advance(settings.reset_otp_ttl - delivery_seconds)
    error_status(400, service._verify, challenge["challenge_id"], mailer.messages[-1][1], "password_reset")


def test_five_wrong_otps_block_three_minutes_even_when_resending(auth):
    service, _, runtime, clock = auth
    request = RegistrationRequest(Email="customer@example.com", PhoneNumber="0912345678",
                                  FullName="Khách", Password="Password7!", ConfirmPassword="Password7!")
    challenge = service.register(request)
    correct = runtime.mailer.messages[-1][1]
    wrong = "111111" if correct != "111111" else "222222"
    for _ in range(4):
        error_status(400, service.verify_registration, challenge["challenge_id"], wrong)
    blocked = error_status(429, service.verify_registration, challenge["challenge_id"], wrong)
    assert int(blocked.headers["Retry-After"]) == 180
    clock.advance(179.5)
    error_status(429, service.resend, challenge["challenge_id"])
    clock.advance(0.5)
    next_challenge = service.resend(challenge["challenge_id"])
    service.verify_registration(next_challenge["challenge_id"], runtime.mailer.messages[-1][1])


def test_login_email_and_phone_share_attempt_counter_and_portal_is_enforced(auth):
    service, _, runtime, clock = auth
    signup(service, runtime.mailer)
    for identity in ["customer@example.com", "0912345678"] * 2:
        error_status(401, service.login, LoginRequest(Identifier=identity, Password="Wrong7!password"))
    error_status(429, service.login, LoginRequest(Identifier="0912345678", Password="Wrong7!password"))
    error_status(429, service.login, LoginRequest(Identifier="customer@example.com", Password="Password7!"))
    clock.advance(180)
    tokens, user = service.login(LoginRequest(Identifier="0912345678", Password="Password7!"))
    runtime.sessions.validate_access(decode_access_token(tokens.access_token, runtime.settings), user)
    error_status(403, service.login, LoginRequest(Identifier="customer@example.com", Password="Password7!", Portal="admin"))


def test_password_reset_grant_single_use_and_revokes_all_devices(auth):
    service, _, runtime, _ = auth
    user = signup(service, runtime.mailer)
    first = runtime.sessions.issue(user, "customer")
    second = runtime.sessions.issue(user, "customer")
    challenge = service.forgot_password("0912345678")
    assert runtime.mailer.messages[-1][0] == user.Email and challenge["expires_in"] == 60
    grant = service.verify_reset(challenge["challenge_id"], runtime.mailer.messages[-1][1])
    data = ResetPasswordRequest(ResetToken=grant["reset_token"], NewPassword="Changed8!", ConfirmPassword="Changed8!")
    service.reset_password(data)
    assert verify_password("Changed8!", user.PasswordHash)
    error_status(400, service.reset_password, data)
    for tokens in (first, second):
        error_status(401, runtime.sessions.validate_access, decode_access_token(tokens.access_token, runtime.settings), user)


def test_reset_grant_expires_at_the_configured_lifetime(auth):
    service, _, runtime, clock = auth
    runtime.settings = replace(runtime.settings, reset_grant_ttl=45)
    service.settings = runtime.settings
    user = signup(service, runtime.mailer)
    challenge = service.forgot_password(user.Email)
    grant = service.verify_reset(challenge["challenge_id"], runtime.mailer.messages[-1][1])
    assert grant["expires_in"] == 45

    clock.advance(45)
    error_status(400, service.reset_password, ResetPasswordRequest(
        ResetToken=grant["reset_token"], NewPassword="Changed8!", ConfirmPassword="Changed8!"))
    assert verify_password("Password7!", user.PasswordHash)


def test_reset_otp_expiry_and_purpose_separation(auth):
    service, _, runtime, clock = auth
    signup(service, runtime.mailer)
    challenge = service.forgot_password("customer@example.com")
    code = runtime.mailer.messages[-1][1]
    error_status(400, service.verify_registration, challenge["challenge_id"], code)
    clock.advance(60)
    error_status(400, service.verify_reset, challenge["challenge_id"], code)


def test_reset_grant_invalidated_by_password_change(auth):
    service, _, runtime, _ = auth
    user = signup(service, runtime.mailer)
    challenge = service.forgot_password("customer@example.com")
    grant = service.verify_reset(challenge["challenge_id"], runtime.mailer.messages[-1][1])
    service.change_password(user, PasswordChangeRequest(CurrentPassword="Password7!", NewPassword="Changed8!", ConfirmPassword="Changed8!"))
    error_status(400, service.reset_password, ResetPasswordRequest(
        ResetToken=grant["reset_token"], NewPassword="Further9!", ConfirmPassword="Further9!"))


def test_email_change_requires_owner_and_verification_then_revokes_session(auth):
    service, _, runtime, _ = auth
    user = signup(service, runtime.mailer)
    other = signup(service, runtime.mailer, "other@example.com", "0987654321")
    tokens = runtime.sessions.issue(user, "customer")
    challenge = service.request_email_change(user, EmailChangeRequest(Email="new@example.com", CurrentPassword="Password7!"))
    assert user.Email == "customer@example.com"
    code = runtime.mailer.messages[-1][1]
    error_status(403, service.verify_email_change, other, challenge["challenge_id"], code)
    service.verify_email_change(user, challenge["challenge_id"], code)
    assert user.Email == "new@example.com" and user.IsEmailVerified
    error_status(401, runtime.sessions.validate_access, decode_access_token(tokens.access_token, runtime.settings), user)


@pytest.mark.parametrize("same_code", [False, True])
def test_email_change_code_cannot_verify_another_target_challenge(auth, monkeypatch, same_code):
    service, _, runtime, _ = auth
    user = signup(service, runtime.mailer)
    codes = iter([123456, 123456 if same_code else 654321])
    monkeypatch.setattr("app.services.auth.secrets.randbelow", lambda _: next(codes))
    first = service.request_email_change(user, EmailChangeRequest(
        Email="first-target@example.com", CurrentPassword="Password7!"))
    first_code = runtime.mailer.messages[-1][1]
    second = service.request_email_change(user, EmailChangeRequest(
        Email="second-target@example.com", CurrentPassword="Password7!"))
    second_code = runtime.mailer.messages[-1][1]

    error_status(400, service.verify_email_change, user, first["challenge_id"], second_code)
    error_status(400, service.verify_email_change, user, first["challenge_id"], first_code)
    assert user.Email == "customer@example.com" and user.OtpCode is not None
    service.verify_email_change(user, second["challenge_id"], second_code)
    assert user.Email == "second-target@example.com" and user.IsEmailVerified
    assert user.OtpCode is None and user.OtpExpiredAt is None
    error_status(400, service.verify_email_change, user, second["challenge_id"], second_code)


def test_new_email_change_otp_does_not_revive_an_expired_target_challenge(auth, monkeypatch):
    service, _, runtime, clock = auth
    user = signup(service, runtime.mailer)
    monkeypatch.setattr("app.services.auth.secrets.randbelow", lambda _: 123456)
    expired = service.request_email_change(user, EmailChangeRequest(
        Email="expired-target@example.com", CurrentPassword="Password7!"))
    clock.advance(runtime.settings.email_otp_ttl)
    current = service.request_email_change(user, EmailChangeRequest(
        Email="current-target@example.com", CurrentPassword="Password7!"))
    code = runtime.mailer.messages[-1][1]

    error_status(400, service.verify_email_change, user, expired["challenge_id"], code)
    assert user.Email == "customer@example.com"
    service.verify_email_change(user, current["challenge_id"], code)
    assert user.Email == "current-target@example.com"


def test_expired_email_change_challenge_can_be_resent_and_only_new_challenge_verifies(auth, monkeypatch):
    service, _, runtime, clock = auth
    user = signup(service, runtime.mailer)
    monkeypatch.setattr("app.services.auth.secrets.randbelow", lambda _: 123456)
    expired = service.request_email_change(user, EmailChangeRequest(
        Email="new@example.com", CurrentPassword="Password7!"))
    code = runtime.mailer.messages[-1][1]
    error_status(429, service.resend, expired["challenge_id"])
    clock.advance(runtime.settings.email_otp_ttl)
    error_status(400, service.verify_email_change, user, expired["challenge_id"], code)

    current = service.resend(expired["challenge_id"])
    assert current["expires_in"] == runtime.settings.email_otp_ttl
    assert runtime.mailer.messages[-1][0] == "new@example.com"
    error_status(400, service.verify_email_change, user, expired["challenge_id"], code)
    service.verify_email_change(user, current["challenge_id"], runtime.mailer.messages[-1][1])
    assert user.Email == "new@example.com"
    error_status(400, service.verify_email_change, user, current["challenge_id"], code)


def test_email_challenge_rejected_after_password_change(auth):
    service, _, runtime, _ = auth
    user = signup(service, runtime.mailer)
    challenge = service.request_email_change(user, EmailChangeRequest(Email="new@example.com", CurrentPassword="Password7!"))
    code = runtime.mailer.messages[-1][1]
    service.change_password(user, PasswordChangeRequest(CurrentPassword="Password7!", NewPassword="Changed8!", ConfirmPassword="Changed8!"))
    error_status(400, service.verify_email_change, user, challenge["challenge_id"], code)
    assert user.Email == "customer@example.com"


def test_expired_lock_auto_unlock_but_current_lock_and_deleted_account_denied(auth):
    service, db, runtime, _ = auth
    user = signup(service, runtime.mailer)
    user.AccountStatus, user.LockReason = "Locked", "Kiểm thử"
    user.LockedUntil = datetime.now(timezone.utc) + timedelta(minutes=5)
    db.commit()
    error_status(403, service.login, LoginRequest(Identifier=user.Email, Password="Password7!"))
    user.LockedUntil = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    service.login(LoginRequest(Identifier=user.Email, Password="Password7!"))
    assert user.AccountStatus == "Active" and user.LockReason is None and user.LockedUntil is None
    user.IsDeleted = True
    db.commit()
    error_status(401, service.login, LoginRequest(Identifier=user.Email, Password="Password7!"))


def test_row_lock_refreshes_existing_identity_before_unlocking(auth):
    service, db, runtime, _ = auth
    user = signup(service, runtime.mailer)
    user.AccountStatus, user.LockReason = "Locked", "Cũ"
    user.LockedUntil = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    user_id = user.UserId
    # Keep the first session's identity map stale while another transaction extends the lock.
    with Session(db.bind) as other:
        current = other.get(User, user_id)
        current.LockedUntil = datetime.now(timezone.utc) + timedelta(minutes=5)
        current.LockReason = "Gia hạn"
        other.commit()
    error_status(403, ensure_active_user, user, db)
    assert user.LockReason == "Gia hạn"
    assert UserRepository(db).get_by_id_for_update(user_id).AccountStatus == "Locked"


def test_refresh_loader_handles_real_uuid_typed_columns(auth):
    service, _, runtime, _ = auth
    signup(service, runtime.mailer)
    tokens, user = service.login(LoginRequest(Identifier="customer@example.com", Password="Password7!"))
    new_tokens, refreshed_user = service.refresh(tokens.refresh_token)
    assert refreshed_user.UserId == user.UserId
    assert new_tokens.refresh_token != tokens.refresh_token


def test_smtp_failure_does_not_create_pending_account(auth):
    service, db, runtime, _ = auth
    class FailingMailer:
        def send_otp(self, *args):
            raise AuthError(503, "SMTP chưa sẵn sàng")
    runtime.mailer = FailingMailer()
    error_status(503, service.register, RegistrationRequest(
        Email="customer@example.com", PhoneNumber="0912345678", FullName="Khách", Password="Password7!", ConfirmPassword="Password7!"))
    assert db.scalar(select(User)) is None


def test_existing_account_otp_is_stored_as_digest_in_users_row_and_consumed_once(auth):
    service, db, runtime, clock = auth
    user = signup(service, runtime.mailer)
    challenge = service.forgot_password("customer@example.com")
    code = runtime.mailer.messages[-1][1]
    db.refresh(user)
    assert user.OtpCode is not None and len(user.OtpCode) == 10 and user.OtpCode != code
    expires_at = user.OtpExpiredAt.replace(tzinfo=user.OtpExpiredAt.tzinfo or timezone.utc)
    assert abs(expires_at.timestamp() - (clock() + runtime.settings.reset_otp_ttl)) < 1
    assert "digest" not in runtime.state.get(f"challenge:{challenge['challenge_id']}")
    service.verify_reset(challenge["challenge_id"], code)
    db.refresh(user)
    assert user.OtpCode is None and user.OtpExpiredAt is None


def test_cleared_users_otp_rejects_pending_code(auth):
    service, db, runtime, _ = auth
    user = signup(service, runtime.mailer)
    challenge = service.forgot_password("customer@example.com")
    code = runtime.mailer.messages[-1][1]
    # The row is the source of truth: clearing it invalidates the pending code.
    user.OtpCode = None
    db.commit()
    error_status(400, service.verify_reset, challenge["challenge_id"], code)


def test_db_otp_expires_by_otp_expired_at(auth):
    service, _, runtime, clock = auth
    signup(service, runtime.mailer)
    challenge = service.forgot_password("customer@example.com")
    clock.advance(runtime.settings.reset_otp_ttl)
    error_status(400, service.verify_reset, challenge["challenge_id"], runtime.mailer.messages[-1][1])


def test_email_change_clears_users_otp(auth):
    service, db, runtime, _ = auth
    user = User(UserId=uuid.uuid4(), Email="staff@example.com", PhoneNumber="0912345678", FullName="Staff",
                PasswordHash=hash_password("Password7!"), Role="Staff", AccountStatus="Active", IsEmailVerified=True)
    db.add(user)
    db.commit()
    challenge = service.request_email_change(user, EmailChangeRequest(Email="new@example.com", CurrentPassword="Password7!"))
    assert user.OtpCode is not None
    service.verify_email_change(user, challenge["challenge_id"], runtime.mailer.messages[-1][1])
    assert user.Email == "new@example.com" and user.OtpCode is None and user.OtpExpiredAt is None


def test_wrong_current_password_is_rate_limited(auth):
    service, _, runtime, clock = auth
    user = signup(service, runtime.mailer)
    wrong = PasswordChangeRequest(CurrentPassword="Wrong7!pass", NewPassword="Changed8!", ConfirmPassword="Changed8!")
    for _ in range(2):
        error_status(400, service.change_password, user, wrong)
    for _ in range(2):
        error_status(400, service.request_email_change, user,
                     EmailChangeRequest(Email="new@example.com", CurrentPassword="Wrong7!pass"))
    blocked = error_status(429, service.change_password, user, wrong)
    assert int(blocked.headers["Retry-After"]) == 180
    right = PasswordChangeRequest(CurrentPassword="Password7!", NewPassword="Changed8!", ConfirmPassword="Changed8!")
    error_status(429, service.change_password, user, right)
    clock.advance(180)
    service.change_password(user, right)
    assert verify_password("Changed8!", user.PasswordHash)


def isolated_sender(mailer=None, **overrides):
    clock = Clock()
    settings = AuthSettings(jwt_secret="isolated-test-key-" * 4, app_env="test", **overrides)
    mailer = mailer or CapturingMailer()
    runtime = SimpleNamespace(settings=settings, state=MemoryStateStore(clock), mailer=mailer)
    return AuthService(None, runtime, clock), clock, settings, mailer


def test_otp_sends_are_capped_per_hour_for_each_purpose_and_recipient():
    service, clock, settings, mailer = isolated_sender()
    assert (settings.send_limit, settings.send_window) == (5, 3600)
    first_sent_at = clock()
    for _ in range(settings.send_limit):
        service._send("password_reset", "staff@example.com", {}, settings.reset_otp_ttl)
        clock.advance(settings.resend_interval)
    blocked = error_status(429, service._send, "password_reset", "staff@example.com", {}, settings.reset_otp_ttl)
    expected_wait = first_sent_at + settings.send_window - clock()
    assert int(blocked.headers["Retry-After"]) == pytest.approx(expected_wait, abs=1)
    assert len(mailer.messages) == settings.send_limit
    # Other recipients and other purposes keep their own quota; the address is case-insensitive.
    service._send("password_reset", "other@example.com", {}, settings.reset_otp_ttl)
    service._send("signup", "staff@example.com", {}, settings.signup_otp_ttl)
    error_status(429, service._send, "password_reset", "STAFF@example.com", {}, settings.reset_otp_ttl)
    # A new window opens one hour after the first send.
    clock.advance(expected_wait)
    service._send("password_reset", "staff@example.com", {}, settings.reset_otp_ttl)


def test_failed_email_delivery_does_not_use_the_send_quota():
    class FailingMailer(CapturingMailer):
        def __init__(self):
            super().__init__()
            self.fail = True

        def send_otp(self, email, code, purpose, ttl):
            if self.fail:
                raise AuthError(503, "Dịch vụ email chưa sẵn sàng")
            super().send_otp(email, code, purpose, ttl)

    mailer = FailingMailer()
    service, clock, settings, _ = isolated_sender(mailer, send_limit=2)
    for _ in range(3):
        error_status(503, service._send, "password_reset", "staff@example.com", {}, settings.reset_otp_ttl)
    mailer.fail = False
    service._send("password_reset", "staff@example.com", {}, settings.reset_otp_ttl)
    clock.advance(settings.resend_interval)
    service._send("password_reset", "staff@example.com", {}, settings.reset_otp_ttl)
    clock.advance(settings.resend_interval)
    error_status(429, service._send, "password_reset", "staff@example.com", {}, settings.reset_otp_ttl)


@pytest.mark.parametrize("field", ["send_limit", "send_window"])
def test_send_quota_settings_must_be_positive(field):
    from app.core.errors import AuthConfigurationError

    with pytest.raises(AuthConfigurationError):
        AuthSettings(jwt_secret="isolated-test-key-" * 4, app_env="test", **{field: 0})
