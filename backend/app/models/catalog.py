from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    FetchedValue,
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
    from .order import OrderItem
    from .promotion import PromotionCategory, PromotionProduct
    from .purchasing import PurchaseOrderItem
    from .review import Review
    from .service_request import WarrantyRequest
    from .wishlist_cart import CartItem, WishlistItem


PRODUCT_STATUSES = ("Draft", "Active", "Inactive", "Discontinued")
PRODUCT_SERIAL_STATUSES = ("Available", "Reserved", "Sold", "Warranty", "Returned")


class Category(Base):
    __tablename__ = "Categories"

    CategoryId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ParentCategoryId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("Categories.CategoryId", ondelete="RESTRICT"),
        nullable=True,
    )
    Name: Mapped[str] = mapped_column(String(255), nullable=False)
    Slug: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    Description: Mapped[str | None] = mapped_column(Text, nullable=True)
    DisplayOrder: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    parent: Mapped[Category | None] = relationship(
        back_populates="children", foreign_keys=[ParentCategoryId], remote_side=[CategoryId]
    )
    children: Mapped[list[Category]] = relationship(
        back_populates="parent", foreign_keys=[ParentCategoryId], passive_deletes="all"
    )
    products: Mapped[list[Product]] = relationship(
        back_populates="category", foreign_keys="Product.CategoryId", passive_deletes="all"
    )
    promotion_categories: Mapped[list[PromotionCategory]] = relationship(
        back_populates="category",
        foreign_keys="PromotionCategory.CategoryId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Brand(Base):
    __tablename__ = "Brands"

    BrandId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    Name: Mapped[str] = mapped_column(String(255), nullable=False)
    Slug: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    Description: Mapped[str | None] = mapped_column(Text, nullable=True)
    LogoUrl: Mapped[str | None] = mapped_column(String(500), nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    products: Mapped[list[Product]] = relationship(
        back_populates="brand", foreign_keys="Product.BrandId", passive_deletes="all"
    )


class Product(Base):
    __tablename__ = "Products"
    __table_args__ = (
        check_in("Status", PRODUCT_STATUSES, "Status_Valid"),
        CheckConstraint('"AverageRating" BETWEEN 0 AND 5', name="AverageRating_Range"),
        CheckConstraint('"ReviewCount" >= 0', name="ReviewCount_NonNegative"),
        CheckConstraint('"SoldQuantity" >= 0', name="SoldQuantity_NonNegative"),
    )

    ProductId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    CategoryId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("Categories.CategoryId", ondelete="RESTRICT"),
        nullable=False,
    )
    BrandId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Brands.BrandId", ondelete="RESTRICT"), nullable=False
    )
    Name: Mapped[str] = mapped_column(String(255), nullable=False)
    Slug: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    Description: Mapped[str | None] = mapped_column(Text, nullable=True)
    Specifications: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    WarrantyMonths: Mapped[int] = mapped_column(Integer, nullable=False)
    Status: Mapped[str] = mapped_column(String(30), nullable=False)
    AverageRating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, server_default=text("0")
    )
    ReviewCount: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    SoldQuantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
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
    IsDeleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    category: Mapped[Category] = relationship(back_populates="products", foreign_keys=[CategoryId])
    brand: Mapped[Brand] = relationship(back_populates="products", foreign_keys=[BrandId])
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product",
        foreign_keys="ProductVariant.ProductId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product",
        foreign_keys="ProductImage.ProductId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    wishlist_items: Mapped[list[WishlistItem]] = relationship(
        back_populates="product",
        foreign_keys="WishlistItem.ProductId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    promotion_products: Mapped[list[PromotionProduct]] = relationship(
        back_populates="product",
        foreign_keys="PromotionProduct.ProductId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reviews: Mapped[list[Review]] = relationship(
        back_populates="product", foreign_keys="Review.ProductId", passive_deletes="all"
    )


class ProductVariant(Base):
    __tablename__ = "ProductVariants"
    __table_args__ = (
        CheckConstraint('"Price" >= 0', name="Price_NonNegative"),
        CheckConstraint('"CostPrice" >= 0', name="CostPrice_NonNegative"),
        CheckConstraint('"StockQuantity" >= 0', name="StockQuantity_NonNegative"),
        CheckConstraint('"MinStockLevel" >= 0', name="MinStockLevel_NonNegative"),
    )

    ProductVariantId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ProductId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Products.ProductId", ondelete="CASCADE"), nullable=False
    )
    Sku: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    VariantName: Mapped[str] = mapped_column(String(255), nullable=False)
    Color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    Storage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    Price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # Giá vốn hiện tại (COGS).
    CostPrice: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default=text("0")
    )
    StockQuantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    MinStockLevel: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    IsDeleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    product: Mapped[Product] = relationship(back_populates="variants", foreign_keys=[ProductId])
    serials: Mapped[list[ProductSerial]] = relationship(
        back_populates="product_variant",
        foreign_keys="ProductSerial.ProductVariantId",
        passive_deletes="all",
    )
    cart_items: Mapped[list[CartItem]] = relationship(
        back_populates="product_variant",
        foreign_keys="CartItem.ProductVariantId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    order_items: Mapped[list[OrderItem]] = relationship(
        back_populates="product_variant",
        foreign_keys="OrderItem.ProductVariantId",
        passive_deletes="all",
    )
    purchase_order_items: Mapped[list[PurchaseOrderItem]] = relationship(
        back_populates="product_variant",
        foreign_keys="PurchaseOrderItem.ProductVariantId",
        passive_deletes="all",
    )


class ProductImage(Base):
    __tablename__ = "ProductImages"

    ProductImageId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ProductId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Products.ProductId", ondelete="CASCADE"), nullable=False
    )
    ImageUrl: Mapped[str] = mapped_column(String(500), nullable=False)
    DisplayOrder: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    IsDefault: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    product: Mapped[Product] = relationship(back_populates="images", foreign_keys=[ProductId])


class ProductSerial(Base):
    __tablename__ = "ProductSerials"
    __table_args__ = (check_in("Status", PRODUCT_SERIAL_STATUSES, "Status_Valid"),)

    ProductSerialId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ProductVariantId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ProductVariants.ProductVariantId", ondelete="RESTRICT"),
        nullable=False,
    )
    OrderItemId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("OrderItems.OrderItemId", ondelete="SET NULL"),
        nullable=True,
    )
    SerialNumber: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    WarrantyStartDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    WarrantyEndDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    Status: Mapped[str] = mapped_column(String(30), nullable=False)

    product_variant: Mapped[ProductVariant] = relationship(
        back_populates="serials", foreign_keys=[ProductVariantId]
    )
    order_item: Mapped[OrderItem | None] = relationship(
        back_populates="product_serials", foreign_keys=[OrderItemId]
    )
    warranty_requests: Mapped[list[WarrantyRequest]] = relationship(
        back_populates="product_serial",
        foreign_keys="WarrantyRequest.ProductSerialId",
        passive_deletes="all",
    )
