"""Map Service layer business errors to HTTP responses (Router responsibility, README 3.2).

Services raise ``ServiceError`` subclasses without knowing about HTTP. The message is written for
the client (Vietnamese, no internal details) and ``code`` lets the client tell errors apart.
The body keeps the ``detail`` key used by Auth errors, plus ``code``.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.exceptions import (
    AccountLockedError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    EmailNotVerifiedError,
    InvalidOtpError,
    NotFoundError,
    PaymentGatewayError,
    PaymentVerificationError,
    PermissionDeniedError,
    ServiceError,
    TooManyRequestsError,
)
from app.services.internal_jobs import JobSelectionError

# Checked in order; the first matching class wins. Unlisted subclasses fall back to 400.
_STATUS_BY_ERROR: tuple[tuple[type[ServiceError], int], ...] = (
    (NotFoundError, 404),
    (ConflictError, 409),
    (PermissionDeniedError, 403),
    (AuthenticationError, 401),
    (AccountLockedError, 403),
    (EmailNotVerifiedError, 403),
    (TooManyRequestsError, 429),
    (PaymentGatewayError, 502),
    (JobSelectionError, 500),  # an internal job could not select its records: nothing was processed
    (InvalidOtpError, 400),
    (PaymentVerificationError, 400),
    (BusinessRuleError, 400),
)

# require_role(None, ...) raises PermissionDeniedError with this code: the caller is not signed in.
_AUTHENTICATION_REQUIRED = "authentication_required"


def service_error_status(error: ServiceError) -> int:
    if isinstance(error, PermissionDeniedError) and error.code == _AUTHENTICATION_REQUIRED:
        return 401
    return next((status for kind, status in _STATUS_BY_ERROR if isinstance(error, kind)), 400)


async def service_error_handler(request: Request, error: ServiceError) -> JSONResponse:
    status_code = service_error_status(error)
    headers: dict[str, str] = {}
    if status_code == 401:
        headers["WWW-Authenticate"] = "Bearer"
    retry_after = getattr(error, "retry_after_seconds", None)
    if status_code == 429 and retry_after is not None:
        headers["Retry-After"] = str(max(int(retry_after), 0))
    return JSONResponse(status_code=status_code, content={"detail": error.message, "code": error.code},
                        headers=headers or None)
