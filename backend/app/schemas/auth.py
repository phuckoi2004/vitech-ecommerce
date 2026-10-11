"""Request/response contracts for authentication, separate from database schemas."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, TypeAdapter, field_validator, model_validator

from .common import RequestSchema
from .user import UserResponse


def normalize_phone_number(value: str) -> str:
    phone = re.sub(r"[\s().-]", "", value)
    if phone.startswith("+84"):
        phone = "0" + phone[3:]
    elif phone.startswith("0084"):
        phone = "0" + phone[4:]
    if not re.fullmatch(r"(?:0[35789][0-9]{8}|02[0-9]{9})", phone):
        raise ValueError("Số điện thoại Việt Nam không hợp lệ")
    return phone


def validate_password(value: str) -> str:
    if len(value) < 8 or not any(c.isupper() for c in value) or not any(c.isdigit() for c in value) or not any(not c.isalnum() and not c.isspace() for c in value):
        raise ValueError("Mật khẩu cần ít nhất 8 ký tự, có chữ hoa, số và ký tự đặc biệt")
    return value


class AuthRequest(RequestSchema):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class RegistrationRequest(AuthRequest):
    Email: EmailStr
    PhoneNumber: str
    FullName: Annotated[str, Field(min_length=1, max_length=255)]
    Password: str
    ConfirmPassword: str

    @field_validator("Email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).strip().lower()

    @field_validator("PhoneNumber")
    @classmethod
    def phone(cls, value):
        return normalize_phone_number(value)

    @field_validator("FullName")
    @classmethod
    def name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Họ tên không được để trống")
        return value

    @field_validator("Password")
    @classmethod
    def password(cls, value):
        return validate_password(value)

    @model_validator(mode="after")
    def confirm(self):
        if self.Password != self.ConfirmPassword:
            raise ValueError("Mật khẩu xác nhận không khớp")
        return self


class IdentifierRequest(AuthRequest):
    Identifier: Annotated[str, Field(min_length=1, max_length=255)]

    @field_validator("Identifier")
    @classmethod
    def identifier(cls, value):
        value = value.strip()
        if "@" in value:
            return str(TypeAdapter(EmailStr).validate_python(value)).lower()
        return normalize_phone_number(value)


class LoginRequest(IdentifierRequest):
    Password: Annotated[str, Field(min_length=1)]
    Portal: Literal["customer", "admin"] = "customer"


class ChallengeRequest(AuthRequest):
    ChallengeId: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]


class OTPVerifyRequest(ChallengeRequest):
    Code: Annotated[str, Field(pattern=r"^[0-9]{6}$")]


class NewPasswordRequest(AuthRequest):
    NewPassword: str
    ConfirmPassword: str

    @field_validator("NewPassword")
    @classmethod
    def password(cls, value):
        return validate_password(value)

    @model_validator(mode="after")
    def confirm(self):
        if self.NewPassword != self.ConfirmPassword:
            raise ValueError("Mật khẩu xác nhận không khớp")
        return self


class ResetPasswordRequest(NewPasswordRequest):
    ResetToken: Annotated[str, Field(min_length=50, max_length=200)]


class PasswordChangeRequest(NewPasswordRequest):
    CurrentPassword: Annotated[str, Field(min_length=1)]


class EmailChangeRequest(AuthRequest):
    Email: EmailStr
    CurrentPassword: Annotated[str, Field(min_length=1)]

    @field_validator("Email")
    @classmethod
    def email(cls, value):
        return str(value).lower()


class MessageResponse(BaseModel):
    message: str


class ChallengeResponse(MessageResponse):
    challenge_id: str
    expires_in: int
    resend_after: int


class ResetGrantResponse(BaseModel):
    reset_token: str
    expires_in: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    csrf_token: str
    user: UserResponse
    permissions: list[str]


class AuthMeResponse(BaseModel):
    user: UserResponse
    permissions: list[str]
