"""Schemas cho Categories, Brands, Products, ProductVariants, ProductImages, ProductSerials.

CostPrice (giá vốn hiện tại) và MinStockLevel chỉ có trong schema dành cho admin/staff.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from .common import (
    Money,
    NonNegativeInt,
    ProductSerialStatus,
    ProductStatus,
    RequestSchema,
    ResponseSchema,
    relation_field,
    varchar,
)

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class CategoryCreate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"ParentCategoryId", "Description"})

    ParentCategoryId: uuid.UUID | None = None
    Name: varchar(255)
    Slug: varchar(300)
    Description: str | None = None
    DisplayOrder: int | None = None
    IsActive: bool | None = None


class CategoryUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"ParentCategoryId", "Description"})

    ParentCategoryId: uuid.UUID | None = None
    Name: varchar(255) | None = None
    Slug: varchar(300) | None = None
    Description: str | None = None
    DisplayOrder: int | None = None
    IsActive: bool | None = None


class CategorySummary(ResponseSchema):
    CategoryId: uuid.UUID
    Name: str
    Slug: str


class CategoryResponse(ResponseSchema):
    CategoryId: uuid.UUID
    ParentCategoryId: uuid.UUID | None
    Name: str
    Slug: str
    Description: str | None
    DisplayOrder: int
    IsActive: bool


# ---------------------------------------------------------------------------
# Brands
# ---------------------------------------------------------------------------


class BrandCreate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Description", "LogoUrl"})

    Name: varchar(255)
    Slug: varchar(300)
    Description: str | None = None
    LogoUrl: varchar(500) | None = None
    IsActive: bool | None = None


class BrandUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Description", "LogoUrl"})

    Name: varchar(255) | None = None
    Slug: varchar(300) | None = None
    Description: str | None = None
    LogoUrl: varchar(500) | None = None
    IsActive: bool | None = None


class BrandSummary(ResponseSchema):
    BrandId: uuid.UUID
    Name: str
    Slug: str
    LogoUrl: str | None


class BrandResponse(ResponseSchema):
    BrandId: uuid.UUID
    Name: str
    Slug: str
    Description: str | None
    LogoUrl: str | None
    IsActive: bool


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class ProductCreate(RequestSchema):
    """AverageRating, ReviewCount, SoldQuantity do hệ thống tính, không nhận từ client."""

    NULLABLE_FIELDS = frozenset({"Description", "Specifications"})

    CategoryId: uuid.UUID
    BrandId: uuid.UUID
    Name: varchar(255)
    Slug: varchar(300)
    Description: str | None = None
    Specifications: dict[str, Any] | None = None
    WarrantyMonths: int
    Status: ProductStatus


class ProductUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Description", "Specifications"})

    CategoryId: uuid.UUID | None = None
    BrandId: uuid.UUID | None = None
    Name: varchar(255) | None = None
    Slug: varchar(300) | None = None
    Description: str | None = None
    Specifications: dict[str, Any] | None = None
    WarrantyMonths: int | None = None
    Status: ProductStatus | None = None


class ProductSummary(ResponseSchema):
    """Dùng cho danh sách sản phẩm."""

    ProductId: uuid.UUID
    CategoryId: uuid.UUID
    BrandId: uuid.UUID
    Name: str
    Slug: str
    Status: ProductStatus
    AverageRating: Decimal = Field(ge=0, le=5)
    ReviewCount: NonNegativeInt
    SoldQuantity: NonNegativeInt


class ProductResponse(ProductSummary):
    Description: str | None
    Specifications: dict[str, Any] | None
    WarrantyMonths: int
    CreatedAt: datetime
    UpdatedAt: datetime


class AdminProductResponse(ProductResponse):
    IsDeleted: bool


# ---------------------------------------------------------------------------
# ProductVariants
# ---------------------------------------------------------------------------


class ProductVariantCreate(RequestSchema):
    """Admin/staff tạo biến thể. ProductId lấy từ đường dẫn hoặc truyền vào tùy endpoint."""

    NULLABLE_FIELDS = frozenset({"Color", "Storage"})

    ProductId: uuid.UUID
    Sku: varchar(50)
    VariantName: varchar(255)
    Color: varchar(50) | None = None
    Storage: varchar(50) | None = None
    Price: Money
    CostPrice: Money | None = None
    StockQuantity: NonNegativeInt | None = None
    MinStockLevel: NonNegativeInt | None = None
    IsActive: bool | None = None


class ProductVariantUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Color", "Storage"})

    Sku: varchar(50) | None = None
    VariantName: varchar(255) | None = None
    Color: varchar(50) | None = None
    Storage: varchar(50) | None = None
    Price: Money | None = None
    CostPrice: Money | None = None
    StockQuantity: NonNegativeInt | None = None
    MinStockLevel: NonNegativeInt | None = None
    IsActive: bool | None = None


class ProductVariantResponse(ResponseSchema):
    """Dành cho khách hàng: không có CostPrice, MinStockLevel."""

    ProductVariantId: uuid.UUID
    ProductId: uuid.UUID
    Sku: str
    VariantName: str
    Color: str | None
    Storage: str | None
    Price: Money
    StockQuantity: NonNegativeInt
    IsActive: bool


class AdminProductVariantResponse(ProductVariantResponse):
    CostPrice: Money
    MinStockLevel: NonNegativeInt
    IsDeleted: bool


# ---------------------------------------------------------------------------
# ProductImages
# ---------------------------------------------------------------------------


class ProductImageCreate(RequestSchema):
    ImageUrl: varchar(500)
    DisplayOrder: int | None = None
    IsDefault: bool | None = None


class ProductImageUpdate(RequestSchema):
    ImageUrl: varchar(500) | None = None
    DisplayOrder: int | None = None
    IsDefault: bool | None = None


class ProductImageResponse(ResponseSchema):
    ProductImageId: uuid.UUID
    ProductId: uuid.UUID
    ImageUrl: str
    DisplayOrder: int
    IsDefault: bool


# ---------------------------------------------------------------------------
# Product detail
# ---------------------------------------------------------------------------


class ProductDetailResponse(ProductResponse):
    """Chi tiết sản phẩm cho khách hàng."""

    Category: CategorySummary = relation_field("category")
    Brand: BrandSummary = relation_field("brand")
    Variants: list[ProductVariantResponse] = relation_field("variants")
    Images: list[ProductImageResponse] = relation_field("images")


class AdminProductDetailResponse(AdminProductResponse):
    Category: CategorySummary = relation_field("category")
    Brand: BrandSummary = relation_field("brand")
    Variants: list[AdminProductVariantResponse] = relation_field("variants")
    Images: list[ProductImageResponse] = relation_field("images")


# ---------------------------------------------------------------------------
# ProductSerials (staff/admin)
# ---------------------------------------------------------------------------


class ProductSerialCreate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"WarrantyStartDate", "WarrantyEndDate"})

    ProductVariantId: uuid.UUID
    SerialNumber: varchar(100)
    WarrantyStartDate: date | None = None
    WarrantyEndDate: date | None = None
    Status: ProductSerialStatus


class ProductSerialUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"OrderItemId", "WarrantyStartDate", "WarrantyEndDate"})

    OrderItemId: uuid.UUID | None = None
    SerialNumber: varchar(100) | None = None
    WarrantyStartDate: date | None = None
    WarrantyEndDate: date | None = None
    Status: ProductSerialStatus | None = None


class ProductSerialResponse(ResponseSchema):
    ProductSerialId: uuid.UUID
    ProductVariantId: uuid.UUID
    OrderItemId: uuid.UUID | None
    SerialNumber: str
    WarrantyStartDate: date | None
    WarrantyEndDate: date | None
    Status: ProductSerialStatus
