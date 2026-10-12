from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, check_in

if TYPE_CHECKING:
    from .order import Order


PAYMENT_TRANSACTION_STATUSES = ("Pending", "Success", "Failed", "Cancelled", "Refunded")
PAYMENT_TRANSACTION_TYPES = ("Payment", "Refund")
# Refund luôn trỏ tới đúng một giao dịch Payment gốc; Payment không có nguồn hoàn.
# (Nguồn phải là Payment cùng đơn và liên kết không đổi được: trigger trong migration 4c2d9e7a1f53.)
REFUND_SOURCE_CONSISTENT_SQL = (
    "(\"TransactionType\" = 'Refund' AND \"RefundOfPaymentTransactionId\" IS NOT NULL) OR "
    "(\"TransactionType\" <> 'Refund' AND \"RefundOfPaymentTransactionId\" IS NULL)"
)

# Kết quả giao dịch Refund (đợt 5.11, phương án D2; migration a9f4c2e7b513): Gateway = cổng thanh toán trả kết quả
# (bằng chứng nằm ở GatewayTransactionCode/ResponseData); Manual = Admin xác nhận thủ công kèm bằng chứng.
RESOLUTION_SOURCE_GATEWAY = "Gateway"
RESOLUTION_SOURCE_MANUAL = "Manual"
RESOLUTION_SOURCES = (RESOLUTION_SOURCE_GATEWAY, RESOLUTION_SOURCE_MANUAL)
EVIDENCE_REFERENCE_MAX_LENGTH = 255
# Chưa có kết quả: mọi trường xác nhận đều NULL (kể cả dữ liệu cũ). Đã có kết quả: chỉ với Refund Success/Failed.
RESOLUTION_CONSISTENT_SQL = (
    "(\"ResolutionSource\" IS NULL AND \"ResolvedByUserId\" IS NULL AND \"ResolvedAt\" IS NULL "
    "AND \"EvidenceReference\" IS NULL AND \"ResolutionNote\" IS NULL) OR "
    "(\"ResolutionSource\" IS NOT NULL AND \"ResolvedAt\" IS NOT NULL AND \"TransactionType\" = 'Refund' "
    "AND \"Status\" IN ('Success', 'Failed'))"
)
# Cổng trả kết quả: không có người xác nhận/bằng chứng thủ công.
GATEWAY_RESOLUTION_SQL = (
    "\"ResolutionSource\" <> 'Gateway' OR (\"ResolvedByUserId\" IS NULL AND \"EvidenceReference\" IS NULL "
    "AND \"ResolutionNote\" IS NULL)"
)
# Xác nhận thủ công: bắt buộc người xác nhận, mã tham chiếu bằng chứng và ghi chú (không rỗng).
MANUAL_RESOLUTION_SQL = (
    "\"ResolutionSource\" <> 'Manual' OR (\"ResolvedByUserId\" IS NOT NULL "
    "AND \"EvidenceReference\" IS NOT NULL AND length(btrim(\"EvidenceReference\")) > 0 "
    "AND \"ResolutionNote\" IS NOT NULL AND length(btrim(\"ResolutionNote\")) > 0)"
)
# Người tạo không tự xác nhận (bỏ qua với dữ liệu cũ chưa có người tạo).
MANUAL_NOT_BY_CREATOR_SQL = (
    "\"ResolutionSource\" <> 'Manual' OR \"CreatedByUserId\" IS NULL "
    "OR \"ResolvedByUserId\" <> \"CreatedByUserId\""
)


class PaymentMethod(Base):
    __tablename__ = "PaymentMethods"

    PaymentMethodId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    Code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    Name: Mapped[str] = mapped_column(String(255), nullable=False)
    Description: Mapped[str | None] = mapped_column(Text, nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    DisplayOrder: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    orders: Mapped[list[Order]] = relationship(
        back_populates="payment_method", foreign_keys="Order.PaymentMethodId", passive_deletes="all"
    )
    payment_transactions: Mapped[list[PaymentTransaction]] = relationship(
        back_populates="payment_method",
        foreign_keys="PaymentTransaction.PaymentMethodId",
        passive_deletes="all",
    )


class PaymentTransaction(Base):
    __tablename__ = "PaymentTransactions"
    __table_args__ = (
        CheckConstraint('"Amount" >= 0', name="Amount_NonNegative"),
        check_in("Status", PAYMENT_TRANSACTION_STATUSES, "Status_Valid"),
        check_in("TransactionType", PAYMENT_TRANSACTION_TYPES, "TransactionType_Valid"),
        CheckConstraint(REFUND_SOURCE_CONSISTENT_SQL, name="RefundSource_Consistent"),
        check_in("ResolutionSource", RESOLUTION_SOURCES, "ResolutionSource_Valid"),
        CheckConstraint(RESOLUTION_CONSISTENT_SQL, name="Resolution_Consistent"),
        CheckConstraint(GATEWAY_RESOLUTION_SQL, name="GatewayResolution_NoManualFields"),
        CheckConstraint(MANUAL_RESOLUTION_SQL, name="ManualResolution_Complete"),
        CheckConstraint(MANUAL_NOT_BY_CREATOR_SQL, name="ManualResolution_NotByCreator"),
    )

    PaymentTransactionId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    OrderId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Orders.OrderId", ondelete="RESTRICT"), nullable=False
    )
    PaymentMethodId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("PaymentMethods.PaymentMethodId", ondelete="RESTRICT"),
        nullable=False,
    )
    GatewayTransactionCode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    TransactionType: Mapped[str] = mapped_column(String(20), nullable=False)
    Amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    Status: Mapped[str] = mapped_column(String(30), nullable=False)
    QrData: Mapped[str | None] = mapped_column(Text, nullable=True)
    ResponseData: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    PaidAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Giao dịch Refund: khoản Payment gốc được hoàn (thêm bởi migration 4c2d9e7a1f53, chưa áp dụng).
    RefundOfPaymentTransactionId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("PaymentTransactions.PaymentTransactionId", ondelete="RESTRICT"),
        nullable=True,
    )
    # Đợt 5.11 (migration a9f4c2e7b513, chưa áp dụng): người tạo giao dịch Refund và kết quả xác nhận.
    # NULL với dữ liệu cũ và giao dịch Payment. FK RESTRICT: giữ dấu vết người tạo/xác nhận hoàn tiền.
    CreatedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=True
    )
    ResolvedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=True
    )
    ResolvedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ResolutionSource: Mapped[str | None] = mapped_column(String(20), nullable=True)
    EvidenceReference: Mapped[str | None] = mapped_column(String(EVIDENCE_REFERENCE_MAX_LENGTH), nullable=True)
    ResolutionNote: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped[Order] = relationship(back_populates="payment_transactions", foreign_keys=[OrderId])
    payment_method: Mapped[PaymentMethod] = relationship(
        back_populates="payment_transactions", foreign_keys=[PaymentMethodId]
    )


Index("IX_PaymentTransactions_RefundOfPaymentTransactionId", PaymentTransaction.RefundOfPaymentTransactionId)
