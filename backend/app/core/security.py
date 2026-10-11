from __future__ import annotations

import hashlib
import hmac
import time
import uuid

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from .config import AuthSettings
from .errors import AuthError


_password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password, password_hash)
    except (ValueError, TypeError, UnknownHashError):
        return False


def secret_digest(secret: str, settings: AuthSettings, context: str = "refresh") -> str:
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        f"{context}\x00{secret}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def otp_digest(code: str, settings: AuthSettings, purpose: str = "otp") -> str:
    return secret_digest(code, settings, context=f"otp:{purpose}")


def issue_access_token(
    user_id: str, session_id: str, portal: str, settings: AuthSettings,
    *, now: float | None = None, expires_in: int | None = None,
) -> str:
    issued = int(time.time() if now is None else now)
    lifetime = settings.access_ttl if expires_in is None else expires_in
    return jwt.encode({
        "sub": str(user_id), "sid": session_id, "portal": portal,
        "iss": settings.jwt_issuer, "aud": "auth", "iat": issued,
        "nbf": issued, "exp": issued + lifetime, "jti": str(uuid.uuid4()),
    }, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: AuthSettings) -> dict:
    try:
        claims = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"],
            issuer=settings.jwt_issuer, audience="auth",
            options={"require": ["sub", "sid", "portal", "iss", "aud", "iat", "nbf", "exp", "jti"]},
        )
        uuid.UUID(claims["sub"])
        uuid.UUID(claims["sid"])
        if claims["portal"] not in {"customer", "admin"}:
            raise ValueError()
        return claims
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise AuthError(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
                        {"WWW-Authenticate": "Bearer"}) from None
