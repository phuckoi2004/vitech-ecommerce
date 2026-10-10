"""PaymentReconciliations: các khoản thanh toán bất thường cần Staff/Admin đối soát thủ công.

- AmountMismatch: callback thành công nhưng số tiền khác số tiền kỳ vọng (đơn KHÔNG chuyển Paid).
- DuplicatePayment: đơn nhận thêm một khoản thanh toán thành công khi đã có khoản thành công khác.
- PaymentAfterCancellation: thanh toán thành công đến sau khi đơn đã hủy/hết hạn.
- UnmatchedPayment: tiền vào nhưng không xác định được duy nhất một đơn/giao dịch (không có mã thanh toán,
  mã không khớp hoặc khớp nhiều giao dịch); OrderId/PaymentTransactionId/ExpectedAmount để trống.
Mỗi (GatewayTransactionCode, IssueType) chỉ một bản ghi: callback gửi lặp không tạo bản ghi trùng.
Không tự hoàn tiền; kết quả xử lý (Resolved, người xử lý, ghi chú) do Staff/Admin ghi nhận.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, check_in

ISSUE_AMOUNT_MISMATCH = "AmountMismatch"
ISSUE_DUPLICATE_PAYMENT = "DuplicatePayment"
ISSUE_PAYMENT_AFTER_CANCELLATION = "PaymentAfterCancellation"
ISSUE_UNMATCHED_PAYMENT = "UnmatchedPayment"
RECONCILIATION_ISSUE_TYPES = (
    ISSUE_AMOUNT_MISMATCH,
    ISSUE_DUPLICATE_PAYMENT,
    ISSUE_PAYMENT_AFTER_CANCELLATION,
    ISSUE_UNMATCHED_PAYMENT,
)
RECONCILIATION_OPEN = "Open"
RECONCILIATION_RESOLVED = "Resolved"
RECONCILIATION_STATUSES = (RECONCILIATION_OPEN, RECONCILIATION_RESOLVED)


class PaymentReconciliation(Base):
    __tablename__ = "PaymentReconciliations"
    __table_args__ = (
        check_in("IssueType", RECONCILIATION_ISSUE_TYPES, "IssueType_Valid"),
        check_in("Status", RECONCILIATION_STATUSES, "Status_Valid"),
        CheckConstraint('"ExpectedAmount" >= 0', name="ExpectedAmount_NonNegative"),
        CheckConstraint('"ReceivedAmount" >= 0', name="ReceivedAmount_NonNegative"),
        CheckConstraint(
            "(\"Status\" = 'Open' AND \"ResolvedAt\" IS NULL) OR (\"Status\" = 'Resolved' AND \"ResolvedAt\" IS NOT NULL)",
            name="Resolution_Consistent",
        ),
        # Chỉ UnmatchedPayment được thiếu đơn/giao dịch/số tiền kỳ vọng.
        CheckConstraint(
            "\"IssueType\" = 'UnmatchedPayment' OR (\"OrderId\" IS NOT NULL AND \"PaymentTransactionId\" IS NOT NULL "
            "AND \"ExpectedAmount\" IS NOT NULL)",
            name="Matched_References_Required",
        ),
        UniqueConstraint("GatewayTransactionCode", "IssueType"),
    )

    PaymentReconciliationId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    OrderId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Orders.OrderId", ondelete="RESTRICT"), nullable=True
    )
    # Giao dịch thanh toán của hệ thống khớp với mã cổng (giao dịch kỳ vọng khi sai số tiền).
    PaymentTransactionId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("PaymentTransactions.PaymentTransactionId", ondelete="RESTRICT"),
        nullable=True,
    )
    # Sự kiện webhook gốc (nếu đối soát phát sinh từ webhook ngân hàng).
    PaymentWebhookEventId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("PaymentWebhookEvents.PaymentWebhookEventId", ondelete="RESTRICT"),
        nullable=True,
    )
    IssueType: Mapped[str] = mapped_column(String(30), nullable=False)
    GatewayTransactionCode: Mapped[str] = mapped_column(String(100), nullable=False)
    ExpectedAmount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    ReceivedAmount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # Phản hồi (đã xác minh) của cổng thanh toán, cùng cách lưu với PaymentTransactions.ResponseData.
    ResponseData: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    Status: Mapped[str] = mapped_column(String(20), nullable=False)
    ResolutionNote: Mapped[str | None] = mapped_column(Text, nullable=True)
    ResolvedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    ResolvedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


Index("IX_PaymentReconciliations_Status_CreatedAt", PaymentReconciliation.Status, PaymentReconciliation.CreatedAt)
Index("IX_PaymentReconciliations_OrderId", PaymentReconciliation.OrderId)
