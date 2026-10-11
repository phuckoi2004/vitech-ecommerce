"""Shared auth dependencies; authorization always reads the current database user."""

import uuid
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.repositories.user import UserRepository
from app.services.actor import Actor

from .auth_state import StateStore, get_auth_state
from .config import AuthSettings, get_auth_settings
from .errors import AuthError
from .mail import get_mailer
from .rbac import has_permission
from .security import decode_access_token, hash_password
from .sessions import SessionManager


@dataclass
class AuthRuntime:
    settings: AuthSettings
    state: StateStore
    mailer: object
    sessions: SessionManager
    dummy_password_hash: str


@lru_cache(maxsize=1)
def get_runtime() -> AuthRuntime:
    settings = get_auth_settings()
    state = get_auth_state(settings)
    return AuthRuntime(settings, state, get_mailer(settings), SessionManager(state, settings), hash_password("TimingOnly7!not-an-account"))


bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    runtime: AuthRuntime = Depends(get_runtime),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthError(401, "Cần đăng nhập", {"WWW-Authenticate": "Bearer"})
    claims = decode_access_token(credentials.credentials, runtime.settings)
    try:
        user_id = uuid.UUID(claims["sub"])
    except (ValueError, TypeError, KeyError):
        raise AuthError(401, "Phiên đăng nhập không hợp lệ") from None
    from app.services.auth import ensure_active_user

    user = ensure_active_user(UserRepository(db).get_by_id(user_id), db)
    runtime.sessions.validate_access(claims, user)
    request.state.auth_session_id = claims["sid"]
    request.state.auth_portal = claims["portal"]
    return user


def get_current_actor(user: User = Depends(get_current_user)) -> Actor:
    """Actor for Stage 4 services, built only from the authenticated, active database user."""
    return Actor(user_id=user.UserId, role=user.Role)


def get_optional_actor(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    runtime: AuthRuntime = Depends(get_runtime),
) -> Actor | None:
    """For public use cases that show more to signed-in staff: no token means anonymous (None).

    A token that is sent but invalid, expired or revoked is still rejected rather than treated as anonymous.
    """
    if credentials is None:
        return None
    return get_current_actor(get_current_user(request, credentials, db, runtime))


def require_permission(permission: str):
    def check(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.Role, permission):
            raise AuthError(403, "Bạn không có quyền thực hiện thao tác này")
        return user

    return check
