"""StockAdjustments: lịch sử khai báo tồn đầu kỳ (Opening) và điều chỉnh kho thủ công của Admin.

Chỉ ghi thêm, không sửa/xóa (database trigger chặn UPDATE/DELETE). Giao dịch mua/bán vẫn được truy vết
qua PurchaseOrderItems/OrderItems; bảng này không phải sổ kho đầy đủ.

StockAdjustmentSerials: Serial/IMEI thuộc từng phiếu (Opening/Increase → In, Decrease → Out); chỉ ghi thêm.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, check_in

ADJUSTMENT_OPENING = "Opening"
ADJUSTMENT_INCREASE = "Increase"
ADJUSTMENT_DECREASE = "Decrease"
STOCK_ADJUSTMENT_TYPES = (ADJUSTMENT_OPENING, ADJUSTMENT_INCREASE, ADJUSTMENT_DECREASE)

SERIAL_DIRECTION_IN = "In"
SERIAL_DIRECTION_OUT = "Out"
SERIAL_DIRECTIONS = (SERIAL_DIRECTION_IN, SERIAL_DIRECTION_OUT)


class StockAdjustment(Base):
    __tablename__ = "StockAdjustments"
    __table_args__ = (
        check_in("AdjustmentType", STOCK_ADJUSTMENT_TYPES, "AdjustmentType_Valid"),
        CheckConstraint('"QuantityBefore" >= 0', name="QuantityBefore_NonNegative"),
        CheckConstraint('"QuantityAfter" >= 0', name="QuantityAfter_NonNegative"),
        CheckConstraint(
            '"QuantityChange" = "QuantityAfter" - "QuantityBefore"', name="QuantityChange_Consistent"
        ),
        CheckConstraint(
            "\"AdjustmentType\" <> 'Increase' OR \"QuantityChange\" > 0", name="Increase_Positive"
        ),
        CheckConstraint(
            "\"AdjustmentType\" <> 'Decrease' OR \"QuantityChange\" < 0", name="Decrease_Negative"
        ),
        CheckConstraint('"CostPriceBefore" >= 0', name="CostPriceBefore_NonNegative"),
        CheckConstraint('"CostPriceAfter" >= 0', name="CostPriceAfter_NonNegative"),
        # Chỉ Opening được đặt giá vốn; điều chỉnh tăng/giảm giữ nguyên giá vốn.
        CheckConstraint(
            "\"AdjustmentType\" = 'Opening' OR \"CostPriceAfter\" = \"CostPriceBefore\"",
            name="CostPrice_OnlyOpening",
        ),
        CheckConstraint("length(btrim(\"Reason\")) > 0", name="Reason_NotBlank"),
    )

    StockAdjustmentId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ProductVariantId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ProductVariants.ProductVariantId", ondelete="RESTRICT"),
        nullable=False,
    )
    AdjustedByUserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    AdjustmentType: Mapped[str] = mapped_column(String(20), nullable=False)
    QuantityBefore: Mapped[int] = mapped_column(Integer, nullable=False)
    QuantityChange: Mapped[int] = mapped_column(Integer, nullable=False)
    QuantityAfter: Mapped[int] = mapped_column(Integer, nullable=False)
    CostPriceBefore: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    CostPriceAfter: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    Reason: Mapped[str] = mapped_column(Text, nullable=False)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


# Mỗi biến thể chỉ có một lần khai báo tồn đầu kỳ.
Index(
    "UX_StockAdjustments_Opening_ProductVariantId",
    StockAdjustment.ProductVariantId,
    unique=True,
    postgresql_where=text("\"AdjustmentType\" = 'Opening'"),
)
Index("IX_StockAdjustments_ProductVariantId_CreatedAt", StockAdjustment.ProductVariantId, StockAdjustment.CreatedAt)


class StockAdjustmentSerial(Base):
    """Serial/IMEI được nhập (In: Opening/Increase) hoặc loại khỏi kho (Out: Decrease) bởi một phiếu điều chỉnh.

    Mỗi serial tối đa một lần In và một lần Out (UNIQUE ProductSerialId + Direction): không nhập hai lần, không loại
    khỏi kho hai lần. Hướng khớp loại phiếu, serial cùng biến thể với phiếu và chỉ ghi thêm: trigger trong migration
    8b7e3d1c5a29 (chưa áp dụng).
    """

    __tablename__ = "StockAdjustmentSerials"
    __table_args__ = (
        check_in("Direction", SERIAL_DIRECTIONS, "Direction_Valid"),
        UniqueConstraint("ProductSerialId", "Direction"),
    )

    StockAdjustmentId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("StockAdjustments.StockAdjustmentId", ondelete="RESTRICT"),
        primary_key=True,
    )
    ProductSerialId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ProductSerials.ProductSerialId", ondelete="RESTRICT"),
        primary_key=True,
    )
    Direction: Mapped[str] = mapped_column(String(10), nullable=False)
