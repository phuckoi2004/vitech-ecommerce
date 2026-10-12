from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, check_in

if TYPE_CHECKING:
    from .catalog import ProductVariant
    from .service_request import WarrantyRequest
    from .user import User


# Closed: Admin đóng phiếu còn thiếu hàng (nhà cung cấp giao thiếu); số thiếu = OrderedQuantity − ReceivedQuantity.
PURCHASE_ORDER_STATUSES = ("Pending", "Approved", "Rejected", "Receiving", "Completed", "Cancelled", "Closed")
# Phiếu Closed bắt buộc có thời điểm + lý do đóng; trạng thái khác không có (migration e2b8c4f6a913).
PURCHASE_ORDER_CLOSED_CONSISTENT_SQL = (
    "(\"Status\" = 'Closed' AND \"ClosedAt\" IS NOT NULL AND \"CloseReason\" IS NOT NULL "
    "AND length(btrim(\"CloseReason\")) > 0) OR "
    "(\"Status\" <> 'Closed' AND \"ClosedAt\" IS NULL AND \"CloseReason\" IS NULL)"
)


class Supplier(Base):
    __tablename__ = "Suppliers"

    SupplierId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    SupplierCode: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    Name: Mapped[str] = mapped_column(String(255), nullable=False)
    Email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    PhoneNumber: Mapped[str] = mapped_column(String(20), nullable=False)
    Address: Mapped[str] = mapped_column(String(500), nullable=False)
    TaxCode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    Note: Mapped[str | None] = mapped_column(Text, nullable=True)

    purchase_orders: Mapped[list[PurchaseOrder]] = relationship(
        back_populates="supplier", foreign_keys="PurchaseOrder.SupplierId", passive_deletes="all"
    )
    warranty_requests: Mapped[list[WarrantyRequest]] = relationship(
        back_populates="supplier", foreign_keys="WarrantyRequest.SupplierId", passive_deletes="all"
    )


class PurchaseOrder(Base):
    __tablename__ = "PurchaseOrders"
    __table_args__ = (
        CheckConstraint('"TotalAmount" >= 0', name="TotalAmount_NonNegative"),
        check_in("Status", PURCHASE_ORDER_STATUSES, "Status_Valid"),
        CheckConstraint(PURCHASE_ORDER_CLOSED_CONSISTENT_SQL, name="Closed_Consistent"),
    )

    PurchaseOrderId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    PurchaseOrderCode: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    SupplierId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Suppliers.SupplierId", ondelete="RESTRICT"), nullable=False
    )
    CreatedByUserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    DecidedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    TotalAmount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    Status: Mapped[str] = mapped_column(String(30), nullable=False)
    Note: Mapped[str | None] = mapped_column(Text, nullable=True)
    RejectReason: Mapped[str | None] = mapped_column(Text, nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    DecidedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ClosedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    ClosedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CloseReason: Mapped[str | None] = mapped_column(Text, nullable=True)

    supplier: Mapped[Supplier] = relationship(back_populates="purchase_orders", foreign_keys=[SupplierId])
    created_by: Mapped[User] = relationship(
        back_populates="created_purchase_orders", foreign_keys=[CreatedByUserId]
    )
    decided_by: Mapped[User | None] = relationship(
        back_populates="decided_purchase_orders", foreign_keys=[DecidedByUserId]
    )
    items: Mapped[list[PurchaseOrderItem]] = relationship(
        back_populates="purchase_order",
        foreign_keys="PurchaseOrderItem.PurchaseOrderId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PurchaseOrderItem(Base):
    __tablename__ = "PurchaseOrderItems"
    __table_args__ = (
        CheckConstraint('"OrderedQuantity" > 0', name="OrderedQuantity_Positive"),
        CheckConstraint('"ReceivedQuantity" >= 0', name="ReceivedQuantity_NonNegative"),
        CheckConstraint(
            '"ReceivedQuantity" <= "OrderedQuantity"', name="ReceivedQuantity_NotExceedOrdered"
        ),
        CheckConstraint('"UnitPrice" >= 0', name="UnitPrice_NonNegative"),
        CheckConstraint('"LineTotal" >= 0', name="LineTotal_NonNegative"),
    )

    PurchaseOrderItemId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    PurchaseOrderId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("PurchaseOrders.PurchaseOrderId", ondelete="CASCADE"),
        nullable=False,
    )
    ProductVariantId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ProductVariants.ProductVariantId", ondelete="RESTRICT"),
        nullable=False,
    )
    OrderedQuantity: Mapped[int] = mapped_column(Integer, nullable=False)
    ReceivedQuantity: Mapped[int] = mapped_column(Integer, nullable=False)
    UnitPrice: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    LineTotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    Note: Mapped[str | None] = mapped_column(Text, nullable=True)

    purchase_order: Mapped[PurchaseOrder] = relationship(
        back_populates="items", foreign_keys=[PurchaseOrderId]
    )
    product_variant: Mapped[ProductVariant] = relationship(
        back_populates="purchase_order_items", foreign_keys=[ProductVariantId]
    )


class PurchaseReceipt(Base):
    """Một lần nhận hàng thực tế của phiếu nhập (lịch sử; chỉ ghi thêm — trigger trong migration e2b8c4f6a913)."""

    __tablename__ = "PurchaseReceipts"

    PurchaseReceiptId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    PurchaseOrderId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("PurchaseOrders.PurchaseOrderId", ondelete="RESTRICT"), nullable=False
    )
    ReceivedByUserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    ReceivedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    Note: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list[PurchaseReceiptItem]] = relationship(
        back_populates="receipt", passive_deletes=True, order_by="PurchaseReceiptItem.PurchaseOrderItemId"
    )


class PurchaseReceiptItem(Base):
    """Số lượng thực nhận của một dòng phiếu nhập trong một lần nhận (đơn giá nhập tại lần nhận)."""

    __tablename__ = "PurchaseReceiptItems"
    __table_args__ = (
        CheckConstraint('"Quantity" > 0', name="Quantity_Positive"),
        CheckConstraint('"UnitPrice" >= 0', name="UnitPrice_NonNegative"),
    )

    PurchaseReceiptId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("PurchaseReceipts.PurchaseReceiptId", ondelete="CASCADE"), primary_key=True
    )
    PurchaseOrderItemId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("PurchaseOrderItems.PurchaseOrderItemId", ondelete="RESTRICT"), primary_key=True
    )
    Quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    UnitPrice: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    receipt: Mapped[PurchaseReceipt] = relationship(back_populates="items", foreign_keys=[PurchaseReceiptId])


Index("IX_PurchaseReceipts_PurchaseOrderId_ReceivedAt", PurchaseReceipt.PurchaseOrderId, PurchaseReceipt.ReceivedAt)
Index("IX_PurchaseReceiptItems_PurchaseOrderItemId", PurchaseReceiptItem.PurchaseOrderItemId)
