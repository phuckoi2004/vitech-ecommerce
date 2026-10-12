"""Validated account requests for phase 5. Responses reuse safe user schemas."""

from datetime import date, datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator, model_validator

from .auth import AuthRequest, normalize_phone_number, validate_password
from .common import PageResponse, RequestSchema, UserRole, varchar
from .user import AdminUserResponse


class ProfileUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Gender", "DateOfBirth", "AvatarUrl"})

    PhoneNumber: varchar(20) | None = None
    FullName: varchar(255) | None = None
    Gender: varchar(10) | None = None
    DateOfBirth: date | None = None
    AvatarUrl: varchar(500) | None = None

    @field_validator("PhoneNumber")
    @classmethod
    def normalize_phone(cls, value):
        return normalize_phone_number(value) if value is not None else value

    @field_validator("FullName")
    @classmethod
    def validate_name(cls, value):
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Họ tên không được để trống.")
        return value

    @field_validator("DateOfBirth")
    @classmethod
    def validate_birth_date(cls, value):
        if value is not None and value > date.today():
            raise ValueError("Ngày sinh không được ở tương lai.")
        return value

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("Cần cung cấp thông tin muốn cập nhật.")
        return self


class DefaultAddressUpdate(RequestSchema):
    """Địa chỉ mặc định trên trang hồ sơ; người nhận lấy theo hồ sơ khi tạo mới."""

    Province: varchar(100)
    Ward: varchar(100)
    DetailAddress: varchar(255)

    @field_validator("Province", "Ward", "DetailAddress")
    @classmethod
    def require_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Địa chỉ cần đủ Tỉnh/Thành phố, Phường/Xã và địa chỉ chi tiết.")
        return value


class InternalUserCreate(AuthRequest):
    NULLABLE_FIELDS = frozenset({"Gender", "DateOfBirth", "AvatarUrl"})

    Email: EmailStr = Field(max_length=255)
    PhoneNumber: varchar(20)
    FullName: str = Field(min_length=1, max_length=255)
    Password: str = Field(min_length=8, max_length=1024)
    ConfirmPassword: str = Field(min_length=8, max_length=1024)
    Role: Literal["Staff"] = "Staff"
    Gender: varchar(10) | None = None
    DateOfBirth: date | None = None
    AvatarUrl: varchar(500) | None = None

    @field_validator("Email")
    @classmethod
    def validate_email(cls, value):
        return value.lower()

    _normalize_phone = field_validator("PhoneNumber")(normalize_phone_number)
    _validate_password = field_validator("Password")(validate_password)
    _validate_name = field_validator("FullName")(ProfileUpdate.validate_name)
    _validate_birth_date = field_validator("DateOfBirth")(ProfileUpdate.validate_birth_date)

    @model_validator(mode="after")
    def matching_passwords(self):
        if self.Password != self.ConfirmPassword:
            raise ValueError("Xác nhận mật khẩu không khớp.")
        return self


class ManagedUserUpdate(ProfileUpdate):
    NULLABLE_FIELDS = ProfileUpdate.NULLABLE_FIELDS | {"LockReason", "LockedUntil"}

    Role: UserRole | None = None
    AccountStatus: Literal["Active", "Locked"] | None = None
    LockReason: str | None = Field(default=None, max_length=2000)
    LockedUntil: datetime | None = None

    @field_validator("LockReason")
    @classmethod
    def validate_reason(cls, value):
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Lý do khóa không được để trống.")
        return value

    @field_validator("LockedUntil")
    @classmethod
    def require_timezone(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Thời hạn khóa phải có múi giờ.")
        return value


class AdminUserPage(PageResponse[AdminUserResponse]):
    pass
