from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Index,
    func,
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
    from .catalog import Category, Product
    from .order import Order
    from .user import User


PROMOTION_STATUSES = ("Draft", "Scheduled", "Active", "Expired", "Cancelled")
DISCOUNT_TYPES = ("Percentage", "FixedAmount")


class Promotion(Base):
    """Nơi duy nhất quản lý thông tin giảm giá; Coupon chỉ tham chiếu Promotion."""

    __tablename__ = "Promotions"
    __table_args__ = (
        check_in("DiscountType", DISCOUNT_TYPES, "DiscountType_Valid"),
        CheckConstraint('"DiscountValue" >= 0', name="DiscountValue_NonNegative"),
        CheckConstraint(
            "\"DiscountType\" <> 'Percentage' OR \"DiscountValue\" <= 100",
            name="DiscountValue_PercentageMax",
        ),
        CheckConstraint('"MinOrderValue" >= 0', name="MinOrderValue_NonNegative"),
        CheckConstraint('"MaxDiscountAmount" >= 0', name="MaxDiscountAmount_NonNegative"),
        CheckConstraint('"EndDate" >= "StartDate"', name="EndDate_AfterStartDate"),
        check_in("Status", PROMOTION_STATUSES, "Status_Valid"),
    )

    PromotionId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    CreatedByUserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    Name: Mapped[str] = mapped_column(String(255), nullable=False)
    Description: Mapped[str | None] = mapped_column(Text, nullable=True)
    DiscountType: Mapped[str] = mapped_column(String(20), nullable=False)
    DiscountValue: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    MinOrderValue: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # NULL = không giới hạn số tiền giảm tối đa.
    MaxDiscountAmount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    StartDate: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    EndDate: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    Status: Mapped[str] = mapped_column(String(30), nullable=False)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    created_by: Mapped[User] = relationship(
        back_populates="created_promotions", foreign_keys=[CreatedByUserId]
    )
    promotion_products: Mapped[list[PromotionProduct]] = relationship(
        back_populates="promotion",
        foreign_keys="PromotionProduct.PromotionId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    promotion_categories: Mapped[list[PromotionCategory]] = relationship(
        back_populates="promotion",
        foreign_keys="PromotionCategory.PromotionId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    coupons: Mapped[list[Coupon]] = relationship(
        back_populates="promotion", foreign_keys="Coupon.PromotionId", passive_deletes="all"
    )


class PromotionProduct(Base):
    __tablename__ = "PromotionProducts"

    PromotionId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("Promotions.PromotionId", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    ProductId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("Products.ProductId", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    promotion: Mapped[Promotion] = relationship(
        back_populates="promotion_products", foreign_keys=[PromotionId]
    )
    product: Mapped[Product] = relationship(
        back_populates="promotion_products", foreign_keys=[ProductId]
    )


class PromotionCategory(Base):
    __tablename__ = "PromotionCategories"

    PromotionId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("Promotions.PromotionId", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    CategoryId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("Categories.CategoryId", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    promotion: Mapped[Promotion] = relationship(
        back_populates="promotion_categories", foreign_keys=[PromotionId]
    )
    category: Mapped[Category] = relationship(
        back_populates="promotion_categories", foreign_keys=[CategoryId]
    )


class Coupon(Base):
    """Chỉ lưu thông tin mã coupon; thông tin giảm giá và thời gian hiệu lực lấy từ Promotion."""

    __tablename__ = "Coupons"
    __table_args__ = (
        CheckConstraint('"UsageLimit" >= 0', name="UsageLimit_NonNegative"),
        CheckConstraint('"UsedCount" >= 0', name="UsedCount_NonNegative"),
    )

    CouponId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    PromotionId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("Promotions.PromotionId", ondelete="RESTRICT"),
        nullable=False,
    )
    CreatedByUserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    # Unique không phân biệt hoa thường: UX_Coupons_Code_Lower trên lower("Code").
    Code: Mapped[str] = mapped_column(String(50), nullable=False)
    Name: Mapped[str] = mapped_column(String(255), nullable=False)
    UsageLimit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    UsedCount: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    promotion: Mapped[Promotion] = relationship(back_populates="coupons", foreign_keys=[PromotionId])
    created_by: Mapped[User] = relationship(
        back_populates="created_coupons", foreign_keys=[CreatedByUserId]
    )
    orders: Mapped[list[Order]] = relationship(
        back_populates="coupon", foreign_keys="Order.CouponId", passive_deletes="all"
    )


# Mã coupon unique không phân biệt hoa thường.
Index("UX_Coupons_Code_Lower", func.lower(Coupon.Code), unique=True)
