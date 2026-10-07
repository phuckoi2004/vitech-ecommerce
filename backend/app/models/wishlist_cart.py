from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .catalog import Product, ProductVariant
    from .user import User


class Wishlist(Base):
    __tablename__ = "Wishlists"

    WishlistId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    UserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("Users.UserId", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    user: Mapped[User] = relationship(back_populates="wishlist", foreign_keys=[UserId])
    items: Mapped[list[WishlistItem]] = relationship(
        back_populates="wishlist",
        foreign_keys="WishlistItem.WishlistId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class WishlistItem(Base):
    __tablename__ = "WishlistItems"
    __table_args__ = (UniqueConstraint("WishlistId", "ProductId"),)

    WishlistItemId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    WishlistId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Wishlists.WishlistId", ondelete="CASCADE"), nullable=False
    )
    ProductId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Products.ProductId", ondelete="CASCADE"), nullable=False
    )
    AddedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    wishlist: Mapped[Wishlist] = relationship(back_populates="items", foreign_keys=[WishlistId])
    product: Mapped[Product] = relationship(back_populates="wishlist_items", foreign_keys=[ProductId])


class Cart(Base):
    __tablename__ = "Carts"

    CartId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    UserId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("Users.UserId", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Database trigger BEFORE UPDATE cập nhật cột này.
    UpdatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        server_onupdate=FetchedValue(),
    )

    user: Mapped[User] = relationship(back_populates="cart", foreign_keys=[UserId])
    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart",
        foreign_keys="CartItem.CartId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CartItem(Base):
    __tablename__ = "CartItems"
    __table_args__ = (
        UniqueConstraint("CartId", "ProductVariantId"),
        CheckConstraint('"Quantity" > 0', name="Quantity_Positive"),
        CheckConstraint('"UnitPrice" >= 0', name="UnitPrice_NonNegative"),
    )

    CartItemId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    CartId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Carts.CartId", ondelete="CASCADE"), nullable=False
    )
    ProductVariantId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ProductVariants.ProductVariantId", ondelete="CASCADE"),
        nullable=False,
    )
    Quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    UnitPrice: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    IsSelected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    AddedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    cart: Mapped[Cart] = relationship(back_populates="items", foreign_keys=[CartId])
    product_variant: Mapped[ProductVariant] = relationship(
        back_populates="cart_items", foreign_keys=[ProductVariantId]
    )
