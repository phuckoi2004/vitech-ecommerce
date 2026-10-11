"""Account profile and administration with transaction and object-level checks."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.rbac import has_permission
from app.core.security import hash_password
from app.core.storage import AvatarStorage, detect_image_type
from app.models import Address, User
from app.repositories.user import AddressRepository, UserRepository
from app.schemas.account import (
    AdminUserPage, DefaultAddressUpdate, InternalUserCreate, ManagedUserUpdate, ProfileUpdate,
)


class UserService:
    def __init__(self, db: Session, runtime: Any):
        self.db = db
        self.runtime = runtime
        self.users = UserRepository(db)
        self.addresses = AddressRepository(db)

    def _require_admin(self, actor: User) -> None:
        if actor.Role != "Admin" or actor.IsDeleted or actor.AccountStatus != "Active" or not has_permission(actor.Role, "users:manage"):
            raise AuthError(403, "Bạn không có quyền quản lý tài khoản.")

    def _managed_target(self, actor: User, user_id: uuid.UUID) -> User:
        self._require_admin(actor)
        target = self.users.get_by_id_for_update(user_id)
        if target is None or target.IsDeleted:
            raise AuthError(404, "Không tìm thấy tài khoản.")
        if target.UserId == actor.UserId:
            raise AuthError(403, "Hãy sử dụng chức năng hồ sơ để sửa tài khoản của bạn.")
        if target.Role not in {"Customer", "Staff"}:
            raise AuthError(403, "Tài khoản này nằm ngoài phạm vi quản lý của bạn.")
        return target

    def _commit(self, user: User, *, refresh: bool = True) -> User:
        try:
            self.db.commit()
            if refresh:
                self.db.refresh(user)
        except IntegrityError:
            self.db.rollback()
            raise AuthError(409, "Email hoặc số điện thoại đã được sử dụng.") from None
        except Exception:
            self.db.rollback()
            raise
        return user

    def _validate_phone_unique(self, user: User, values: dict) -> None:
        if "PhoneNumber" in values and self.users.exists_by_phone(values["PhoneNumber"], user.UserId):
            raise AuthError(409, "Số điện thoại đã được sử dụng.")

    @staticmethod
    def _require_active(actor: User) -> None:
        if actor.IsDeleted or actor.AccountStatus != "Active":
            raise AuthError(403, "Tài khoản không được phép thực hiện thao tác này.")

    def update_profile(self, actor: User, payload: ProfileUpdate) -> User:
        self._require_active(actor)
        values = payload.model_dump(exclude_unset=True)
        self._validate_phone_unique(actor, values)
        self.users.update(actor, values)
        return self._commit(actor)

    def update_avatar(self, actor: User, data: bytes, storage: AvatarStorage | None) -> User:
        self._require_active(actor)
        if storage is None:
            raise AuthError(503, "Chưa cấu hình kho lưu ảnh. Vui lòng liên hệ quản trị hệ thống.")
        content_type = detect_image_type(data)
        if content_type is None:
            raise AuthError(415, "Ảnh đại diện phải là tệp JPG, PNG hoặc WEBP.")
        previous = storage.path_of(actor.AvatarUrl, actor.UserId)
        path = storage.upload(actor.UserId, data, content_type)
        try:
            self.users.update(actor, {"AvatarUrl": storage.public_url(path)})
            user = self._commit(actor, refresh=False)
        except Exception:
            try:
                storage.delete(path)
            except Exception:
                pass  # Cleanup is best effort; keep the original database error.
            raise
        # A refresh error cannot undo this commit or justify deleting the saved image.
        self.db.refresh(user)
        if previous:
            storage.delete(previous)
        return user

    def get_default_address(self, actor: User) -> Address | None:
        defaults = self.addresses.list_default_by_user(actor.UserId)
        return defaults[0] if defaults else None

    def save_default_address(self, actor: User, payload: DefaultAddressUpdate) -> Address:
        self._require_active(actor)
        address = self.get_default_address(actor)
        values = payload.model_dump()
        if address is None:
            address = self.addresses.create({
                **values, "AddressId": uuid.uuid4(), "UserId": actor.UserId,
                "ReceiverName": actor.FullName, "ReceiverPhone": actor.PhoneNumber,
                "IsDefault": True, "IsDeleted": False,
            })
        else:
            self.addresses.update(address, values)
        try:
            self.db.commit()
            self.db.refresh(address)
        except Exception:
            self.db.rollback()
            raise
        return address

    def list_users(self, actor: User, *, page: int = 1, page_size: int = 20,
                   role: str | None = None, account_status: str | None = None,
                   include_deleted: bool = False, search: str | None = None,
                   deleted_only: bool = False) -> AdminUserPage:
        self._require_admin(actor)
        if page < 1 or not 1 <= page_size <= 100:
            raise AuthError(422, "Thông tin phân trang không hợp lệ.")
        if role is not None and role not in {"Customer", "Staff"}:
            raise AuthError(403, "Tài khoản này nằm ngoài phạm vi quản lý của bạn.")
        search = search.strip() if search else None
        filters = dict(role=role, roles={"Customer", "Staff"}, account_status=account_status,
                       include_deleted=include_deleted, search=search or None,
                       deleted_only=deleted_only)
        total = self.users.count_users(**filters)
        items = self.users.list_users(**filters, offset=(page - 1) * page_size, limit=page_size)
        return AdminUserPage(Items=items, Total=total, Page=page, PageSize=page_size)

    def get_user(self, actor: User, user_id: uuid.UUID, *, include_deleted: bool = False) -> User:
        self._require_admin(actor)
        target = self.users.get_by_id(user_id)
        # Admin accounts are outside the managed scope; like the list, they look absent.
        if (target is None or target.Role not in {"Customer", "Staff"}
                or (target.IsDeleted and not include_deleted)):
            raise AuthError(404, "Không tìm thấy tài khoản.")
        return target

    def create_user(self, actor: User, payload: InternalUserCreate) -> User:
        self._require_admin(actor)
        if payload.Role != "Staff":
            raise AuthError(403, "Chỉ được tạo tài khoản Staff qua chức năng này.")
        if self.users.exists_by_email(payload.Email) or self.users.exists_by_phone(payload.PhoneNumber):
            raise AuthError(409, "Email hoặc số điện thoại đã được sử dụng.")
        values = payload.model_dump(exclude={"Password", "ConfirmPassword"})
        values.update(UserId=uuid.uuid4(), PasswordHash=hash_password(payload.Password),
                      AccountStatus="Active", IsEmailVerified=True, IsDeleted=False)
        user = self.users.create(values)
        return self._commit(user)

    def update_user(self, actor: User, user_id: uuid.UUID, payload: ManagedUserUpdate) -> User:
        target = self._managed_target(actor, user_id)
        values = payload.model_dump(exclude_unset=True)
        new_role = values.get("Role", target.Role)
        if new_role != target.Role:
            raise AuthError(403, "Không được phép thực hiện thay đổi vai trò này.")
        status = values.get("AccountStatus")
        if status == "Locked":
            deadline = values.get("LockedUntil")
            if not values.get("LockReason") or deadline is None or deadline <= datetime.now(timezone.utc):
                raise AuthError(422, "Khóa tài khoản cần lý do và thời hạn trong tương lai.")
        elif status == "Active":
            if values.get("LockReason") is not None or values.get("LockedUntil") is not None:
                raise AuthError(422, "Tài khoản hoạt động không được có thời hạn hoặc lý do khóa.")
            values.update(LockReason=None, LockedUntil=None)
        elif {"LockReason", "LockedUntil"} & values.keys():
            raise AuthError(422, "Cần chọn trạng thái tài khoản khi thay đổi thông tin khóa.")
        self._validate_phone_unique(target, values)
        revoke = status is not None
        # Revoke first. If the state service is unavailable, no account mutation is committed.
        if revoke:
            self.runtime.sessions.revoke_user(target.UserId)
        self.users.update(target, values)
        return self._commit(target)

    def delete_user(self, actor: User, user_id: uuid.UUID) -> None:
        target = self._managed_target(actor, user_id)
        self.runtime.sessions.revoke_user(target.UserId)
        self.users.update(target, {"IsDeleted": True, "OtpCode": None, "OtpExpiredAt": None})
        self._commit(target)
