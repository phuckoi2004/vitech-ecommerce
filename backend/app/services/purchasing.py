"""Purchasing services: nhà cung cấp, phiếu nhập hàng và nhận hàng.

Nguồn nghiệp vụ: docs/business-requirements.md mục 1, 2, 8, 17 và quyết định đã chốt:
- Quyền (Actor do Router dựng từ JWT đã xác thực): Staff/Admin lập, sửa, gửi lại, hủy phiếu và nhận hàng
  (business-requirements 8.2: cả Staff và Admin được lập phiếu); chỉ Admin duyệt/từ chối.
- Phiếu Staff lập → Pending (chờ duyệt, thông báo Admin) → một Admin KHÁC người lập duyệt (Approved) hoặc
  từ chối (Rejected, bắt buộc lý do không rỗng); phiếu Rejected được sửa và gửi lại (→ Pending).
- Phiếu Admin lập không cần bước duyệt: tạo ở trạng thái Approved (DecidedByUserId/DecidedAt để trống vì không
  có quyết định duyệt), nhận hàng được ngay; muốn sửa thì hủy và lập lại (chỉ sửa ở Pending/Rejected).
- Người lập không được ra quyết định (duyệt/từ chối) trên phiếu của chính mình.
- Tồn kho chỉ tăng khi nhận hàng, theo số lượng thực nhận (không theo số lượng đặt, không tăng khi duyệt).
- Nhận hàng một phần/nhiều lần: Approved/Receiving → Receiving; nhận đủ mọi dòng → Completed.
  Không nhận cho phiếu Pending/Rejected/Cancelled/Completed/Closed. ReceivedQuantity <= OrderedQuantity.
  Mỗi lần nhận ghi lịch sử PurchaseReceipts/PurchaseReceiptItems (người nhận, thời điểm, số lượng, đơn giá).
- Nhà cung cấp giao thiếu: chỉ Admin đóng phiếu đang Receiving (còn thiếu) với lý do bắt buộc → Closed.
  Không coi phần thiếu là đã nhận, không cộng tồn; giữ nguyên số đặt/đã nhận (số thiếu = đặt − đã nhận).
  Phiếu Closed không nhận thêm hàng (chưa có nghiệp vụ mở lại).
- Nhận hàng: khóa phiếu (FOR UPDATE) → InventoryService khóa biến thể theo thứ tự id, tính giá vốn bình quân
  gia quyền, cộng tồn, ghi Serial/IMEI (biến thể IsSerialTracked) trong cùng transaction; một dòng lỗi thì
  rollback toàn bộ. Không nhận khi biến thể còn tồn mà chưa có giá vốn đầu kỳ.
- Nhà cung cấp: Admin tạo/sửa/xóa; Staff/Admin xem (để lập phiếu).
"""

import secrets
import string
import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import PurchaseOrder, PurchaseOrderItem, Supplier
from app.repositories import (
    ProductVariantRepository,
    PurchaseOrderItemRepository,
    PurchaseOrderRepository,
    PurchaseReceiptItemRepository,
    PurchaseReceiptRepository,
    SupplierRepository,
    UserRepository,
    WarrantyRequestRepository,
)
from app.schemas import (
    PageResponse,
    PurchaseOrderCreate,
    PurchaseOrderDecision,
    PurchaseOrderDetailResponse,
    PurchaseOrderItemCreate,
    PurchaseOrderItemUpdate,
    PurchaseOrderReceive,
    PurchaseOrderResponse,
    PurchaseOrderUpdate,
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
    PurchaseOrderClose,
    PurchaseReceiptResponse,
)

from .actor import ADMIN, ADMIN_ONLY, STAFF_OR_ADMIN, Actor, require_role
from .base import BaseService, utc_now
from .exceptions import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from .inventory import InventoryService, ReceiptLine
from .promotion import money
from .user import NotificationService

PO_PENDING = "Pending"
PO_APPROVED = "Approved"
PO_REJECTED = "Rejected"
PO_RECEIVING = "Receiving"
PO_COMPLETED = "Completed"
PO_CANCELLED = "Cancelled"
PO_CLOSED = "Closed"

EDITABLE_STATUSES = (PO_PENDING, PO_REJECTED)
RECEIVABLE_STATUSES = (PO_APPROVED, PO_RECEIVING)
CANCELLABLE_STATUSES = (PO_PENDING, PO_REJECTED, PO_APPROVED)
ADMIN_ROLE = ADMIN
PO_NOTIFICATION_TYPE = "PurchaseOrder"


class SupplierService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.suppliers = SupplierRepository(session)
        self.purchase_orders = PurchaseOrderRepository(session)
        self.warranty_requests = WarrantyRequestRepository(session)

    def list_suppliers(
        self, actor: Actor, *, active_only: bool = False, page: int = 1, page_size: int = 20
    ) -> PageResponse[SupplierResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        offset, limit = self._page_args(page, page_size)
        is_active = True if active_only else None
        items = self.suppliers.list_suppliers(is_active=is_active, offset=offset, limit=limit)
        return PageResponse[SupplierResponse](
            Items=[SupplierResponse.model_validate(x) for x in items],
            Total=self.suppliers.count_suppliers(is_active=is_active),
            Page=page,
            PageSize=page_size,
        )

    def get_supplier(self, actor: Actor, supplier_id: uuid.UUID) -> SupplierResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        return SupplierResponse.model_validate(self._get(supplier_id))

    def create_supplier(self, actor: Actor, data: SupplierCreate) -> SupplierResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            values = data.model_dump(exclude_unset=True)
            if self.suppliers.exists_by_code(values["SupplierCode"]):
                raise ConflictError("Mã nhà cung cấp đã tồn tại", code="supplier_code_exists")
            supplier = self.suppliers.create(values)
            self.suppliers.flush()
            return SupplierResponse.model_validate(supplier)

    def update_supplier(self, actor: Actor, supplier_id: uuid.UUID, data: SupplierUpdate) -> SupplierResponse:
        """Cập nhật; ngừng hợp tác bằng IsActive = false."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            supplier = self._get(supplier_id)
            values = data.model_dump(exclude_unset=True)
            if "SupplierCode" in values and self.suppliers.exists_by_code(values["SupplierCode"], supplier_id):
                raise ConflictError("Mã nhà cung cấp đã tồn tại", code="supplier_code_exists")
            self.suppliers.update(supplier, values)
            self.suppliers.flush()
            return SupplierResponse.model_validate(supplier)

    def delete_supplier(self, actor: Actor, supplier_id: uuid.UUID) -> None:
        """Xóa nhà cung cấp chưa có phiếu nhập/yêu cầu bảo hành tham chiếu (FK RESTRICT)."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            supplier = self._get(supplier_id)
            in_use = self.purchase_orders.count_purchase_orders(supplier_id=supplier_id) > 0 or (
                self.warranty_requests.count_requests(supplier_id=supplier_id) > 0
            )
            if in_use:
                raise BusinessRuleError(
                    "Nhà cung cấp đang được sử dụng; hãy ngừng hoạt động (IsActive = false)", code="supplier_in_use"
                )
            self.suppliers.delete(supplier)

    def _get(self, supplier_id: uuid.UUID) -> Supplier:
        supplier = self.suppliers.get_by_id(supplier_id)
        if supplier is None:
            raise NotFoundError("Không tìm thấy nhà cung cấp", code="supplier_not_found")
        return supplier


class PurchaseOrderService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.purchase_orders = PurchaseOrderRepository(session)
        self.items = PurchaseOrderItemRepository(session)
        self.receipts = PurchaseReceiptRepository(session)
        self.receipt_items = PurchaseReceiptItemRepository(session)
        self.suppliers = SupplierRepository(session)
        self.variants = ProductVariantRepository(session)
        self.users = UserRepository(session)
        self.inventory = InventoryService(session, clock=clock)
        self.notifications = NotificationService(session, clock=clock)

    # ------------------------------------------------------------------ xem / tìm

    def list_purchase_orders(
        self,
        actor: Actor,
        *,
        code: str | None = None,
        status: str | None = None,
        supplier_id: uuid.UUID | None = None,
        created_by_user_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[PurchaseOrderResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        offset, limit = self._page_args(page, page_size)
        filters = {
            "status": status,
            "supplier_id": supplier_id,
            "created_by_user_id": created_by_user_id,
            "code_contains": code.strip() if code and code.strip() else None,
        }
        items = self.purchase_orders.list_purchase_orders(**filters, offset=offset, limit=limit)
        return PageResponse[PurchaseOrderResponse](
            Items=[PurchaseOrderResponse.model_validate(x) for x in items],
            Total=self.purchase_orders.count_purchase_orders(**filters),
            Page=page,
            PageSize=page_size,
        )

    def get_purchase_order(self, actor: Actor, purchase_order_id: uuid.UUID) -> PurchaseOrderDetailResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        po = self.purchase_orders.get_detail(purchase_order_id)
        if po is None:
            raise NotFoundError("Không tìm thấy phiếu nhập", code="purchase_order_not_found")
        return PurchaseOrderDetailResponse.model_validate(po)

    # ------------------------------------------------------------------ lập / sửa / gửi lại

    def create_purchase_order(self, actor: Actor, data: PurchaseOrderCreate) -> PurchaseOrderDetailResponse:
        """Staff/Admin lập phiếu nhập. Người lập (CreatedByUserId) luôn là Actor, không nhận từ dữ liệu client.

        - Staff lập: Pending (chờ Admin khác duyệt), thông báo Admin.
        - Admin lập: Approved ngay (không cần bước duyệt), nhận hàng được.
        """
        require_role(actor, *STAFF_OR_ADMIN)
        created_by_admin = actor.role == ADMIN
        with self.transaction():
            if not data.Items:
                raise BusinessRuleError("Phiếu nhập phải có ít nhất một sản phẩm", code="purchase_order_empty")
            self._ensure_supplier(data.SupplierId)
            self._ensure_distinct_variants(item.ProductVariantId for item in data.Items)
            po = self.purchase_orders.create(
                {
                    "PurchaseOrderCode": self._new_code(),
                    "SupplierId": data.SupplierId,
                    "CreatedByUserId": actor.user_id,
                    "TotalAmount": Decimal("0"),
                    "Status": PO_APPROVED if created_by_admin else PO_PENDING,
                    "Note": data.Note,
                }
            )
            self.purchase_orders.flush()
            for item in data.Items:
                self._add_item(po, item)
            self._recalculate_total(po)
            if not created_by_admin:
                self._notify_admins(
                    po, "Phiếu nhập chờ duyệt", f"Phiếu nhập {po.PurchaseOrderCode} đang chờ phê duyệt.",
                    exclude=actor.user_id,
                )
            return self._detail(po)

    def update_purchase_order(
        self, actor: Actor, purchase_order_id: uuid.UUID, data: PurchaseOrderUpdate
    ) -> PurchaseOrderDetailResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            po = self._lock_editable(purchase_order_id)
            values = data.model_dump(exclude_unset=True)
            if "SupplierId" in values:
                self._ensure_supplier(values["SupplierId"])
            self.purchase_orders.update(po, values)
            return self._detail(po)

    def add_item(
        self, actor: Actor, purchase_order_id: uuid.UUID, data: PurchaseOrderItemCreate
    ) -> PurchaseOrderDetailResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            po = self._lock_editable(purchase_order_id)
            existing = [i.ProductVariantId for i in self.items.list_by_purchase_order(po.PurchaseOrderId)]
            self._ensure_distinct_variants([*existing, data.ProductVariantId])
            self._add_item(po, data)
            self._recalculate_total(po)
            return self._detail(po)

    def update_item(
        self,
        actor: Actor,
        purchase_order_id: uuid.UUID,
        purchase_order_item_id: uuid.UUID,
        data: PurchaseOrderItemUpdate,
    ) -> PurchaseOrderDetailResponse:
        """Sửa số lượng đặt / đơn giá / ghi chú khi phiếu còn Pending/Rejected. ReceivedQuantity chỉ đổi qua nhận hàng."""
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            po = self._lock_editable(purchase_order_id)
            item = self._get_item(po, purchase_order_item_id)
            values = data.model_dump(exclude_unset=True)
            if "ReceivedQuantity" in values:
                raise BusinessRuleError("Số lượng thực nhận chỉ cập nhật khi nhận hàng", code="received_quantity_not_editable")
            self._check_line_values(values.get("OrderedQuantity", item.OrderedQuantity), values.get("UnitPrice", item.UnitPrice))
            self.items.update(item, values)
            item.LineTotal = money(item.UnitPrice * item.OrderedQuantity)
            self._recalculate_total(po)
            return self._detail(po)

    def remove_item(
        self, actor: Actor, purchase_order_id: uuid.UUID, purchase_order_item_id: uuid.UUID
    ) -> PurchaseOrderDetailResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            po = self._lock_editable(purchase_order_id)
            item = self._get_item(po, purchase_order_item_id)
            if len(self.items.list_by_purchase_order(po.PurchaseOrderId)) <= 1:
                raise BusinessRuleError("Phiếu nhập phải có ít nhất một sản phẩm", code="purchase_order_empty")
            self.items.delete(item)
            self.items.flush()
            self._recalculate_total(po)
            return self._detail(po)

    def resubmit_purchase_order(self, actor: Actor, purchase_order_id: uuid.UUID) -> PurchaseOrderDetailResponse:
        """Gửi lại phiếu đã bị từ chối: Rejected → Pending (xóa kết quả duyệt trước), thông báo Admin."""
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            po = self._lock(purchase_order_id)
            if po.Status != PO_REJECTED:
                raise BusinessRuleError("Chỉ gửi lại phiếu đã bị từ chối", code="invalid_purchase_order_status")
            po.Status = PO_PENDING
            po.DecidedByUserId = None
            po.DecidedAt = None
            po.RejectReason = None
            self._notify_admins(
                po, "Phiếu nhập gửi lại", f"Phiếu nhập {po.PurchaseOrderCode} được gửi lại để duyệt.",
                exclude=po.CreatedByUserId,
            )
            return self._detail(po)

    # ------------------------------------------------------------------ duyệt / hủy

    def decide_purchase_order(
        self, actor: Actor, purchase_order_id: uuid.UUID, data: PurchaseOrderDecision
    ) -> PurchaseOrderDetailResponse:
        """Admin (khác người lập) phê duyệt hoặc từ chối phiếu Pending do Staff lập. Duyệt không làm thay đổi tồn kho.

        Từ chối bắt buộc có lý do không rỗng. Người lập không được duyệt/từ chối phiếu của mình.
        """
        require_role(actor, *ADMIN_ONLY)
        if data.Status not in (PO_APPROVED, PO_REJECTED):
            raise BusinessRuleError(f"Quyết định không hợp lệ: {data.Status}", code="invalid_decision")
        reject_reason = (data.RejectReason or "").strip() or None
        if data.Status == PO_REJECTED and reject_reason is None:
            raise BusinessRuleError("Từ chối phiếu nhập phải ghi lý do", code="reject_reason_required")
        if data.Status == PO_APPROVED and data.RejectReason is not None:
            raise BusinessRuleError("RejectReason chỉ dùng khi từ chối", code="reject_reason_not_allowed")
        with self.transaction():
            po = self._lock(purchase_order_id)
            if po.Status != PO_PENDING:
                raise BusinessRuleError("Chỉ duyệt phiếu đang chờ duyệt", code="invalid_purchase_order_status")
            if po.CreatedByUserId == actor.user_id:
                raise PermissionDeniedError(
                    "Người lập phiếu không được tự duyệt/từ chối phiếu của mình", code="self_approval_forbidden"
                )
            po.Status = data.Status
            po.DecidedByUserId = actor.user_id
            po.DecidedAt = self.now()
            po.RejectReason = reject_reason
            if data.Status == PO_APPROVED:
                title, content = "Phiếu nhập được duyệt", f"Phiếu nhập {po.PurchaseOrderCode} đã được phê duyệt."
            else:
                title, content = "Phiếu nhập bị từ chối", f"Phiếu nhập {po.PurchaseOrderCode} bị từ chối."
            self._notify(po.CreatedByUserId, po, title, content)
            return self._detail(po)

    def cancel_purchase_order(self, actor: Actor, purchase_order_id: uuid.UUID) -> PurchaseOrderDetailResponse:
        """Hủy phiếu Pending/Rejected/Approved chưa nhận hàng."""
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            po = self._lock(purchase_order_id)
            if po.Status not in CANCELLABLE_STATUSES:
                raise BusinessRuleError(f"Không thể hủy phiếu ở trạng thái {po.Status}", code="invalid_purchase_order_status")
            if any(i.ReceivedQuantity > 0 for i in self.items.list_by_purchase_order(po.PurchaseOrderId)):
                raise BusinessRuleError("Phiếu đã nhận hàng, không thể hủy", code="purchase_order_has_receipts")
            po.Status = PO_CANCELLED
            return self._detail(po)

    # ------------------------------------------------------------------ nhận hàng

    def receive_items(
        self, actor: Actor, purchase_order_id: uuid.UUID, data: PurchaseOrderReceive
    ) -> PurchaseOrderDetailResponse:
        """Nhận hàng theo số lượng thực nhận (có thể một phần, nhiều lần).

        Trong một transaction: khóa phiếu → kiểm tra từng dòng (ReceivedQuantity mới <= OrderedQuantity) →
        cập nhật ReceivedQuantity → InventoryService (khóa biến thể theo thứ tự id, giá vốn bình quân gia quyền,
        tăng StockQuantity, ghi Serial/IMEI) → ghi lịch sử nhận hàng (PurchaseReceipts) → Receiving/Completed.
        Một dòng không hợp lệ thì không dòng nào được nhận. Dòng trùng trong cùng yêu cầu được cộng dồn
        (cả số lượng lẫn Serial/IMEI). Phiếu Closed/Completed không nhận thêm.
        """
        require_role(actor, *STAFF_OR_ADMIN)
        if not data.Items:
            raise BusinessRuleError("Phải có ít nhất một dòng nhận hàng", code="receive_items_empty")
        with self.transaction():
            po = self._lock(purchase_order_id)
            if po.Status not in RECEIVABLE_STATUSES:
                raise BusinessRuleError(
                    f"Không thể nhận hàng cho phiếu ở trạng thái {po.Status}", code="purchase_order_not_receivable"
                )
            items = {i.PurchaseOrderItemId: i for i in self.items.list_by_purchase_order(po.PurchaseOrderId)}
            requested: dict[uuid.UUID, int] = {}
            serials: dict[uuid.UUID, list[str]] = {}
            for line in data.Items:
                if line.PurchaseOrderItemId not in items:
                    raise NotFoundError("Không tìm thấy dòng phiếu nhập", code="purchase_order_item_not_found")
                if line.Quantity <= 0:
                    # Schema đã chặn; kiểm tra lại để Service không phụ thuộc hoàn toàn vào Router.
                    raise BusinessRuleError("Số lượng nhận phải lớn hơn 0", code="invalid_receive_quantity")
                requested[line.PurchaseOrderItemId] = requested.get(line.PurchaseOrderItemId, 0) + line.Quantity
                serials.setdefault(line.PurchaseOrderItemId, []).extend(line.SerialNumbers or [])
            over = [
                str(item_id)
                for item_id, quantity in requested.items()
                if items[item_id].ReceivedQuantity + quantity > items[item_id].OrderedQuantity
            ]
            if over:
                raise BusinessRuleError(f"Số lượng nhận vượt số lượng còn lại: {sorted(over)}", code="receive_exceeds_ordered")

            # Cập nhật kho/giá vốn TRƯỚC khi cộng ReceivedQuantity: kiểm tra "đã từng nhận hàng" (giá vốn hợp lệ)
            # không được tính chính lần nhận này. Cùng transaction nên lỗi ở bất kỳ bước nào đều rollback toàn bộ.
            self.inventory.receive_purchase_lines(
                [
                    ReceiptLine(items[item_id].ProductVariantId, quantity, items[item_id].UnitPrice, serials[item_id])
                    for item_id, quantity in requested.items()
                ]
            )
            for item_id, quantity in requested.items():
                items[item_id].ReceivedQuantity += quantity
            receipt = self.receipts.create(
                {
                    "PurchaseOrderId": po.PurchaseOrderId,
                    "ReceivedByUserId": actor.user_id,
                    "ReceivedAt": self.now(),
                    "Note": data.Note,
                }
            )
            self.receipts.flush()
            for item_id in sorted(requested):
                self.receipt_items.create(
                    {
                        "PurchaseReceiptId": receipt.PurchaseReceiptId,
                        "PurchaseOrderItemId": item_id,
                        "Quantity": requested[item_id],
                        "UnitPrice": items[item_id].UnitPrice,
                    }
                )

            fully_received = all(i.ReceivedQuantity == i.OrderedQuantity for i in items.values())
            po.Status = PO_COMPLETED if fully_received else PO_RECEIVING
            return self._detail(po)

    def close_purchase_order(
        self, actor: Actor, purchase_order_id: uuid.UUID, data: PurchaseOrderClose
    ) -> PurchaseOrderDetailResponse:
        """Admin đóng phiếu còn thiếu hàng (nhà cung cấp giao thiếu, không giao tiếp): Receiving → Closed.

        Chỉ phiếu đã nhận một phần (Receiving, còn thiếu); lý do bắt buộc. Không đổi số đặt/đã nhận, không cộng
        tồn, không coi phần thiếu là đã nhận. Phiếu chưa nhận gì: dùng hủy phiếu. Sau khi đóng không nhận thêm.
        """
        require_role(actor, *ADMIN_ONLY)
        reason = (data.Reason or "").strip()
        if not reason:
            raise BusinessRuleError("Phải ghi lý do đóng phiếu", code="close_reason_required")
        with self.transaction():
            po = self._lock(purchase_order_id)
            if po.Status != PO_RECEIVING:
                raise BusinessRuleError(
                    f"Chỉ đóng phiếu đang nhận hàng còn thiếu (hiện tại: {po.Status})", code="purchase_order_not_closable"
                )
            items = self.items.list_by_purchase_order(po.PurchaseOrderId)
            if not any(i.ReceivedQuantity < i.OrderedQuantity for i in items):
                raise BusinessRuleError("Phiếu không còn thiếu hàng", code="purchase_order_not_closable")
            po.Status = PO_CLOSED
            po.ClosedByUserId = actor.user_id
            po.ClosedAt = self.now()
            po.CloseReason = reason
            missing = sum(i.OrderedQuantity - i.ReceivedQuantity for i in items)
            if po.CreatedByUserId != actor.user_id:
                self._notify(
                    po.CreatedByUserId, po, "Phiếu nhập đã đóng",
                    f"Phiếu nhập {po.PurchaseOrderCode} đã đóng khi còn thiếu {missing} sản phẩm. Lý do: {reason}",
                )
            return self._detail(po)

    def list_receipts(self, actor: Actor, purchase_order_id: uuid.UUID) -> list[PurchaseReceiptResponse]:
        """Staff/Admin xem lịch sử các lần nhận hàng của phiếu (lần nhận trước khi có bảng lịch sử không có ở đây)."""
        require_role(actor, *STAFF_OR_ADMIN)
        if self.purchase_orders.get_by_id(purchase_order_id) is None:
            raise NotFoundError("Không tìm thấy phiếu nhập", code="purchase_order_not_found")
        return [PurchaseReceiptResponse.model_validate(r) for r in self.receipts.list_by_purchase_order(purchase_order_id)]

    # ------------------------------------------------------------------ helpers

    def _lock(self, purchase_order_id: uuid.UUID) -> PurchaseOrder:
        po = self.purchase_orders.get_by_id_for_update(purchase_order_id)
        if po is None:
            raise NotFoundError("Không tìm thấy phiếu nhập", code="purchase_order_not_found")
        return po

    def _lock_editable(self, purchase_order_id: uuid.UUID) -> PurchaseOrder:
        po = self._lock(purchase_order_id)
        if po.Status not in EDITABLE_STATUSES:
            raise BusinessRuleError(
                f"Chỉ sửa phiếu đang chờ duyệt hoặc bị từ chối (hiện tại: {po.Status})", code="purchase_order_not_editable"
            )
        return po

    def _get_item(self, po: PurchaseOrder, purchase_order_item_id: uuid.UUID) -> PurchaseOrderItem:
        item = self.items.get_by_id_and_purchase_order(purchase_order_item_id, po.PurchaseOrderId)
        if item is None:
            raise NotFoundError("Không tìm thấy dòng phiếu nhập", code="purchase_order_item_not_found")
        return item

    def _ensure_supplier(self, supplier_id: uuid.UUID) -> None:
        supplier = self.suppliers.get_by_id(supplier_id)
        if supplier is None or not supplier.IsActive:
            raise NotFoundError("Nhà cung cấp không hợp lệ", code="supplier_not_available")

    @staticmethod
    def _ensure_distinct_variants(variant_ids) -> None:
        seen: set[uuid.UUID] = set()
        for variant_id in variant_ids:
            if variant_id in seen:
                raise BusinessRuleError("Một biến thể chỉ xuất hiện một lần trong phiếu nhập", code="duplicate_variant")
            seen.add(variant_id)

    @staticmethod
    def _check_line_values(ordered_quantity: int, unit_price: Decimal) -> None:
        """OrderedQuantity > 0, UnitPrice >= 0 (CHECK của PurchaseOrderItems); không phụ thuộc vào validation của Router."""
        if ordered_quantity is None or ordered_quantity <= 0:
            raise BusinessRuleError("Số lượng đặt phải lớn hơn 0", code="invalid_ordered_quantity")
        if unit_price is None or unit_price < 0:
            raise BusinessRuleError("Đơn giá nhập không được âm", code="invalid_unit_price")

    def _add_item(self, po: PurchaseOrder, data: PurchaseOrderItemCreate) -> None:
        self._check_line_values(data.OrderedQuantity, data.UnitPrice)
        variant = self.variants.get_by_id(data.ProductVariantId)
        if variant is None or variant.IsDeleted:
            raise NotFoundError("Không tìm thấy biến thể", code="variant_not_found")
        self.items.create(
            {
                "PurchaseOrderId": po.PurchaseOrderId,
                "ProductVariantId": data.ProductVariantId,
                "OrderedQuantity": data.OrderedQuantity,
                "ReceivedQuantity": 0,
                "UnitPrice": data.UnitPrice,
                "LineTotal": money(data.UnitPrice * data.OrderedQuantity),
                "Note": data.Note,
            }
        )

    def _recalculate_total(self, po: PurchaseOrder) -> None:
        """TotalAmount = Σ LineTotal (= UnitPrice × OrderedQuantity) của các dòng."""
        self.items.flush()
        po.TotalAmount = sum((i.LineTotal for i in self.items.list_by_purchase_order(po.PurchaseOrderId)), Decimal("0"))

    def _new_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(10):
            code = f"PN{self.now():%y%m%d}{''.join(secrets.choice(alphabet) for _ in range(6))}"
            if not self.purchase_orders.exists_by_code(code):
                return code
        raise BusinessRuleError("Không tạo được mã phiếu nhập", code="purchase_order_code_generation_failed")

    def _detail(self, po: PurchaseOrder) -> PurchaseOrderDetailResponse:
        self.purchase_orders.flush()
        self.session.expire(po, ["items"])
        return PurchaseOrderDetailResponse.model_validate(self.purchase_orders.get_detail(po.PurchaseOrderId))

    def _notify_admins(self, po: PurchaseOrder, title: str, content: str, *, exclude: uuid.UUID | None = None) -> None:
        """Thông báo Admin đang hoạt động (trừ ``exclude``, ví dụ người lập phiếu không tự duyệt được)."""
        for admin in self.users.list_users(role=ADMIN_ROLE, account_status="Active"):
            if admin.UserId != exclude:
                self._notify(admin.UserId, po, title, content)

    def _notify(self, user_id: uuid.UUID, po: PurchaseOrder, title: str, content: str) -> None:
        self.notifications.notify(
            user_id,
            title=title,
            content=content,
            notification_type=PO_NOTIFICATION_TYPE,
            reference_type="PurchaseOrder",
            reference_id=po.PurchaseOrderId,
        )
