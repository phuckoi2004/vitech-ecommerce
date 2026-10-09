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

    order: Mapped[Order] = relationship(back_populates="payment_transactions", foreign_keys=[OrderId])
    payment_method: Mapped[PaymentMethod] = relationship(
        back_populates="payment_transactions", foreign_keys=[PaymentMethodId]
    )
