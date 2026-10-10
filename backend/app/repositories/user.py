"""Repositories cho Users, Addresses, Notifications, OtpChallenges.

Không xử lý mật khẩu/OTP và không log dữ liệu nhạy cảm.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.models import Address, Notification, OtpChallenge, User

from .base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    @staticmethod
    def _email_matches(email: str):
        # Khớp unique index UX_Users_Email_Lower: lower("Email").
        return func.lower(User.Email) == func.lower(email)

    def get_by_email(self, email: str) -> User | None:
        """Tìm theo Email không phân biệt hoa thường; trả cả tài khoản IsDeleted (Service tự quyết định)."""
        return self.get_one(self._email_matches(email))

    def get_by_phone(self, phone_number: str) -> User | None:
        return self.get_one(User.PhoneNumber == phone_number)

    def exists_by_email(self, email: str, exclude_user_id: uuid.UUID | None = None) -> bool:
        """Kiểm tra trùng Email trên mọi dòng (kể cả IsDeleted), giống phạm vi của unique index."""
        conditions = [self._email_matches(email)]
        if exclude_user_id is not None:
            conditions.append(User.UserId != exclude_user_id)
        return self.exists(*conditions)

    def exists_by_phone(self, phone_number: str, exclude_user_id: uuid.UUID | None = None) -> bool:
        """Kiểm tra trùng PhoneNumber trên mọi dòng (kể cả IsDeleted), giống phạm vi của UNIQUE."""
        conditions = [User.PhoneNumber == phone_number]
        if exclude_user_id is not None:
            conditions.append(User.UserId != exclude_user_id)
        return self.exists(*conditions)

    def _filters(self, role: str | None, account_status: str | None, include_deleted: bool) -> list:
        conditions = []
        if role is not None:
            conditions.append(User.Role == role)
        if account_status is not None:
            conditions.append(User.AccountStatus == account_status)
        if not include_deleted:
            conditions.append(User.IsDeleted.is_(False))
        return conditions

    def list_users(
        self,
        *,
        role: str | None = None,
        account_status: str | None = None,
        include_deleted: bool = False,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[User]:
        return self.get_all(
            *self._filters(role, account_status, include_deleted),
            order_by=(User.CreatedAt.desc(), User.UserId),
            offset=offset,
            limit=limit,
        )

    def count_users(
        self, *, role: str | None = None, account_status: str | None = None, include_deleted: bool = False
    ) -> int:
        return self.count(*self._filters(role, account_status, include_deleted))

    def list_admins_for_update(self) -> list[User]:
        """Khóa mọi tài khoản Admin chưa xóa (FOR UPDATE, thứ tự UserId) trước khi kiểm tra "Admin cuối cùng".

        Hai thao tác quản trị đồng thời trên các Admin khác nhau chạy tuần tự, không cùng khóa/xóa hết Admin.
        """
        stmt = (
            select(User)
            .where(User.Role == "Admin", User.IsDeleted.is_(False))
            .order_by(User.UserId)
            .with_for_update()
        )
        return self._scalars_for_update(stmt)


class OtpChallengeRepository(BaseRepository[OtpChallenge]):
    """Các lần gửi OTP (chỉ bản băm). Caller khóa dòng Users trước khi đọc/ghi để xử lý đồng thời an toàn."""

    model = OtpChallenge

    def latest_for(self, user_id: uuid.UUID, purpose: str) -> OtpChallenge | None:
        stmt = (
            select(OtpChallenge)
            .where(OtpChallenge.UserId == user_id, OtpChallenge.Purpose == purpose)
            .order_by(OtpChallenge.CreatedAt.desc(), OtpChallenge.OtpChallengeId.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def count_sent_since(self, user_id: uuid.UUID, purpose: str, since: datetime) -> int:
        return self.count(
            OtpChallenge.UserId == user_id, OtpChallenge.Purpose == purpose, OtpChallenge.CreatedAt > since
        )


class AddressRepository(BaseRepository[Address]):
    model = Address

    def list_by_user(self, user_id: uuid.UUID, *, include_deleted: bool = False) -> list[Address]:
        conditions = [Address.UserId == user_id]
        if not include_deleted:
            conditions.append(Address.IsDeleted.is_(False))
        return self.get_all(*conditions, order_by=(Address.IsDefault.desc(), Address.AddressId))

    def get_by_id_and_user(self, address_id: uuid.UUID, user_id: uuid.UUID) -> Address | None:
        return self.get_one(Address.AddressId == address_id, Address.UserId == user_id)

    def list_default_by_user(self, user_id: uuid.UUID) -> list[Address]:
        """Các địa chỉ đang IsDefault của user (chưa xóa); Service quyết định giữ một địa chỉ mặc định."""
        return self.get_all(
            Address.UserId == user_id, Address.IsDefault.is_(True), Address.IsDeleted.is_(False)
        )


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    def list_by_user(
        self,
        user_id: uuid.UUID,
        *,
        is_read: bool | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Notification]:
        conditions = [Notification.UserId == user_id]
        if is_read is not None:
            conditions.append(Notification.IsRead.is_(is_read))
        return self.get_all(
            *conditions,
            order_by=(Notification.CreatedAt.desc(), Notification.NotificationId),
            offset=offset,
            limit=limit,
        )

    def count_by_user(self, user_id: uuid.UUID, *, is_read: bool | None = None) -> int:
        conditions = [Notification.UserId == user_id]
        if is_read is not None:
            conditions.append(Notification.IsRead.is_(is_read))
        return self.count(*conditions)
