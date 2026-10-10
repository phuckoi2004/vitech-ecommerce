"""ShipmentReturns / ShipmentReturnItems: hàng của đơn bị hủy khi đang giao (Shipping), chờ quay về kho.

Hủy đơn đang giao KHÔNG hoàn tồn ngay: hàng còn ở bên vận chuyển. Staff xác nhận nhận lại và kiểm tra thực tế:
hàng đạt → nhập lại tồn (serial Available); hàng hỏng → không nhập tồn (serial Returned, không tự WrittenOff).
Mỗi đơn tối đa một hồ sơ (UNIQUE OrderId); nhận hàng chỉ một lần (Status) nên không cộng tồn hai lần.
Thêm bởi migration 5d1f9a3c7e64 (chưa áp dụng).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, check_in

SHIPMENT_RETURN_AWAITING = "AwaitingReturn"
SHIPMENT_RETURN_RECEIVED = "Received"
SHIPMENT_RETURN_STATUSES = (SHIPMENT_RETURN_AWAITING, SHIPMENT_RETURN_RECEIVED)


class ShipmentReturn(Base):
    __tablename__ = "ShipmentReturns"
    __table_args__ = (
        check_in("Status", SHIPMENT_RETURN_STATUSES, "Status_Valid"),
        CheckConstraint(
            "(\"Status\" = 'AwaitingReturn' AND \"ReceivedAt\" IS NULL) OR "
            "(\"Status\" = 'Received' AND \"ReceivedAt\" IS NOT NULL)",
            name="Receipt_Consistent",
        ),
    )

    ShipmentReturnId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    OrderId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Orders.OrderId", ondelete="RESTRICT"), nullable=False, unique=True
    )
    Status: Mapped[str] = mapped_column(String(20), nullable=False)
    CreatedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ReceivedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    ReceivedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    Note: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list[ShipmentReturnItem]] = relationship(
        back_populates="shipment_return", passive_deletes=True, order_by="ShipmentReturnItem.OrderItemId"
    )


class ShipmentReturnItem(Base):
    """Một dòng hàng chờ quay về: serial (1 dòng/serial, ExpectedQuantity = 1) hoặc dòng đơn không quản lý serial.

    RestockedQuantity/DamagedQuantity NULL cho đến khi nhận hàng; khi đã nhận: tổng bằng ExpectedQuantity.
    """

    __tablename__ = "ShipmentReturnItems"
    __table_args__ = (
        CheckConstraint('"ExpectedQuantity" > 0', name="ExpectedQuantity_Positive"),
        CheckConstraint('"ProductSerialId" IS NULL OR "ExpectedQuantity" = 1', name="Serial_SingleUnit"),
        CheckConstraint(
            '("RestockedQuantity" IS NULL AND "DamagedQuantity" IS NULL) OR '
            '("RestockedQuantity" >= 0 AND "DamagedQuantity" >= 0 '
            'AND "RestockedQuantity" + "DamagedQuantity" = "ExpectedQuantity")',
            name="Outcome_Consistent",
        ),
    )

    ShipmentReturnItemId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ShipmentReturnId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ShipmentReturns.ShipmentReturnId", ondelete="CASCADE"), nullable=False
    )
    OrderItemId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("OrderItems.OrderItemId", ondelete="RESTRICT"), nullable=False
    )
    ProductSerialId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ProductSerials.ProductSerialId", ondelete="RESTRICT"), nullable=True
    )
    ExpectedQuantity: Mapped[int] = mapped_column(Integer, nullable=False)
    RestockedQuantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    DamagedQuantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    shipment_return: Mapped[ShipmentReturn] = relationship(back_populates="items", foreign_keys=[ShipmentReturnId])


Index("IX_ShipmentReturns_Status_CreatedAt", ShipmentReturn.Status, ShipmentReturn.CreatedAt)
# Dòng đơn không quản lý serial: một dòng mỗi hồ sơ; serial: một dòng mỗi serial trong hồ sơ.
Index(
    "UX_ShipmentReturnItems_Return_OrderItem_NoSerial",
    ShipmentReturnItem.ShipmentReturnId,
    ShipmentReturnItem.OrderItemId,
    unique=True,
    postgresql_where=text('"ProductSerialId" IS NULL'),
)
Index(
    "UX_ShipmentReturnItems_Return_Serial",
    ShipmentReturnItem.ShipmentReturnId,
    ShipmentReturnItem.ProductSerialId,
    unique=True,
    postgresql_where=text('"ProductSerialId" IS NOT NULL'),
)
Index("IX_ShipmentReturnItems_ProductSerialId", ShipmentReturnItem.ProductSerialId)
