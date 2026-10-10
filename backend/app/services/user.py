"""User / Account services: tài khoản, hồ sơ, quản trị tài khoản, địa chỉ, thông báo.

Nguồn nghiệp vụ: docs/business-requirements.md mục 1, 2 và quyết định đợt 5.1:
- OTP: chỉ lưu bản băm (OtpChallenges, qua PasswordHasher); tách theo mục đích (Registration/PasswordReset);
  hết hạn 5 phút; tối đa 5 lần nhập sai rồi khóa xác minh 15 phút (trong lúc khóa cũng chặn gửi OTP mới);
  gửi cách nhau tối thiểu 60 giây, tối đa 5 lần/giờ cho mỗi tài khoản + mục đích; gửi lại không xóa số lần sai đã
  tích lũy (trong vòng 1 giờ, chưa xác minh thành công, chưa bị khóa). Khóa dòng Users khi gửi/xác minh.
- Admin không tự khóa/tự xóa/tự hạ quyền; không khóa/xóa/hạ quyền Admin hoạt động cuối cùng (khóa mọi dòng Admin
  theo thứ tự trước khi đếm). Admin đang bị khóa hoặc đã xóa mềm không tính là đang hoạt động.
Không trả ORM User ra ngoài; mọi kết quả là response schema (không có PasswordHash, OtpCode, OtpExpiredAt).
"""

import math
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Address, Notification, OtpChallenge, User
from app.models.user import ACCOUNT_STATUSES, OTP_PURPOSE_PASSWORD_RESET, OTP_PURPOSE_REGISTRATION
from app.repositories import AddressRepository, NotificationRepository, OtpChallengeRepository, UserRepository
from app.schemas import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    AdminUserCreate,
    AdminUserResponse,
    AdminUserUpdate,
    NotificationResponse,
    PageResponse,
    PasswordChange,
    UserProfileUpdate,
    UserRegister,
    UserResponse,
)

from .actor import ADMIN_ONLY, ANY_ROLE, CUSTOMER_ONLY, Actor, require_role
from .base import BaseService, utc_now
from .exceptions import (
    AccountLockedError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    EmailNotVerifiedError,
    InvalidOtpError,
    NotFoundError,
    ServiceError,
    TooManyRequestsError,
)
from .ports import OtpSender, PasswordHasher

# Role tự đăng ký (business-requirements: Customer đăng ký tài khoản).
CUSTOMER_ROLE = "Customer"

# AccountStatus: CHECK IN ('Active', 'Locked') (docs/database-schema.md).
ACCOUNT_STATUS_ACTIVE, ACCOUNT_STATUS_LOCKED = ACCOUNT_STATUSES
ADMIN_ROLE = "Admin"


@dataclass(frozen=True)
class AccountSettings:
    """Cấu hình OTP (giá trị ban đầu đã chốt): hết hạn 5 phút, 6 chữ số; tối đa 5 lần nhập sai rồi khóa xác minh
    15 phút; gửi cách nhau tối thiểu 60 giây, tối đa 5 lần mỗi giờ cho mỗi tài khoản + mục đích."""

    otp_ttl: timedelta = timedelta(minutes=5)
    otp_length: int = 6
    otp_max_failed_attempts: int = 5
    otp_verify_lock: timedelta = timedelta(minutes=15)
    otp_resend_interval: timedelta = timedelta(seconds=60)
    otp_max_sends_per_hour: int = 5

    def __post_init__(self) -> None:
        if not 4 <= self.otp_length <= 10:
            raise ValueError("otp_length phải từ 4 đến 10")
        if self.otp_max_failed_attempts < 1 or self.otp_max_sends_per_hour < 1:
            raise ValueError("Giới hạn OTP phải lớn hơn 0")
        for value in (self.otp_ttl, self.otp_verify_lock, self.otp_resend_interval):
            if value <= timedelta(0):
                raise ValueError("Thời gian cấu hình OTP phải lớn hơn 0")


def is_locked(user: User, now: datetime) -> bool:
    """Tài khoản bị khóa: AccountStatus = Locked và chưa qua LockedUntil (NULL = khóa không thời hạn)."""
    return _is_lock_in_effect(user.AccountStatus, user.LockedUntil, now)


def _is_lock_in_effect(account_status: str, locked_until: datetime | None, now: datetime) -> bool:
    if account_status != ACCOUNT_STATUS_LOCKED:
        return False
    return locked_until is None or locked_until > now


def is_active_admin(user: User, now: datetime) -> bool:
    """Admin đang hoạt động: Role Admin, chưa xóa mềm, không bị khóa (khóa đã hết hạn coi như mở)."""
    return user.Role == ADMIN_ROLE and not user.IsDeleted and not is_locked(user, now)


def _check_account_status(value: str) -> None:
    if value not in ACCOUNT_STATUSES:
        raise BusinessRuleError(
            f"AccountStatus không hợp lệ: {value}. Giá trị hợp lệ: {', '.join(ACCOUNT_STATUSES)}",
            code="invalid_account_status",
        )


class UserService(BaseService):
    """Đăng ký, xác thực OTP, đăng nhập, quên/đổi mật khẩu, hồ sơ cá nhân và quản trị tài khoản."""

    def __init__(
        self,
        session: Session,
        *,
        password_hasher: PasswordHasher,
        otp_sender: OtpSender,
        settings: AccountSettings | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(session, clock=clock)
        self.users = UserRepository(session)
        self.otp_challenges = OtpChallengeRepository(session)
        self.password_hasher = password_hasher
        self.otp_sender = otp_sender
        self.settings = settings or AccountSettings()

    # ------------------------------------------------------------------
    # Đăng ký + xác thực OTP
    # ------------------------------------------------------------------

    def register(self, data: UserRegister) -> UserResponse:
        """Tạo tài khoản Customer chưa xác thực email và gửi OTP.

        OTP được lưu và commit trước, sau đó mới gửi email. Nếu gửi lỗi, Customer dùng
        ``resend_registration_otp`` để nhận OTP mới.
        """
        with self.transaction():
            self._ensure_unique(email=data.Email, phone_number=data.PhoneNumber)
            values = data.model_dump(exclude_unset=True, exclude={"Password"})
            user = self.users.create(
                {
                    **values,
                    "PasswordHash": self.password_hasher.hash(data.Password),
                    "Role": CUSTOMER_ROLE,
                    "AccountStatus": ACCOUNT_STATUS_ACTIVE,
                    "IsEmailVerified": False,
                }
            )
            self.users.flush()
            otp_code = self._issue_otp(user, OTP_PURPOSE_REGISTRATION)
            response = UserResponse.model_validate(user)
        self.otp_sender.send_registration_otp(response.Email, otp_code)
        return response

    def resend_registration_otp(self, email: str) -> None:
        """Gửi lại OTP đăng ký (giới hạn 60 giây/lần, 5 lần/giờ; bị chặn khi đang khóa xác minh)."""
        with self.transaction():
            user = self._lock_active_user_by_email(email)
            if user.IsEmailVerified:
                raise BusinessRuleError("Email đã được xác thực", code="email_already_verified")
            otp_code = self._issue_otp(user, OTP_PURPOSE_REGISTRATION)
            recipient = user.Email
        self.otp_sender.send_registration_otp(recipient, otp_code)

    def verify_registration_otp(self, email: str, otp_code: str) -> UserResponse:
        """Xác thực OTP đăng ký; thành công thì kích hoạt (IsEmailVerified = true).

        Nhập sai: số lần sai được ghi (commit) rồi mới báo lỗi; quá giới hạn thì khóa xác minh 15 phút.
        """
        with self.transaction():
            user = self._lock_active_user_by_email(email)
            if user.IsEmailVerified:
                raise BusinessRuleError("Email đã được xác thực", code="email_already_verified")
            failure = self._verify_otp(user, OTP_PURPOSE_REGISTRATION, otp_code)
            if failure is None:
                user.IsEmailVerified = True
                self.users.flush()
                response = UserResponse.model_validate(user)
        if failure is not None:
            raise failure
        return response

    # ------------------------------------------------------------------
    # Đăng nhập
    # ------------------------------------------------------------------

    def authenticate(self, email: str, password: str) -> UserResponse:
        """Kiểm tra Email + mật khẩu, sau đó trạng thái tài khoản. Không phát hành JWT (giai đoạn Auth)."""
        user = self.users.get_by_email(email)
        # Cùng một lỗi cho: không tồn tại, đã xóa, sai mật khẩu (tránh dò tài khoản).
        if user is None or user.IsDeleted or not self.password_hasher.verify(password, user.PasswordHash):
            raise AuthenticationError("Email hoặc mật khẩu không đúng")
        if is_locked(user, self.now()):
            raise AccountLockedError("Tài khoản đang bị khóa")
        if not user.IsEmailVerified:
            raise EmailNotVerifiedError("Tài khoản chưa xác thực email")
        return UserResponse.model_validate(user)

    # ------------------------------------------------------------------
    # Quên mật khẩu / đổi mật khẩu
    # ------------------------------------------------------------------

    def request_password_reset(self, email: str) -> None:
        """Kiểm tra tài khoản và gửi OTP đặt lại mật khẩu.

        Raise NotFoundError nếu không có tài khoản; Router quyết định có ẩn thông tin này với client hay không.
        """
        with self.transaction():
            user = self._lock_active_user_by_email(email)
            otp_code = self._issue_otp(user, OTP_PURPOSE_PASSWORD_RESET)
            recipient = user.Email
        self.otp_sender.send_password_reset_otp(recipient, otp_code)

    def reset_password(self, email: str, otp_code: str, new_password: str) -> None:
        """Đặt lại mật khẩu bằng OTP mục đích PasswordReset (OTP đăng ký không dùng được ở đây)."""
        with self.transaction():
            user = self._lock_active_user_by_email(email)
            failure = self._verify_otp(user, OTP_PURPOSE_PASSWORD_RESET, otp_code)
            if failure is None:
                user.PasswordHash = self.password_hasher.hash(new_password)
        if failure is not None:
            raise failure

    def change_password(self, actor: Actor, data: PasswordChange) -> None:
        """Người dùng đăng nhập đổi mật khẩu của chính mình (xác minh mật khẩu hiện tại)."""
        require_role(actor, *ANY_ROLE)
        with self.transaction():
            user = self._get_active_user(actor.user_id)
            if not self.password_hasher.verify(data.CurrentPassword, user.PasswordHash):
                raise AuthenticationError("Mật khẩu hiện tại không đúng")
            user.PasswordHash = self.password_hasher.hash(data.NewPassword)

    # ------------------------------------------------------------------
    # Hồ sơ cá nhân (Customer/Staff/Admin)
    # ------------------------------------------------------------------

    def get_profile(self, actor: Actor) -> UserResponse:
        require_role(actor, *ANY_ROLE)
        return UserResponse.model_validate(self._get_active_user(actor.user_id))

    def update_profile(self, actor: Actor, data: UserProfileUpdate) -> UserResponse:
        """Sửa hồ sơ của chính mình; không đổi Email, Role, AccountStatus (Schema không có các trường này)."""
        require_role(actor, *ANY_ROLE)
        with self.transaction():
            user = self._get_active_user(actor.user_id)
            values = data.model_dump(exclude_unset=True)
            if "PhoneNumber" in values:
                self._ensure_unique(phone_number=values["PhoneNumber"], exclude_user_id=user.UserId)
            self.users.update(user, values)
            self.users.flush()
            return UserResponse.model_validate(user)

    # ------------------------------------------------------------------
    # Quản trị tài khoản (chỉ Admin)
    # ------------------------------------------------------------------

    def admin_list_users(
        self,
        actor: Actor,
        *,
        role: str | None = None,
        account_status: str | None = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[AdminUserResponse]:
        require_role(actor, *ADMIN_ONLY)
        offset, limit = self._page_args(page, page_size)
        filters = {"role": role, "account_status": account_status, "include_deleted": include_deleted}
        users = self.users.list_users(**filters, offset=offset, limit=limit)
        return PageResponse[AdminUserResponse](
            Items=[AdminUserResponse.model_validate(u) for u in users],
            Total=self.users.count_users(**filters),
            Page=page,
            PageSize=page_size,
        )

    def admin_get_user(self, actor: Actor, user_id: uuid.UUID) -> AdminUserResponse:
        require_role(actor, *ADMIN_ONLY)
        return AdminUserResponse.model_validate(self._get_user(user_id))

    def admin_create_user(self, actor: Actor, data: AdminUserCreate) -> AdminUserResponse:
        """Admin thêm tài khoản. IsEmailVerified theo default database (false)."""
        require_role(actor, *ADMIN_ONLY)
        _check_account_status(data.AccountStatus)
        with self.transaction():
            self._ensure_unique(email=data.Email, phone_number=data.PhoneNumber)
            values = data.model_dump(exclude_unset=True, exclude={"Password"})
            user = self.users.create({**values, "PasswordHash": self.password_hasher.hash(data.Password)})
            self.users.flush()
            return AdminUserResponse.model_validate(user)

    def admin_update_user(self, actor: Actor, user_id: uuid.UUID, data: AdminUserUpdate) -> AdminUserResponse:
        """Admin phân quyền / cập nhật trạng thái, lý do và thời hạn khóa.

        Không tự khóa/tự hạ quyền; không khóa/hạ quyền Admin hoạt động cuối cùng.
        """
        require_role(actor, *ADMIN_ONLY)
        values = data.model_dump(exclude_unset=True)
        if "AccountStatus" in values:
            _check_account_status(values["AccountStatus"])
        with self.transaction():
            user = self._get_active_user(user_id)
            self._guard_admin_access(
                actor,
                user,
                role=values.get("Role", user.Role),
                account_status=values.get("AccountStatus", user.AccountStatus),
                locked_until=values.get("LockedUntil", user.LockedUntil),
                deleting=False,
            )
            self.users.update(user, values)
            self.users.flush()
            return AdminUserResponse.model_validate(user)

    def lock_user(
        self, actor: Actor, user_id: uuid.UUID, *, reason: str | None = None, locked_until: datetime | None = None
    ) -> AdminUserResponse:
        """Khóa tài khoản và ghi nhận lý do/thời gian khóa (LockedUntil NULL = không thời hạn)."""
        return self.admin_update_user(
            actor,
            user_id,
            AdminUserUpdate(AccountStatus=ACCOUNT_STATUS_LOCKED, LockReason=reason, LockedUntil=locked_until),
        )

    def unlock_user(self, actor: Actor, user_id: uuid.UUID) -> AdminUserResponse:
        return self.admin_update_user(
            actor,
            user_id, AdminUserUpdate(AccountStatus=ACCOUNT_STATUS_ACTIVE, LockReason=None, LockedUntil=None)
        )

    def admin_delete_user(self, actor: Actor, user_id: uuid.UUID) -> None:
        """Xóa mềm (IsDeleted = true); không xóa dòng vì dữ liệu nghiệp vụ tham chiếu Users (RESTRICT).

        Không tự xóa; không xóa Admin hoạt động cuối cùng.
        """
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            user = self._get_active_user(user_id)
            self._guard_admin_access(
                actor, user, role=user.Role, account_status=user.AccountStatus, locked_until=user.LockedUntil, deleting=True
            )
            user.IsDeleted = True

    # ------------------------------------------------------------------
    # Helpers (không mở transaction riêng)
    # ------------------------------------------------------------------

    def _get_user(self, user_id: uuid.UUID) -> User:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Không tìm thấy tài khoản", code="user_not_found")
        return user

    def _get_active_user(self, user_id: uuid.UUID) -> User:
        user = self._get_user(user_id)
        if user.IsDeleted:
            raise NotFoundError("Không tìm thấy tài khoản", code="user_not_found")
        return user

    def _get_active_user_by_email(self, email: str) -> User:
        user = self.users.get_by_email(email)
        if user is None or user.IsDeleted:
            raise NotFoundError("Không tìm thấy tài khoản", code="user_not_found")
        return user

    def _ensure_unique(
        self,
        *,
        email: str | None = None,
        phone_number: str | None = None,
        exclude_user_id: uuid.UUID | None = None,
    ) -> None:
        if email is not None and self.users.exists_by_email(email, exclude_user_id):
            raise ConflictError("Email đã được sử dụng", code="email_exists")
        if phone_number is not None and self.users.exists_by_phone(phone_number, exclude_user_id):
            raise ConflictError("Số điện thoại đã được sử dụng", code="phone_number_exists")

    def _lock_active_user_by_email(self, email: str) -> User:
        """Khóa dòng Users (FOR UPDATE): gửi/xác minh OTP đồng thời cho cùng tài khoản chạy tuần tự."""
        user = self._get_active_user_by_email(email)
        locked = self.users.get_by_id_for_update(user.UserId)
        if locked is None or locked.IsDeleted:
            raise NotFoundError("Không tìm thấy tài khoản", code="user_not_found")
        return locked

    def _issue_otp(self, user: User, purpose: str) -> str:
        """Tạo OTP mới cho (tài khoản, mục đích) đã khóa dòng; chỉ lưu bản băm. Trả mã để gửi email (không log).

        Chặn khi đang khóa xác minh, gửi lại chưa đủ 60 giây hoặc đã gửi đủ 5 lần trong một giờ. Số lần nhập sai
        của OTP trước (chưa dùng, chưa bị khóa, tạo trong vòng 1 giờ) được mang sang OTP mới.
        """
        now = self.now()
        settings = self.settings
        latest = self.otp_challenges.latest_for(user.UserId, purpose)
        if latest is not None and latest.LockedUntil is not None and latest.LockedUntil > now:
            raise self._verification_locked(latest.LockedUntil, now)
        if latest is not None and latest.CreatedAt > now - settings.otp_resend_interval:
            raise TooManyRequestsError(
                "Vui lòng chờ trước khi yêu cầu gửi lại OTP",
                code="otp_send_too_soon",
                retry_after_seconds=_seconds_until(latest.CreatedAt + settings.otp_resend_interval, now),
            )
        window_start = now - timedelta(hours=1)
        if self.otp_challenges.count_sent_since(user.UserId, purpose, window_start) >= settings.otp_max_sends_per_hour:
            raise TooManyRequestsError("Đã vượt số lần gửi OTP cho phép trong một giờ", code="otp_send_limit_exceeded")
        carried = (
            latest.FailedAttempts
            if latest is not None
            and latest.ConsumedAt is None
            and latest.LockedUntil is None
            and latest.CreatedAt > window_start
            else 0
        )
        otp_code = "".join(secrets.choice("0123456789") for _ in range(settings.otp_length))
        self.otp_challenges.create(
            {
                "UserId": user.UserId,
                "Purpose": purpose,
                "CodeHash": self.password_hasher.hash(otp_code),
                "ExpiresAt": now + settings.otp_ttl,
                "FailedAttempts": carried,
                "CreatedAt": now,
            }
        )
        # Cơ chế cũ lưu OTP văn bản thuần ở Users: không dùng nữa, luôn để trống.
        user.OtpCode = None
        user.OtpExpiredAt = None
        self.otp_challenges.flush()
        return otp_code

    def _verify_otp(self, user: User, purpose: str, otp_code: str) -> ServiceError | None:
        """Kiểm tra OTP mới nhất của (tài khoản, mục đích). Trả lỗi (caller raise SAU khi commit để giữ số lần sai).

        Thông báo không nêu OTP hay thông tin nhạy cảm; code phân biệt: otp_invalid, otp_expired,
        otp_verification_locked.
        """
        now = self.now()
        challenge: OtpChallenge | None = self.otp_challenges.latest_for(user.UserId, purpose)
        if challenge is None or challenge.ConsumedAt is not None:
            return InvalidOtpError("OTP không đúng hoặc đã hết hạn", code="otp_invalid")
        if challenge.LockedUntil is not None and challenge.LockedUntil > now:
            return self._verification_locked(challenge.LockedUntil, now)
        if challenge.ExpiresAt <= now:
            return InvalidOtpError("OTP đã hết hạn; vui lòng yêu cầu mã mới", code="otp_expired")
        if not self.password_hasher.verify(otp_code, challenge.CodeHash):
            challenge.FailedAttempts += 1
            if challenge.FailedAttempts >= self.settings.otp_max_failed_attempts:
                challenge.LockedUntil = now + self.settings.otp_verify_lock
                self.otp_challenges.flush()
                return self._verification_locked(challenge.LockedUntil, now)
            self.otp_challenges.flush()
            return InvalidOtpError("OTP không đúng hoặc đã hết hạn", code="otp_invalid")
        challenge.ConsumedAt = now
        self.otp_challenges.flush()
        return None

    @staticmethod
    def _verification_locked(locked_until: datetime, now: datetime) -> TooManyRequestsError:
        return TooManyRequestsError(
            "Nhập sai OTP quá số lần cho phép; vui lòng thử lại sau",
            code="otp_verification_locked",
            retry_after_seconds=_seconds_until(locked_until, now),
        )

    def _guard_admin_access(
        self,
        actor: Actor,
        user: User,
        *,
        role: str,
        account_status: str,
        locked_until: datetime | None,
        deleting: bool,
    ) -> None:
        """Không để Admin tự khóa/xóa/hạ quyền; không để hệ thống mất Admin đang hoạt động cuối cùng.

        Khi thay đổi làm một Admin không còn hoạt động: khóa mọi dòng Admin (thứ tự UserId) rồi mới đếm, nên hai
        thao tác đồng thời (ví dụ hai Admin khóa lẫn nhau) chạy tuần tự và thao tác sau thấy kết quả thao tác trước.
        """
        now = self.now()
        active_after = (
            not deleting and role == ADMIN_ROLE and not _is_lock_in_effect(account_status, locked_until, now)
        )
        if user.UserId == actor.user_id and not active_after:
            raise BusinessRuleError(
                "Admin không được tự khóa, tự xóa hoặc tự hạ quyền của chính mình", code="admin_self_change_not_allowed"
            )
        if user.Role != ADMIN_ROLE or active_after:
            return
        admins = self.users.list_admins_for_update()
        if not any(a.UserId != user.UserId and is_active_admin(a, now) for a in admins):
            raise BusinessRuleError("Phải còn ít nhất một Admin đang hoạt động", code="last_active_admin")


class AddressService(BaseService):
    """Sổ địa chỉ nhận hàng của người dùng."""

    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.addresses = AddressRepository(session)

    def list_addresses(self, actor: Actor) -> list[AddressResponse]:
        require_role(actor, *CUSTOMER_ONLY)
        return [AddressResponse.model_validate(a) for a in self.addresses.list_by_user(actor.user_id)]

    def get_address(self, actor: Actor, address_id: uuid.UUID) -> AddressResponse:
        require_role(actor, *CUSTOMER_ONLY)
        return AddressResponse.model_validate(self._get_owned(actor.user_id, address_id))

    def create_address(self, actor: Actor, data: AddressCreate) -> AddressResponse:
        require_role(actor, *CUSTOMER_ONLY)
        user_id = actor.user_id
        with self.transaction():
            values = data.model_dump(exclude_unset=True)
            if values.get("IsDefault"):
                self._clear_default(user_id)
            address = self.addresses.create({**values, "UserId": user_id})
            self.addresses.flush()
            return AddressResponse.model_validate(address)

    def update_address(self, actor: Actor, address_id: uuid.UUID, data: AddressUpdate) -> AddressResponse:
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            address = self._get_owned(actor.user_id, address_id)
            values = data.model_dump(exclude_unset=True)
            if values.get("IsDefault"):
                self._clear_default(actor.user_id, keep=address)
            self.addresses.update(address, values)
            self.addresses.flush()
            return AddressResponse.model_validate(address)

    def delete_address(self, actor: Actor, address_id: uuid.UUID) -> None:
        """Xóa mềm; Orders.AddressId vẫn tham chiếu được địa chỉ cũ."""
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            address = self._get_owned(actor.user_id, address_id)
            address.IsDeleted = True
            address.IsDefault = False

    def _get_owned(self, user_id: uuid.UUID, address_id: uuid.UUID) -> Address:
        address = self.addresses.get_by_id_and_user(address_id, user_id)
        if address is None or address.IsDeleted:
            raise NotFoundError("Không tìm thấy địa chỉ", code="address_not_found")
        return address

    def _clear_default(self, user_id: uuid.UUID, keep: Address | None = None) -> None:
        """Mỗi người dùng chỉ có một địa chỉ mặc định."""
        for other in self.addresses.list_default_by_user(user_id):
            if other is not keep:
                other.IsDefault = False


class NotificationService(BaseService):
    """Thông báo của người dùng. ``notify`` dùng cho Service khác, tham gia transaction của use case gọi nó."""

    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.notifications = NotificationRepository(session)

    def list_notifications(
        self, actor: Actor, *, is_read: bool | None = None, page: int = 1, page_size: int = 20
    ) -> PageResponse[NotificationResponse]:
        """Thông báo của chính người dùng đăng nhập."""
        require_role(actor, *ANY_ROLE)
        user_id = actor.user_id
        offset, limit = self._page_args(page, page_size)
        items = self.notifications.list_by_user(user_id, is_read=is_read, offset=offset, limit=limit)
        return PageResponse[NotificationResponse](
            Items=[NotificationResponse.model_validate(n) for n in items],
            Total=self.notifications.count_by_user(user_id, is_read=is_read),
            Page=page,
            PageSize=page_size,
        )

    def count_unread(self, actor: Actor) -> int:
        require_role(actor, *ANY_ROLE)
        return self.notifications.count_by_user(actor.user_id, is_read=False)

    def mark_read(self, actor: Actor, notification_id: uuid.UUID) -> NotificationResponse:
        require_role(actor, *ANY_ROLE)
        with self.transaction():
            notification = self.notifications.get_one(
                Notification.NotificationId == notification_id, Notification.UserId == actor.user_id
            )
            if notification is None:
                raise NotFoundError("Không tìm thấy thông báo", code="notification_not_found")
            if not notification.IsRead:
                notification.IsRead = True
                notification.ReadAt = self.now()
            self.notifications.flush()
            return NotificationResponse.model_validate(notification)

    def mark_all_read(self, actor: Actor) -> int:
        require_role(actor, *ANY_ROLE)
        with self.transaction():
            unread = self.notifications.list_by_user(actor.user_id, is_read=False)
            now = self.now()
            for notification in unread:
                notification.IsRead = True
                notification.ReadAt = now
            return len(unread)

    def notify(
        self,
        user_id: uuid.UUID,
        *,
        title: str,
        content: str,
        notification_type: str,
        action_url: str | None = None,
        reference_type: str | None = None,
        reference_id: uuid.UUID | None = None,
    ) -> Notification:
        """Tạo thông báo cho ``user_id`` (người nhận) trong transaction của use case gọi nó (không gọi từ Router)."""
        self.require_enclosing_use_case()
        with self.transaction():
            return self.notifications.create(
                {
                    "UserId": user_id,
                    "Title": title,
                    "Content": content,
                    "NotificationType": notification_type,
                    "ActionUrl": action_url,
                    "ReferenceType": reference_type,
                    "ReferenceId": reference_id,
                }
            )


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(1, math.ceil((moment - now).total_seconds()))
