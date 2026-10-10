"""Schemas cho PaymentMethods, PaymentTransactions.

PaymentTransactions do server/cổng thanh toán tạo; client chỉ đọc.
ResponseData (phản hồi thô từ cổng thanh toán) chỉ có trong schema admin.
Đợt 5.11: người tạo/xác nhận Refund, nguồn kết quả (Gateway/Manual), mã bằng chứng và ghi chú chỉ có trong schema admin;
Admin xác nhận thủ công Refund Pending bằng RefundResolution.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import StringConstraints

from app.models.payment import EVIDENCE_REFERENCE_MAX_LENGTH

from .common import (
    Money,
    NonBlankText,
    PaymentTransactionStatus,
    RequestSchema,
    ResponseSchema,
    TransactionTypeValue,
    varchar,
)

# ---------------------------------------------------------------------------
# PaymentMethods
# ---------------------------------------------------------------------------


class PaymentMethodCreate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Description"})

    Code: varchar(50)
    Name: varchar(255)
    Description: str | None = None
    IsActive: bool | None = None
    DisplayOrder: int | None = None


class PaymentMethodUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Description"})

    Code: varchar(50) | None = None
    Name: varchar(255) | None = None
    Description: str | None = None
    IsActive: bool | None = None
    DisplayOrder: int | None = None


class PaymentMethodResponse(ResponseSchema):
    PaymentMethodId: uuid.UUID
    Code: str
    Name: str
    Description: str | None
    IsActive: bool
    DisplayOrder: int


# ---------------------------------------------------------------------------
# PaymentTransactions
# ---------------------------------------------------------------------------


class PaymentTransactionResponse(ResponseSchema):
    """Dành cho khách hàng (ví dụ hiển thị QR thanh toán)."""

    PaymentTransactionId: uuid.UUID
    OrderId: uuid.UUID
    PaymentMethodId: uuid.UUID
    TransactionType: TransactionTypeValue
    Amount: Money
    Status: PaymentTransactionStatus
    QrData: str | None
    PaidAt: datetime | None
    CreatedAt: datetime
    # Giao dịch Refund: khoản Payment gốc được hoàn (NULL với Payment).
    RefundOfPaymentTransactionId: uuid.UUID | None


class AdminPaymentTransactionResponse(PaymentTransactionResponse):
    GatewayTransactionCode: str | None
    ResponseData: dict[str, Any] | None
    CreatedByUserId: uuid.UUID | None
    ResolvedByUserId: uuid.UUID | None
    ResolvedAt: datetime | None
    ResolutionSource: str | None
    EvidenceReference: str | None
    ResolutionNote: str | None


class RefundResolution(RequestSchema):
    """Admin (khác người tạo giao dịch) xác nhận thủ công kết quả Refund đang Pending.

    Success: tiền đã thực sự được hoàn (true) hoặc không hoàn được (false). EvidenceReference: mã tham chiếu bằng chứng
    (mã giao dịch ngân hàng/cổng, số biên nhận...) — lưu riêng, không ghi đè GatewayTransactionCode/ResponseData.
    ResolutionNote: ghi chú kết quả đối soát. Người xác nhận/thời điểm do server gán.
    """

    Success: bool
    EvidenceReference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                                        max_length=EVIDENCE_REFERENCE_MAX_LENGTH)]
    ResolutionNote: NonBlankText


class RefundSourceResponse(ResponseSchema):
    """Staff/Admin: một khoản Payment thành công của đơn và số tiền còn có thể hoàn từ khoản đó (server tính).

    RefundableAmount = Amount − RefundedAmount (Refund Success) − PendingRefundAmount (Refund Pending).
    Refund Failed/Cancelled không giữ tiền.
    """

    PaymentTransactionId: uuid.UUID
    PaymentMethodId: uuid.UUID
    GatewayTransactionCode: str | None
    Amount: Money
    PaidAt: datetime | None
    RefundedAmount: Money
    PendingRefundAmount: Money
    RefundableAmount: Money


# ---------------------------------------------------------------------------
# PaymentReconciliations (đối soát thủ công; do server tạo khi có thanh toán bất thường)
# ---------------------------------------------------------------------------


class PaymentReconciliationResponse(ResponseSchema):
    """Dành cho Staff/Admin."""

    PaymentReconciliationId: uuid.UUID
    OrderId: uuid.UUID | None  # NULL với UnmatchedPayment
    PaymentTransactionId: uuid.UUID | None
    PaymentWebhookEventId: uuid.UUID | None
    IssueType: str
    GatewayTransactionCode: str
    ExpectedAmount: Money | None
    ReceivedAmount: Money
    ResponseData: dict[str, Any] | None
    Status: str
    ResolutionNote: str | None
    ResolvedByUserId: uuid.UUID | None
    ResolvedAt: datetime | None
    CreatedAt: datetime


class PaymentReconciliationResolve(RequestSchema):
    """Staff/Admin đóng bản ghi đối soát; ghi chú kết quả xử lý (ví dụ đã hoàn tiền/đã liên hệ khách) là bắt buộc.

    Đóng đối soát không tự hoàn tiền; hoàn tiền (nếu cần) thực hiện riêng qua PaymentService.refund_order.
    """

    ResolutionNote: NonBlankText
