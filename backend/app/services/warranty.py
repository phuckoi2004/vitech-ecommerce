"""Warranty service (đợt 5.4): yêu cầu bảo hành từ khi khách gửi đến khi trả máy hoặc đổi máy thay thế.

Nguồn nghiệp vụ: docs/business-requirements.md mục 12, docs/database-schema.md 3.31, quyết định đợt 5.1.1 và 5.4.
Luồng (Status / EligibilityStatus):
1. Customer gửi yêu cầu cho dòng đơn của mình; đơn đã giao (Delivered/Completed, có DeliveredAt). Hệ thống kiểm tra
   serial đúng dòng đơn và còn ở khách (Sold), không có yêu cầu đang xử lý trùng, thời hạn bảo hành
   (``warranty_period``, tính cả ngày hết hạn).
   - Lỗi đầu vào (không sở hữu, đơn chưa giao, serial sai, yêu cầu trùng, dữ liệu bảo hành lệch): báo lỗi, không lưu.
   - Hết hạn hoặc 0 tháng: hệ thống tự từ chối — lưu Rejected/Ineligible kèm lý do, lịch sử (người thực hiện =
     hệ thống) và thông báo khách. Còn hạn: New/Pending.
2. Staff tiếp nhận sản phẩm: ReceivedAt, AssignedStaffId (nếu chưa có); serial Sold → Warranty. Status giữ New.
3. Staff kiểm tra thực tế: Eligible (giữ New) hoặc Ineligible + lý do → Rejected, trả máy (serial Warranty → Sold).
4. Staff bàn giao trung tâm bảo hành/NCC: New → HandedOver (ServiceCenter bắt buộc; HandoverCode, SupplierId).
5. Trung tâm tiếp nhận xử lý: HandedOver → Processing.
6. Staff/Admin đề xuất kết quả (ResultType, ResultNote; ghi ResultProposedByUserId/At); một Admin KHÁC người đề xuất
   duyệt (ResultApprovedAt/By) hoặc từ chối đề xuất (xóa đề xuất để đề xuất lại; đề xuất bị từ chối còn trong lịch sử
   nội bộ). Kết quả đã duyệt không đổi được.
7. Staff hoàn tất khi kết quả đã duyệt: Processing → Completed (CompletedAt). Repaired/PartReplaced/NotRepairable:
   trả máy cũ (serial Warranty → Sold, ngày bảo hành giữ nguyên). ProductReplaced: bàn giao máy thay thế.
8. Admin từ chối toàn bộ yêu cầu đang xử lý (đã tiếp nhận sản phẩm, kết quả chưa duyệt; bắt buộc lý do công khai):
   → Rejected/Ineligible, trả sản phẩm cho khách theo khả năng hiện có (serial Warranty → Sold).
Customer chỉ hủy khi còn New và sản phẩm chưa được tiếp nhận (chưa có quy trình bàn giao trả lại sản phẩm đã tiếp nhận).
Customer không gọi được các bước của Staff/Admin. Lịch sử: Note khách xem được; InternalNote/dòng IsInternal (đề xuất,
từ chối đề xuất) chỉ Staff/Admin xem; khách chỉ thấy kết quả sau khi đã duyệt.

Máy thay thế (ProductReplaced):
- Chỉ dòng đơn quản lý serial (dòng không serial chưa có cách lưu thời hạn của máy thay thế → từ chối đề xuất).
- Serial thay thế: serial thực tế, CÙNG biến thể với dòng đơn (chưa có chính sách đổi khác biến thể), Available,
  chưa gắn đơn. Xuất kho: StockQuantity − 1 qua ``change_stock`` (khóa biến thể, chặn tồn âm — không lấy hàng đã
  hứa cho đơn khác).
- Thời hạn bảo hành MỚI từ ngày Staff xác nhận bàn giao (ReplacementHandedOverAt = thời điểm ghi nhận bàn giao,
  ReplacementHandedOverByUserId = Staff), số tháng = OrderItems.WarrantyMonths của dòng đơn gốc
  (``apply_replacement_warranty``). Serial thay thế → Sold, gắn OrderItemId của dòng đơn gốc.
- Serial cũ (đợt 5.4.1): chuyển Returned khi bàn giao máy thay thế (đã thu về, không phải hàng bán được; không chuyển
  Available); giữ nguyên ngày bảo hành, OrderItemId và các yêu cầu bảo hành đã ghi.
Thứ tự khóa: Order → WarrantyRequest → ProductVariant → ProductSerial. Mọi bước ghi ServiceRequestHistories
(người thực hiện, thời điểm, ghi chú) và thông báo trong cùng transaction; lỗi giữa chừng rollback toàn bộ.
"""

import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Order, OrderItem, ProductSerial, WarrantyRequest
from app.models.service_request import RETURN_OPEN_STATUSES
from app.repositories import (
    OrderItemRepository,
    OrderRepository,
    ProductSerialRepository,
    ProductVariantRepository,
    ReturnRequestRepository,
    ServiceRequestAttachmentRepository,
    ServiceRequestHistoryRepository,
    SupplierRepository,
    UserRepository,
    WarrantyRequestRepository,
)
from app.schemas import (
    AdminWarrantyRequestDetailResponse,
    AdminWarrantyRequestResponse,
    PageResponse,
    ServiceRequestNote,
    ServiceRequestRejection,
    WarrantyCompletion,
    WarrantyEligibilityUpdate,
    WarrantyHandoverCreate,
    WarrantyRequestCreate,
    WarrantyRequestDetailResponse,
    WarrantyRequestResponse,
    WarrantyResultProposal,
    WarrantyResultRejection,
)

from .actor import ADMIN_ONLY, CUSTOMER_ONLY, STAFF_OR_ADMIN, Actor, require_role
from .base import BaseService, utc_now
from .catalog import ProductVariantService
from .exceptions import BusinessRuleError, ConflictError, NotFoundError
from .service_request import (
    allowed_values,
    compose_note,
    generate_request_code,
    optional_text,
    required_text,
    step_notes,
    validate_attachments,
)
from .user import NotificationService
from .warranty_period import (
    WarrantyPeriod,
    apply_replacement_warranty,
    delivery_warranty_period,
    replacement_warranty_period,
    stored_warranty_period,
    vietnam_date,
)

NEW = "New"
REJECTED = "Rejected"
HANDED_OVER = "HandedOver"
PROCESSING = "Processing"
COMPLETED = "Completed"
CANCELLED = "Cancelled"
ELIGIBILITY_PENDING = "Pending"
ELIGIBLE = "Eligible"
INELIGIBLE = "Ineligible"
RESULT_PRODUCT_REPLACED = "ProductReplaced"

# Đơn đã giao thành công (Completed là bước sau Delivered).
DELIVERED_ORDER_STATUSES = ("Delivered", "Completed")
SERIAL_AVAILABLE = "Available"
SERIAL_SOLD = "Sold"
SERIAL_WARRANTY = "Warranty"
# Máy cũ đã thu về khi đổi máy: không phải hàng bán được (không Available).
SERIAL_RETURNED = "Returned"
NOTE_FIELD_CODE = "warranty_field_not_allowed"

REQUEST_CODE_PREFIX = "BH"
WARRANTY_NOTIFICATION_TYPE = "Warranty"
REFERENCE_TYPE = "WarrantyRequest"
CREATE_FIELDS = frozenset({"OrderItemId", "ProductSerialId", "IssueDescription", "Attachments"})
_DATE_FORMAT = "%d/%m/%Y"


class WarrantyService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.requests = WarrantyRequestRepository(session)
        self.attachments = ServiceRequestAttachmentRepository(session)
        self.histories = ServiceRequestHistoryRepository(session)
        self.order_items = OrderItemRepository(session)
        self.orders = OrderRepository(session)
        self.variants = ProductVariantRepository(session)
        self.serials = ProductSerialRepository(session)
        self.suppliers = SupplierRepository(session)
        self.returns = ReturnRequestRepository(session)
        self.users = UserRepository(session)
        self.variant_service = ProductVariantService(session, clock=clock)
        self.notifications = NotificationService(session, clock=clock)

    # ================================================================== Customer

    def create_warranty_request(self, actor: Actor, data: WarrantyRequestCreate) -> WarrantyRequestDetailResponse:
        """Customer gửi yêu cầu bảo hành; hệ thống kiểm tra điều kiện, không đủ thời hạn thì tự từ chối (lưu lý do)."""
        require_role(actor, *CUSTOMER_ONLY)
        values = allowed_values(data, CREATE_FIELDS, code="warranty_field_not_allowed")
        description = required_text(values.get("IssueDescription"), code="issue_description_required",
                                    message="Cần mô tả lỗi của sản phẩm")
        attachments = validate_attachments(values.get("Attachments"))
        order_item_id = values.get("OrderItemId")
        serial_id = values.get("ProductSerialId")
        with self.transaction():
            item = self.order_items.get_by_id_and_customer(order_item_id, actor.user_id) if order_item_id else None
            if item is None:  # không tồn tại hoặc thuộc đơn của khách khác: không tiết lộ
                raise NotFoundError("Không tìm thấy dòng đơn hàng", code="order_item_not_found")
            order = self.orders.get_by_id_for_update(item.OrderId)
            if order is None or order.OrderStatus not in DELIVERED_ORDER_STATUSES:
                raise BusinessRuleError("Chỉ gửi yêu cầu bảo hành cho sản phẩm thuộc đơn hàng đã giao",
                                        code="warranty_order_not_delivered")
            variant = self.variants.get_by_id(item.ProductVariantId)
            if variant is None:
                raise NotFoundError("Không tìm thấy sản phẩm của dòng đơn", code="product_not_found")
            serial = self._customer_serial(item, serial_id, serial_tracked=variant.IsSerialTracked)
            self._ensure_no_open_request(item, serial)
            self._ensure_not_being_returned(item, serial)
            if serial is not None and serial.Status != SERIAL_SOLD:
                raise BusinessRuleError("Serial/IMEI không còn ở trạng thái đã bán cho khách hàng",
                                        code="serial_not_with_customer")
            period = self._warranty_period(order, item, serial)
            now = self.now()
            reason = _ineligible_reason(period, now)
            status, eligibility = (REJECTED, INELIGIBLE) if reason else (NEW, ELIGIBILITY_PENDING)
            request = self.requests.create(
                {
                    "RequestCode": generate_request_code(REQUEST_CODE_PREFIX, now, self.requests.exists_by_code,
                                                         failure_code="warranty_request_code_generation_failed"),
                    "CustomerId": actor.user_id,
                    "OrderItemId": item.OrderItemId,
                    "ProductSerialId": serial.ProductSerialId if serial else None,
                    "IssueDescription": description,
                    "EligibilityStatus": eligibility,
                    "EligibilityReason": reason,
                    "Status": status,
                    "RequestedAt": now,
                }
            )
            self.requests.flush()
            for url, file_type in attachments:
                self.attachments.create({"WarrantyRequestId": request.WarrantyRequestId, "FileUrl": url,
                                         "FileType": file_type, "UploadedAt": now})
            if reason:
                self._history(request, None, None, REJECTED, f"Hệ thống tự động từ chối: {reason}")
                self._notify_customer(request, "Yêu cầu bảo hành bị từ chối",
                                      f"Yêu cầu {request.RequestCode} không đủ điều kiện bảo hành: {reason}")
            else:
                checked = f"Hệ thống kiểm tra: còn bảo hành đến {period.end.strftime(_DATE_FORMAT)}."
                self._history(request, actor.user_id, None, NEW, f"Khách hàng gửi yêu cầu bảo hành. {checked}")
                self._notify_customer(request, "Đã nhận yêu cầu bảo hành",
                                      f"Yêu cầu {request.RequestCode} đã được ghi nhận và chờ tiếp nhận sản phẩm.")
            return self._customer_detail(request)

    def cancel_warranty_request(
        self, actor: Actor, request_id: uuid.UUID, data: ServiceRequestNote | None = None
    ) -> WarrantyRequestDetailResponse:
        """Customer hủy yêu cầu của mình khi còn New và sản phẩm chưa được tiếp nhận."""
        require_role(actor, *CUSTOMER_ONLY)
        note, _ = step_notes(data, allowed=frozenset({"Note"}), code=NOTE_FIELD_CODE)
        with self.transaction():
            request, _ = self._lock(request_id, customer_id=actor.user_id)
            if request.Status != NEW or request.ReceivedAt is not None:
                raise BusinessRuleError("Chỉ hủy được yêu cầu mới, chưa tiếp nhận sản phẩm",
                                        code="warranty_not_cancellable")
            request.Status = CANCELLED
            self._history(request, actor.user_id, NEW, CANCELLED, compose_note("Khách hàng hủy yêu cầu.", note))
            return self._customer_detail(request)

    def list_my_warranty_requests(
        self, actor: Actor, *, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> PageResponse[WarrantyRequestResponse]:
        require_role(actor, *CUSTOMER_ONLY)
        offset, limit = self._page_args(page, page_size)
        items = self.requests.list_requests(customer_id=actor.user_id, status=status, offset=offset, limit=limit)
        return PageResponse[WarrantyRequestResponse](
            Items=[WarrantyRequestResponse.model_validate(r) for r in items],
            Total=self.requests.count_requests(customer_id=actor.user_id, status=status),
            Page=page,
            PageSize=page_size,
        )

    def get_my_warranty_request(self, actor: Actor, request_id: uuid.UUID) -> WarrantyRequestDetailResponse:
        require_role(actor, *CUSTOMER_ONLY)
        if self.requests.get_by_id_and_customer(request_id, actor.user_id) is None:
            raise NotFoundError("Không tìm thấy yêu cầu bảo hành", code="warranty_request_not_found")
        return WarrantyRequestDetailResponse.model_validate(self.requests.get_detail(request_id))

    # ================================================================== Staff / Admin: xem

    def list_warranty_requests(
        self,
        actor: Actor,
        *,
        status: str | None = None,
        eligibility_status: str | None = None,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[AdminWarrantyRequestResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        offset, limit = self._page_args(page, page_size)
        filters = {"customer_id": customer_id, "assigned_staff_id": assigned_staff_id, "supplier_id": supplier_id,
                   "status": status, "eligibility_status": eligibility_status}
        items = self.requests.list_requests(**filters, offset=offset, limit=limit)
        return PageResponse[AdminWarrantyRequestResponse](
            Items=[AdminWarrantyRequestResponse.model_validate(r) for r in items],
            Total=self.requests.count_requests(**filters),
            Page=page,
            PageSize=page_size,
        )

    def get_warranty_request(self, actor: Actor, request_id: uuid.UUID) -> AdminWarrantyRequestDetailResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        request = self.requests.get_detail(request_id)
        if request is None:
            raise NotFoundError("Không tìm thấy yêu cầu bảo hành", code="warranty_request_not_found")
        return AdminWarrantyRequestDetailResponse.model_validate(request)

    # ================================================================== Staff: tiếp nhận / kiểm tra / bàn giao

    def receive_warranty_request(
        self, actor: Actor, request_id: uuid.UUID, data: ServiceRequestNote | None = None
    ) -> AdminWarrantyRequestDetailResponse:
        """Staff xác nhận đã nhận sản phẩm thực tế từ khách (serial Sold → Warranty). Status giữ New."""
        require_role(actor, *STAFF_OR_ADMIN)
        note, internal_note = step_notes(data, code=NOTE_FIELD_CODE)
        with self.transaction():
            request, item = self._lock(request_id)
            self._require_status(request, NEW)
            if request.ReceivedAt is not None:
                raise BusinessRuleError("Sản phẩm đã được tiếp nhận", code="warranty_already_received")
            if request.ProductSerialId is not None:
                serial = self._lock_request_serial(request, item)
                if serial.Status != SERIAL_SOLD:
                    raise BusinessRuleError("Serial/IMEI không còn ở trạng thái đã bán cho khách hàng",
                                            code="serial_not_with_customer")
                serial.Status = SERIAL_WARRANTY
            request.ReceivedAt = self.now()
            if request.AssignedStaffId is None:
                request.AssignedStaffId = actor.user_id
            self._history(request, actor.user_id, NEW, NEW, compose_note("Tiếp nhận sản phẩm từ khách hàng.", note),
                          internal_note=internal_note)
            self._notify_customer(request, "Đã tiếp nhận sản phẩm bảo hành",
                                  f"Sản phẩm của yêu cầu {request.RequestCode} đã được tiếp nhận để kiểm tra.")
            return self._admin_detail(request)

    def inspect_warranty_request(
        self, actor: Actor, request_id: uuid.UUID, data: WarrantyEligibilityUpdate
    ) -> AdminWarrantyRequestDetailResponse:
        """Staff ghi nhận kết quả kiểm tra thực tế: Eligible (giữ New) hoặc Ineligible → Rejected, trả máy cho khách."""
        require_role(actor, *STAFF_OR_ADMIN)
        values = allowed_values(data, frozenset({"EligibilityStatus", "EligibilityReason", "InternalNote"}),
                                code=NOTE_FIELD_CODE)
        internal_note = optional_text(values.get("InternalNote"))
        decision = values.get("EligibilityStatus")
        if decision not in (ELIGIBLE, INELIGIBLE):
            raise BusinessRuleError("Kết quả kiểm tra phải là Eligible hoặc Ineligible",
                                    code="invalid_eligibility_decision")
        reason = optional_text(values.get("EligibilityReason"))
        if decision == INELIGIBLE and not reason:
            raise BusinessRuleError("Cần ghi lý do không đủ điều kiện bảo hành", code="eligibility_reason_required")
        with self.transaction():
            request, item = self._lock(request_id)
            self._require_status(request, NEW)
            if request.ReceivedAt is None:
                raise BusinessRuleError("Chưa tiếp nhận sản phẩm, chưa thể kiểm tra", code="warranty_not_received")
            if request.EligibilityStatus != ELIGIBILITY_PENDING:
                raise BusinessRuleError("Yêu cầu đã có kết quả kiểm tra", code="warranty_already_inspected")
            request.EligibilityStatus = decision
            request.EligibilityReason = reason
            if decision == ELIGIBLE:
                self._history(request, actor.user_id, NEW, NEW,
                              compose_note("Kiểm tra thực tế: đủ điều kiện bảo hành.", reason), internal_note=internal_note)
                self._notify_customer(request, "Sản phẩm đủ điều kiện bảo hành",
                                      f"Yêu cầu {request.RequestCode} đủ điều kiện và sẽ được bàn giao xử lý.")
            else:
                self._return_original_serial(request, item)
                request.Status = REJECTED
                self._history(request, actor.user_id, NEW, REJECTED,
                              f"Kiểm tra thực tế: không đủ điều kiện bảo hành. Lý do: {reason}", internal_note=internal_note)
                self._notify_customer(request, "Yêu cầu bảo hành bị từ chối",
                                      f"Yêu cầu {request.RequestCode} không đủ điều kiện bảo hành: {reason}")
            return self._admin_detail(request)

    def hand_over_warranty_request(
        self, actor: Actor, request_id: uuid.UUID, data: WarrantyHandoverCreate
    ) -> AdminWarrantyRequestDetailResponse:
        """Staff bàn giao sản phẩm đã kiểm tra đủ điều kiện cho trung tâm bảo hành/NCC: New → HandedOver."""
        require_role(actor, *STAFF_OR_ADMIN)
        values = allowed_values(data, frozenset({"ServiceCenter", "HandoverCode", "SupplierId", "Note", "InternalNote"}),
                                code=NOTE_FIELD_CODE)
        service_center = required_text(values.get("ServiceCenter"), code="service_center_required",
                                       message="Cần ghi trung tâm bảo hành nhận sản phẩm")
        handover_code = optional_text(values.get("HandoverCode"))
        supplier_id = values.get("SupplierId")
        note, internal_note = optional_text(values.get("Note")), optional_text(values.get("InternalNote"))
        with self.transaction():
            request, _ = self._lock(request_id)
            self._require_status(request, NEW)
            if request.ReceivedAt is None:
                raise BusinessRuleError("Chưa tiếp nhận sản phẩm", code="warranty_not_received")
            if request.EligibilityStatus != ELIGIBLE:
                raise BusinessRuleError("Sản phẩm chưa được kiểm tra đủ điều kiện bảo hành",
                                        code="warranty_not_eligible")
            if supplier_id is not None:
                supplier = self.suppliers.get_by_id(supplier_id)
                if supplier is None or not supplier.IsActive:
                    raise NotFoundError("Nhà cung cấp không hợp lệ", code="supplier_not_available")
            request.ServiceCenter = service_center
            request.HandoverCode = handover_code
            request.SupplierId = supplier_id
            request.HandedOverAt = self.now()
            request.Status = HANDED_OVER
            self._history(request, actor.user_id, NEW, HANDED_OVER,
                          compose_note(f"Bàn giao trung tâm bảo hành {service_center}.", note),
                          internal_note=internal_note)
            self._notify_customer(request, "Đã bàn giao trung tâm bảo hành",
                                  f"Sản phẩm của yêu cầu {request.RequestCode} đã được chuyển đến {service_center}.")
            return self._admin_detail(request)

    def start_warranty_processing(
        self, actor: Actor, request_id: uuid.UUID, data: ServiceRequestNote | None = None
    ) -> AdminWarrantyRequestDetailResponse:
        """Trung tâm bảo hành tiếp nhận xử lý: HandedOver → Processing."""
        require_role(actor, *STAFF_OR_ADMIN)
        note, internal_note = step_notes(data, code=NOTE_FIELD_CODE)
        with self.transaction():
            request, _ = self._lock(request_id)
            self._require_status(request, HANDED_OVER)
            request.Status = PROCESSING
            self._history(request, actor.user_id, HANDED_OVER, PROCESSING,
                          compose_note("Trung tâm bảo hành đang xử lý.", note), internal_note=internal_note)
            self._notify_customer(request, "Bảo hành đang được xử lý",
                                  f"Yêu cầu {request.RequestCode} đang được trung tâm bảo hành xử lý.")
            return self._admin_detail(request)

    # ================================================================== Kết quả: Staff đề xuất, Admin duyệt

    def propose_warranty_result(
        self, actor: Actor, request_id: uuid.UUID, data: WarrantyResultProposal
    ) -> AdminWarrantyRequestDetailResponse:
        """Staff/Admin đề xuất kết quả (nội bộ); chờ một Admin khác duyệt (thay đề xuất chưa duyệt)."""
        require_role(actor, *STAFF_OR_ADMIN)
        values = allowed_values(data, frozenset({"ResultType", "ResultNote"}), code="warranty_field_not_allowed")
        result_type = values.get("ResultType")
        if result_type not in _RESULT_LABELS:
            raise BusinessRuleError("Kết quả bảo hành không hợp lệ", code="invalid_warranty_result")
        result_note = required_text(values.get("ResultNote"), code="result_note_required",
                                    message="Cần ghi kết quả kiểm tra/xử lý")
        with self.transaction():
            request, _ = self._lock(request_id)
            self._require_status(request, PROCESSING)
            if request.ResultApprovedAt is not None:
                raise BusinessRuleError("Kết quả đã được Admin duyệt, không thể thay đổi",
                                        code="warranty_result_already_approved")
            if result_type == RESULT_PRODUCT_REPLACED and request.ProductSerialId is None:
                raise BusinessRuleError(
                    "Đổi máy chỉ áp dụng cho sản phẩm quản lý Serial/IMEI (chưa có quy tắc cho sản phẩm không serial)",
                    code="replacement_requires_serial",
                )
            request.ResultType = result_type
            request.ResultNote = result_note
            request.ResultProposedByUserId = actor.user_id
            request.ResultProposedAt = self.now()
            self._history(request, actor.user_id, PROCESSING, PROCESSING, None, internal=True,
                          internal_note=f"Đề xuất kết quả: {_RESULT_LABELS[result_type]}. Ghi chú: {result_note}")
            for admin in self.users.list_users(role="Admin", account_status="Active"):
                if admin.UserId != actor.user_id:
                    self.notifications.notify(
                        admin.UserId,
                        title="Kết quả bảo hành chờ duyệt",
                        content=f"Yêu cầu {request.RequestCode}: đề xuất {_RESULT_LABELS[result_type]}.",
                        notification_type=WARRANTY_NOTIFICATION_TYPE,
                        reference_type=REFERENCE_TYPE,
                        reference_id=request.WarrantyRequestId,
                    )
            return self._admin_detail(request)

    def approve_warranty_result(
        self, actor: Actor, request_id: uuid.UUID, data: ServiceRequestNote | None = None
    ) -> AdminWarrantyRequestDetailResponse:
        """Admin (khác người đề xuất) duyệt kết quả; ghi người duyệt, thời điểm. Chưa hoàn tất: Staff trả/đổi máy sau."""
        require_role(actor, *ADMIN_ONLY)
        note, internal_note = step_notes(data, code=NOTE_FIELD_CODE)
        with self.transaction():
            request, _ = self._lock(request_id)
            self._require_pending_result(request)
            self._require_other_reviewer(request, actor)
            request.ResultApprovedAt = self.now()
            request.ResultApprovedByUserId = actor.user_id
            self._history(request, actor.user_id, PROCESSING, PROCESSING,
                          compose_note(f"Kết quả bảo hành được duyệt: {_RESULT_LABELS[request.ResultType]}.", note),
                          internal_note=internal_note)
            self._notify_staff(request, "Kết quả bảo hành đã được duyệt",
                               f"Yêu cầu {request.RequestCode}: kết quả {_RESULT_LABELS[request.ResultType]} đã duyệt.")
            return self._admin_detail(request)

    def reject_warranty_result(
        self, actor: Actor, request_id: uuid.UUID, data: WarrantyResultRejection
    ) -> AdminWarrantyRequestDetailResponse:
        """Admin (khác người đề xuất) từ chối đề xuất (bắt buộc lý do, nội bộ): xóa đề xuất để đề xuất lại."""
        require_role(actor, *ADMIN_ONLY)
        reason = required_text(getattr(data, "Reason", None), code="rejection_reason_required",
                               message="Cần ghi lý do từ chối")
        with self.transaction():
            request, _ = self._lock(request_id)
            self._require_pending_result(request)
            self._require_other_reviewer(request, actor)
            label = _RESULT_LABELS[request.ResultType]
            self._clear_proposal(request)
            self._history(request, actor.user_id, PROCESSING, PROCESSING, None, internal=True,
                          internal_note=f"Admin từ chối đề xuất kết quả: {label}. Lý do: {reason}")
            self._notify_staff(request, "Đề xuất bảo hành bị từ chối",
                               f"Yêu cầu {request.RequestCode}: đề xuất {label} bị từ chối. Lý do: {reason}")
            return self._admin_detail(request)

    def reject_warranty_request(
        self, actor: Actor, request_id: uuid.UUID, data: ServiceRequestRejection
    ) -> AdminWarrantyRequestDetailResponse:
        """Admin từ chối toàn bộ yêu cầu đang xử lý (đã tiếp nhận sản phẩm, kết quả chưa duyệt).

        Reason (bắt buộc) là lý do/kết luận khách hàng được xem; InternalNote chỉ Staff/Admin. EligibilityStatus →
        Ineligible; đề xuất chưa duyệt bị xóa (còn trong lịch sử nội bộ); trả sản phẩm cho khách theo khả năng hiện có
        (serial Warranty → Sold) — chưa có bước ghi nhận bàn giao vật lý riêng.
        """
        require_role(actor, *ADMIN_ONLY)
        values = allowed_values(data, frozenset({"Reason", "InternalNote"}), code=NOTE_FIELD_CODE)
        reason = required_text(values.get("Reason"), code="rejection_reason_required", message="Cần ghi lý do từ chối")
        internal_note = optional_text(values.get("InternalNote"))
        with self.transaction():
            request, item = self._lock(request_id)
            old = request.Status
            if old not in (NEW, HANDED_OVER, PROCESSING):
                raise BusinessRuleError(f"Yêu cầu đang ở trạng thái {old}, không thể từ chối",
                                        code="invalid_warranty_transition")
            if request.ReceivedAt is None:
                raise BusinessRuleError("Chưa tiếp nhận sản phẩm; yêu cầu chưa vào quá trình xử lý",
                                        code="warranty_not_received")
            if request.ResultApprovedAt is not None:
                raise BusinessRuleError("Kết quả đã được duyệt, không thể từ chối yêu cầu",
                                        code="warranty_result_already_approved")
            self._return_original_serial(request, item)
            self._clear_proposal(request)
            request.EligibilityStatus = INELIGIBLE
            request.EligibilityReason = reason
            request.Status = REJECTED
            self._history(request, actor.user_id, old, REJECTED,
                          f"Yêu cầu bảo hành bị từ chối. Lý do: {reason} Sản phẩm được trả lại khách hàng.",
                          internal_note=internal_note)
            self._notify_customer(request, "Yêu cầu bảo hành bị từ chối",
                                  f"Yêu cầu {request.RequestCode} bị từ chối. Lý do: {reason}")
            self._notify_staff(request, "Yêu cầu bảo hành bị từ chối",
                               f"Admin từ chối yêu cầu {request.RequestCode}. Lý do: {reason}")
            return self._admin_detail(request)

    # ================================================================== Hoàn tất / đổi máy

    def complete_warranty_request(
        self, actor: Actor, request_id: uuid.UUID, data: WarrantyCompletion | None = None
    ) -> AdminWarrantyRequestDetailResponse:
        """Staff hoàn tất khi kết quả đã duyệt: trả máy cũ, hoặc bàn giao máy thay thế (ProductReplaced)."""
        require_role(actor, *STAFF_OR_ADMIN)
        values = (allowed_values(data, frozenset({"ReplacementProductSerialId", "Note", "InternalNote"}),
                                 code=NOTE_FIELD_CODE) if data is not None else {})
        replacement_id = values.get("ReplacementProductSerialId")
        note, internal_note = optional_text(values.get("Note")), optional_text(values.get("InternalNote"))
        with self.transaction():
            request, item = self._lock(request_id)
            self._require_status(request, PROCESSING)
            if request.ResultType is None or request.ResultApprovedAt is None:
                raise BusinessRuleError("Kết quả bảo hành chưa được Admin duyệt", code="warranty_result_not_approved")
            now = self.now()
            if request.ResultType == RESULT_PRODUCT_REPLACED:
                if replacement_id is None:
                    raise BusinessRuleError("Cần serial thực tế của máy thay thế", code="replacement_serial_required")
                replacement = self._hand_over_replacement(request, item, replacement_id, actor, now)
                event = f"Bàn giao máy thay thế (serial {replacement.SerialNumber}) cho khách hàng."
            else:
                if replacement_id is not None:
                    raise BusinessRuleError("Chỉ kết quả đổi máy mới có máy thay thế", code="replacement_not_applicable")
                self._return_original_serial(request, item)
                event = f"Hoàn tất bảo hành ({_RESULT_LABELS[request.ResultType]}), trả sản phẩm cho khách hàng."
            request.CompletedAt = now
            request.Status = COMPLETED
            self._history(request, actor.user_id, PROCESSING, COMPLETED, compose_note(event, note),
                          internal_note=internal_note)
            self._notify_customer(request, "Bảo hành đã hoàn tất", f"Yêu cầu {request.RequestCode}: {event}")
            return self._admin_detail(request)

    # ================================================================== helpers

    def _customer_serial(self, item: OrderItem, serial_id: uuid.UUID | None, *, serial_tracked: bool
                         ) -> ProductSerial | None:
        """Serial thực tế thuộc dòng đơn (khóa dòng; sau khóa Order)."""
        if not serial_tracked:
            if serial_id is not None:
                raise BusinessRuleError("Sản phẩm không quản lý Serial/IMEI", code="serial_not_applicable")
            return None
        if serial_id is None:
            raise BusinessRuleError("Cần chọn Serial/IMEI của thiết bị cần bảo hành", code="warranty_serial_required")
        serial = self.serials.get_by_id_for_update(serial_id)
        if (serial is None or serial.OrderItemId != item.OrderItemId
                or serial.ProductVariantId != item.ProductVariantId):
            raise BusinessRuleError("Serial/IMEI không thuộc dòng đơn hàng này", code="serial_not_in_order_item")
        return serial

    def _ensure_no_open_request(self, item: OrderItem, serial: ProductSerial | None) -> None:
        existing = (self.requests.get_open_by_product_serial(serial.ProductSerialId) if serial is not None
                    else self.requests.get_open_by_order_item_without_serial(item.OrderItemId))
        if existing is not None:
            raise ConflictError(f"Sản phẩm đang có yêu cầu bảo hành {existing.RequestCode} chưa xử lý xong",
                                code="warranty_request_open")

    def _ensure_not_being_returned(self, item: OrderItem, serial: ProductSerial | None) -> None:
        """Không nhận bảo hành sản phẩm đang trong yêu cầu đổi/trả chưa xử lý xong, hoặc dòng đơn đã trả hết."""
        if serial is not None:
            if self.returns.get_open_by_product_serial(serial.ProductSerialId) is not None:
                raise ConflictError("Serial/IMEI đang có yêu cầu đổi/trả chưa xử lý xong", code="serial_has_open_return")
            return
        returns = self.returns.list_by_order_item(item.OrderItemId)
        if any(r.Status in RETURN_OPEN_STATUSES for r in returns):
            raise ConflictError("Sản phẩm đang có yêu cầu đổi/trả chưa xử lý xong", code="item_has_open_return")
        returned = sum(r.Quantity for r in returns if r.RequestType == "Return" and r.Status == COMPLETED)
        if returned >= item.Quantity:
            raise BusinessRuleError("Toàn bộ sản phẩm của dòng đơn đã được trả lại", code="item_fully_returned")

    def _warranty_period(self, order: Order, item: OrderItem, serial: ProductSerial | None) -> WarrantyPeriod | None:
        """Thời hạn theo quy tắc warranty_period; serial: đối chiếu ngày đã lưu, lệch thì báo lỗi (không tự sửa)."""
        if serial is None:
            return delivery_warranty_period(order.DeliveredAt, item.WarrantyMonths)
        replacement_of = self.requests.get_latest_replacement_handover(serial.ProductSerialId)
        if replacement_of is not None and replacement_of.OrderItemId == item.OrderItemId:
            expected = replacement_warranty_period(replacement_of.ReplacementHandedOverAt, item.WarrantyMonths)
        else:
            expected = delivery_warranty_period(order.DeliveredAt, item.WarrantyMonths)
        stored = stored_warranty_period(serial.WarrantyStartDate, serial.WarrantyEndDate)
        if stored != expected:
            raise BusinessRuleError(
                f"Thời hạn bảo hành đã lưu của serial {serial.SerialNumber} không khớp dữ liệu đơn hàng; "
                "cần kiểm tra thủ công",
                code="warranty_data_inconsistent",
            )
        return stored

    def _lock(self, request_id: uuid.UUID, *, customer_id: uuid.UUID | None = None
              ) -> tuple[WarrantyRequest, OrderItem]:
        """Khóa theo thứ tự Order → WarrantyRequest rồi đọc lại yêu cầu đã khóa."""
        request = (self.requests.get_by_id_and_customer(request_id, customer_id) if customer_id is not None
                   else self.requests.get_by_id(request_id))
        if request is None:
            raise NotFoundError("Không tìm thấy yêu cầu bảo hành", code="warranty_request_not_found")
        item = self.order_items.get_by_id(request.OrderItemId)
        if item is None:
            raise NotFoundError("Không tìm thấy dòng đơn hàng", code="order_item_not_found")
        self.orders.get_by_id_for_update(item.OrderId)
        request = self.requests.get_by_id_for_update(request_id)
        if request is None:
            raise NotFoundError("Không tìm thấy yêu cầu bảo hành", code="warranty_request_not_found")
        return request, item

    @staticmethod
    def _require_status(request: WarrantyRequest, expected: str) -> None:
        if request.Status != expected:
            raise BusinessRuleError(
                f"Yêu cầu đang ở trạng thái {request.Status}, không thực hiện được bước này (cần {expected})",
                code="invalid_warranty_transition",
            )

    def _require_pending_result(self, request: WarrantyRequest) -> None:
        self._require_status(request, PROCESSING)
        if request.ResultType is None:
            raise BusinessRuleError("Chưa có kết quả được đề xuất", code="warranty_result_not_proposed")
        if request.ResultApprovedAt is not None:
            raise BusinessRuleError("Kết quả đã được duyệt", code="warranty_result_already_approved")

    @staticmethod
    def _require_other_reviewer(request: WarrantyRequest, actor: Actor) -> None:
        """Người đề xuất không tự duyệt/từ chối đề xuất của mình; không rõ người đề xuất thì phải đề xuất lại."""
        if request.ResultProposedByUserId is None:
            raise BusinessRuleError("Không xác định được người đề xuất; cần đề xuất lại kết quả",
                                    code="warranty_result_proposer_unknown")
        if request.ResultProposedByUserId == actor.user_id:
            raise BusinessRuleError("Người đề xuất không được tự duyệt hoặc từ chối đề xuất của mình",
                                    code="warranty_self_review_not_allowed")

    @staticmethod
    def _clear_proposal(request: WarrantyRequest) -> None:
        request.ResultType = None
        request.ResultNote = None
        request.ResultProposedByUserId = None
        request.ResultProposedAt = None

    def _lock_request_serial(self, request: WarrantyRequest, item: OrderItem) -> ProductSerial:
        serial = self.serials.get_by_id_for_update(request.ProductSerialId)
        if serial is None or serial.OrderItemId != item.OrderItemId:
            raise BusinessRuleError("Serial/IMEI của yêu cầu không còn khớp dòng đơn hàng; cần kiểm tra thủ công",
                                    code="serial_state_inconsistent")
        return serial

    def _return_original_serial(self, request: WarrantyRequest, item: OrderItem) -> None:
        """Trả máy cũ cho khách (đã tiếp nhận): serial Warranty → Sold; ngày bảo hành giữ nguyên."""
        if request.ProductSerialId is None:
            return
        serial = self._lock_request_serial(request, item)
        if serial.Status != SERIAL_WARRANTY:
            raise BusinessRuleError("Serial/IMEI không ở trạng thái đang bảo hành; cần kiểm tra thủ công",
                                    code="serial_state_inconsistent")
        serial.Status = SERIAL_SOLD

    def _hand_over_replacement(self, request: WarrantyRequest, item: OrderItem, replacement_id: uuid.UUID,
                               actor: Actor, handed_over_at: datetime) -> ProductSerial:
        """Xuất kho serial thay thế cùng biến thể và bàn giao cho khách; serial cũ → Returned, giữ nguyên lịch sử."""
        if replacement_id == request.ProductSerialId:
            raise BusinessRuleError("Máy thay thế phải là serial khác serial cũ", code="replacement_same_serial")
        preview = self.serials.get_by_id(replacement_id)
        if preview is None:
            raise NotFoundError("Không tìm thấy serial máy thay thế", code="replacement_serial_not_found")
        if preview.ProductVariantId != item.ProductVariantId:
            raise BusinessRuleError("Máy thay thế phải cùng biến thể với sản phẩm đã mua (chưa có chính sách đổi khác "
                                    "biến thể)", code="replacement_variant_mismatch")
        self.variant_service.change_stock({item.ProductVariantId: -1})  # khóa biến thể trước serial, chặn tồn âm
        original = self._lock_request_serial(request, item)
        if original.Status != SERIAL_WARRANTY:
            raise BusinessRuleError("Serial cũ không ở trạng thái đang bảo hành; cần kiểm tra thủ công",
                                    code="serial_state_inconsistent")
        replacement = self.serials.get_by_id_for_update(replacement_id)
        if replacement is None:
            raise NotFoundError("Không tìm thấy serial máy thay thế", code="replacement_serial_not_found")
        if (replacement.ProductVariantId != item.ProductVariantId or replacement.Status != SERIAL_AVAILABLE
                or replacement.OrderItemId is not None):
            raise BusinessRuleError("Serial máy thay thế không còn trong kho (Available, chưa gắn đơn)",
                                    code="replacement_serial_unavailable")
        request.ReplacementProductSerialId = replacement.ProductSerialId
        request.ReplacementHandedOverAt = handed_over_at
        request.ReplacementHandedOverByUserId = actor.user_id
        apply_replacement_warranty(original, replacement, months=item.WarrantyMonths,
                                   handed_over_at=request.ReplacementHandedOverAt)
        replacement.Status = SERIAL_SOLD
        replacement.OrderItemId = item.OrderItemId
        # Máy cũ đã thu về: Returned (không bán lại tự động); giữ ngày bảo hành và OrderItemId của lần bán gốc.
        original.Status = SERIAL_RETURNED
        self.serials.flush()
        return replacement

    def _history(self, request: WarrantyRequest, changed_by: uuid.UUID | None, old: str | None, new: str,
                 note: str | None, *, internal_note: str | None = None, internal: bool = False) -> None:
        """Note: khách xem được; internal_note: chỉ Staff/Admin; internal=True: cả dòng chỉ Staff/Admin (không có Note)."""
        self.requests.flush()
        self.histories.create(
            {
                "WarrantyRequestId": request.WarrantyRequestId,
                "ChangedByUserId": changed_by,
                "OldStatus": old,
                "NewStatus": new,
                "Note": None if internal else note,
                "InternalNote": internal_note,
                "IsInternal": internal,
                "ChangedAt": self.now(),
            }
        )
        self.histories.flush()

    def _notify_customer(self, request: WarrantyRequest, title: str, content: str) -> None:
        self.notifications.notify(request.CustomerId, title=title, content=content,
                                  notification_type=WARRANTY_NOTIFICATION_TYPE, reference_type=REFERENCE_TYPE,
                                  reference_id=request.WarrantyRequestId)

    def _notify_staff(self, request: WarrantyRequest, title: str, content: str) -> None:
        if request.AssignedStaffId is not None:
            self.notifications.notify(request.AssignedStaffId, title=title, content=content,
                                      notification_type=WARRANTY_NOTIFICATION_TYPE, reference_type=REFERENCE_TYPE,
                                      reference_id=request.WarrantyRequestId)

    def _customer_detail(self, request: WarrantyRequest) -> WarrantyRequestDetailResponse:
        self.requests.flush()
        return WarrantyRequestDetailResponse.model_validate(self.requests.get_detail(request.WarrantyRequestId))

    def _admin_detail(self, request: WarrantyRequest) -> AdminWarrantyRequestDetailResponse:
        self.requests.flush()
        return AdminWarrantyRequestDetailResponse.model_validate(self.requests.get_detail(request.WarrantyRequestId))


_RESULT_LABELS = {
    "Repaired": "Sửa chữa",
    "ProductReplaced": "Đổi máy",
    "PartReplaced": "Thay linh kiện",
    "NotRepairable": "Không thể sửa chữa",
}


def _ineligible_reason(period: WarrantyPeriod | None, at: datetime) -> str | None:
    """Lý do hệ thống tự từ chối theo thời hạn (None = còn bảo hành tại ngày Việt Nam của ``at``)."""
    if period is None:
        return "Sản phẩm không có bảo hành (0 tháng)."
    today = vietnam_date(at)
    if today > period.end:
        return f"Đã hết hạn bảo hành (ngày cuối còn bảo hành: {period.end.strftime(_DATE_FORMAT)})."
    if today < period.start:
        return f"Thời hạn bảo hành bắt đầu từ ngày {period.start.strftime(_DATE_FORMAT)}."
    return None
