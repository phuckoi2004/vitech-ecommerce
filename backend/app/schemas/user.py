"""Schemas cho Users, Addresses, Notifications.

Không response schema nào chứa PasswordHash, OtpCode, OtpExpiredAt.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import Field

from .common import (
    AccountStatusValue,
    EmailAddress,
    Money,
    NonNegativeInt,
    RequestSchema,
    ResponseSchema,
    UserRole,
    varchar,
)

# Mật khẩu dạng plain text chỉ có trong request; database chỉ lưu PasswordHash.
# Chưa có quy định độ dài/độ mạnh mật khẩu trong schema hiện tại.
PlainPassword = Annotated[str, Field(min_length=1)]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserRegister(RequestSchema):
    """Khách hàng tự đăng ký. Role, AccountStatus do server gán."""

    NULLABLE_FIELDS = frozenset({"Gender", "DateOfBirth", "AvatarUrl"})

    Email: EmailAddress
    PhoneNumber: varchar(20)
    Password: PlainPassword
    FullName: varchar(255)
    Gender: varchar(10) | None = None
    DateOfBirth: date | None = None
    AvatarUrl: varchar(500) | None = None


class AdminUserCreate(UserRegister):
    """Quản trị viên tạo tài khoản (ví dụ tài khoản nhân viên)."""

    Role: UserRole
    AccountStatus: AccountStatusValue


class UserProfileUpdate(RequestSchema):
    """Người dùng tự cập nhật hồ sơ (PATCH). Không đổi Email, Role, AccountStatus tại đây."""

    NULLABLE_FIELDS = frozenset({"Gender", "DateOfBirth", "AvatarUrl"})

    PhoneNumber: varchar(20) | None = None
    FullName: varchar(255) | None = None
    Gender: varchar(10) | None = None
    DateOfBirth: date | None = None
    AvatarUrl: varchar(500) | None = None


class PasswordChange(RequestSchema):
    CurrentPassword: PlainPassword
    NewPassword: PlainPassword


class AdminUserUpdate(RequestSchema):
    """Phân quyền và khóa/mở khóa tài khoản (PATCH)."""

    NULLABLE_FIELDS = frozenset({"LockReason", "LockedUntil"})

    Role: UserRole | None = None
    AccountStatus: AccountStatusValue | None = None
    LockReason: str | None = None
    LockedUntil: datetime | None = None


class UserSummary(ResponseSchema):
    """Thông tin rút gọn khi nhúng vào resource khác."""

    UserId: uuid.UUID
    FullName: str
    AvatarUrl: str | None


class UserResponse(ResponseSchema):
    """Hồ sơ của chính người dùng."""

    UserId: uuid.UUID
    Email: str
    PhoneNumber: str
    FullName: str
    Gender: str | None
    DateOfBirth: date | None
    AvatarUrl: str | None
    Role: UserRole
    AccountStatus: AccountStatusValue
    IsEmailVerified: bool
    CreatedAt: datetime
    UpdatedAt: datetime


class AdminUserResponse(UserResponse):
    """Thông tin tài khoản cho quản trị viên."""

    LockReason: str | None
    LockedUntil: datetime | None
    TotalSpent: Money
    TotalOrders: NonNegativeInt
    IsDeleted: bool


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------


class AddressCreate(RequestSchema):
    """UserId lấy từ người dùng đăng nhập; IsDefault bỏ qua = database default (false)."""

    ReceiverName: varchar(255)
    ReceiverPhone: varchar(20)
    Province: varchar(100)
    Ward: varchar(100)
    DetailAddress: varchar(255)
    IsDefault: bool | None = None


class AddressUpdate(RequestSchema):
    ReceiverName: varchar(255) | None = None
    ReceiverPhone: varchar(20) | None = None
    Province: varchar(100) | None = None
    Ward: varchar(100) | None = None
    DetailAddress: varchar(255) | None = None
    IsDefault: bool | None = None


class AddressResponse(ResponseSchema):
    AddressId: uuid.UUID
    UserId: uuid.UUID
    ReceiverName: str
    ReceiverPhone: str
    Province: str
    Ward: str
    DetailAddress: str
    IsDefault: bool


# ---------------------------------------------------------------------------
# Notifications (do server tạo, client chỉ đọc)
# ---------------------------------------------------------------------------


class NotificationResponse(ResponseSchema):
    NotificationId: uuid.UUID
    Title: str
    Content: str
    NotificationType: str
    ActionUrl: str | None
    ReferenceType: str | None
    ReferenceId: uuid.UUID | None
    IsRead: bool
    ReadAt: datetime | None
    CreatedAt: datetime
