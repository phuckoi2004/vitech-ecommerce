from __future__ import annotations

import concurrent.futures
import time
import uuid
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import jwt
import pytest

from app.core.auth_state import MemoryStateStore, RedisStateStore
from app.core.config import AuthSettings
from app.core.errors import AuthConfigurationError, AuthError, StateUnavailable
from app.core.mail import SMTPMailer
from app.core.security import decode_access_token, hash_password, issue_access_token, otp_digest, verify_password
from app.core.sessions import SessionManager


@pytest.fixture
def settings():
    return AuthSettings(jwt_secret="test-secret-is-32-bytes-or-longer-for-unit-tests", app_env="test")


@pytest.fixture
def user():
    return SimpleNamespace(
        UserId=uuid.uuid4(), Email="customer@example.test", PasswordHash="stored-argon2-hash",
        Role="Customer", AccountStatus="Active", IsDeleted=False,
    )


@pytest.fixture
def clock():
    value = [time.time()]
    return value, lambda: value[0]


def manager(settings, clock):
    return SessionManager(MemoryStateStore(now=clock[1]), settings, now=clock[1])


def test_password_hash_and_invalid_hash_are_safe():
    encoded = hash_password("Password1!")
    assert encoded.startswith("$argon2id$")
    assert "Password1!" not in encoded
    assert verify_password("Password1!", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("Password1!", "invalid-hash")


def test_otp_digest_separates_purposes(settings):
    assert otp_digest("123456", settings, "signup") != otp_digest("123456", settings, "reset")
    assert "123456" not in otp_digest("123456", settings, "signup")


def test_memory_state_expires_and_returns_copies(clock):
    state = MemoryStateStore(now=clock[1])
    state.put("challenge", {"nested": {"attempts": 0}}, 90)
    retrieved = state.get("challenge")
    retrieved["nested"]["attempts"] = 5
    assert state.get("challenge")["nested"]["attempts"] == 0
    clock[0][0] += 90
    assert state.get("challenge") is None


def test_memory_lock_protects_read_modify_write():
    state = MemoryStateStore()
    state.put("counter", {"n": 0}, 60)

    def increment(_):
        for _ in range(50):
            with state.lock("counter"):
                entry = state.get("counter")
                entry["n"] += 1
                state.put("counter", entry, 60)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(increment, range(4)))
    assert state.get("counter")["n"] == 200


def test_jwt_rejects_wrong_algorithm_issuer_and_audience(settings, user):
    token = issue_access_token(str(user.UserId), str(uuid.uuid4()), "customer", settings)
    claims = decode_access_token(token, settings)
    assert claims["sub"] == str(user.UserId)
    for changed in ({"iss": "attacker"}, {"aud": "other"}):
        altered = jwt.encode({**claims, **changed}, settings.jwt_secret, algorithm="HS256")
        with pytest.raises(AuthError) as error:
            decode_access_token(altered, settings)
        assert error.value.status_code == 401
    wrong_algorithm = jwt.encode(claims, settings.jwt_secret, algorithm="HS384")
    with pytest.raises(AuthError):
        decode_access_token(wrong_algorithm, settings)


def test_expired_jwt_is_rejected(settings, user):
    token = issue_access_token(str(user.UserId), str(uuid.uuid4()), "customer", settings, now=time.time() - 1000)
    with pytest.raises(AuthError):
        decode_access_token(token, settings)


def test_logout_revokes_access_but_preserves_other_device(settings, user, clock):
    sessions = manager(settings, clock)
    first, second = sessions.issue(user, "customer"), sessions.issue(user, "customer")
    sessions.logout(first.session_id)
    with pytest.raises(AuthError):
        sessions.validate_access(decode_access_token(first.access_token, settings), user)
    sessions.validate_access(decode_access_token(second.access_token, settings), user)


def test_refresh_rotates_and_replay_revokes_entire_session(settings, user, clock):
    sessions = manager(settings, clock)
    original = sessions.issue(user, "customer")
    rotated = sessions.refresh(original.refresh_token, lambda _: user)
    assert rotated.refresh_token != original.refresh_token
    assert rotated.session_id == original.session_id
    with pytest.raises(AuthError):
        sessions.refresh(original.refresh_token, lambda _: user)
    with pytest.raises(AuthError):
        sessions.refresh(rotated.refresh_token, lambda _: user)
    with pytest.raises(AuthError):
        sessions.validate_access(decode_access_token(rotated.access_token, settings), user)


def test_refresh_loads_database_user_outside_state_locks(settings, user, clock):
    class TrackingStore(MemoryStateStore):
        held_locks = 0

        @contextmanager
        def lock(self, key):
            with super().lock(key):
                self.held_locks += 1
                try:
                    yield
                finally:
                    self.held_locks -= 1

    state = TrackingStore(now=clock[1])
    sessions = SessionManager(state, settings, now=clock[1])
    original = sessions.issue(user, "customer")

    def load_user(_):
        # Auto-unlocking can take a DB row lock; never nest that under Redis locks.
        assert state.held_locks == 0
        return user

    sessions.refresh(original.refresh_token, load_user)


def test_refresh_rechecks_revocation_after_loading_user(settings, user, clock):
    sessions = manager(settings, clock)
    original = sessions.issue(user, "customer")

    def load_user(_):
        sessions.revoke_user(str(user.UserId))
        return user

    with pytest.raises(AuthError):
        sessions.refresh(original.refresh_token, load_user)


def test_refresh_does_not_extend_maximum_lifetime(settings, user, clock):
    sessions = manager(settings, clock)
    original = sessions.issue(user, "customer")
    clock[0][0] += 100
    rotated = sessions.refresh(original.refresh_token, lambda _: user)
    assert rotated.refresh_expires_in == settings.customer_session_ttl - 100
    clock[0][0] += settings.customer_session_ttl - 100
    with pytest.raises(AuthError):
        sessions.refresh(rotated.refresh_token, lambda _: user)


def test_internal_idle_timeout_and_customer_session(settings, user, clock):
    sessions = manager(settings, clock)
    staff = SimpleNamespace(**{**vars(user), "UserId": uuid.uuid4(), "Role": "Staff"})
    internal = sessions.issue(staff, "admin")
    customer = sessions.issue(user, "customer")
    clock[0][0] += settings.internal_idle_ttl
    with pytest.raises(AuthError):
        sessions.refresh(internal.refresh_token, lambda _: staff)
    sessions.refresh(customer.refresh_token, lambda _: user)


def test_internal_server_activity_updates_idle_timer(settings, user, clock):
    sessions = manager(settings, clock)
    user.Role = "Staff"
    internal = sessions.issue(user, "admin")
    clock[0][0] += 1700
    sessions.validate_access(decode_access_token(internal.access_token, settings), user)
    clock[0][0] += 1700
    sessions.refresh(internal.refresh_token, lambda _: user)


@pytest.mark.parametrize("field,new_value", [("PasswordHash", "new-hash"), ("Email", "new@example.test"), ("Role", "Staff")])
def test_live_user_changes_revoke_session(settings, user, clock, field, new_value):
    sessions = manager(settings, clock)
    pair = sessions.issue(user, "customer")
    setattr(user, field, new_value)
    with pytest.raises(AuthError):
        sessions.validate_access(decode_access_token(pair.access_token, settings), user)


def test_user_revocation_invalidates_all_sessions_and_allows_fresh_login(settings, user, clock):
    sessions = manager(settings, clock)
    old = [sessions.issue(user, "customer") for _ in range(2)]
    sessions.revoke_user(str(user.UserId))
    for pair in old:
        with pytest.raises(AuthError):
            sessions.refresh(pair.refresh_token, lambda _: user)
    fresh = sessions.issue(user, "customer")
    sessions.validate_access(decode_access_token(fresh.access_token, settings), user)


def test_portal_separation(settings, user, clock):
    sessions = manager(settings, clock)
    with pytest.raises(AuthError) as error:
        sessions.issue(user, "admin")
    assert error.value.status_code == 403
    user.Role = "Admin"
    with pytest.raises(AuthError):
        sessions.issue(user, "customer")


@pytest.mark.parametrize("portal", ["customer", "admin"])
def test_unknown_role_cannot_start_a_session(settings, user, clock, portal):
    sessions = manager(settings, clock)
    user.Role = "Owner"
    with pytest.raises(AuthError) as error:
        sessions.issue(user, portal)
    assert error.value.status_code == 403


def test_production_requires_shared_state_strong_secret_https_origins(settings):
    with pytest.raises(AuthConfigurationError):
        replace(settings, app_env="production")
    with pytest.raises(AuthConfigurationError):
        replace(settings, app_env="production", state_backend="redis", redis_url="redis://localhost:6379")
    with pytest.raises(AuthConfigurationError):
        replace(settings, jwt_secret="x" * 64, app_env="production", state_backend="redis",
                redis_url="redis://localhost:6379", cors_origins=("https://vietech.example",))


@pytest.mark.parametrize("placeholder", [
    "replace-with-a-random-secret-at-least-32-bytes",
    "change-me-to-a-random-secret-at-least-32-bytes",
])
def test_production_rejects_public_secret_placeholders(settings, placeholder):
    with pytest.raises(AuthConfigurationError):
        replace(settings, jwt_secret=placeholder, app_env="production", state_backend="redis",
                redis_url="redis://localhost:6379", cors_origins=("https://vietech.example",))


def test_production_accepts_generated_secret(settings):
    import secrets

    configured = replace(settings, jwt_secret=secrets.token_urlsafe(48), app_env="production",
                         state_backend="redis", redis_url="redis://localhost:6379",
                         cors_origins=("https://vietech.example",))
    assert configured.app_env == "production"


def test_mail_configuration_never_echoes_code(settings):
    with pytest.raises(AuthError) as error:
        SMTPMailer(settings).send_otp("customer@example.test", "123456", "signup", 90)
    assert error.value.status_code == 503
    assert "123456" not in error.value.message


def test_redis_outage_fails_closed(monkeypatch):
    import redis

    class DownRedis:
        def ping(self):
            raise redis.exceptions.ConnectionError("backend details should be private")

    monkeypatch.setattr(redis.Redis, "from_url", lambda *args, **kwargs: DownRedis())
    with pytest.raises(StateUnavailable) as error:
        RedisStateStore("redis://private-password@localhost:6379")
    assert "private" not in str(error.value)


def test_malformed_redis_config_is_safe():
    with pytest.raises(StateUnavailable):
        RedisStateStore("not-a-redis-url")
