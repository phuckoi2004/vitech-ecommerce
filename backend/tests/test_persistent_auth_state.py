"""Local sessions survive backend restarts without relaxing rotation, expiry or revocation."""
import concurrent.futures
import json
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from app.core.config import AuthSettings
from app.core.errors import AuthConfigurationError, AuthError, StateUnavailable
from app.core.sessions import SessionManager
from app.core.sqlite_state import SQLiteStateStore


@pytest.fixture
def setup(tmp_path):
    current = [time.time()]
    path = tmp_path / "private" / "auth.sqlite3"
    settings = AuthSettings(jwt_secret="test-only-secret-at-least-thirty-two-bytes", app_env="test", state_backend="sqlite", state_path=str(path))
    return path, settings, current, lambda: current[0]


@pytest.mark.parametrize("role,portal", [("Customer", "customer"), ("Staff", "admin"), ("Admin", "admin")])
def test_session_refresh_after_fifteen_minutes_and_restart(setup, role, portal):
    path, settings, current, now = setup
    user = SimpleNamespace(UserId=uuid.uuid4(), Email="test@example.test", PasswordHash="test-hash", Role=role, AccountStatus="Active", IsDeleted=False)
    original = SessionManager(SQLiteStateStore(path, now=now), settings, now=now).issue(user, portal)
    current[0] += 901
    restarted = SessionManager(SQLiteStateStore(path, now=now), settings, now=now)
    renewed = restarted.refresh(original.refresh_token, lambda _: user)
    assert renewed.session_id == original.session_id
    assert renewed.refresh_token != original.refresh_token
    assert renewed.expires_in == settings.access_ttl
    restarted.validate_access({"sub": str(user.UserId), "sid": renewed.session_id, "portal": portal}, user)
    with pytest.raises(AuthError):
        restarted.refresh(original.refresh_token, lambda _: user)
    with pytest.raises(AuthError):
        SessionManager(SQLiteStateStore(path, now=now), settings, now=now).refresh(renewed.refresh_token, lambda _: user)


def test_state_expiry_and_independent_copies_survive_restart(setup):
    path, _, current, now = setup
    store = SQLiteStateStore(path, now=now)
    store.put("otp", {"nested": {"attempts": 0}}, 60)
    restored = SQLiteStateStore(path, now=now)
    restored.get("otp")["nested"]["attempts"] = 10
    assert restored.get("otp") == {"nested": {"attempts": 0}}
    current[0] += 60
    assert restored.get("otp") is None
    assert SQLiteStateStore(path, now=now).get("otp") is None


def test_refresh_in_new_python_process_after_access_expiry(setup):
    path, settings, current, now = setup
    user = SimpleNamespace(UserId=uuid.uuid4(), Email="test@example.test", PasswordHash="test-hash", Role="Customer", AccountStatus="Active", IsDeleted=False)
    pair = SessionManager(SQLiteStateStore(path, now=now), settings, now=now).issue(user, "customer")
    current[0] += 901
    script = '''
import json, sys
from types import SimpleNamespace
from app.core.config import AuthSettings
from app.core.sessions import SessionManager
from app.core.sqlite_state import SQLiteStateStore
data = json.load(sys.stdin)
settings = AuthSettings(**data["settings"])
now = lambda: data["now"]
manager = SessionManager(SQLiteStateStore(data["path"], now=now), settings, now=now)
renewed = manager.refresh(data["token"], lambda _: SimpleNamespace(**data["user"]))
assert renewed.session_id == data["sid"]
print("refreshed")
'''
    result = subprocess.run([sys.executable, "-c", script], input=json.dumps({
        "path": str(path), "settings": asdict(settings), "now": now(), "token": pair.refresh_token,
        "sid": pair.session_id, "user": {**vars(user), "UserId": str(user.UserId)},
    }), text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "refreshed"


def test_nested_locks_serialize_two_store_instances(setup):
    path, _, _, now = setup
    stores = [SQLiteStateStore(path, now=now), SQLiteStateStore(path, now=now)]
    stores[0].put("counter", {"n": 0}, 60)

    def increment(index):
        store = stores[index % 2]
        for _ in range(20):
            with store.lock("user"):
                with store.lock("session"):
                    value = store.get("counter")
                    value["n"] += 1
                    store.put("counter", value, 60)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(increment, range(4)))
    assert stores[0].get("counter")["n"] == 80


def test_failed_locked_operation_keeps_security_updates_and_releases_lock(setup):
    path, _, _, now = setup
    store = SQLiteStateStore(path, now=now)
    with pytest.raises(ValueError):
        with store.lock("session"):
            store.put("session", {"valid": True}, 60)
            raise ValueError("failed attempt must still be saved")
    assert store.get("session") == {"valid": True}
    with store.lock("session"):
        store.put("session", {"valid": True}, 60)
    assert SQLiteStateStore(path, now=now).get("session") == {"valid": True}


def test_logout_and_user_revocation_remain_effective_after_restart(setup):
    path, settings, _, now = setup
    user = SimpleNamespace(UserId=uuid.uuid4(), Email="test@example.test", PasswordHash="test-hash", Role="Customer", AccountStatus="Active", IsDeleted=False)
    sessions = SessionManager(SQLiteStateStore(path, now=now), settings, now=now)
    first, second = sessions.issue(user, "customer"), sessions.issue(user, "customer")
    sessions.logout(first.session_id)
    restarted = SessionManager(SQLiteStateStore(path, now=now), settings, now=now)
    with pytest.raises(AuthError):
        restarted.refresh(first.refresh_token, lambda _: user)
    renewed = restarted.refresh(second.refresh_token, lambda _: user)
    restarted.revoke_user(str(user.UserId))
    with pytest.raises(AuthError):
        SessionManager(SQLiteStateStore(path, now=now), settings, now=now).refresh(renewed.refresh_token, lambda _: user)


def test_local_store_does_not_replace_production_redis_requirement(setup):
    _, settings, _, _ = setup
    with pytest.raises(AuthConfigurationError):
        replace(settings, app_env="production", cors_origins=("https://example.test",))


def test_unavailable_local_store_fails_closed(tmp_path):
    file = tmp_path / "not-a-directory"
    file.write_text("invalid parent")
    with pytest.raises(StateUnavailable):
        SQLiteStateStore(file / "auth.sqlite3")
