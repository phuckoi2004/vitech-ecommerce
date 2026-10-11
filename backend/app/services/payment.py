"""Payment service: phương thức thanh toán, giao dịch thanh toán QR/COD và hoàn tiền.

Nguồn nghiệp vụ: docs/business-requirements.md mục 1 (Admin quản lý phương thức thanh toán), 7, 12, 17.
- Số tiền luôn lấy từ Order/database (Decimal), không nhận từ client.
- QR chỉ chuyển Paid khi cổng thanh toán xác nhận (callback đã xác minh); Staff/Admin không tự đánh dấu Paid.
- Callback lặp lại không tạo giao dịch trùng và không đổi kết quả đã ghi nhận.
- Callback thành công đến muộn (đơn đã hủy), thanh toán trùng hoặc sai số tiền: ghi nhận khoản tiền (sai số tiền
  thì không Paid), mở bản ghi đối soát PaymentReconciliations (idempotent theo mã cổng + loại), KHÔNG khôi phục
  đơn, KHÔNG tự hoàn tiền; thông báo Staff/Admin xử lý thủ công.
- COD: OrderService.confirm_cod_delivery ghi Paid + PaymentTransaction khi xác nhận giao hàng và đã thu tiền.
  ``record_cod_payment`` chỉ dùng để bổ sung giao dịch cho đơn COD cũ đã Paid nhưng thiếu giao dịch.
- Refund (thủ công): đơn đã hủy → hoàn tối đa số đã thanh toán; đơn chưa hủy → chỉ phần thu dư. Tổng hoàn
  (gồm cả Refund đang Pending) không vượt số tiền thực nhận.
  Mỗi Refund trỏ tới đúng một khoản Payment gốc thành công của đơn (RefundOfPaymentTransactionId); số còn có thể
  hoàn của từng khoản = Amount − Refund (Success + Pending) của khoản đó; Refund Failed/Cancelled không giữ tiền.
  Khoản Payment gốc giữ Status Success (khoản thu đã xảy ra); không dùng Status Refunded cho khoản gốc.
  Cổng thanh toán được gọi NGOÀI transaction database; kết quả chưa rõ thì giao dịch giữ Pending để đối soát.
- TransactionType chỉ gồm Payment / Refund.
- Hoàn tiền trả hàng (đợt 5.4, ``create_return_refund``): chỉ ReturnService gọi bên trong use case của nó, sau khi
  hàng đã nhận, kiểm tra đạt và Admin đã duyệt số tiền; đơn Delivered/Completed đang Paid; dùng chung cách chọn/khóa
  khoản nguồn và giới hạn số tiền với refund_order (tổng hoàn gồm Pending không vượt số đã thu). Không tự động hoàn.
- Hoàn phần thu vượt của đơn chưa hủy (đợt 5.8): giao dịch Refund liên kết với yêu cầu trả hàng
  (ReturnRequests.RefundPaymentTransactionId) không thuộc phần thu vượt nên không được trừ vào đó; trần tổng vẫn là
  đã thu − mọi Refund Success/Pending.
- Xác nhận Refund (đợt 5.11, phương án D2): mọi giao dịch Refund tạo ra ở Pending, ghi CreatedByUserId (Staff/Admin
  lập). Chỉ hai cách chuyển Success/Failed:
  1. Cổng thanh toán trả kết quả (ResolutionSource = Gateway; bằng chứng là GatewayTransactionCode/ResponseData của
     cổng; không có người xác nhận).
  2. Admin KHÁC người tạo xác nhận thủ công (``resolve_pending_refund``; ResolutionSource = Manual) với mã tham chiếu
     bằng chứng và ghi chú bắt buộc; lưu ResolvedByUserId/ResolvedAt; không ghi đè GatewayTransactionCode/ResponseData.
  Hoàn trực tiếp không qua cổng (ví dụ COD) và cổng không có API hoàn tiền (SePay) chỉ thành Success qua cách 2.
  Pending/Failed không phải đã hoàn: không tính vào tiền đã hoàn, không đổi PaymentStatus.
"""

import logging
import uuid
from dataclasses import dataclass
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import Order, PaymentTransaction
from app.models.payment import EVIDENCE_REFERENCE_MAX_LENGTH, RESOLUTION_SOURCE_GATEWAY, RESOLUTION_SOURCE_MANUAL
from app.models.reconciliation import (
    ISSUE_AMOUNT_MISMATCH,
    ISSUE_DUPLICATE_PAYMENT,
    ISSUE_PAYMENT_AFTER_CANCELLATION,
    ISSUE_UNMATCHED_PAYMENT,
    RECONCILIATION_ISSUE_TYPES,
    RECONCILIATION_OPEN,
    RECONCILIATION_RESOLVED,
    RECONCILIATION_STATUSES,
)
from app.repositories import (
    OrderRepository,
    PaymentMethodRepository,
    PaymentReconciliationRepository,
    PaymentTransactionRepository,
    ReturnRequestRepository,
    UserRepository,
)
from app.schemas import (
    AdminOrderResponse,
    AdminPaymentTransactionResponse,
    PageResponse,
    PaymentMethodCreate,
    PaymentReconciliationResolve,
    PaymentReconciliationResponse,
    PaymentMethodResponse,
    PaymentMethodUpdate,
    PaymentTransactionResponse,
    RefundResolution,
    RefundSourceResponse,
)

from .actor import ADMIN_ONLY, CUSTOMER_ONLY, STAFF_OR_ADMIN, Actor, has_role, require_role
from .base import BaseService, utc_now
from .exceptions import BusinessRuleError, ConflictError, NotFoundError, PaymentGatewayError
from .order import PAYMENT_METHOD_COD, qr_payment_deadline
from .ports import GatewayPaymentResult, GatewayRefundResult, PaymentGateway, QrPaymentRequest
from .service_request import required_text
from .user import NotificationService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BankTransfer:
    """Khoản tiền vào đã xác thực từ webhook ngân hàng (giá trị lấy từ sự kiện đã lưu, không từ client)."""

    reconciliation_key: str  # định danh giao dịch thực tế của cổng (khóa đối soát)
    payment_code: str | None
    amount: Decimal
    response_data: dict[str, Any]
    webhook_event_id: uuid.UUID | None = None

TX_PAYMENT = "Payment"
TX_REFUND = "Refund"
TX_PENDING = "Pending"
TX_SUCCESS = "Success"
TX_FAILED = "Failed"
TX_CANCELLED = "Cancelled"

PAYMENT_PENDING = "Pending"
PAYMENT_PAID = "Paid"
PAYMENT_FAILED = "Failed"
PAYMENT_REFUNDED = "Refunded"

ORDER_PENDING = "Pending"
ORDER_CANCELLED = "Cancelled"
# Đơn không phải COD phải Paid trước Shipping, nên chỉ tạo thanh toán QR trước Shipping.
QR_PAYABLE_ORDER_STATUSES = ("Pending", "Confirmed", "Processing")
QR_PAYABLE_PAYMENT_STATUSES = (PAYMENT_PENDING, PAYMENT_FAILED)
COD_RECORDABLE_ORDER_STATUSES = ("Delivered", "Completed")
# Hoàn tiền trả hàng: đơn đã giao thành công.
RETURN_REFUNDABLE_ORDER_STATUSES = ("Delivered", "Completed")

_CENT = Decimal("0.01")
_ZERO = Decimal("0")
# Refund còn giữ tiền của khoản nguồn: đã hoàn (Success) hoặc đang chờ kết quả (Pending).
# Failed/Cancelled: tiền không được hoàn → không trừ vào số còn có thể hoàn.
REFUND_HOLDING_STATUSES = (TX_PENDING, TX_SUCCESS)
PAYMENT_NOTIFICATION_TYPE = "Payment"


class PaymentService(BaseService):
    def __init__(
        self,
        session: Session,
        *,
        gateway: PaymentGateway | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(session, clock=clock)
        self.gateway = gateway
        self.methods = PaymentMethodRepository(session)
        self.transactions = PaymentTransactionRepository(session)
        self.orders = OrderRepository(session)
        self.users = UserRepository(session)
        self.reconciliations = PaymentReconciliationRepository(session)
        self.returns = ReturnRequestRepository(session)
        self.notifications = NotificationService(session, clock=clock)

    # ==================================================================
    # Phương thức thanh toán (Admin quản lý; khách xem phương thức đang hoạt động)
    # ==================================================================

    def list_payment_methods(self, *, actor: Actor | None = None, active_only: bool = False) -> list[PaymentMethodResponse]:
        """Khách (không cần đăng nhập) chỉ xem phương thức đang hoạt động; xem tất cả cần Staff/Admin."""
        if not active_only:
            require_role(actor, *STAFF_OR_ADMIN)
        items = self.methods.list_methods(is_active=True if active_only else None)
        return [PaymentMethodResponse.model_validate(m) for m in items]

    def get_payment_method(self, payment_method_id: uuid.UUID, *, actor: Actor | None = None) -> PaymentMethodResponse:
        method = self.methods.get_by_id(payment_method_id)
        if method is None or (not method.IsActive and not has_role(actor, *STAFF_OR_ADMIN)):
            raise NotFoundError("Không tìm thấy phương thức thanh toán", code="payment_method_not_found")
        return PaymentMethodResponse.model_validate(method)

    def create_payment_method(self, actor: Actor, data: PaymentMethodCreate) -> PaymentMethodResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            values = data.model_dump(exclude_unset=True)
            if self.methods.exists_by_code(values["Code"]):
                raise ConflictError("Mã phương thức thanh toán đã tồn tại", code="payment_method_code_exists")
            method = self.methods.create(values)
            self.methods.flush()
            return PaymentMethodResponse.model_validate(method)

    def update_payment_method(
        self, actor: Actor, payment_method_id: uuid.UUID, data: PaymentMethodUpdate
    ) -> PaymentMethodResponse:
        """Cập nhật; ẩn phương thức bằng IsActive = false."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            method = self.methods.get_by_id(payment_method_id)
            if method is None:
                raise NotFoundError("Không tìm thấy phương thức thanh toán", code="payment_method_not_found")
            values = data.model_dump(exclude_unset=True)
            if "Code" in values and self.methods.exists_by_code(values["Code"], payment_method_id):
                raise ConflictError("Mã phương thức thanh toán đã tồn tại", code="payment_method_code_exists")
            self.methods.update(method, values)
            self.methods.flush()
            return PaymentMethodResponse.model_validate(method)

    def delete_payment_method(self, actor: Actor, payment_method_id: uuid.UUID) -> None:
        """Xóa phương thức chưa được Order/PaymentTransaction tham chiếu (FK RESTRICT)."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            method = self.methods.get_by_id(payment_method_id)
            if method is None:
                raise NotFoundError("Không tìm thấy phương thức thanh toán", code="payment_method_not_found")
            in_use = self.orders.exists(Order.PaymentMethodId == payment_method_id) or self.transactions.exists(
                PaymentTransaction.PaymentMethodId == payment_method_id
            )
            if in_use:
                raise BusinessRuleError("Phương thức thanh toán đang được sử dụng", code="payment_method_in_use")
            self.methods.delete(method)

    # ==================================================================
    # Thanh toán QR
    # ==================================================================

    def create_qr_payment(self, actor: Actor, order_id: uuid.UUID) -> PaymentTransactionResponse:
        """Customer tạo yêu cầu thanh toán QR cho đơn của chính mình; số tiền = Orders.TotalAmount (server).

        Không gọi cổng thanh toán khi đang giữ khóa Order:
        1. Transaction 1: khóa Order, kiểm tra (chủ đơn, không COD, chờ thanh toán, chưa quá hạn 15 phút).
           Đã có giao dịch Pending kèm QR → trả lại giao dịch đó (retry không tạo giao dịch trùng).
           Đang có giao dịch Pending chưa có QR (yêu cầu khác đang xử lý/bị gián đoạn) → ConflictError;
           khách có thể hủy giao dịch đó (``cancel_qr_payment``) rồi tạo lại.
           Chưa có → ghi giao dịch Pending (chưa có mã cổng/QR) để giữ chỗ và đối soát, commit.
        2. Gọi cổng tạo QR (ngoài transaction). Lỗi → giao dịch giữ chỗ chuyển Cancelled (QR chưa được giao
           cho khách nên không thể được thanh toán), raise PaymentGatewayError.
        3. Transaction 2: khóa lại Order và giao dịch, lưu mã giao dịch cổng + QR. Nếu trong lúc gọi cổng giao dịch
           đã bị hủy hoặc đơn không còn chờ thanh toán: vẫn lưu mã cổng để đối soát nhưng không trả QR.
        Cần xác minh với nhà cung cấp: QR/hosted page có thể truy cập được ngoài dữ liệu trả về cho server không.
        """
        require_role(actor, *CUSTOMER_ONLY)
        if self.in_transaction():
            raise BusinessRuleError(
                "Tạo thanh toán QR phải là use case độc lập", code="qr_payment_requires_own_transaction"
            )
        gateway = self._require_gateway()
        with self.transaction():
            order = self._lock_order(order_id)
            if order.CustomerId != actor.user_id:
                raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
            self._ensure_qr_payable(order)
            validate_amount = getattr(gateway, "validate_payment_amount", None)
            if validate_amount is not None:
                validate_amount(order.TotalAmount)
            pending = self._payments(order.OrderId, status=TX_PENDING)
            ready = [t for t in pending if t.QrData]
            if ready:
                return PaymentTransactionResponse.model_validate(ready[0])
            if pending:
                raise ConflictError(
                    "Yêu cầu thanh toán QR của đơn đang được xử lý; thử lại sau hoặc hủy yêu cầu đang chờ",
                    code="qr_payment_in_progress",
                )
            placeholder = self.transactions.create(
                {
                    "OrderId": order.OrderId,
                    "PaymentMethodId": order.PaymentMethodId,
                    "TransactionType": TX_PAYMENT,
                    "Amount": order.TotalAmount,
                    "Status": TX_PENDING,
                }
            )
            self.transactions.flush()
            transaction_id = placeholder.PaymentTransactionId
            order_code, amount = order.OrderCode, order.TotalAmount

        try:
            request = gateway.create_qr_payment(order_code=order_code, amount=amount)
        except Exception as exc:
            # Không ghi chi tiết lỗi của cổng vào log (có thể chứa thông tin nhạy cảm).
            logger.warning("Tạo yêu cầu thanh toán QR không thành công; giao dịch %s được hủy", transaction_id)
            self._abandon_qr_request(transaction_id)
            raise PaymentGatewayError(
                "Không tạo được yêu cầu thanh toán QR; vui lòng thử lại", code="qr_payment_unavailable"
            ) from exc
        return self._attach_qr(transaction_id, request)

    def handle_payment_callback(self, payload: Mapping[str, Any]) -> PaymentTransactionResponse:
        """Xử lý kết quả thanh toán từ cổng thanh toán (chỉ sau khi đã xác minh chữ ký).

        - Thành công, đúng số tiền: giao dịch Success, PaymentStatus Paid; các yêu cầu QR khác đang chờ của đơn bị hủy.
        - Thành công nhưng đơn đã hủy/hết hạn (đến muộn): giao dịch Success (ghi nhận tiền), PaymentStatus Paid để đơn
          đủ điều kiện hoàn tiền; KHÔNG khôi phục đơn, KHÔNG tự hoàn; mở đối soát PaymentAfterCancellation.
        - Thành công khi đơn đã có khoản Success khác (thanh toán trùng): giao dịch này Success, không ghi đè khoản
          trước; mở đối soát DuplicatePayment; không tự hoàn.
        - Thành công nhưng SAI số tiền: giao dịch giữ nguyên, đơn KHÔNG Paid; mở đối soát AmountMismatch (số tiền kỳ
          vọng/thực nhận, mã cổng, phản hồi đã xác minh), commit rồi raise ``payment_amount_mismatch``.
        - Thất bại: Pending → Failed (callback thất bại sai số tiền: từ chối, không đổi dữ liệu).
        - Gửi lặp: giao dịch đã Success → không đổi gì; đối soát cùng (mã cổng, loại) đã có → không tạo/thông báo thêm.
        Mở đối soát luôn kèm thông báo Staff/Admin.
        """
        result = self._require_gateway().verify_callback(payload)
        amount_mismatch = False
        with self.transaction():
            matches = [
                t for t in self.transactions.list_by_gateway_code(result.gateway_transaction_code)
                if t.TransactionType == TX_PAYMENT
            ]
            if not matches:
                raise NotFoundError("Không tìm thấy giao dịch thanh toán", code="payment_transaction_not_found")
            if len(matches) > 1:
                raise BusinessRuleError("Mã giao dịch cổng thanh toán bị trùng", code="duplicate_gateway_transaction")
            # Thứ tự khóa: Order rồi PaymentTransaction (giống các use case khác).
            order = self._lock_order(matches[0].OrderId)
            transaction = self.transactions.get_by_id_for_update(matches[0].PaymentTransactionId)

            if transaction.Status == TX_SUCCESS:
                return PaymentTransactionResponse.model_validate(transaction)
            if result.amount != transaction.Amount:
                logger.warning(
                    "Callback sai số tiền cho giao dịch %s: kỳ vọng %s, nhận %s",
                    transaction.PaymentTransactionId, transaction.Amount, result.amount,
                )
                if not result.success:
                    raise BusinessRuleError("Số tiền thanh toán không khớp đơn hàng", code="payment_amount_mismatch")
                self._open_reconciliation(
                    order,
                    transaction,
                    ISSUE_AMOUNT_MISMATCH,
                    result,
                    "Thanh toán sai số tiền",
                    f"Đơn hàng {order.OrderCode} nhận {result.amount} thay vì {transaction.Amount}. "
                    "Đơn chưa được ghi nhận đã thanh toán; kiểm tra và xử lý thủ công.",
                )
                amount_mismatch = True
                response = PaymentTransactionResponse.model_validate(transaction)
            else:
                transaction.ResponseData = result.response_data
                if result.success:
                    self._record_successful_payment(order, transaction, result)
                    response = PaymentTransactionResponse.model_validate(transaction)
                else:
                    if transaction.Status == TX_PENDING:
                        transaction.Status = TX_FAILED
                        if order.PaymentStatus == PAYMENT_PENDING:
                            order.PaymentStatus = PAYMENT_FAILED
                    self.transactions.flush()
                    response = PaymentTransactionResponse.model_validate(transaction)
        if amount_mismatch:
            # Bản ghi đối soát đã được commit; báo lỗi để Router không xác nhận thanh toán.
            raise BusinessRuleError("Số tiền thanh toán không khớp đơn hàng", code="payment_amount_mismatch")
        return response

    def _record_successful_payment(
        self,
        order: Order,
        transaction: PaymentTransaction,
        result: GatewayPaymentResult,
        *,
        webhook_event_id: uuid.UUID | None = None,
    ) -> str:
        """Ghi nhận giao dịch thanh toán thành công; trả kết quả: paid / payment_after_cancellation / duplicate_payment."""
        other_success = [
            t for t in self._payments(order.OrderId, status=TX_SUCCESS)
            if t.PaymentTransactionId != transaction.PaymentTransactionId
        ]
        transaction.Status = TX_SUCCESS
        transaction.PaidAt = self.now()
        for other in self._payments(order.OrderId, status=TX_PENDING):
            if other.PaymentTransactionId != transaction.PaymentTransactionId:
                other.Status = TX_CANCELLED
        if order.OrderStatus == ORDER_CANCELLED:
            outcome = self._flag_payment_after_cancellation(order, transaction, result, webhook_event_id)
        elif other_success:
            outcome = self._flag_duplicate_payment(order, transaction, result, webhook_event_id)
        else:
            order.PaymentStatus = PAYMENT_PAID
            self._notify(order, "Thanh toán thành công", f"Đơn hàng {order.OrderCode} đã được thanh toán.")
            outcome = "paid"
        self.transactions.flush()
        return outcome

    def _flag_payment_after_cancellation(
        self, order: Order, transaction: PaymentTransaction, result: GatewayPaymentResult, webhook_event_id: uuid.UUID | None
    ) -> str:
        # Ghi nhận tiền đã nhận (Paid) để đơn đủ điều kiện hoàn thủ công; không khôi phục đơn.
        order.PaymentStatus = PAYMENT_PAID
        self._open_reconciliation(
            order,
            transaction,
            ISSUE_PAYMENT_AFTER_CANCELLATION,
            result,
            "Cần hoàn tiền thủ công",
            f"Đơn hàng {order.OrderCode} đã hủy nhưng nhận được thanh toán {transaction.Amount}. "
            "Kiểm tra và hoàn tiền cho khách hàng.",
            webhook_event_id=webhook_event_id,
        )
        self._notify(
            order,
            "Đã nhận thanh toán",
            f"Đơn hàng {order.OrderCode} đã bị hủy trước khi nhận được thanh toán; cửa hàng sẽ hoàn tiền.",
        )
        return "payment_after_cancellation"

    def _flag_duplicate_payment(
        self, order: Order, transaction: PaymentTransaction, result: GatewayPaymentResult, webhook_event_id: uuid.UUID | None
    ) -> str:
        self._open_reconciliation(
            order,
            transaction,
            ISSUE_DUPLICATE_PAYMENT,
            result,
            "Thanh toán trùng",
            f"Đơn hàng {order.OrderCode} nhận thêm một thanh toán {transaction.Amount}. "
            "Kiểm tra và hoàn khoản thanh toán trùng.",
            webhook_event_id=webhook_event_id,
        )
        return "duplicate_payment"

    def _open_reconciliation(
        self,
        order: Order,
        transaction: PaymentTransaction,
        issue_type: str,
        result: GatewayPaymentResult,
        title: str,
        content: str,
        *,
        webhook_event_id: uuid.UUID | None = None,
    ) -> bool:
        """Mở bản ghi đối soát (khóa idempotency: mã cổng + loại) và thông báo Staff/Admin; đã có thì không tạo lại."""
        if self.reconciliations.get_by_key(result.gateway_transaction_code, issue_type) is not None:
            return False
        self.reconciliations.create(
            {
                "OrderId": order.OrderId,
                "PaymentTransactionId": transaction.PaymentTransactionId,
                "PaymentWebhookEventId": webhook_event_id,
                "IssueType": issue_type,
                "GatewayTransactionCode": result.gateway_transaction_code,
                "ExpectedAmount": transaction.Amount,
                "ReceivedAmount": result.amount,
                "ResponseData": result.response_data,
                "Status": RECONCILIATION_OPEN,
                "CreatedAt": self.now(),
            }
        )
        self._notify_staff(order, title, content)
        return True

    # ==================================================================
    # Giao dịch ngân hàng đã xác thực (webhook SePay) — dùng nội bộ bởi PaymentWebhookService
    # ==================================================================

    def apply_bank_transfer(self, transfer: BankTransfer) -> tuple[str, uuid.UUID | None]:
        """Áp dụng một khoản tiền vào đã được xác thực (chữ ký webhook) và đã lưu bền vững.

        Đối chiếu bằng mã thanh toán do server sinh (PaymentTransactions.GatewayTransactionCode) và số tiền:
        - Không có mã / mã không khớp / khớp nhiều giao dịch → đối soát UnmatchedPayment (không tự chọn đơn).
        - Giao dịch khớp đã Success (mã đã được thanh toán bởi khoản khác) → ghi PaymentTransaction riêng cho
          khoản mới (không ghi đè khoản trước) + đối soát DuplicatePayment/PaymentAfterCancellation.
        - Sai số tiền → đối soát AmountMismatch; giao dịch giữ nguyên, đơn KHÔNG Paid.
        - Đúng số tiền → ghi nhận thành công theo quy trình hiện có (Paid / đến muộn / trùng).
        Không hoàn tiền tự động. Trả (kết quả, PaymentTransactionId liên quan). Phải chạy trong use case gọi nó.
        """
        self.require_enclosing_use_case()
        code = (transfer.payment_code or "").strip() or None
        matches = (
            [t for t in self.transactions.list_by_gateway_code(code) if t.TransactionType == TX_PAYMENT] if code else []
        )
        if len(matches) != 1:
            reason = "không có mã thanh toán" if code is None else (
                "mã thanh toán không khớp giao dịch nào" if not matches else "mã thanh toán khớp nhiều giao dịch"
            )
            self._open_unmatched_reconciliation(transfer, reason)
            return "unmatched", None

        result = GatewayPaymentResult(
            gateway_transaction_code=transfer.reconciliation_key,
            amount=transfer.amount,
            success=True,
            response_data=transfer.response_data,
        )
        order = self._lock_order(matches[0].OrderId)
        transaction = self.transactions.get_by_id_for_update(matches[0].PaymentTransactionId)
        if transaction.Status == TX_SUCCESS:
            extra = self.transactions.create(
                {
                    "OrderId": order.OrderId,
                    "PaymentMethodId": transaction.PaymentMethodId,
                    "TransactionType": TX_PAYMENT,
                    "Amount": transfer.amount,
                    "Status": TX_SUCCESS,
                    "PaidAt": self.now(),
                    "ResponseData": transfer.response_data,
                }
            )
            self.transactions.flush()
            if order.OrderStatus == ORDER_CANCELLED:
                outcome = self._flag_payment_after_cancellation(order, extra, result, transfer.webhook_event_id)
            else:
                outcome = self._flag_duplicate_payment(order, extra, result, transfer.webhook_event_id)
            return outcome, extra.PaymentTransactionId
        if transfer.amount != transaction.Amount:
            self._open_reconciliation(
                order,
                transaction,
                ISSUE_AMOUNT_MISMATCH,
                result,
                "Thanh toán sai số tiền",
                f"Đơn hàng {order.OrderCode} nhận {transfer.amount} thay vì {transaction.Amount}. "
                "Đơn chưa được ghi nhận đã thanh toán; kiểm tra và xử lý thủ công.",
                webhook_event_id=transfer.webhook_event_id,
            )
            return "amount_mismatch", transaction.PaymentTransactionId
        transaction.ResponseData = transfer.response_data
        outcome = self._record_successful_payment(
            order, transaction, result, webhook_event_id=transfer.webhook_event_id
        )
        return outcome, transaction.PaymentTransactionId

    def _open_unmatched_reconciliation(self, transfer: BankTransfer, reason: str) -> None:
        if self.reconciliations.get_by_key(transfer.reconciliation_key, ISSUE_UNMATCHED_PAYMENT) is not None:
            return
        self.reconciliations.create(
            {
                "OrderId": None,
                "PaymentTransactionId": None,
                "PaymentWebhookEventId": transfer.webhook_event_id,
                "IssueType": ISSUE_UNMATCHED_PAYMENT,
                "GatewayTransactionCode": transfer.reconciliation_key,
                "ExpectedAmount": None,
                "ReceivedAmount": transfer.amount,
                "ResponseData": transfer.response_data,
                "Status": RECONCILIATION_OPEN,
                "CreatedAt": self.now(),
            }
        )
        self._notify_staff_about(
            "PaymentWebhookEvent",
            transfer.webhook_event_id,
            "Tiền vào chưa xác định đơn hàng",
            f"Nhận {transfer.amount} nhưng {reason}. Kiểm tra và đối soát thủ công.",
        )

    # ==================================================================
    # Đối soát thủ công
    # ==================================================================

    def list_reconciliations(
        self,
        actor: Actor,
        *,
        status: str | None = None,
        issue_type: str | None = None,
        order_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[PaymentReconciliationResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        if status is not None and status not in RECONCILIATION_STATUSES:
            raise BusinessRuleError(f"Trạng thái đối soát không hợp lệ: {status}", code="invalid_reconciliation_status")
        if issue_type is not None and issue_type not in RECONCILIATION_ISSUE_TYPES:
            raise BusinessRuleError(f"Loại đối soát không hợp lệ: {issue_type}", code="invalid_reconciliation_type")
        offset, limit = self._page_args(page, page_size)
        filters = {"status": status, "issue_type": issue_type, "order_id": order_id}
        items = self.reconciliations.list_reconciliations(**filters, offset=offset, limit=limit)
        return PageResponse[PaymentReconciliationResponse](
            Items=[PaymentReconciliationResponse.model_validate(r) for r in items],
            Total=self.reconciliations.count_reconciliations(**filters),
            Page=page,
            PageSize=page_size,
        )

    def resolve_reconciliation(
        self, actor: Actor, reconciliation_id: uuid.UUID, data: PaymentReconciliationResolve
    ) -> PaymentReconciliationResponse:
        """Staff/Admin đóng đối soát với ghi chú kết quả. KHÔNG tự hoàn tiền (hoàn tiền: ``refund_order`` riêng).

        Đóng lặp bị từ chối (khóa dòng, kiểm tra trạng thái) nên kết quả xử lý không bị ghi đè.
        """
        require_role(actor, *STAFF_OR_ADMIN)
        note = (data.ResolutionNote or "").strip()
        if not note:
            raise BusinessRuleError("Phải ghi kết quả xử lý đối soát", code="resolution_note_required")
        with self.transaction():
            reconciliation = self.reconciliations.get_by_id_for_update(reconciliation_id)
            if reconciliation is None:
                raise NotFoundError("Không tìm thấy bản ghi đối soát", code="reconciliation_not_found")
            if reconciliation.Status != RECONCILIATION_OPEN:
                raise BusinessRuleError("Bản ghi đối soát đã được xử lý", code="reconciliation_already_resolved")
            reconciliation.Status = RECONCILIATION_RESOLVED
            reconciliation.ResolutionNote = note
            reconciliation.ResolvedByUserId = actor.user_id
            reconciliation.ResolvedAt = self.now()
            self.reconciliations.flush()
            return PaymentReconciliationResponse.model_validate(reconciliation)

    def cancel_qr_payment(self, actor: Actor, payment_transaction_id: uuid.UUID) -> PaymentTransactionResponse:
        """Customer hủy giao dịch QR đang chờ của đơn mình (Pending → Cancelled); PaymentStatus của đơn không đổi."""
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            transaction = self.transactions.get_by_id(payment_transaction_id)
            if transaction is None:
                raise NotFoundError("Không tìm thấy giao dịch", code="payment_transaction_not_found")
            order = self._lock_order(transaction.OrderId)
            if order.CustomerId != actor.user_id:
                raise NotFoundError("Không tìm thấy giao dịch", code="payment_transaction_not_found")
            transaction = self.transactions.get_by_id_for_update(payment_transaction_id)
            if transaction.TransactionType != TX_PAYMENT or transaction.Status != TX_PENDING:
                raise BusinessRuleError("Giao dịch không ở trạng thái chờ thanh toán", code="payment_not_pending")
            transaction.Status = TX_CANCELLED
            self.transactions.flush()
            return PaymentTransactionResponse.model_validate(transaction)

    def _ensure_qr_payable(self, order: Order) -> None:
        if order.payment_method.Code == PAYMENT_METHOD_COD:
            raise BusinessRuleError("Đơn thanh toán khi nhận hàng (COD)", code="payment_method_is_cod")
        if order.OrderStatus not in QR_PAYABLE_ORDER_STATUSES or order.PaymentStatus not in QR_PAYABLE_PAYMENT_STATUSES:
            raise BusinessRuleError("Đơn hàng không ở trạng thái chờ thanh toán", code="order_not_payable")
        if order.OrderStatus == ORDER_PENDING and qr_payment_deadline(order) <= self.now():
            raise BusinessRuleError("Đơn hàng đã quá hạn thanh toán QR (15 phút)", code="order_payment_expired")

    def _abandon_qr_request(self, transaction_id: uuid.UUID) -> None:
        """Hủy giao dịch giữ chỗ khi không tạo được QR. Lỗi ở bước này: giao dịch giữ Pending (khách hủy được)."""
        try:
            with self.transaction():
                transaction = self.transactions.get_by_id(transaction_id)
                if transaction is None:
                    return
                self._lock_order(transaction.OrderId)
                transaction = self.transactions.get_by_id_for_update(transaction_id)
                if transaction.Status == TX_PENDING and not transaction.QrData:
                    transaction.Status = TX_CANCELLED
        except Exception:
            logger.warning("Không hủy được giao dịch QR giữ chỗ %s; cần đối soát", transaction_id)

    def _attach_qr(self, transaction_id: uuid.UUID, request: QrPaymentRequest) -> PaymentTransactionResponse:
        with self.transaction():
            transaction = self.transactions.get_by_id(transaction_id)
            if transaction is None:
                raise NotFoundError("Không tìm thấy giao dịch", code="payment_transaction_not_found")
            order = self._lock_order(transaction.OrderId)
            transaction = self.transactions.get_by_id_for_update(transaction_id)
            code_taken = any(
                t.PaymentTransactionId != transaction_id
                for t in self.transactions.list_by_gateway_code(request.gateway_transaction_code)
                if t.TransactionType == TX_PAYMENT
            )
            # Luôn lưu mã cổng để đối soát, kể cả khi yêu cầu không còn hiệu lực (trừ khi mã đã thuộc giao dịch khác).
            if not code_taken:
                transaction.GatewayTransactionCode = request.gateway_transaction_code
            transaction.ResponseData = request.response_data
            still_payable = (
                not code_taken
                and transaction.Status == TX_PENDING
                and order.OrderStatus in QR_PAYABLE_ORDER_STATUSES
                and order.PaymentStatus in QR_PAYABLE_PAYMENT_STATUSES
            )
            if still_payable:
                transaction.QrData = request.qr_data
            elif transaction.Status == TX_PENDING:
                transaction.Status = TX_CANCELLED
            self.transactions.flush()
            response = PaymentTransactionResponse.model_validate(transaction)
        if code_taken:
            raise PaymentGatewayError("Mã thanh toán bị trùng; vui lòng tạo lại yêu cầu", code="payment_code_collision")
        if not still_payable:
            raise BusinessRuleError(
                "Yêu cầu thanh toán đã bị hủy hoặc đơn không còn chờ thanh toán", code="payment_request_cancelled"
            )
        return response

    # ==================================================================
    # COD
    # ==================================================================

    def record_cod_payment(self, actor: Actor, order_id: uuid.UUID) -> AdminPaymentTransactionResponse:
        """Bổ sung PaymentTransaction (Payment, Success) cho đơn COD cũ đã Paid nhưng chưa có giao dịch.

        Luồng mới dùng OrderService.confirm_cod_delivery (tạo giao dịch cùng lúc ghi nhận Paid).
        Gọi nhiều lần không tạo giao dịch trùng. Không tự chuyển đơn sang Paid.
        """
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            order = self._lock_order(order_id)
            if order.payment_method.Code != PAYMENT_METHOD_COD:
                raise BusinessRuleError("Đơn không thanh toán khi nhận hàng (COD)", code="payment_method_not_cod")
            if order.OrderStatus not in COD_RECORDABLE_ORDER_STATUSES or order.PaymentStatus != PAYMENT_PAID:
                raise BusinessRuleError("Đơn COD chưa được ghi nhận đã thanh toán", code="cod_not_paid")
            existing = self._payments(order.OrderId, status=TX_SUCCESS)
            if existing:
                return AdminPaymentTransactionResponse.model_validate(existing[0])
            transaction = self.transactions.create(
                {
                    "OrderId": order.OrderId,
                    "PaymentMethodId": order.PaymentMethodId,
                    "TransactionType": TX_PAYMENT,
                    "Amount": order.TotalAmount,
                    "Status": TX_SUCCESS,
                    "PaidAt": order.DeliveredAt or self.now(),
                }
            )
            self.transactions.flush()
            return AdminPaymentTransactionResponse.model_validate(transaction)

    # ==================================================================
    # Refund
    # ==================================================================

    def refund_order(
        self,
        actor: Actor,
        order_id: uuid.UUID,
        *,
        amount: Decimal | None = None,
        payment_transaction_id: uuid.UUID | None = None,
    ) -> AdminPaymentTransactionResponse:
        """Staff/Admin hoàn tiền thủ công cho đơn đang Paid (không có hoàn tiền tự động).

        Số tiền còn có thể hoàn (``amount`` mặc định):
        - Đơn đã hủy: đã thanh toán − đã hoàn − đang chờ hoàn.
        - Đơn chưa hủy: chỉ phần thu dư = đã thanh toán − TotalAmount − các Refund Success/Pending KHÔNG thuộc yêu cầu
          trả hàng (thanh toán trùng); đồng thời không vượt đã thanh toán − mọi Refund Success/Pending. Hoàn trả hàng
          (ReturnRequests.RefundPaymentTransactionId) trả lại giá trị hàng, không làm giảm phần thu dư còn phải hoàn.
        ``payment_transaction_id``: khoản Payment gốc (Success, cùng đơn) để hoàn; mặc định khoản đầu tiên (ưu tiên
        khoản qua cổng) còn đủ số dư. Số tiền hoàn không vượt số còn có thể hoàn của khoản nguồn
        (Amount − Refund Success − Refund Pending của chính khoản đó). Giao dịch Refund không làm nguồn được.
        Mọi thao tác ghi giao dịch của đơn đều khóa Order trước, nên các yêu cầu hoàn đồng thời chạy tuần tự;
        khoản nguồn được khóa thêm (thứ tự Order → PaymentTransaction).
        Không gọi cổng thanh toán khi đang giữ transaction/khóa dòng:
        1. Transaction 1: khóa Order, kiểm tra, ghi giao dịch Refund ở trạng thái Pending, commit.
        2. Gọi cổng hoàn tiền (ngoài transaction).
        3. Transaction 2: khóa lại Order và giao dịch, ghi Success/Failed (chỉ khi giao dịch còn Pending).
        Cổng lỗi hoặc không rõ kết quả: giao dịch giữ Pending để đối soát (``resolve_pending_refund``)
        và raise PaymentGatewayError. Khoản nguồn không qua cổng (ví dụ COD): giao dịch Pending, không gọi cổng,
        chờ Admin khác người tạo xác nhận kèm bằng chứng (đợt 5.11).
        PaymentStatus → Refunded khi đã hoàn đủ số tiền đã thanh toán (chỉ tính Refund Success).
        """
        require_role(actor, *STAFF_OR_ADMIN)
        if self.in_transaction():
            raise BusinessRuleError(
                "Hoàn tiền phải là use case độc lập, không nằm trong transaction khác",
                code="refund_requires_own_transaction",
            )
        with self.transaction():
            order = self._lock_order(order_id)
            if order.PaymentStatus != PAYMENT_PAID:
                raise BusinessRuleError("Đơn hàng không ở trạng thái đã thanh toán", code="refund_not_allowed")
            payments = self._payments(order.OrderId, status=TX_SUCCESS)
            paid = sum((t.Amount for t in payments), Decimal("0"))
            refunded = sum((t.Amount for t in self._refunds(order.OrderId, status=TX_SUCCESS)), Decimal("0"))
            pending = sum((t.Amount for t in self._refunds(order.OrderId, status=TX_PENDING)), Decimal("0"))
            if order.OrderStatus == ORDER_CANCELLED:
                refundable = paid - refunded - pending
            else:
                overpaid = paid - order.TotalAmount
                if overpaid <= 0:
                    raise BusinessRuleError(
                        "Đơn chưa hủy chỉ được hoàn phần thanh toán vượt tổng tiền đơn", code="refund_not_allowed"
                    )
                # Refund của yêu cầu trả hàng hoàn giá trị hàng, không phải phần thu dư: không trừ vào phần thu dư.
                return_refund_ids = self.returns.list_refund_transaction_ids_for_order(order.OrderId)

                def held_for_overpayment(*statuses: str) -> Decimal:
                    return sum((t.Amount for status in statuses for t in self._refunds(order.OrderId, status=status)
                                if t.PaymentTransactionId not in return_refund_ids), Decimal("0"))

                refundable = min(overpaid - held_for_overpayment(*REFUND_HOLDING_STATUSES), paid - refunded - pending)
                # Chỉ Refund Pending của phần thu dư mới là "đang chờ" đối với yêu cầu này.
                pending = held_for_overpayment(TX_PENDING)
            amount = self._check_refund_amount(amount, refundable, pending)
            refund, dispatch = self._create_refund(order, payments, amount, payment_transaction_id,
                                                   created_by=actor.user_id)
            if dispatch is None:
                return AdminPaymentTransactionResponse.model_validate(refund)
        return dispatch()

    def create_return_refund(
        self, order: Order, amount: Decimal, payment_transaction_id: uuid.UUID | None = None, *, created_by: uuid.UUID
    ) -> tuple[PaymentTransaction, Callable[[], AdminPaymentTransactionResponse] | None]:
        """Nội bộ (ReturnService): ghi giao dịch Refund cho số tiền trả hàng Admin đã duyệt, đơn đã giao và đang Paid.

        Chạy trong use case của ReturnService (Order đã được khóa; thứ tự Order → ReturnRequest → PaymentTransaction).
        Giới hạn: đã thu − đã hoàn − đang chờ hoàn của đơn, và số còn có thể hoàn của khoản nguồn
        (RefundOfPaymentTransactionId). Giao dịch luôn Pending, ghi người tạo (``created_by``). Khoản nguồn không qua
        cổng: không có ``dispatch``, chờ Admin khác người tạo xác nhận (resolve_pending_refund).
        Qua cổng: trả về ``dispatch`` — caller gọi đúng một lần SAU khi commit để gửi cổng
        (cổng không có API hoàn tiền: giữ Pending chờ xác nhận thủ công qua resolve_pending_refund).
        """
        self.require_enclosing_use_case()
        if amount is None:
            raise BusinessRuleError("Cần số tiền hoàn đã được duyệt", code="invalid_refund_amount")
        with self.transaction():
            if order.OrderStatus not in RETURN_REFUNDABLE_ORDER_STATUSES or order.PaymentStatus != PAYMENT_PAID:
                raise BusinessRuleError(
                    "Chỉ hoàn tiền trả hàng cho đơn đã giao và đang ở trạng thái đã thanh toán", code="refund_not_allowed"
                )
            payments = self._payments(order.OrderId, status=TX_SUCCESS)
            paid = sum((t.Amount for t in payments), Decimal("0"))
            refunded = sum((t.Amount for t in self._refunds(order.OrderId, status=TX_SUCCESS)), Decimal("0"))
            pending = sum((t.Amount for t in self._refunds(order.OrderId, status=TX_PENDING)), Decimal("0"))
            amount = self._check_refund_amount(amount, paid - refunded - pending, pending)
            return self._create_refund(order, payments, amount, payment_transaction_id, created_by=created_by)

    def list_orders_awaiting_refund(
        self, actor: Actor, *, page: int = 1, page_size: int = 20
    ) -> PageResponse[AdminOrderResponse]:
        """Danh sách chờ hoàn tiền: đơn đã hủy nhưng vẫn Paid (chưa hoàn đủ; gồm cả đơn có Refund đang chờ kết quả).

        Đơn chuyển Refunded khi đã hoàn đủ thì tự rời danh sách. Không coi đơn đã hủy là đã hoàn tiền.
        """
        require_role(actor, *STAFF_OR_ADMIN)
        offset, limit = self._page_args(page, page_size)
        filters = {"order_status": ORDER_CANCELLED, "payment_status": PAYMENT_PAID}
        items = self.orders.list_orders(**filters, offset=offset, limit=limit)
        return PageResponse[AdminOrderResponse](
            Items=[AdminOrderResponse.model_validate(o) for o in items],
            Total=self.orders.count_orders(**filters),
            Page=page,
            PageSize=page_size,
        )

    def list_refund_sources(self, actor: Actor, order_id: uuid.UUID) -> list[RefundSourceResponse]:
        """Staff/Admin xem các khoản Payment thành công của đơn và số còn có thể hoàn của từng khoản."""
        require_role(actor, *STAFF_OR_ADMIN)
        if self.orders.get_by_id(order_id) is None:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        refunded = self.transactions.sum_refunds_by_source(order_id, statuses=(TX_SUCCESS,))
        pending = self.transactions.sum_refunds_by_source(order_id, statuses=(TX_PENDING,))
        sources = []
        for payment in self._payments(order_id, status=TX_SUCCESS):
            done = refunded.get(payment.PaymentTransactionId, _ZERO)
            waiting = pending.get(payment.PaymentTransactionId, _ZERO)
            sources.append(
                RefundSourceResponse(
                    PaymentTransactionId=payment.PaymentTransactionId,
                    PaymentMethodId=payment.PaymentMethodId,
                    GatewayTransactionCode=payment.GatewayTransactionCode,
                    Amount=payment.Amount,
                    PaidAt=payment.PaidAt,
                    RefundedAmount=done,
                    PendingRefundAmount=waiting,
                    RefundableAmount=max(payment.Amount - done - waiting, _ZERO),
                )
            )
        return sources

    def resolve_pending_refund(
        self, actor: Actor, refund_transaction_id: uuid.UUID, data: RefundResolution
    ) -> AdminPaymentTransactionResponse:
        """Admin xác nhận thủ công kết quả giao dịch Refund đang Pending (đợt 5.11, phương án D2).

        - Chỉ Admin và không phải người tạo giao dịch (CreatedByUserId). Refund cũ chưa ghi người tạo (dữ liệu trước
          migration a9f4c2e7b513) không kiểm tra được người tạo; vẫn bắt buộc Admin và bằng chứng.
        - Bắt buộc mã tham chiếu bằng chứng (EvidenceReference) và ghi chú (ResolutionNote); thành công hay thất bại
          đều phải có. Lưu ResolutionSource = Manual, ResolvedByUserId, ResolvedAt. KHÔNG ghi GatewayTransactionCode/
          ResponseData (dữ liệu của cổng thanh toán).
        - Khóa Order rồi giao dịch; chỉ giao dịch còn Pending mới được xác nhận — gọi lặp hoặc hai Admin đồng thời:
          người sau thấy đã có kết quả (refund_not_pending); kết quả cổng đã ghi trước thì không bị ghi đè.
        - Thành công: kiểm tra lại tổng Refund Success không vượt số đã thu của đơn và của khoản nguồn.
        """
        require_role(actor, *ADMIN_ONLY)
        success, evidence, note = _resolution_values(data)
        with self.transaction():
            refund = self.transactions.get_by_id(refund_transaction_id)
            if refund is None or refund.TransactionType != TX_REFUND:
                raise NotFoundError("Không tìm thấy giao dịch hoàn tiền", code="refund_transaction_not_found")
            order = self._lock_order(refund.OrderId)
            refund = self.transactions.get_by_id_for_update(refund_transaction_id)
            if refund.Status != TX_PENDING:
                raise BusinessRuleError(f"Giao dịch hoàn tiền đã có kết quả ({refund.Status})", code="refund_not_pending")
            if refund.CreatedByUserId is not None and refund.CreatedByUserId == actor.user_id:
                raise BusinessRuleError(
                    "Người lập giao dịch hoàn tiền không được tự xác nhận; cần Admin khác xác nhận",
                    code="refund_self_confirmation_not_allowed",
                )
            if success:
                self._check_success_within_limits(order, refund)
            refund.ResolutionSource = RESOLUTION_SOURCE_MANUAL
            refund.ResolvedByUserId = actor.user_id
            refund.ResolvedAt = self.now()
            refund.EvidenceReference = evidence
            refund.ResolutionNote = note
            self._apply_refund_result(order, refund, success=success)
            self.transactions.flush()
            return AdminPaymentTransactionResponse.model_validate(refund)

    # ==================================================================
    # Xem giao dịch
    # ==================================================================

    def list_order_transactions(self, actor: Actor, order_id: uuid.UUID) -> list[PaymentTransactionResponse]:
        """Customer xem giao dịch của đơn mình (đơn của người khác: không tìm thấy)."""
        require_role(actor, *CUSTOMER_ONLY)
        order = self.orders.get_by_id(order_id)
        if order is None or order.CustomerId != actor.user_id:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        return [PaymentTransactionResponse.model_validate(t) for t in self.transactions.list_by_order(order_id)]

    def admin_list_order_transactions(self, actor: Actor, order_id: uuid.UUID) -> list[AdminPaymentTransactionResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        if self.orders.get_by_id(order_id) is None:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        return [AdminPaymentTransactionResponse.model_validate(t) for t in self.transactions.list_by_order(order_id)]

    def admin_list_transactions(
        self,
        actor: Actor,
        *,
        status: str | None = None,
        payment_method_id: uuid.UUID | None = None,
        transaction_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[AdminPaymentTransactionResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        offset, limit = self._page_args(page, page_size)
        filters = {"status": status, "payment_method_id": payment_method_id, "transaction_type": transaction_type}
        items = self.transactions.list_transactions(**filters, offset=offset, limit=limit)
        return PageResponse[AdminPaymentTransactionResponse](
            Items=[AdminPaymentTransactionResponse.model_validate(t) for t in items],
            Total=self.transactions.count_transactions(**filters),
            Page=page,
            PageSize=page_size,
        )

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _check_refund_amount(amount: Decimal | None, refundable: Decimal, pending: Decimal) -> Decimal:
        """Số tiền hoàn hợp lệ (mặc định = toàn bộ số còn có thể hoàn): dương, đúng đơn vị xu, không vượt số còn lại."""
        if refundable <= 0:
            if pending > 0:
                raise BusinessRuleError("Đang có giao dịch hoàn tiền chờ kết quả", code="refund_pending")
            raise BusinessRuleError("Không còn số tiền có thể hoàn", code="nothing_to_refund")
        amount = refundable if amount is None else amount
        if amount <= 0 or amount != amount.quantize(_CENT):
            raise BusinessRuleError("Số tiền hoàn không hợp lệ", code="invalid_refund_amount")
        if amount > refundable:
            raise BusinessRuleError(
                f"Số tiền hoàn vượt số tiền còn có thể hoàn ({refundable})", code="refund_exceeds_paid"
            )
        return amount

    def _create_refund(
        self,
        order: Order,
        payments: list[PaymentTransaction],
        amount: Decimal,
        payment_transaction_id: uuid.UUID | None,
        *,
        created_by: uuid.UUID,
    ) -> tuple[PaymentTransaction, Callable[[], AdminPaymentTransactionResponse] | None]:
        """Chọn/khóa khoản nguồn và ghi giao dịch Refund Pending (Order đã khóa, trong transaction của caller).

        Không qua cổng (ví dụ COD): không có bước gửi cổng (None) — chờ Admin khác người tạo xác nhận thủ công.
        Qua cổng: trả về hàm gửi cổng để caller gọi đúng một lần sau khi commit.
        """
        source = self._lock_refund_source(order, payments, amount, payment_transaction_id)
        values = {
            "OrderId": order.OrderId,
            "PaymentMethodId": source.PaymentMethodId,
            "TransactionType": TX_REFUND,
            "Amount": amount,
            "Status": TX_PENDING,
            "RefundOfPaymentTransactionId": source.PaymentTransactionId,
            "CreatedByUserId": created_by,
        }
        if not source.GatewayTransactionCode:
            refund = self.transactions.create(values)
            self.transactions.flush()
            return refund, None

        gateway = self._require_gateway()
        refund = self.transactions.create(values)
        self.transactions.flush()
        refund_id = refund.PaymentTransactionId
        gateway_code = source.GatewayTransactionCode
        pending_response = AdminPaymentTransactionResponse.model_validate(refund)
        return refund, lambda: self._send_refund(gateway, refund_id, gateway_code, amount, pending_response)

    def _send_refund(
        self,
        gateway: PaymentGateway,
        refund_id: uuid.UUID,
        gateway_code: str,
        amount: Decimal,
        pending_response: AdminPaymentTransactionResponse,
    ) -> AdminPaymentTransactionResponse:
        """Gửi cổng hoàn tiền cho giao dịch Refund Pending đã commit (không giữ transaction/khóa dòng khi gọi cổng)."""
        if self.in_transaction():
            raise BusinessRuleError(
                "Không gọi cổng hoàn tiền bên trong transaction", code="refund_requires_own_transaction"
            )
        if not getattr(gateway, "supports_refund", True):
            # Cổng không có API hoàn tiền (ví dụ SePay): chuyển khoản thủ công, sau đó Admin khác người lập xác nhận
            # kết quả kèm bằng chứng (resolve_pending_refund). Giao dịch Refund Pending đã giữ phần tiền đang hoàn.
            return pending_response
        try:
            result = gateway.refund(gateway_transaction_code=gateway_code, amount=amount)
        except Exception as exc:
            # Không ghi chi tiết lỗi của cổng vào log (có thể chứa thông tin nhạy cảm).
            logger.warning("Gọi cổng hoàn tiền không thành công; giao dịch %s chờ đối soát", refund_id)
            raise PaymentGatewayError(
                f"Chưa xác định được kết quả hoàn tiền; giao dịch {refund_id} đang chờ đối soát",
                code="refund_pending_reconciliation",
            ) from exc
        return self._record_gateway_result(refund_id, result)

    def _record_gateway_result(self, refund_id: uuid.UUID, result: GatewayRefundResult) -> AdminPaymentTransactionResponse:
        """Ghi kết quả cổng cho giao dịch Refund còn Pending (khóa Order rồi giao dịch, theo thứ tự khóa chung).

        ResolutionSource = Gateway, ResolvedAt; bằng chứng là GatewayTransactionCode/ResponseData do cổng trả.
        Giao dịch đã có kết quả (ví dụ Admin đã xác nhận thủ công): không ghi đè, trả lại trạng thái hiện tại.
        """
        with self.transaction():
            refund = self.transactions.get_by_id(refund_id)
            if refund is None or refund.TransactionType != TX_REFUND:
                raise NotFoundError("Không tìm thấy giao dịch hoàn tiền", code="refund_transaction_not_found")
            order = self._lock_order(refund.OrderId)
            refund = self.transactions.get_by_id_for_update(refund_id)
            if refund.Status != TX_PENDING:
                return AdminPaymentTransactionResponse.model_validate(refund)
            if result.gateway_transaction_code is not None:
                refund.GatewayTransactionCode = result.gateway_transaction_code
            if result.response_data is not None:
                refund.ResponseData = result.response_data
            refund.ResolutionSource = RESOLUTION_SOURCE_GATEWAY
            refund.ResolvedAt = self.now()
            self._apply_refund_result(order, refund, success=result.success)
            self.transactions.flush()
            return AdminPaymentTransactionResponse.model_validate(refund)

    def _apply_refund_result(self, order: Order, refund: PaymentTransaction, *, success: bool) -> None:
        """Pending → Success (tiền đã hoàn: PaidAt, có thể chuyển đơn Refunded) hoặc Failed (không giữ tiền)."""
        if not success:
            refund.Status = TX_FAILED
            return
        refund.Status = TX_SUCCESS
        refund.PaidAt = self.now()
        paid = sum((t.Amount for t in self._payments(order.OrderId, status=TX_SUCCESS)), Decimal("0"))
        refunded_before = sum(
            (t.Amount for t in self._refunds(order.OrderId, status=TX_SUCCESS)
             if t.PaymentTransactionId != refund.PaymentTransactionId),
            Decimal("0"),
        )
        self._after_refund_success(order, refund, total_refunded=refunded_before + refund.Amount, paid=paid)

    def _check_success_within_limits(self, order: Order, refund: PaymentTransaction) -> None:
        """Xác nhận thủ công Success: tổng Refund Success (kể cả giao dịch này) không vượt số đã thu của đơn và của khoản
        nguồn. Refund Pending đã giữ phần tiền này từ lúc tạo, nên chỉ vi phạm khi dữ liệu không nhất quán."""
        paid = sum((t.Amount for t in self._payments(order.OrderId, status=TX_SUCCESS)), Decimal("0"))
        succeeded = self.transactions.sum_refunds_by_source(order.OrderId, statuses=(TX_SUCCESS,))
        if sum(succeeded.values(), _ZERO) + refund.Amount > paid:
            raise BusinessRuleError("Tổng tiền hoàn thành công sẽ vượt số đã thanh toán; cần kiểm tra dữ liệu",
                                    code="refund_exceeds_paid")
        source = self.transactions.get_by_id(refund.RefundOfPaymentTransactionId)
        if source is None or source.Status != TX_SUCCESS or (
                succeeded.get(source.PaymentTransactionId, _ZERO) + refund.Amount > source.Amount):
            raise BusinessRuleError("Tổng tiền hoàn thành công sẽ vượt khoản thanh toán nguồn; cần kiểm tra dữ liệu",
                                    code="refund_exceeds_source_payment")

    def _lock_refund_source(
        self,
        order: Order,
        payments: list[PaymentTransaction],
        amount: Decimal,
        payment_transaction_id: uuid.UUID | None,
    ) -> PaymentTransaction:
        """Chọn, khóa và kiểm tra khoản Payment gốc cho một lần hoàn (Order đã được khóa bởi caller).

        Số còn có thể hoàn = Amount − Refund (Success + Pending) trỏ tới khoản đó; Refund Failed/Cancelled không tính.
        """
        held = self.transactions.sum_refunds_by_source(order.OrderId, statuses=REFUND_HOLDING_STATUSES)

        def remaining(payment: PaymentTransaction) -> Decimal:
            return payment.Amount - held.get(payment.PaymentTransactionId, _ZERO)

        if payment_transaction_id is not None:
            source = self.transactions.get_by_id(payment_transaction_id)
            if source is None or source.OrderId != order.OrderId:
                raise NotFoundError("Không tìm thấy khoản thanh toán của đơn", code="payment_transaction_not_found")
            if source.TransactionType != TX_PAYMENT:
                raise BusinessRuleError(
                    "Giao dịch hoàn tiền không được dùng làm nguồn hoàn tiền", code="invalid_refund_source"
                )
            if source.Status != TX_SUCCESS:
                raise BusinessRuleError("Chỉ hoàn từ khoản thanh toán thành công", code="invalid_refund_source")
        else:
            # (Không có Payment thành công thì số đã thu = 0: caller đã dừng ở nothing_to_refund/refund_not_allowed.)
            # Ưu tiên khoản qua cổng; chỉ chọn khoản còn đủ số dư (không hoàn vượt một khoản thanh toán).
            candidates = [t for t in payments if t.GatewayTransactionCode] or payments
            source = next((t for t in candidates if remaining(t) >= amount), None)
            if source is None:
                raise BusinessRuleError(
                    "Không có khoản thanh toán nào còn đủ để hoàn số tiền này; chọn khoản nguồn và số tiền phù hợp",
                    code="refund_requires_source_payment",
                )
        source = self.transactions.get_by_id_for_update(source.PaymentTransactionId)
        available = remaining(source)
        if available <= 0:
            raise BusinessRuleError(
                "Khoản thanh toán đã được hoàn hết (gồm cả yêu cầu hoàn đang chờ)", code="source_payment_fully_refunded"
            )
        if amount > available:
            raise BusinessRuleError(
                f"Số tiền hoàn vượt số còn có thể hoàn của khoản thanh toán nguồn ({available})",
                code="refund_exceeds_source_payment",
            )
        return source

    def _after_refund_success(
        self, order: Order, refund: PaymentTransaction, *, total_refunded: Decimal, paid: Decimal
    ) -> None:
        # Đơn chưa hủy (hoàn phần thu dư) vẫn giữ Paid; chỉ đơn đã hủy được hoàn đủ mới chuyển Refunded.
        if order.OrderStatus == ORDER_CANCELLED and total_refunded >= paid:
            order.PaymentStatus = PAYMENT_REFUNDED
        self._notify(order, "Hoàn tiền", f"Đơn hàng {order.OrderCode} đã được hoàn {refund.Amount}.")

    def _notify_staff(self, order: Order, title: str, content: str) -> None:
        """Thông báo cho mọi Staff/Admin đang hoạt động (ví dụ cần hoàn tiền thủ công)."""
        self._notify_staff_about("Order", order.OrderId, title, content)

    def _notify_staff_about(
        self, reference_type: str, reference_id: uuid.UUID | None, title: str, content: str
    ) -> None:
        for role in STAFF_OR_ADMIN:
            for user in self.users.list_users(role=role, account_status="Active"):
                self.notifications.notify(
                    user.UserId,
                    title=title,
                    content=content,
                    notification_type=PAYMENT_NOTIFICATION_TYPE,
                    reference_type=reference_type,
                    reference_id=reference_id,
                )

    def _require_gateway(self) -> PaymentGateway:
        if self.gateway is None:
            raise BusinessRuleError("Chưa cấu hình cổng thanh toán", code="payment_gateway_not_configured")
        return self.gateway

    def _lock_order(self, order_id: uuid.UUID) -> Order:
        order = self.orders.get_by_id_for_update(order_id)
        if order is None:
            raise NotFoundError("Không tìm thấy đơn hàng", code="order_not_found")
        return order

    def _payments(self, order_id: uuid.UUID, *, status: str) -> list[PaymentTransaction]:
        return [t for t in self.transactions.list_by_order(order_id, status=status) if t.TransactionType == TX_PAYMENT]

    def _refunds(self, order_id: uuid.UUID, *, status: str) -> list[PaymentTransaction]:
        return [t for t in self.transactions.list_by_order(order_id, status=status) if t.TransactionType == TX_REFUND]

    def _notify(self, order: Order, title: str, content: str) -> None:
        self.notifications.notify(
            order.CustomerId,
            title=title,
            content=content,
            notification_type=PAYMENT_NOTIFICATION_TYPE,
            reference_type="Order",
            reference_id=order.OrderId,
        )


def _resolution_values(data: RefundResolution) -> tuple[bool, str, str]:
    """(thành công?, mã bằng chứng, ghi chú) — kiểm tra lại kể cả khi Schema bị bỏ qua."""
    values = dict(data.model_dump(exclude_unset=True))
    not_allowed = sorted(set(values) - {"Success", "EvidenceReference", "ResolutionNote"})
    if not_allowed:  # GatewayTransactionCode/ResponseData/người xác nhận... không nhận từ client
        raise BusinessRuleError(f"Không được gửi các trường: {not_allowed}", code="refund_resolution_field_not_allowed")
    success = values.get("Success")
    if not isinstance(success, bool):
        raise BusinessRuleError("Phải chọn kết quả hoàn tiền (thành công/thất bại)", code="invalid_refund_resolution")
    evidence = required_text(values.get("EvidenceReference"), code="refund_evidence_required",
                             message="Phải nhập mã tham chiếu bằng chứng hoàn tiền")
    if len(evidence) > EVIDENCE_REFERENCE_MAX_LENGTH:
        raise BusinessRuleError(f"Mã tham chiếu bằng chứng tối đa {EVIDENCE_REFERENCE_MAX_LENGTH} ký tự",
                                code="refund_evidence_too_long")
    note = required_text(values.get("ResolutionNote"), code="refund_resolution_note_required",
                         message="Phải ghi chú kết quả xác nhận hoàn tiền")
    return success, evidence, note
