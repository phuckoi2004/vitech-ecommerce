import hmac
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.dependencies import AuthRuntime, get_current_user, get_runtime
from app.core.errors import AuthError
from app.core.rbac import permission_list
from app.core.security import secret_digest
from app.database import get_db
from app.models import User
from app.schemas.auth import (
    AuthMeResponse, ChallengeRequest, ChallengeResponse, EmailChangeRequest,
    IdentifierRequest, LoginRequest, MessageResponse, OTPVerifyRequest,
    PasswordChangeRequest, RegistrationRequest, ResetGrantResponse,
    ResetPasswordRequest, TokenResponse,
)
from app.schemas.user import UserResponse
from app.services.auth import AuthService


router = APIRouter(prefix="/auth", tags=["Xác thực"])
Database = Annotated[Session, Depends(get_db)]
Runtime = Annotated[AuthRuntime, Depends(get_runtime)]
CurrentUser = Annotated[User, Depends(get_current_user)]
REFRESH_COOKIE = "vietech_refresh"
CSRF_COOKIE = "vietech_csrf"


def _set_tokens(response, tokens, user, runtime):
    nonce = secrets.token_urlsafe(24)
    csrf = nonce + "." + secret_digest(nonce + tokens.refresh_token, runtime.settings, context="csrf")
    secure = runtime.settings.app_env == "production"
    response.set_cookie(REFRESH_COOKIE, tokens.refresh_token, httponly=True, secure=secure,
                        samesite="lax", max_age=tokens.refresh_expires_in, path="/auth")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=secure,
                        samesite="lax", max_age=tokens.refresh_expires_in, path="/")
    return {"access_token": tokens.access_token, "expires_in": tokens.expires_in,
            "token_type": "bearer", "csrf_token": csrf, "user": UserResponse.model_validate(user),
            "permissions": permission_list(user.Role)}


def _clear_tokens(response):
    response.delete_cookie(REFRESH_COOKIE, path="/auth")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _check_csrf(request, runtime):
    refresh = request.cookies.get(REFRESH_COOKIE)
    csrf = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get("X-CSRF-Token")
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") not in runtime.settings.cors_origins:
        raise AuthError(403, "Nguồn yêu cầu không được phép")
    if not refresh or not csrf or not header or not hmac.compare_digest(csrf, header):
        raise AuthError(403, "Yêu cầu thiếu mã bảo vệ CSRF hợp lệ")
    try:
        nonce, signature = csrf.split(".", 1)
    except ValueError:
        raise AuthError(403, "Mã bảo vệ CSRF không hợp lệ") from None
    expected = secret_digest(nonce + refresh, runtime.settings, context="csrf")
    if not hmac.compare_digest(signature, expected):
        raise AuthError(403, "Mã bảo vệ CSRF không hợp lệ")
    return refresh


@router.post("/register", response_model=ChallengeResponse, status_code=202)
def register(payload: RegistrationRequest, db: Database, runtime: Runtime):
    return AuthService(db, runtime).register(payload)


@router.post("/register/verify", response_model=MessageResponse, status_code=201)
def verify_registration(payload: OTPVerifyRequest, db: Database, runtime: Runtime):
    AuthService(db, runtime).verify_registration(payload.ChallengeId, payload.Code)
    return {"message": "Đăng ký thành công. Bạn có thể đăng nhập"}


@router.post("/otp/resend", response_model=ChallengeResponse, status_code=202)
def resend_otp(payload: ChallengeRequest, db: Database, runtime: Runtime):
    return AuthService(db, runtime).resend(payload.ChallengeId)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Database, runtime: Runtime):
    tokens, user = AuthService(db, runtime).login(payload)
    return _set_tokens(response, tokens, user, runtime)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Database, runtime: Runtime):
    tokens, user = AuthService(db, runtime).refresh(_check_csrf(request, runtime))
    return _set_tokens(response, tokens, user, runtime)


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, response: Response, user: CurrentUser, runtime: Runtime):
    if request.cookies.get(REFRESH_COOKIE):
        _check_csrf(request, runtime)
    runtime.sessions.logout(request.state.auth_session_id)
    _clear_tokens(response)
    return {"message": "Đã đăng xuất"}


@router.get("/me", response_model=AuthMeResponse)
def me(user: CurrentUser):
    return {"user": UserResponse.model_validate(user), "permissions": permission_list(user.Role)}


@router.post("/forgot-password", response_model=ChallengeResponse, status_code=202)
def forgot_password(payload: IdentifierRequest, db: Database, runtime: Runtime):
    return AuthService(db, runtime).forgot_password(payload.Identifier)


@router.post("/reset-password/verify", response_model=ResetGrantResponse)
def verify_reset(payload: OTPVerifyRequest, db: Database, runtime: Runtime):
    return AuthService(db, runtime).verify_reset(payload.ChallengeId, payload.Code)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, response: Response, db: Database, runtime: Runtime):
    AuthService(db, runtime).reset_password(payload)
    _clear_tokens(response)
    return {"message": "Đã đặt lại mật khẩu. Vui lòng đăng nhập lại"}


@router.post("/change-password", response_model=MessageResponse)
def change_password(payload: PasswordChangeRequest, response: Response, user: CurrentUser, db: Database, runtime: Runtime):
    AuthService(db, runtime).change_password(user, payload)
    _clear_tokens(response)
    return {"message": "Đã đổi mật khẩu. Vui lòng đăng nhập lại"}


@router.post("/email-change", response_model=ChallengeResponse, status_code=202)
def request_email_change(payload: EmailChangeRequest, user: CurrentUser, db: Database, runtime: Runtime):
    return AuthService(db, runtime).request_email_change(user, payload)


@router.post("/email-change/verify", response_model=MessageResponse)
def verify_email_change(payload: OTPVerifyRequest, response: Response, user: CurrentUser, db: Database, runtime: Runtime):
    AuthService(db, runtime).verify_email_change(user, payload.ChallengeId, payload.Code)
    _clear_tokens(response)
    return {"message": "Đã đổi và xác minh email. Vui lòng đăng nhập lại"}
