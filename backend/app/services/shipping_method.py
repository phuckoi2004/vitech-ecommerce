"""ShippingMethodService (đợt 5.10): quản lý phương thức vận chuyển.

Nguồn: docs/business-requirements.md mục 2 (Admin quản lý dữ liệu hệ thống), mục 6 (khách chọn phương thức vận chuyển
khi đặt hàng; phí tính ở server) và docs/database-schema.md mục 3.14.
- Chỉ Admin thêm/sửa/xóa. Khách (không cần đăng nhập) chỉ xem phương thức đang hoạt động; xem tất cả cần Staff/Admin
  (cùng quy ước với phương thức thanh toán).
- Client chỉ gửi Code, Name, BaseFee, EstimatedDays, IsActive (Schema extra=forbid; Service chặn cả khi Schema bị bỏ qua).
  ShippingMethodId do database sinh. Code/Name bỏ khoảng trắng đầu/cuối và không được rỗng; Code duy nhất, phân biệt
  hoa thường như UQ_ShippingMethods_Code. BaseFee >= 0, đúng đơn vị xu. EstimatedDays là số nguyên trong khoảng
  0..30 (0 = giao trong ngày; quyết định đợt 5.13).
- Đổi BaseFee chỉ áp dụng cho đơn đặt sau: Orders.ShippingFee đã chụp lúc đặt hàng không đổi.
- Ngừng sử dụng bằng IsActive = false: đơn mới không chọn được (OrderService kiểm tra), đơn cũ giữ tham chiếu.
- Xóa chỉ khi chưa có đơn hàng nào tham chiếu (Orders.ShippingMethodId, FK RESTRICT); đã dùng → lỗi, dùng IsActive.
  Khóa dòng phương thức trước khi kiểm tra (đơn đang tạo đồng thời giữ khóa khóa ngoại trên dòng này trong PostgreSQL;
  chưa kiểm chứng trên database thật).
"""

import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.repositories import OrderRepository, ShippingMethodRepository
from app.schemas import ShippingMethodCreate, ShippingMethodResponse, ShippingMethodUpdate

from .actor import ADMIN_ONLY, STAFF_OR_ADMIN, Actor, has_role, require_role
from .base import BaseService, utc_now
from .exceptions import BusinessRuleError, ConflictError, NotFoundError
from .service_request import required_text

EDITABLE_FIELDS = frozenset({"Code", "Name", "BaseFee", "EstimatedDays", "IsActive"})
REQUIRED_FIELDS = ("Code", "Name", "BaseFee", "EstimatedDays")
_CENT = Decimal("0.01")
MAX_ESTIMATED_DAYS = 30


class ShippingMethodService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.methods = ShippingMethodRepository(session)
        self.orders = OrderRepository(session)

    def list_shipping_methods(
        self, *, actor: Actor | None = None, active_only: bool = False
    ) -> list[ShippingMethodResponse]:
        """Khách (không cần đăng nhập) chỉ xem phương thức đang hoạt động; xem tất cả cần Staff/Admin."""
        if not active_only:
            require_role(actor, *STAFF_OR_ADMIN)
        items = self.methods.list_methods(is_active=True if active_only else None)
        return [ShippingMethodResponse.model_validate(m) for m in items]

    def get_shipping_method(self, shipping_method_id: uuid.UUID, *, actor: Actor | None = None) -> ShippingMethodResponse:
        method = self.methods.get_by_id(shipping_method_id)
        if method is None or (not method.IsActive and not has_role(actor, *STAFF_OR_ADMIN)):
            raise NotFoundError("Không tìm thấy phương thức vận chuyển", code="shipping_method_not_found")
        return ShippingMethodResponse.model_validate(method)

    def create_shipping_method(self, actor: Actor, data: ShippingMethodCreate) -> ShippingMethodResponse:
        require_role(actor, *ADMIN_ONLY)
        values = _clean_values(data, creating=True)
        with self.transaction():
            if self.methods.exists_by_code(values["Code"]):
                raise ConflictError("Mã phương thức vận chuyển đã tồn tại", code="shipping_method_code_exists")
            method = self.methods.create(values)
            self.methods.flush()
            return ShippingMethodResponse.model_validate(method)

    def update_shipping_method(
        self, actor: Actor, shipping_method_id: uuid.UUID, data: ShippingMethodUpdate
    ) -> ShippingMethodResponse:
        """Cập nhật (PATCH); ngừng sử dụng bằng IsActive = false. Đơn hàng cũ giữ ShippingFee đã chụp."""
        require_role(actor, *ADMIN_ONLY)
        values = _clean_values(data, creating=False)
        with self.transaction():
            method = self.methods.get_by_id(shipping_method_id)
            if method is None:
                raise NotFoundError("Không tìm thấy phương thức vận chuyển", code="shipping_method_not_found")
            if "Code" in values and self.methods.exists_by_code(values["Code"], shipping_method_id):
                raise ConflictError("Mã phương thức vận chuyển đã tồn tại", code="shipping_method_code_exists")
            self.methods.update(method, values)
            self.methods.flush()
            return ShippingMethodResponse.model_validate(method)

    def delete_shipping_method(self, actor: Actor, shipping_method_id: uuid.UUID) -> None:
        """Xóa phương thức chưa được đơn hàng nào tham chiếu; đã dùng thì chỉ ngừng sử dụng (IsActive = false)."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            method = self.methods.get_by_id_for_update(shipping_method_id)
            if method is None:
                raise NotFoundError("Không tìm thấy phương thức vận chuyển", code="shipping_method_not_found")
            if self.orders.exists_by_shipping_method(shipping_method_id):
                raise BusinessRuleError(
                    "Phương thức vận chuyển đã được dùng trong đơn hàng; ngừng sử dụng bằng IsActive = false",
                    code="shipping_method_in_use",
                )
            self.methods.delete(method)


def _clean_values(data: Any, *, creating: bool) -> dict[str, Any]:
    """Chỉ nhận các trường cho phép; kiểm tra lại giá trị (kể cả khi Schema bị bỏ qua)."""
    values = dict(data.model_dump(exclude_unset=True))
    not_allowed = sorted(set(values) - EDITABLE_FIELDS)
    if not_allowed:
        raise BusinessRuleError(f"Không được gửi các trường: {not_allowed}", code="shipping_method_field_not_allowed")
    if creating:
        missing = [field for field in REQUIRED_FIELDS if values.get(field) is None]
        if missing:
            raise BusinessRuleError(f"Thiếu thông tin: {missing}", code="shipping_method_field_required")
    if "Code" in values:
        values["Code"] = required_text(values["Code"], code="shipping_method_code_required",
                                       message="Phải nhập mã phương thức vận chuyển")
    if "Name" in values:
        values["Name"] = required_text(values["Name"], code="shipping_method_name_required",
                                       message="Phải nhập tên phương thức vận chuyển")
    if "BaseFee" in values:
        fee = values["BaseFee"]
        if not isinstance(fee, Decimal) or fee < 0 or fee != fee.quantize(_CENT):
            raise BusinessRuleError("Phí vận chuyển phải >= 0 và đúng đơn vị xu", code="invalid_shipping_fee")
    if "EstimatedDays" in values:
        days = values["EstimatedDays"]
        if not isinstance(days, int) or isinstance(days, bool) or days < 0 or days > MAX_ESTIMATED_DAYS:
            raise BusinessRuleError(f"Số ngày giao dự kiến phải là số nguyên từ 0 đến {MAX_ESTIMATED_DAYS}",
                                    code="invalid_estimated_days")
    if "IsActive" in values and not isinstance(values["IsActive"], bool):
        raise BusinessRuleError("IsActive phải là true/false", code="invalid_is_active")
    return values
