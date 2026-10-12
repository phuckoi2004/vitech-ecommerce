"""Return service (đợt 5.4): yêu cầu đổi hàng (Exchange) / trả hàng (Return) cho sản phẩm thuộc đơn đã giao.

Nguồn nghiệp vụ: docs/business-requirements.md mục 13, quyết định đợt 5.1 (mục 5.2–5.3) và 5.4 (mục 6).
Chính sách được truyền vào qua ``ReturnPolicy`` (không hard-code trong Service):
- ``window_days``: số ngày được gửi yêu cầu kể từ ngày giao. Cấu hình ứng dụng: biến môi trường RETURN_WINDOW_DAYS đọc
  bằng ``ReturnPolicy.from_env`` (không khai báo → mặc định DEFAULT_RETURN_WINDOW_DAYS = 7, giá trị sai → lỗi cấu hình).
  Service không được truyền chính sách (window_days None) → từ chối tạo yêu cầu (return_policy_not_configured).
  Còn hạn khi ngày Việt Nam hiện tại <= ngày giao (lịch Việt Nam) + window_days − 1 (ngày giao là ngày thứ nhất, cùng
  cách tính với bảo hành). DeliveredAt thiếu múi giờ hoặc sau thời điểm hiện tại: dữ liệu giao hàng không hợp lệ.
- Khấu trừ/phí: chưa có chính sách → không khấu trừ. Có hàng hỏng: chưa có quy tắc khấu trừ → không tính tiền,
  Admin không duyệt được (chỉ từ chối). Phí vận chuyển không hoàn (chưa có chính sách).
- Đổi hàng: chỉ đổi cùng biến thể (yêu cầu không có sản phẩm đích). Chênh lệch = giá mới − giá cũ theo giá trị lịch sử
  của dòng đơn = 0. Giao hàng đổi (xuất serial mới, bảo hành của máy đổi) chưa có quy tắc → Admin chưa duyệt được.

Luồng (Status; mỗi bước ghi ServiceRequestHistories — người thực hiện, thời điểm, ghi chú):
1. Customer gửi (Pending): dòng đơn của mình, đơn Delivered/Completed, trong thời hạn đã cấu hình. Hàng quản lý serial:
   serial thực tế của dòng đơn, đang ở khách (Sold), Quantity = 1. Hàng không serial: Quantity <= số còn có thể trả
   (Quantity dòng đơn − các yêu cầu không bị từ chối/hủy). Không trùng yêu cầu đổi/trả hoặc bảo hành đang xử lý.
2. Staff/Admin tiếp nhận (Approved) hoặc từ chối (Rejected, bắt buộc lý do). Customer hủy khi còn Pending.
3. Điều phối nhận hàng (Receiving) → Staff xác nhận hàng thực tế đã về (Processing, ReceivedAt; quét đúng serial;
   serial Sold → Returned: đã về cửa hàng, chưa nhập tồn).
4. Staff kiểm tra: số đạt (RestockedQuantity) + số hỏng (DamagedQuantity) = Quantity, đánh giá hư hại; hệ thống tính
   CompensationAmount và lưu căn cứ (CompensationBasis) từ giá trị lịch sử của dòng đơn.
5. Admin duyệt ĐÚNG số tiền hệ thống tính (tính lại khi duyệt): nhập lại tồn hàng đạt trong cùng transaction
   (serial Returned → Available, bỏ gắn đơn; StockQuantity + số đạt) — chỉ một lần. Hoặc Admin từ chối: trả hàng cho
   khách (serial → Sold), không nhập tồn.
6. Staff/Admin tạo hoàn tiền (Return) qua PaymentService: giao dịch Refund Pending trỏ khoản thanh toán gốc
   (RefundOfPaymentTransactionId), ghi người tạo, liên kết RefundPaymentTransactionId. Completed chỉ khi Refund
   Success; Pending (cổng chưa xác nhận / hoàn trực tiếp COD / chuyển khoản thủ công) không phải đã hoàn. Số tiền 0:
   hoàn tất khi duyệt.
Hoàn tiền: Pending KHÔNG phải đã hoàn và vẫn giữ tiền — không tạo giao dịch mới. Cổng trả Success thì hoàn tất ngay;
còn lại Admin khác người tạo xác nhận kèm bằng chứng (PaymentService.resolve_pending_refund, đợt 5.11) rồi
confirm_return_refund.
Failed/Cancelled: có thể tạo lại giao dịch. Completed chỉ khi Refund Success. Cổng hiện không hỗ trợ idempotency key
hay tra cứu trạng thái nên không tự gửi lại.
Lịch sử: Note khách xem được; InternalNote/dòng IsInternal chỉ Staff/Admin (schema khách chỉ trả dòng công khai).
Nhập lại tồn: serial bỏ gắn OrderItemId (để bán lại), giữ ngày bảo hành; liên kết đơn gốc còn ở ReturnRequests
(ProductSerialId, OrderItemId) và lịch sử.
Thứ tự khóa: Order → ReturnRequest → ProductVariant → ProductSerial → PaymentTransaction.
"""

import os
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import Order, OrderItem, ProductSerial, ReturnRequest
from app.models.service_request import RETURN_REQUEST_TYPES
from app.repositories import (
    OrderItemRepository,
    OrderRepository,
    PaymentTransactionRepository,
    ProductSerialRepository,
    ProductVariantRepository,
    ReturnRequestRepository,
    ServiceRequestAttachmentRepository,
    ServiceRequestHistoryRepository,
    UserRepository,
    WarrantyRequestRepository,
)
from app.schemas import (
    AdminReturnRequestDetailResponse,
    AdminReturnRequestResponse,
    PageResponse,
    ReturnApproval,
    ReturnGoodsReceive,
    ReturnInspection,
    ReturnRefundCreate,
    ReturnRequestCreate,
    ReturnRequestDetailResponse,
    ReturnRequestResponse,
    ServiceRequestNote,
    ServiceRequestRejection,
)

from .actor import ADMIN_ONLY, CUSTOMER_ONLY, STAFF_OR_ADMIN, Actor, require_role
from .base import BaseService, utc_now
from .catalog import ProductVariantService, normalize_serial_number
from .exceptions import BusinessRuleError, ConflictError, NotFoundError, PaymentGatewayError
from .payment import PaymentService
from .ports import PaymentGateway
from .promotion import money
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
from .warranty_period import vietnam_date

PENDING = "Pending"
APPROVED = "Approved"
REJECTED = "Rejected"
RECEIVING = "Receiving"
PROCESSING = "Processing"
COMPLETED = "Completed"
CANCELLED = "Cancelled"
TYPE_RETURN = "Return"
TYPE_EXCHANGE = "Exchange"
# Yêu cầu bị từ chối/hủy không giữ số lượng của dòng đơn.
RELEASED_STATUSES = (REJECTED, CANCELLED)
# Staff/Admin từ chối trước khi hàng về; sau khi nhận hàng (Processing) quyết định thuộc Admin.
REJECTABLE_BEFORE_RECEIPT = (PENDING, APPROVED, RECEIVING)

DELIVERED_ORDER_STATUSES = ("Delivered", "Completed")
SERIAL_SOLD = "Sold"
SERIAL_RETURNED = "Returned"
SERIAL_AVAILABLE = "Available"
TX_SUCCESS = "Success"
TX_PENDING = "Pending"
REFUND_ACTIVE_STATUSES = ("Pending", "Success")  # giao dịch đang giữ/đã hoàn tiền: không tạo thêm

REQUEST_CODE_PREFIX = "DT"
RETURN_NOTIFICATION_TYPE = "Return"
REFERENCE_TYPE = "ReturnRequest"
CREATE_FIELDS = frozenset({"OrderItemId", "RequestType", "ProductSerialId", "Quantity", "Reason", "Attachments"})
FIELD_CODE = "return_field_not_allowed"
# Cấu hình ứng dụng (biến môi trường, theo cùng cách với SePaySettings.from_env).
RETURN_WINDOW_ENV = "RETURN_WINDOW_DAYS"
DEFAULT_RETURN_WINDOW_DAYS = 7
_ZERO = Decimal("0.00")
_DATE_FORMAT = "%d/%m/%Y"
_TYPE_LABELS = {TYPE_RETURN: "trả hàng", TYPE_EXCHANGE: "đổi hàng"}


@dataclass(frozen=True)
class ReturnPolicy:
    """Chính sách đổi trả (chưa được chốt: mặc định không cấu hình → không tiếp nhận yêu cầu mới).

    ``window_days``: số ngày (>= 1) được gửi yêu cầu, tính ngày giao (lịch Việt Nam) là ngày thứ nhất.
    """

    window_days: int | None = None

    def __post_init__(self) -> None:
        days = self.window_days
        if days is not None and (isinstance(days, bool) or not isinstance(days, int) or days < 1):
            raise ValueError("window_days phải là số nguyên >= 1")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ReturnPolicy":
        """Đọc RETURN_WINDOW_DAYS; không khai báo/để trống → DEFAULT_RETURN_WINDOW_DAYS (7). Sai định dạng → ValueError."""
        env = os.environ if env is None else env
        raw = (env.get(RETURN_WINDOW_ENV) or "").strip()
        if not raw:
            return cls(window_days=DEFAULT_RETURN_WINDOW_DAYS)
        try:
            days = int(raw)
        except ValueError:
            raise ValueError(f"{RETURN_WINDOW_ENV} phải là số nguyên >= 1") from None
        return cls(window_days=days)


def return_deadline(delivered_at: datetime, window_days: int) -> date:
    """Ngày cuối được gửi yêu cầu (tính cả ngày này)."""
    return vietnam_date(delivered_at) + timedelta(days=window_days - 1)


def historical_value(item: OrderItem, already: int, quantity: int) -> Decimal:
    """Giá trị lịch sử (LineTotal: đã trừ giảm giá phân bổ, không gồm phí vận chuyển) của ``quantity`` đơn vị tiếp theo
    sau ``already`` đơn vị đã tính. Phân bổ lũy kế nên tổng các lần trả bằng đúng LineTotal (không lệch do làm tròn)."""
    if already < 0 or quantity < 1 or already + quantity > item.Quantity:
        raise BusinessRuleError("Số lượng tính tiền vượt số lượng của dòng đơn", code="return_quantity_exceeded")
    line_total, line_quantity = item.LineTotal, Decimal(item.Quantity)
    return money(line_total * (already + quantity) / line_quantity) - money(line_total * already / line_quantity)


class ReturnService(BaseService):
    def __init__(
        self,
        session: Session,
        *,
        policy: ReturnPolicy | None = None,
        gateway: PaymentGateway | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(session, clock=clock)
        self.policy = policy or ReturnPolicy()
        self.requests = ReturnRequestRepository(session)
        self.attachments = ServiceRequestAttachmentRepository(session)
        self.histories = ServiceRequestHistoryRepository(session)
        self.order_items = OrderItemRepository(session)
        self.orders = OrderRepository(session)
        self.variants = ProductVariantRepository(session)
        self.serials = ProductSerialRepository(session)
        self.warranty_requests = WarrantyRequestRepository(session)
        self.transactions = PaymentTransactionRepository(session)
        self.users = UserRepository(session)
        self.variant_service = ProductVariantService(session, clock=clock)
        self.notifications = NotificationService(session, clock=clock)
        self.payments = PaymentService(session, gateway=gateway, clock=clock)

    # ================================================================== Customer

    def create_return_request(self, actor: Actor, data: ReturnRequestCreate) -> ReturnRequestDetailResponse:
        """Customer gửi yêu cầu đổi/trả cho hàng thuộc đơn đã giao của mình, trong thời hạn đã cấu hình."""
        require_role(actor, *CUSTOMER_ONLY)
        values = allowed_values(data, CREATE_FIELDS, code="return_field_not_allowed")
        request_type = values.get("RequestType")
        if request_type not in RETURN_REQUEST_TYPES:
            raise BusinessRuleError("Loại yêu cầu chỉ gồm Return hoặc Exchange", code="invalid_return_type")
        quantity = values.get("Quantity", 1)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise BusinessRuleError("Số lượng phải là số nguyên dương", code="invalid_return_quantity")
        reason = required_text(values.get("Reason"), code="return_reason_required", message="Cần ghi lý do đổi/trả")
        attachments = validate_attachments(values.get("Attachments"))
        order_item_id = values.get("OrderItemId")
        serial_id = values.get("ProductSerialId")
        with self.transaction():
            item = self.order_items.get_by_id_and_customer(order_item_id, actor.user_id) if order_item_id else None
            if item is None:  # không tồn tại hoặc thuộc đơn của khách khác: không tiết lộ
                raise NotFoundError("Không tìm thấy dòng đơn hàng", code="order_item_not_found")
            order = self.orders.get_by_id_for_update(item.OrderId)
            if order is None or order.OrderStatus not in DELIVERED_ORDER_STATUSES:
                raise BusinessRuleError("Chỉ đổi/trả sản phẩm thuộc đơn hàng đã giao", code="return_order_not_delivered")
            self._check_window(order)
            variant = self.variants.get_by_id(item.ProductVariantId)
            if variant is None:
                raise NotFoundError("Không tìm thấy sản phẩm của dòng đơn", code="product_not_found")
            serial = self._customer_serial(item, serial_id, serial_tracked=variant.IsSerialTracked)
            if serial is not None:
                if quantity != 1:
                    raise BusinessRuleError("Mỗi serial là một đơn vị hàng (Quantity = 1)", code="invalid_return_quantity")
                existing = self.requests.get_open_by_product_serial(serial.ProductSerialId)
                if existing is not None:
                    raise ConflictError(f"Serial/IMEI đang có yêu cầu đổi/trả {existing.RequestCode}",
                                        code="return_request_open")
                if self.warranty_requests.get_open_by_product_serial(serial.ProductSerialId) is not None:
                    raise ConflictError("Serial/IMEI đang có yêu cầu bảo hành chưa xử lý xong",
                                        code="serial_has_open_warranty")
                if serial.Status != SERIAL_SOLD:
                    raise BusinessRuleError("Serial/IMEI không còn ở trạng thái đã bán cho khách hàng",
                                            code="serial_not_with_customer")
            else:
                if self.warranty_requests.get_open_by_order_item_without_serial(item.OrderItemId) is not None:
                    raise ConflictError("Sản phẩm đang có yêu cầu bảo hành chưa xử lý xong",
                                        code="item_has_open_warranty")
                remaining = item.Quantity - self._held_quantity(item)
                if quantity > remaining:
                    raise BusinessRuleError(f"Số lượng vượt số còn có thể đổi/trả của dòng đơn ({max(remaining, 0)})",
                                            code="return_quantity_exceeded")
            now = self.now()
            request = self.requests.create(
                {
                    "RequestCode": generate_request_code(REQUEST_CODE_PREFIX, now, self.requests.exists_by_code,
                                                         failure_code="return_request_code_generation_failed"),
                    "CustomerId": actor.user_id,
                    "OrderItemId": item.OrderItemId,
                    "ProductSerialId": serial.ProductSerialId if serial else None,
                    "Quantity": quantity,
                    "RequestType": request_type,
                    "Reason": reason,
                    "Status": PENDING,
                    "RequestedAt": now,
                }
            )
            self.requests.flush()
            for url, file_type in attachments:
                self.attachments.create({"ReturnRequestId": request.ReturnRequestId, "FileUrl": url,
                                         "FileType": file_type, "UploadedAt": now})
            self._history(request, actor.user_id, None, PENDING,
                          f"Khách hàng gửi yêu cầu {_TYPE_LABELS[request_type]} ({quantity} sản phẩm).")
            self._notify_customer(request, "Đã nhận yêu cầu đổi/trả",
                                  f"Yêu cầu {request.RequestCode} đã được ghi nhận và chờ xem xét.")
            return self._customer_detail(request)

    def cancel_return_request(
        self, actor: Actor, request_id: uuid.UUID, data: ServiceRequestNote | None = None
    ) -> ReturnRequestDetailResponse:
        """Customer hủy yêu cầu của mình khi còn Pending (chưa được tiếp nhận)."""
        require_role(actor, *CUSTOMER_ONLY)
        note, _ = step_notes(data, allowed=frozenset({"Note"}), code=FIELD_CODE)
        with self.transaction():
            request, _, _ = self._lock(request_id, customer_id=actor.user_id)
            if request.Status != PENDING:
                raise BusinessRuleError("Chỉ hủy được yêu cầu đang chờ xem xét", code="return_not_cancellable")
            request.Status = CANCELLED
            self._history(request, actor.user_id, PENDING, CANCELLED, compose_note("Khách hàng hủy yêu cầu.", note))
            return self._customer_detail(request)

    def list_my_return_requests(
        self, actor: Actor, *, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> PageResponse[ReturnRequestResponse]:
        require_role(actor, *CUSTOMER_ONLY)
        offset, limit = self._page_args(page, page_size)
        items = self.requests.list_requests(customer_id=actor.user_id, status=status, offset=offset, limit=limit)
        return PageResponse[ReturnRequestResponse](
            Items=[ReturnRequestResponse.model_validate(r) for r in items],
            Total=self.requests.count_requests(customer_id=actor.user_id, status=status),
            Page=page,
            PageSize=page_size,
        )

    def get_my_return_request(self, actor: Actor, request_id: uuid.UUID) -> ReturnRequestDetailResponse:
        require_role(actor, *CUSTOMER_ONLY)
        if self.requests.get_by_id_and_customer(request_id, actor.user_id) is None:
            raise NotFoundError("Không tìm thấy yêu cầu đổi/trả", code="return_request_not_found")
        return ReturnRequestDetailResponse.model_validate(self.requests.get_detail(request_id))

    # ================================================================== Staff / Admin: xem

    def list_return_requests(
        self,
        actor: Actor,
        *,
        status: str | None = None,
        request_type: str | None = None,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[AdminReturnRequestResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        offset, limit = self._page_args(page, page_size)
        filters = {"customer_id": customer_id, "assigned_staff_id": assigned_staff_id, "status": status,
                   "request_type": request_type}
        items = self.requests.list_requests(**filters, offset=offset, limit=limit)
        return PageResponse[AdminReturnRequestResponse](
            Items=[AdminReturnRequestResponse.model_validate(r) for r in items],
            Total=self.requests.count_requests(**filters),
            Page=page,
            PageSize=page_size,
        )

    def get_return_request(self, actor: Actor, request_id: uuid.UUID) -> AdminReturnRequestDetailResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        request = self.requests.get_detail(request_id)
        if request is None:
            raise NotFoundError("Không tìm thấy yêu cầu đổi/trả", code="return_request_not_found")
        return AdminReturnRequestDetailResponse.model_validate(request)

    # ================================================================== Staff: xem xét / nhận hàng / kiểm tra

    def accept_return_request(
        self, actor: Actor, request_id: uuid.UUID, data: ServiceRequestNote | None = None
    ) -> AdminReturnRequestDetailResponse:
        """Staff/Admin tiếp nhận yêu cầu (Pending → Approved); chưa nhận hàng, chưa có quyết định về tiền."""
        require_role(actor, *STAFF_OR_ADMIN)
        note, internal_note = step_notes(data, code=FIELD_CODE)
        with self.transaction():
            request, _, _ = self._lock(request_id)
            self._require_status(request, PENDING)
            request.Status = APPROVED
            if request.AssignedStaffId is None:
                request.AssignedStaffId = actor.user_id
            self._history(request, actor.user_id, PENDING, APPROVED, compose_note("Tiếp nhận yêu cầu đổi/trả.", note),
                          internal_note=internal_note)
            self._notify_customer(request, "Yêu cầu đổi/trả được tiếp nhận",
                                  f"Yêu cầu {request.RequestCode} đã được tiếp nhận; cửa hàng sẽ liên hệ nhận hàng.")
            return self._admin_detail(request)

    def reject_return_request(
        self, actor: Actor, request_id: uuid.UUID, data: ServiceRequestRejection
    ) -> AdminReturnRequestDetailResponse:
        """Từ chối (bắt buộc lý do). Trước khi hàng về: Staff/Admin. Sau khi nhận hàng: chỉ Admin, trả hàng cho khách."""
        require_role(actor, *STAFF_OR_ADMIN)
        values = allowed_values(data, frozenset({"Reason", "InternalNote"}), code=FIELD_CODE)
        reason = required_text(values.get("Reason"), code="rejection_reason_required", message="Cần ghi lý do từ chối")
        internal_note = optional_text(values.get("InternalNote"))
        with self.transaction():
            request, item, _ = self._lock(request_id)
            old = request.Status
            if old == PROCESSING:
                require_role(actor, *ADMIN_ONLY)  # quyết định sau kiểm tra thực tế thuộc Admin
                if request.CompensationApprovedAt is not None:
                    raise BusinessRuleError("Yêu cầu đã được duyệt", code="return_already_approved")
                if request.ProductSerialId is not None:
                    serial = self._lock_request_serial(request, item, expected_status=SERIAL_RETURNED)
                    serial.Status = SERIAL_SOLD  # trả lại thiết bị cho khách
                event = f"Từ chối yêu cầu, trả lại hàng cho khách hàng. Lý do: {reason}"
            elif old in REJECTABLE_BEFORE_RECEIPT:
                event = f"Từ chối yêu cầu. Lý do: {reason}"
            else:
                raise BusinessRuleError(f"Yêu cầu đang ở trạng thái {old}, không thể từ chối",
                                        code="invalid_return_transition")
            request.Status = REJECTED
            request.DecisionReason = reason
            self._history(request, actor.user_id, old, REJECTED, event, internal_note=internal_note)
            self._notify_customer(request, "Yêu cầu đổi/trả bị từ chối",
                                  f"Yêu cầu {request.RequestCode} bị từ chối. Lý do: {reason}")
            return self._admin_detail(request)

    def start_return_receiving(
        self, actor: Actor, request_id: uuid.UUID, data: ServiceRequestNote | None = None
    ) -> AdminReturnRequestDetailResponse:
        """Điều phối nhận hàng từ khách: Approved → Receiving (hàng chưa về cửa hàng)."""
        require_role(actor, *STAFF_OR_ADMIN)
        note, internal_note = step_notes(data, code=FIELD_CODE)
        with self.transaction():
            request, _, _ = self._lock(request_id)
            self._require_status(request, APPROVED)
            request.Status = RECEIVING
            self._history(request, actor.user_id, APPROVED, RECEIVING, compose_note("Điều phối nhận hàng.", note),
                          internal_note=internal_note)
            self._notify_customer(request, "Đang điều phối nhận hàng đổi/trả",
                                  f"Yêu cầu {request.RequestCode}: cửa hàng đang điều phối nhận hàng.")
            return self._admin_detail(request)

    def receive_return_goods(
        self, actor: Actor, request_id: uuid.UUID, data: ReturnGoodsReceive
    ) -> AdminReturnRequestDetailResponse:
        """Staff xác nhận hàng thực tế đã về (quét đúng serial): Receiving → Processing; serial Sold → Returned."""
        require_role(actor, *STAFF_OR_ADMIN)
        values = allowed_values(data, frozenset({"SerialNumber", "Note", "InternalNote"}), code=FIELD_CODE)
        scanned = values.get("SerialNumber")
        note, internal_note = optional_text(values.get("Note")), optional_text(values.get("InternalNote"))
        with self.transaction():
            request, item, _ = self._lock(request_id)
            self._require_status(request, RECEIVING)
            if request.ProductSerialId is not None:
                if not scanned:
                    raise BusinessRuleError("Cần quét Serial/IMEI của hàng nhận về", code="return_serial_required")
                serial = self._lock_request_serial(request, item, expected_status=SERIAL_SOLD)
                if normalize_serial_number(scanned) != serial.SerialNumber:
                    raise BusinessRuleError("Serial/IMEI nhận về không khớp yêu cầu", code="return_serial_mismatch")
                serial.Status = SERIAL_RETURNED
            elif scanned:
                raise BusinessRuleError("Sản phẩm không quản lý Serial/IMEI", code="serial_not_applicable")
            request.ReceivedAt = self.now()
            request.Status = PROCESSING
            self._history(request, actor.user_id, RECEIVING, PROCESSING,
                          compose_note(f"Đã nhận hàng thực tế ({request.Quantity} sản phẩm), chờ kiểm tra.", note),
                          internal_note=internal_note)
            self._notify_customer(request, "Cửa hàng đã nhận hàng đổi/trả",
                                  f"Yêu cầu {request.RequestCode}: cửa hàng đã nhận hàng và đang kiểm tra.")
            return self._admin_detail(request)

    def inspect_return_goods(
        self, actor: Actor, request_id: uuid.UUID, data: ReturnInspection
    ) -> AdminReturnRequestDetailResponse:
        """Staff ghi nhận kết quả kiểm tra (số đạt/hỏng, đánh giá hư hại); hệ thống tính số tiền và căn cứ (chờ Admin)."""
        require_role(actor, *STAFF_OR_ADMIN)
        values = allowed_values(data, frozenset({"RestockedQuantity", "DamagedQuantity", "DamageAssessment",
                                                 "InternalNote"}), code=FIELD_CODE)
        internal_note = optional_text(values.get("InternalNote"))
        restocked, damaged = values.get("RestockedQuantity"), values.get("DamagedQuantity")
        for value in (restocked, damaged):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BusinessRuleError("Số lượng kiểm tra phải là số nguyên không âm", code="invalid_inspection_quantity")
        assessment = optional_text(values.get("DamageAssessment"))
        if damaged and not assessment:
            raise BusinessRuleError("Cần mô tả tình trạng hư hại", code="damage_assessment_required")
        with self.transaction():
            request, item, _ = self._lock(request_id)
            self._require_status(request, PROCESSING)
            if request.ReceivedAt is None:
                raise BusinessRuleError("Chưa nhận hàng thực tế", code="return_not_received")
            if request.RestockedQuantity is not None:
                raise BusinessRuleError("Yêu cầu đã có kết quả kiểm tra", code="return_already_inspected")
            if restocked + damaged != request.Quantity:
                raise BusinessRuleError(f"Số đạt + số hỏng phải bằng {request.Quantity}",
                                        code="return_inspection_quantity_mismatch")
            request.RestockedQuantity, request.DamagedQuantity = restocked, damaged
            request.DamageAssessment = assessment
            amount, basis = self._assessment(request, item)
            request.CompensationAmount, request.CompensationBasis = amount, basis
            summary = f"Kiểm tra thực tế: đạt {restocked}, hỏng {damaged}."
            money_note = (f" Số tiền dự kiến: {amount} (chờ Admin duyệt)." if amount is not None
                          else " Chưa tính được số tiền: có hàng hỏng, chưa có chính sách khấu trừ.")
            self._history(request, actor.user_id, PROCESSING, PROCESSING, compose_note(summary + money_note, assessment),
                          internal_note=internal_note)
            for admin in self.users.list_users(role="Admin", account_status="Active"):
                self.notifications.notify(
                    admin.UserId,
                    title="Yêu cầu đổi/trả chờ duyệt",
                    content=f"Yêu cầu {request.RequestCode}: {summary}",
                    notification_type=RETURN_NOTIFICATION_TYPE,
                    reference_type=REFERENCE_TYPE,
                    reference_id=request.ReturnRequestId,
                )
            return self._admin_detail(request)

    # ================================================================== Admin: duyệt số tiền

    def approve_return_request(
        self, actor: Actor, request_id: uuid.UUID, data: ReturnApproval
    ) -> AdminReturnRequestDetailResponse:
        """Admin duyệt đúng số tiền hệ thống tính lại; nhập lại tồn hàng đạt trong cùng transaction (một lần)."""
        require_role(actor, *ADMIN_ONLY)
        values = allowed_values(data, frozenset({"CompensationAmount", "Note", "InternalNote"}), code=FIELD_CODE)
        approved_amount = values.get("CompensationAmount")
        note, internal_note = optional_text(values.get("Note")), optional_text(values.get("InternalNote"))
        with self.transaction():
            request, item, _ = self._lock(request_id)
            self._require_status(request, PROCESSING)
            if request.RestockedQuantity is None:
                raise BusinessRuleError("Chưa có kết quả kiểm tra hàng", code="return_not_inspected")
            if request.CompensationApprovedAt is not None:
                raise BusinessRuleError("Yêu cầu đã được duyệt", code="return_already_approved")
            if request.RequestType == TYPE_EXCHANGE:
                raise BusinessRuleError(
                    "Chưa có quy tắc giao hàng đổi (xuất serial mới, bảo hành của máy đổi); chưa thể duyệt đổi hàng",
                    code="exchange_fulfillment_policy_missing",
                )
            if request.DamagedQuantity:
                raise BusinessRuleError("Có hàng hỏng nhưng chưa có chính sách khấu trừ; chưa thể duyệt số tiền",
                                        code="return_damage_policy_missing")
            amount, basis = self._assessment(request, item)
            if approved_amount is None or Decimal(approved_amount) != amount:
                raise BusinessRuleError(f"Số tiền duyệt phải đúng số tiền hệ thống tính: {amount}",
                                        code="compensation_amount_mismatch")
            stock_note = self._restock(request, item)
            now = self.now()
            request.CompensationAmount, request.CompensationBasis = amount, basis
            request.CompensationApprovedAt = now
            request.CompensationApprovedByUserId = actor.user_id
            self._history(request, actor.user_id, PROCESSING, PROCESSING,
                          compose_note(f"Đã duyệt số tiền hoàn {amount}.", note),
                          internal_note=compose_note(stock_note, internal_note))
            if amount == _ZERO:
                self._complete(request, actor.user_id, "Hoàn tất: không có số tiền cần hoàn.")
            else:
                self._notify_customer(request, "Yêu cầu trả hàng được duyệt",
                                      f"Yêu cầu {request.RequestCode}: số tiền hoàn {amount} đang được xử lý.")
            return self._admin_detail(request)

    # ================================================================== Hoàn tiền (PaymentService)

    def refund_return_request(
        self, actor: Actor, request_id: uuid.UUID, data: ReturnRefundCreate | None = None
    ) -> AdminReturnRequestDetailResponse:
        """Tạo giao dịch hoàn tiền cho yêu cầu trả hàng đã nhận, kiểm tra đạt và được Admin duyệt (không tự động).

        Dùng PaymentService (RefundOfPaymentTransactionId, giới hạn theo đơn/khoản nguồn; giao dịch luôn tạo Pending,
        ghi người tạo). Cổng được gọi SAU khi commit; cổng trả Success thì hoàn tất. Hoàn trực tiếp (không qua cổng)
        hoặc kết quả chưa rõ: yêu cầu chưa hoàn tất — Admin khác người tạo xác nhận giao dịch (resolve_pending_refund),
        sau đó confirm_return_refund.
        """
        require_role(actor, *STAFF_OR_ADMIN)
        if self.in_transaction():
            raise BusinessRuleError("Hoàn tiền phải là use case độc lập", code="refund_requires_own_transaction")
        values = (allowed_values(data, frozenset({"PaymentTransactionId"}), code="return_field_not_allowed")
                  if data is not None else {})
        with self.transaction():
            request, _, order = self._lock(request_id)
            if request.RequestType != TYPE_RETURN:
                raise BusinessRuleError("Chỉ yêu cầu trả hàng mới hoàn tiền", code="refund_requires_return_request")
            if request.ReceivedAt is None:
                raise BusinessRuleError("Hàng chưa được nhận thực tế, chưa thể hoàn tiền", code="return_not_received")
            self._require_status(request, PROCESSING)
            if request.CompensationApprovedAt is None:
                raise BusinessRuleError("Số tiền hoàn chưa được Admin duyệt", code="return_not_approved")
            if request.RefundPaymentTransactionId is not None:
                linked = self.transactions.get_by_id_for_update(request.RefundPaymentTransactionId)
                if linked is not None and linked.Status in REFUND_ACTIVE_STATUSES:
                    raise ConflictError(f"Yêu cầu đã có giao dịch hoàn tiền ({linked.Status})", code="return_refund_exists")
            refund, dispatch = self.payments.create_return_refund(
                order, request.CompensationAmount, values.get("PaymentTransactionId"), created_by=actor.user_id)
            request.RefundPaymentTransactionId = refund.PaymentTransactionId
            waiting = "" if dispatch is not None else (
                " Hoàn trực tiếp không qua cổng: chờ Admin khác người tạo xác nhận kèm bằng chứng.")
            self._history(request, actor.user_id, PROCESSING, PROCESSING, f"Đang hoàn tiền {refund.Amount}.",
                          internal_note=(f"Giao dịch Refund {refund.PaymentTransactionId} ({refund.Status}), khoản nguồn "
                                         f"{refund.RefundOfPaymentTransactionId}.{waiting}"))
        if dispatch is not None:
            try:
                result = dispatch()  # ngoài transaction, đúng một lần cho giao dịch vừa tạo
            except PaymentGatewayError:
                # Lỗi/timeout: KHÔNG coi là thất bại — giao dịch giữ Pending (vẫn giữ tiền), không tạo giao dịch mới.
                self._note_refund_outcome(actor, request_id, "Chưa xác định kết quả hoàn tiền từ cổng (lỗi/timeout); "
                                          "giao dịch giữ Pending. Tra cứu cổng và đối soát trước khi thử lại.")
                raise
            if result.Status == TX_SUCCESS:
                self._complete_if_refunded(actor, request_id)
            elif result.Status == TX_PENDING:
                self._note_refund_outcome(actor, request_id, "Cổng chưa xác nhận hoàn tiền (Pending); chờ đối soát "
                                          "hoặc xác nhận chuyển khoản thủ công.")
            else:
                self._note_refund_outcome(actor, request_id, f"Cổng trả kết quả hoàn tiền {result.Status}; "
                                          "có thể tạo lại giao dịch hoàn tiền.")
        return self.get_return_request(actor, request_id)

    def confirm_return_refund(self, actor: Actor, request_id: uuid.UUID) -> AdminReturnRequestDetailResponse:
        """Hoàn tất yêu cầu khi giao dịch hoàn tiền đã liên kết có kết quả Success (sau đối soát/chuyển khoản thủ công)."""
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            request, _, _ = self._lock(request_id)
            self._require_status(request, PROCESSING)
            if request.RefundPaymentTransactionId is None:
                raise BusinessRuleError("Yêu cầu chưa có giao dịch hoàn tiền", code="return_refund_missing")
            refund = self.transactions.get_by_id_for_update(request.RefundPaymentTransactionId)
            if refund is None:
                raise BusinessRuleError("Không tìm thấy giao dịch hoàn tiền đã liên kết", code="return_refund_missing")
            if refund.Status == TX_PENDING:
                raise BusinessRuleError(
                    "Giao dịch hoàn tiền chưa có kết quả xác nhận (Pending); tra cứu cổng/đối soát trước khi thử lại",
                    code="return_refund_pending",
                )
            if refund.Status != TX_SUCCESS:
                raise BusinessRuleError(f"Giao dịch hoàn tiền không thành công ({refund.Status}); có thể tạo lại giao dịch",
                                        code="return_refund_failed")
            self._complete(request, actor.user_id, "Hoàn tất: giao dịch hoàn tiền đã thành công.")
            return self._admin_detail(request)

    # ================================================================== helpers

    def _check_window(self, order: Order) -> None:
        if self.policy.window_days is None:
            raise BusinessRuleError("Chưa cấu hình chính sách thời hạn đổi/trả; chưa thể tiếp nhận yêu cầu",
                                    code="return_policy_not_configured")
        if order.DeliveredAt is None:
            raise BusinessRuleError("Chưa ghi nhận thời điểm giao hàng thành công", code="delivery_not_recorded")
        if order.DeliveredAt.tzinfo is None or order.DeliveredAt > self.now():
            raise BusinessRuleError("Thời điểm giao hàng không hợp lệ (thiếu múi giờ hoặc sau thời điểm hiện tại); "
                                    "cần kiểm tra dữ liệu đơn hàng", code="invalid_delivery_time")
        deadline = return_deadline(order.DeliveredAt, self.policy.window_days)
        if vietnam_date(self.now()) > deadline:
            raise BusinessRuleError(f"Đã quá thời hạn đổi/trả (ngày cuối: {deadline.strftime(_DATE_FORMAT)})",
                                    code="return_window_expired")

    def _customer_serial(self, item: OrderItem, serial_id: uuid.UUID | None, *, serial_tracked: bool
                         ) -> ProductSerial | None:
        if not serial_tracked:
            if serial_id is not None:
                raise BusinessRuleError("Sản phẩm không quản lý Serial/IMEI", code="serial_not_applicable")
            return None
        if serial_id is None:
            raise BusinessRuleError("Cần chọn Serial/IMEI của thiết bị cần đổi/trả", code="return_serial_required")
        serial = self.serials.get_by_id_for_update(serial_id)
        if (serial is None or serial.OrderItemId != item.OrderItemId
                or serial.ProductVariantId != item.ProductVariantId):
            raise BusinessRuleError("Serial/IMEI không thuộc dòng đơn hàng này", code="serial_not_in_order_item")
        return serial

    def _held_quantity(self, item: OrderItem) -> int:
        """Số lượng của dòng đơn đã nằm trong yêu cầu đổi/trả (trừ yêu cầu bị từ chối/hủy)."""
        return sum(r.Quantity for r in self.requests.list_by_order_item(item.OrderItemId)
                   if r.Status not in RELEASED_STATUSES)

    def _assessment(self, request: ReturnRequest, item: OrderItem) -> tuple[Decimal | None, dict[str, Any]]:
        """Số tiền + căn cứ theo giá trị lịch sử của dòng đơn (không dùng giá catalog hiện tại)."""
        prior = sum(r.Quantity for r in self.requests.list_by_order_item(item.OrderItemId)
                    if r.ReturnRequestId != request.ReturnRequestId and r.RequestType == TYPE_RETURN
                    and r.CompensationApprovedAt is not None)
        basis: dict[str, Any] = {
            "Source": "OrderItems (giá trị lịch sử của dòng đơn: LineTotal đã trừ giảm giá phân bổ)",
            "OrderItemId": str(item.OrderItemId),
            "LineQuantity": item.Quantity,
            "UnitPrice": str(item.UnitPrice),
            "LineDiscountAmount": str(item.DiscountAmount),
            "LineTotal": str(item.LineTotal),
            "Quantity": request.Quantity,
            "RestockedQuantity": request.RestockedQuantity,
            "DamagedQuantity": request.DamagedQuantity,
            "ShippingFeeRefunded": False,
            "CalculatedAt": self.now().isoformat(),
        }
        if request.RequestType == TYPE_EXCHANGE:
            old_value = historical_value(item, 0, request.Quantity)
            basis.update({
                "Formula": "Chênh lệch = Giá sản phẩm mới − Giá sản phẩm cũ",
                "NewProduct": "Cùng biến thể của dòng đơn (giá theo giá trị lịch sử)",
                "OldValue": str(old_value),
                "NewValue": str(old_value),
                "Difference": str(_ZERO),
            })
            return _ZERO, basis
        basis.update({
            "Formula": "Tiền dự kiến hoàn = Giá trị hàng đủ điều kiện trả − Khấu trừ theo chính sách",
            "PreviouslyApprovedQuantity": prior,
            "Deductions": [],
            "DeductionPolicy": "Chưa có chính sách khấu trừ/phí",
        })
        if request.DamagedQuantity:
            basis.update({"EligibleValue": None, "CompensationAmount": None,
                          "Pending": "Có hàng hỏng: chưa có chính sách khấu trừ, chưa tính số tiền"})
            return None, basis
        value = historical_value(item, prior, request.Quantity)
        basis.update({"EligibleValue": str(value), "CompensationAmount": str(value)})
        return value, basis

    def _restock(self, request: ReturnRequest, item: OrderItem) -> str:
        """Nhập lại tồn hàng đạt (biến thể khóa trước serial); serial Returned → Available, bỏ gắn đơn để bán lại.

        Không đổi ngày bảo hành của serial; liên kết đơn gốc còn ở ReturnRequests (ProductSerialId, OrderItemId).
        Trả về mô tả cho lịch sử nội bộ.
        """
        if request.RestockedQuantity:
            self.variant_service.change_stock({item.ProductVariantId: request.RestockedQuantity})
        described = f"Nhập lại tồn {request.RestockedQuantity} sản phẩm (dòng đơn gốc {item.OrderItemId})."
        if request.ProductSerialId is not None:
            serial = self._lock_request_serial(request, item, expected_status=SERIAL_RETURNED)
            serial.Status, serial.OrderItemId = SERIAL_AVAILABLE, None
            described = f"{described[:-1]}; serial {serial.SerialNumber} → Available."
        self.serials.flush()
        return described

    def _lock_request_serial(self, request: ReturnRequest, item: OrderItem, *, expected_status: str) -> ProductSerial:
        serial = self.serials.get_by_id_for_update(request.ProductSerialId)
        if serial is None or serial.OrderItemId != item.OrderItemId or serial.Status != expected_status:
            raise BusinessRuleError("Serial/IMEI của yêu cầu không ở trạng thái mong đợi; cần kiểm tra thủ công",
                                    code="serial_state_inconsistent")
        return serial

    def _complete(self, request: ReturnRequest, changed_by: uuid.UUID | None, event: str) -> None:
        request.CompletedAt = self.now()
        request.Status = COMPLETED
        self._history(request, changed_by, PROCESSING, COMPLETED, event)
        self._notify_customer(request, "Yêu cầu đổi/trả đã hoàn tất", f"Yêu cầu {request.RequestCode}: {event}")

    def _complete_if_refunded(self, actor: Actor, request_id: uuid.UUID) -> None:
        """Sau khi cổng xác nhận hoàn tiền thành công: hoàn tất yêu cầu (transaction riêng, gọi lặp không đổi gì)."""
        with self.transaction():
            request, _, _ = self._lock(request_id)
            if request.Status != PROCESSING or request.RefundPaymentTransactionId is None:
                return
            refund = self.transactions.get_by_id_for_update(request.RefundPaymentTransactionId)
            if refund is not None and refund.Status == TX_SUCCESS:
                self._complete(request, actor.user_id, "Hoàn tất: cổng thanh toán xác nhận đã hoàn tiền.")

    def _note_refund_outcome(self, actor: Actor, request_id: uuid.UUID, internal_note: str) -> None:
        """Ghi lịch sử nội bộ về kết quả gọi cổng (transaction riêng, sau khi cổng trả về hoặc lỗi)."""
        with self.transaction():
            request, _, _ = self._lock(request_id)
            self._history(request, actor.user_id, request.Status, request.Status, None, internal=True,
                          internal_note=internal_note)

    def _lock(self, request_id: uuid.UUID, *, customer_id: uuid.UUID | None = None
              ) -> tuple[ReturnRequest, OrderItem, Order]:
        """Khóa theo thứ tự Order → ReturnRequest rồi đọc lại yêu cầu đã khóa."""
        request = (self.requests.get_by_id_and_customer(request_id, customer_id) if customer_id is not None
                   else self.requests.get_by_id(request_id))
        if request is None:
            raise NotFoundError("Không tìm thấy yêu cầu đổi/trả", code="return_request_not_found")
        item = self.order_items.get_by_id(request.OrderItemId)
        if item is None:
            raise NotFoundError("Không tìm thấy dòng đơn hàng", code="order_item_not_found")
        order = self.orders.get_by_id_for_update(item.OrderId)
        if order is None:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        request = self.requests.get_by_id_for_update(request_id)
        if request is None:
            raise NotFoundError("Không tìm thấy yêu cầu đổi/trả", code="return_request_not_found")
        return request, item, order

    @staticmethod
    def _require_status(request: ReturnRequest, expected: str) -> None:
        if request.Status != expected:
            raise BusinessRuleError(
                f"Yêu cầu đang ở trạng thái {request.Status}, không thực hiện được bước này (cần {expected})",
                code="invalid_return_transition",
            )

    def _history(self, request: ReturnRequest, changed_by: uuid.UUID | None, old: str | None, new: str,
                 note: str | None, *, internal_note: str | None = None, internal: bool = False) -> None:
        """Note: khách xem được; internal_note: chỉ Staff/Admin; internal=True: cả dòng chỉ Staff/Admin (không có Note)."""
        self.requests.flush()
        self.histories.create(
            {
                "ReturnRequestId": request.ReturnRequestId,
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

    def _notify_customer(self, request: ReturnRequest, title: str, content: str) -> None:
        self.notifications.notify(request.CustomerId, title=title, content=content,
                                  notification_type=RETURN_NOTIFICATION_TYPE, reference_type=REFERENCE_TYPE,
                                  reference_id=request.ReturnRequestId)

    def _customer_detail(self, request: ReturnRequest) -> ReturnRequestDetailResponse:
        self.requests.flush()
        return ReturnRequestDetailResponse.model_validate(self.requests.get_detail(request.ReturnRequestId))

    def _admin_detail(self, request: ReturnRequest) -> AdminReturnRequestDetailResponse:
        self.requests.flush()
        return AdminReturnRequestDetailResponse.model_validate(self.requests.get_detail(request.ReturnRequestId))
