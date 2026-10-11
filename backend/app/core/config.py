from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from .errors import AuthConfigurationError


@dataclass(frozen=True)
class AuthSettings:
    jwt_secret: str = ""
    jwt_issuer: str = "vietech"
    access_ttl: int = 900
    customer_session_ttl: int = 604800
    internal_session_ttl: int = 28800
    internal_idle_ttl: int = 1800
    signup_otp_ttl: int = 90
    reset_otp_ttl: int = 60
    reset_grant_ttl: int = 300
    email_otp_ttl: int = 90
    failure_limit: int = 5
    block_ttl: int = 180
    failure_window: int = 900
    resend_interval: int = 60
    # At most send_limit OTP emails per purpose and recipient within send_window seconds.
    send_limit: int = 5
    send_window: int = 3600
    state_backend: str = "memory"
    redis_url: str = ""
    app_env: str = "development"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender: str = ""
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    smtp_timeout: int = 10
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    def __post_init__(self):
        if len(self.jwt_secret.encode("utf-8")) < 32 or not self.jwt_issuer:
            raise AuthConfigurationError()
        if self.app_env not in {"development", "test", "production"}:
            raise AuthConfigurationError()
        if self.state_backend not in {"memory", "redis"}:
            raise AuthConfigurationError()
        if self.state_backend == "redis" and not self.redis_url:
            raise AuthConfigurationError()
        if self.app_env == "production" and (
            self.state_backend != "redis"
            or len(set(self.jwt_secret)) < 10
            or self.jwt_secret.strip().lower().startswith(("replace-", "change-me", "changeme"))
            or not self.cors_origins
            or "*" in self.cors_origins
            or any(not origin.startswith("https://") for origin in self.cors_origins)
        ):
            raise AuthConfigurationError()
        durations = (
            self.access_ttl, self.customer_session_ttl, self.internal_session_ttl,
            self.internal_idle_ttl, self.signup_otp_ttl, self.reset_otp_ttl, self.reset_grant_ttl,
            self.email_otp_ttl, self.failure_limit, self.block_ttl,
            self.failure_window, self.resend_interval, self.send_limit, self.send_window, self.smtp_timeout,
        )
        if any(not isinstance(value, int) or value <= 0 for value in durations):
            raise AuthConfigurationError()
        if not 1 <= self.smtp_port <= 65535:
            raise AuthConfigurationError()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        raise AuthConfigurationError() from None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no"}:
        return False
    raise AuthConfigurationError()


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    integer_settings = {
        "access_ttl": ("AUTH_ACCESS_TTL", 900),
        "customer_session_ttl": ("AUTH_CUSTOMER_SESSION_TTL", 604800),
        "internal_session_ttl": ("AUTH_INTERNAL_SESSION_TTL", 28800),
        "internal_idle_ttl": ("AUTH_INTERNAL_IDLE_TTL", 1800),
        "signup_otp_ttl": ("AUTH_SIGNUP_OTP_TTL", 90),
        "reset_otp_ttl": ("AUTH_RESET_OTP_TTL", 60),
        "reset_grant_ttl": ("AUTH_RESET_GRANT_TTL", 300),
        "email_otp_ttl": ("AUTH_EMAIL_OTP_TTL", 90),
        "failure_limit": ("AUTH_FAILURE_LIMIT", 5),
        "block_ttl": ("AUTH_BLOCK_TTL", 180),
        "failure_window": ("AUTH_FAILURE_WINDOW", 900),
        "resend_interval": ("AUTH_RESEND_INTERVAL", 60),
        "send_limit": ("AUTH_SEND_LIMIT", 5),
        "send_window": ("AUTH_SEND_WINDOW", 3600),
        "smtp_port": ("SMTP_PORT", 587),
        "smtp_timeout": ("SMTP_TIMEOUT", 10),
    }
    cors_origins = tuple(origin.strip().rstrip("/") for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if origin.strip())
    return AuthSettings(
        jwt_secret=os.getenv("AUTH_JWT_SECRET", ""),
        jwt_issuer=os.getenv("AUTH_JWT_ISSUER", "vietech"),
        app_env=os.getenv("APP_ENV", "development").lower(),
        state_backend=os.getenv("AUTH_STATE_BACKEND", "memory").lower(),
        redis_url=os.getenv("REDIS_URL", ""),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_username=os.getenv("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_sender=os.getenv("SMTP_SENDER", ""),
        smtp_starttls=_env_bool("SMTP_STARTTLS", True),
        smtp_ssl=_env_bool("SMTP_SSL", False),
        cors_origins=cors_origins,
        **{field: _env_int(name, default) for field, (name, default) in integer_settings.items()},
    )
