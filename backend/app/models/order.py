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
    from .catalog import ProductSerial, ProductVariant
    from .payment import PaymentMethod, PaymentTransaction
    from .promotion import Coupon
    from .review import Review
    from .service_request import ReturnRequest, WarrantyRequest
    from .user import Address, User


ORDER_STATUSES = (
    "Pending",
    "Confirmed",
    "Processing",
    "Shipping",
    "Delivered",
    "Completed",
    "Cancelled",
)
PAYMENT_STATUSES = ("Pending", "Paid", "Failed", "Refunded", "Cancelled")


class ShippingMethod(Base):
    __tablename__ = "ShippingMethods"
    __table_args__ = (CheckConstraint('"BaseFee" >= 0', name="BaseFee_NonNegative"),)

    ShippingMethodId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    Code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    Name: Mapped[str] = mapped_column(String(255), nullable=False)
    BaseFee: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    EstimatedDays: Mapped[int] = mapped_column(Integer, nullable=False)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    orders: Mapped[list[Order]] = relationship(
        back_populates="shipping_method",
        foreign_keys="Order.ShippingMethodId",
        passive_deletes="all",
    )


class Order(Base):
    __tablename__ = "Orders"
    __table_args__ = (
        CheckConstraint('"Subtotal" >= 0', name="Subtotal_NonNegative"),
        CheckConstraint('"ShippingFee" >= 0', name="ShippingFee_NonNegative"),
        CheckConstraint('"DiscountAmount" >= 0', name="DiscountAmount_NonNegative"),
        CheckConstraint('"TotalAmount" >= 0', name="TotalAmount_NonNegative"),
        check_in("OrderStatus", ORDER_STATUSES, "OrderStatus_Valid"),
        check_in("PaymentStatus", PAYMENT_STATUSES, "PaymentStatus_Valid"),
    )

    OrderId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    OrderCode: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    CustomerId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    AssignedStaffId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    AddressId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Addresses.AddressId", ondelete="SET NULL"), nullable=True
    )
    ShippingMethodId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ShippingMethods.ShippingMethodId", ondelete="RESTRICT"),
        nullable=False,
    )
    PaymentMethodId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("PaymentMethods.PaymentMethodId", ondelete="RESTRICT"),
        nullable=False,
    )
    CouponId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Coupons.CouponId", ondelete="RESTRICT"), nullable=True
    )
    Subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    ShippingFee: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default=text("0")
    )
    DiscountAmount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    TotalAmount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    OrderStatus: Mapped[str] = mapped_column(String(30), nullable=False)
    PaymentStatus: Mapped[str] = mapped_column(String(30), nullable=False)
    ReceiverName: Mapped[str] = mapped_column(String(255), nullable=False)
    ReceiverPhone: Mapped[str] = mapped_column(String(20), nullable=False)
    ShippingAddress: Mapped[str] = mapped_column(String(500), nullable=False)
    CustomerNote: Mapped[str | None] = mapped_column(Text, nullable=True)
    InternalNote: Mapped[str | None] = mapped_column(Text, nullable=True)
    CancelReason: Mapped[str | None] = mapped_column(Text, nullable=True)
    OrderedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ConfirmedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ShippedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    DeliveredAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CompletedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CancelledAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[User] = relationship(back_populates="customer_orders", foreign_keys=[CustomerId])
    assigned_staff: Mapped[User | None] = relationship(
        back_populates="assigned_orders", foreign_keys=[AssignedStaffId]
    )
    address: Mapped[Address | None] = relationship(back_populates="orders", foreign_keys=[AddressId])
    shipping_method: Mapped[ShippingMethod] = relationship(
        back_populates="orders", foreign_keys=[ShippingMethodId]
    )
    payment_method: Mapped[PaymentMethod] = relationship(
        back_populates="orders", foreign_keys=[PaymentMethodId]
    )
    coupon: Mapped[Coupon | None] = relationship(back_populates="orders", foreign_keys=[CouponId])
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order",
        foreign_keys="OrderItem.OrderId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    status_histories: Mapped[list[OrderStatusHistory]] = relationship(
        back_populates="order", foreign_keys="OrderStatusHistory.OrderId", passive_deletes="all"
    )
    payment_transactions: Mapped[list[PaymentTransaction]] = relationship(
        back_populates="order", foreign_keys="PaymentTransaction.OrderId", passive_deletes="all"
    )


class OrderItem(Base):
    __tablename__ = "OrderItems"
    __table_args__ = (
        CheckConstraint('"Quantity" > 0', name="Quantity_Positive"),
        CheckConstraint('"UnitPrice" >= 0', name="UnitPrice_NonNegative"),
        CheckConstraint('"UnitCost" >= 0', name="UnitCost_NonNegative"),
        CheckConstraint('"DiscountAmount" >= 0', name="DiscountAmount_NonNegative"),
        CheckConstraint('"LineTotal" >= 0', name="LineTotal_NonNegative"),
    )

    OrderItemId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    OrderId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Orders.OrderId", ondelete="CASCADE"), nullable=False
    )
    ProductVariantId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ProductVariants.ProductVariantId", ondelete="RESTRICT"),
        nullable=False,
    )
    ProductName: Mapped[str] = mapped_column(String(255), nullable=False)
    Sku: Mapped[str] = mapped_column(String(50), nullable=False)
    VariantInfo: Mapped[str] = mapped_column(String(255), nullable=False)
    WarrantyMonths: Mapped[int] = mapped_column(Integer, nullable=False)
    Quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    UnitPrice: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # Giá vốn tại thời điểm bán, lấy từ ProductVariants.CostPrice khi tạo OrderItem (COGS).
    UnitCost: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default=text("0")
    )
    DiscountAmount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    LineTotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    order: Mapped[Order] = relationship(back_populates="items", foreign_keys=[OrderId])
    product_variant: Mapped[ProductVariant] = relationship(
        back_populates="order_items", foreign_keys=[ProductVariantId]
    )
    product_serials: Mapped[list[ProductSerial]] = relationship(
        back_populates="order_item", foreign_keys="ProductSerial.OrderItemId", passive_deletes=True
    )
    review: Mapped[Review | None] = relationship(
        back_populates="order_item",
        foreign_keys="Review.OrderItemId",
        uselist=False,
        passive_deletes="all",
    )
    warranty_requests: Mapped[list[WarrantyRequest]] = relationship(
        back_populates="order_item", foreign_keys="WarrantyRequest.OrderItemId", passive_deletes="all"
    )
    return_requests: Mapped[list[ReturnRequest]] = relationship(
        back_populates="order_item", foreign_keys="ReturnRequest.OrderItemId", passive_deletes="all"
    )


class OrderStatusHistory(Base):
    __tablename__ = "OrderStatusHistories"
    __table_args__ = (
        check_in("OldStatus", ORDER_STATUSES, "OldStatus_Valid"),
        check_in("NewStatus", ORDER_STATUSES, "NewStatus_Valid"),
    )

    OrderStatusHistoryId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    OrderId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Orders.OrderId", ondelete="RESTRICT"), nullable=False
    )
    ChangedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    OldStatus: Mapped[str | None] = mapped_column(String(30), nullable=True)
    NewStatus: Mapped[str] = mapped_column(String(30), nullable=False)
    Note: Mapped[str | None] = mapped_column(Text, nullable=True)
    ChangedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    order: Mapped[Order] = relationship(back_populates="status_histories", foreign_keys=[OrderId])
    changed_by: Mapped[User | None] = relationship(
        back_populates="order_status_changes", foreign_keys=[ChangedByUserId]
    )
