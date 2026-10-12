"""PaymentWebhookEvents: sự kiện giao dịch ngân hàng nhận từ webhook cổng thanh toán (hiện tại: SePay).

Lưu bền vững TRƯỚC khi xử lý nghiệp vụ để không mất giao dịch khi xử lý lỗi; idempotent theo
(Provider, AccountNumber, ProviderTransactionId): SePay giữ nguyên `id` qua mọi lần retry.
Payload chứa dữ liệu cá nhân (tên/nội dung chuyển khoản): chỉ lưu trong database, không ghi log.
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

PROVIDER_SEPAY = "SePay"
WEBHOOK_PROVIDERS = (PROVIDER_SEPAY,)
WEBHOOK_RECEIVED = "Received"
WEBHOOK_PROCESSED = "Processed"
WEBHOOK_IGNORED = "Ignored"
WEBHOOK_EVENT_STATUSES = (WEBHOOK_RECEIVED, WEBHOOK_PROCESSED, WEBHOOK_IGNORED)
TRANSFER_TYPES = ("in", "out")


class PaymentWebhookEvent(Base):
    __tablename__ = "PaymentWebhookEvents"
    __table_args__ = (
        check_in("Provider", WEBHOOK_PROVIDERS, "Provider_Valid"),
        check_in("Status", WEBHOOK_EVENT_STATUSES, "Status_Valid"),
        check_in("TransferType", TRANSFER_TYPES, "TransferType_Valid"),
        CheckConstraint('"TransferAmount" >= 0', name="TransferAmount_NonNegative"),
        CheckConstraint(
            "(\"Status\" = 'Received' AND \"ProcessedAt\" IS NULL) OR (\"Status\" <> 'Received' AND \"ProcessedAt\" IS NOT NULL)",
            name="Processing_Consistent",
        ),
        # Phạm vi duy nhất bảo thủ: tài liệu SePay khuyến nghị UNIQUE theo `id`, nhưng chưa xác nhận phạm vi
        # (toàn hệ thống hay theo tài khoản) nên khóa gồm cả tài khoản nhận.
        UniqueConstraint("Provider", "AccountNumber", "ProviderTransactionId", name="UQ_PaymentWebhookEvents_ProviderTxn"),
    )

    PaymentWebhookEventId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    Provider: Mapped[str] = mapped_column(String(30), nullable=False)
    ProviderTransactionId: Mapped[str] = mapped_column(String(100), nullable=False)
    AccountNumber: Mapped[str] = mapped_column(String(50), nullable=False)
    TransferType: Mapped[str] = mapped_column(String(10), nullable=False)
    TransferAmount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # Mã thanh toán cổng trích từ nội dung chuyển khoản (SePay `code`, có thể NULL).
    PaymentCode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ReferenceCode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Thời điểm giao dịch ngân hàng (SePay gửi giờ Việt Nam, lưu UTC); NULL nếu không đọc được.
    TransactionDate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    Payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    Status: Mapped[str] = mapped_column(String(20), nullable=False)
    ProcessingNote: Mapped[str | None] = mapped_column(Text, nullable=True)
    PaymentTransactionId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("PaymentTransactions.PaymentTransactionId", ondelete="RESTRICT"),
        nullable=True,
    )
    ReceivedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ProcessedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("IX_PaymentWebhookEvents_Status_ReceivedAt", PaymentWebhookEvent.Status, PaymentWebhookEvent.ReceivedAt)
Index("IX_PaymentWebhookEvents_PaymentCode", PaymentWebhookEvent.PaymentCode)
