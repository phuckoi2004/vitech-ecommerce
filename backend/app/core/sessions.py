from __future__ import annotations

import hmac
import math
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .auth_state import StateStore
from .config import AuthSettings
from .errors import AuthError
from .security import issue_access_token, secret_digest


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    session_id: str
    refresh_expires_in: int


def _field(user: Any, name: str):
    return user.get(name) if isinstance(user, dict) else getattr(user, name, None)


class SessionManager:
    def __init__(
        self, state: StateStore, settings: AuthSettings,
        now: Callable[[], float] = time.time,
    ):
        self.state = state
        self.settings = settings
        self.now = now

    @staticmethod
    def _invalid() -> AuthError:
        return AuthError(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
                         {"WWW-Authenticate": "Bearer"})

    @staticmethod
    def _session_key(session_id: str) -> str:
        return f"session:{session_id}"

    @staticmethod
    def _user_lock(user_id: str) -> str:
        return f"session-user:{user_id}"

    @staticmethod
    def _epoch_key(user_id: str) -> str:
        return f"session-epoch:{user_id}"

    def _epoch_ttl(self) -> int:
        return max(self.settings.customer_session_ttl, self.settings.internal_session_ttl) + self.settings.access_ttl + 60

    def _epoch(self, user_id: str) -> str:
        record = self.state.get(self._epoch_key(user_id))
        return record["value"] if record else "0"

    def _retain_epoch(self, user_id: str, epoch: str) -> None:
        self.state.put(self._epoch_key(user_id), {"value": epoch}, self._epoch_ttl())

    def _fingerprint(self, user: Any) -> str:
        value = "\x00".join(str(_field(user, field)) for field in ("PasswordHash", "Email", "Role"))
        return secret_digest(value, self.settings, context="user-fingerprint")

    @staticmethod
    def _portal_allowed(user: Any, portal: str) -> bool:
        role = _field(user, "Role")
        return (portal == "customer" and role == "Customer") or (
            portal == "admin" and role in {"Staff", "Admin"}
        )

    def _save(self, session_id: str, record: dict) -> None:
        ttl = math.ceil(record["expires_at"] - self.now())
        if ttl <= 0:
            self.state.delete(self._session_key(session_id))
            raise self._invalid()
        self.state.put(self._session_key(session_id), record, ttl)

    def _check(self, session_id: str, record: dict | None, user: Any) -> dict:
        if record is None or user is None:
            raise self._invalid()
        now = self.now()
        user_id = str(_field(user, "UserId"))
        valid = (
            record["user_id"] == user_id
            and record["expires_at"] > now
            and record["epoch"] == self._epoch(user_id)
            and self._portal_allowed(user, record["portal"])
            and hmac.compare_digest(record["fingerprint"], self._fingerprint(user))
            and not bool(_field(user, "IsDeleted"))
            and _field(user, "AccountStatus") == "Active"
            and (
                record["portal"] != "admin"
                or now - record["last_seen"] < self.settings.internal_idle_ttl
            )
        )
        if not valid:
            self.state.delete(self._session_key(session_id))
            raise self._invalid()
        return record

    def _pair(self, session_id: str, record: dict, refresh_secret: str) -> TokenPair:
        remaining = max(1, int(record["expires_at"] - self.now()))
        access_ttl = min(self.settings.access_ttl, remaining)
        return TokenPair(
            access_token=issue_access_token(
                record["user_id"], session_id, record["portal"], self.settings,
                now=self.now(), expires_in=access_ttl,
            ),
            refresh_token=f"{session_id}.{refresh_secret}",
            expires_in=access_ttl, session_id=session_id,
            refresh_expires_in=remaining,
        )

    def issue(self, user: Any, portal: str) -> TokenPair:
        if not self._portal_allowed(user, portal):
            raise AuthError(403, "Tài khoản không được phép truy cập giao diện này.")
        if bool(_field(user, "IsDeleted")) or _field(user, "AccountStatus") != "Active":
            raise self._invalid()
        user_id = str(_field(user, "UserId"))
        session_id = str(uuid.uuid4())
        refresh_secret = secrets.token_urlsafe(48)
        now = self.now()
        lifetime = self.settings.customer_session_ttl if portal == "customer" else self.settings.internal_session_ttl
        with self.state.lock(self._user_lock(user_id)):
            epoch = self._epoch(user_id)
            self._retain_epoch(user_id, epoch)
            record = {
                "user_id": user_id, "portal": portal, "epoch": epoch,
                "fingerprint": self._fingerprint(user), "created_at": now,
                "expires_at": now + lifetime, "last_seen": now,
                "refresh_digest": secret_digest(refresh_secret, self.settings),
            }
            self._save(session_id, record)
        return self._pair(session_id, record, refresh_secret)

    def validate_access(self, claims: dict, user: Any) -> None:
        session_id = claims.get("sid", "")
        user_id = str(_field(user, "UserId"))
        if claims.get("sub") != user_id:
            raise self._invalid()
        with self.state.lock(self._user_lock(user_id)):
            with self.state.lock(self._session_key(session_id)):
                record = self._check(session_id, self.state.get(self._session_key(session_id)), user)
                if claims.get("portal") != record["portal"]:
                    raise self._invalid()
                record["last_seen"] = self.now()
                self._retain_epoch(user_id, record["epoch"])
                self._save(session_id, record)

    def refresh(self, refresh_token: str, load_user: Callable[[str], Any]) -> TokenPair:
        try:
            session_id, presented_secret = refresh_token.split(".", 1)
            uuid.UUID(session_id)
            if not presented_secret:
                raise ValueError()
        except (ValueError, AttributeError):
            raise self._invalid() from None
        initial = self.state.get(self._session_key(session_id))
        if initial is None:
            raise self._invalid()
        user_id = initial["user_id"]
        # Loading may auto-unlock a database row. Do it before acquiring state
        # locks: account mutations take a database row lock before revoking the
        # user's epoch. Re-checking the epoch below catches a concurrent change.
        user = load_user(user_id)
        # The lock order is always user, then session. User-wide revocation cannot
        # race with issuing/rotating a session on another device.
        with self.state.lock(self._user_lock(user_id)):
            with self.state.lock(self._session_key(session_id)):
                record = self._check(session_id, self.state.get(self._session_key(session_id)), user)
                if not hmac.compare_digest(record["refresh_digest"], secret_digest(presented_secret, self.settings)):
                    self.state.delete(self._session_key(session_id))
                    raise self._invalid()
                next_secret = secrets.token_urlsafe(48)
                record["refresh_digest"] = secret_digest(next_secret, self.settings)
                record["last_seen"] = self.now()
                self._retain_epoch(user_id, record["epoch"])
                self._save(session_id, record)
                return self._pair(session_id, record, next_secret)

    def logout(self, session_id: str) -> None:
        with self.state.lock(self._session_key(session_id)):
            self.state.delete(self._session_key(session_id))

    def revoke_user(self, user_id: str) -> None:
        user_id = str(user_id)
        with self.state.lock(self._user_lock(user_id)):
            self._retain_epoch(user_id, str(uuid.uuid4()))
