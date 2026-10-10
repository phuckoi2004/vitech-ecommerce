"""Actor: người thực hiện một use case (danh tính + vai trò).

- Router xác thực JWT và trạng thái tài khoản (tồn tại, chưa xóa, không bị khóa) rồi mới dựng Actor
  từ dữ liệu đã xác thực. Không dựng Actor từ body/query của request: UserId/Role do client tự gửi
  không bao giờ là nguồn phân quyền.
- Actor không phải Pydantic schema nên không thể bị deserialize trực tiếp từ dữ liệu client.
- Service nhận Actor và tự kiểm tra quyền nghiệp vụ bằng ``require_role`` (docs/business-requirements.md mục 2).
- Role chỉ gồm Customer, Staff, Admin (CHECK "Users"."Role"); không có vai trò nào khác.
"""

import uuid
from dataclasses import dataclass

from app.models.user import USER_ROLES

from .exceptions import PermissionDeniedError

CUSTOMER = "Customer"
STAFF = "Staff"
ADMIN = "Admin"

# Admin kế thừa chức năng của Staff (business-requirements mục 2).
STAFF_OR_ADMIN = (STAFF, ADMIN)
ADMIN_ONLY = (ADMIN,)
CUSTOMER_ONLY = (CUSTOMER,)
# Chức năng chung của mọi tài khoản đã đăng nhập (hồ sơ, đổi mật khẩu, thông báo của chính mình).
ANY_ROLE = tuple(USER_ROLES)


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    role: str

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, uuid.UUID):
            raise TypeError("Actor.user_id phải là uuid.UUID")
        if self.role not in USER_ROLES:
            raise ValueError(f"Role không hợp lệ: {self.role!r}. Giá trị hợp lệ: {', '.join(USER_ROLES)}")


def has_role(actor: Actor | None, *roles: str) -> bool:
    """True khi đã đăng nhập và thuộc một trong các role (dùng cho use case công khai có thêm quyền nội bộ)."""
    if actor is None:
        return False
    if not isinstance(actor, Actor):
        raise TypeError("Use case cần Actor do Router dựng từ thông tin đã xác thực")
    return actor.role in roles


def require_role(actor: Actor | None, *roles: str) -> None:
    """Raise PermissionDeniedError nếu chưa đăng nhập (None) hoặc Actor không thuộc role được phép.

    Truyền thứ khác Actor (UUID, dict, ...) là lỗi lập trình → TypeError.
    """
    if actor is None:
        raise PermissionDeniedError("Cần đăng nhập để thực hiện thao tác này", code="authentication_required")
    if not isinstance(actor, Actor):
        raise TypeError("Use case cần Actor do Router dựng từ thông tin đã xác thực")
    if actor.role not in roles:
        raise PermissionDeniedError("Bạn không có quyền thực hiện thao tác này", code="permission_denied")
