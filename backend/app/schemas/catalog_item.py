"""Admin forms preserve the Product parent and its independently managed variants."""

import uuid
from typing import Any
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from .catalog import AdminProductVariantListResponse, ProductImageResponse
from .common import Money, NonNegativeInt, ProductStatus, RequestSchema, varchar
from app.core.catalog_media import technical_specifications, validate_specifications


class CatalogItemImage(RequestSchema):
    ImageUrl: varchar(500)
    IsDefault: bool = False

    @field_validator("ImageUrl")
    @classmethod
    def valid_url(cls, value: str) -> str:
        value = value.strip()
        url = urlsplit(value)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("Đường dẫn ảnh phải là URL HTTP hoặc HTTPS hợp lệ")
        return value


class CatalogProductWrite(RequestSchema):
    """Shared information: updating this form affects every variant of this Product."""

    NULLABLE_FIELDS = frozenset({"Description", "Specifications"})

    Name: varchar(255)
    CategoryId: uuid.UUID
    BrandId: uuid.UUID
    WarrantyMonths: NonNegativeInt
    Status: ProductStatus
    Description: str | None = None
    Specifications: dict[str, Any] | None = None
    Images: list[CatalogItemImage] = Field(default_factory=list)
    _specifications = field_validator("Specifications")(validate_specifications)

    @field_validator("Name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Tên sản phẩm không được để trống")
        return value.strip()

    @model_validator(mode="after")
    def one_default_image(self):
        if sum(image.IsDefault for image in self.Images) > 1:
            raise ValueError("Chỉ chọn một ảnh mặc định")
        if len({image.ImageUrl for image in self.Images}) != len(self.Images):
            raise ValueError("Bộ ảnh sản phẩm có ảnh bị trùng")
        return self


class CatalogVariantWrite(RequestSchema):
    """No parent metadata, ProductId, stock or cost may be changed by a variant edit."""

    NULLABLE_FIELDS = frozenset({"Storage", "CompareAtPrice", "VariantImageUrls", "DefaultImageUrl"})

    Sku: varchar(50)
    Color: varchar(50)
    Storage: varchar(50) | None = None
    Price: Money
    CompareAtPrice: Money | None = None
    MinStockLevel: NonNegativeInt = 0
    IsActive: bool = True
    IsSerialTracked: bool = False
    VariantImageUrls: list[varchar(500)] | None = None
    DefaultImageUrl: varchar(500) | None = None
    IsDefaultVariant: bool = False
    AdditionalImages: list[CatalogItemImage] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_image_selection(self):
        if self.CompareAtPrice is not None and self.CompareAtPrice < self.Price:
            raise ValueError("Giá niêm yết phải lớn hơn hoặc bằng giá bán")
        if self.VariantImageUrls is not None and len(set(self.VariantImageUrls)) != len(self.VariantImageUrls):
            raise ValueError("Không chọn trùng ảnh cho biến thể")
        if self.DefaultImageUrl is not None and (self.VariantImageUrls is None or self.DefaultImageUrl not in self.VariantImageUrls):
            raise ValueError("Ảnh đại diện phải nằm trong những ảnh đã chọn")
        return self

    @field_validator("Sku", "Color")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("SKU và màu sắc không được để trống")
        return value.strip()

    @field_validator("Storage")
    @classmethod
    def trim_storage(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class CatalogItemCreate(CatalogVariantWrite):
    NULLABLE_FIELDS = CatalogVariantWrite.NULLABLE_FIELDS | frozenset({"Product", "ProductId"})

    ProductId: uuid.UUID | None = None
    Product: CatalogProductWrite | None = None

    @model_validator(mode="after")
    def one_parent(self):
        if (self.ProductId is None) == (self.Product is None):
            raise ValueError("Chọn sản phẩm đã có hoặc nhập thông tin sản phẩm mới")
        return self


class CatalogItemResponse(AdminProductVariantListResponse):
    CategoryId: uuid.UUID
    BrandId: uuid.UUID
    WarrantyMonths: int
    Description: str | None
    Specifications: dict[str, Any] | None
    Images: list[ProductImageResponse]
    VariantImages: list[ProductImageResponse] = Field(default_factory=list)
    DefaultVariantId: uuid.UUID | None = None
    IsDefaultVariant: bool = False
    _specifications = field_validator("Specifications")(technical_specifications)
