"""Product parent / variant admin forms, using existing services and transactions.

New Product creation always includes its first variant. Further variants reuse the
selected ProductId. Variant edits never reparent, clone or overwrite shared metadata.
"""

import re
import unicodedata
import uuid

from app.repositories.catalog import ProductImageRepository
from app.schemas.catalog import (AdminProductDetailResponse, ProductCreate, ProductUpdate,
                                 ProductVariantCreate, ProductVariantUpdate)
from app.schemas.catalog_item import (CatalogItemCreate, CatalogItemResponse, CatalogProductWrite,
                                      CatalogVariantWrite)
from .actor import ADMIN_ONLY, STAFF_OR_ADMIN, Actor, require_role
from .base import BaseService
from .catalog import ProductService, ProductVariantService
from .exceptions import NotFoundError


CATALOG_FIELDS = ("Name", "CategoryId", "BrandId", "WarrantyMonths", "Description", "Specifications", "Status")


class CatalogItemService(BaseService):
    def __init__(self, session):
        super().__init__(session)
        self.catalog = ProductService(session)
        self.stock_items = ProductVariantService(session)
        self.products = self.catalog.products
        self.variants = self.stock_items.variants
        self.images = ProductImageRepository(session)

    @staticmethod
    def _slug(name):
        text = unicodedata.normalize("NFKD", name.lower().replace("đ", "d"))
        text = text.encode("ascii", "ignore").decode()
        base = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:260] or "san-pham"
        return f"{base}-{uuid.uuid4().hex}"

    def _product(self, product_id, *, lock=False):
        product = self.products.get_by_id_for_update(product_id) if lock else self.products.get_by_id(product_id)
        if product is None or product.IsDeleted:
            raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
        return product

    def _get(self, variant_id, *, lock=False):
        variant = self.variants.get_by_id_for_update(variant_id) if lock else self.variants.get_by_id(variant_id)
        if variant is None or variant.IsDeleted:
            raise NotFoundError("Không tìm thấy biến thể", code="variant_not_found")
        return variant, self._product(variant.ProductId)

    def get_item(self, actor: Actor, variant_id: uuid.UUID) -> CatalogItemResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        variant, product = self._get(variant_id)
        images = self.images.list_by_product(product.ProductId)
        images.sort(key=lambda image: (not image.IsDefault, image.DisplayOrder, str(image.ProductImageId)))
        return CatalogItemResponse(
            **self.stock_items.get_variant(actor, variant_id).model_dump(),
            **{field: getattr(product, field) for field in CATALOG_FIELDS},
            Category=product.category, Brand=product.brand, Images=images,
            ThumbnailUrl=images[0].ImageUrl if images else None,
            IsLowStock=0 < variant.StockQuantity <= variant.MinStockLevel,
        )

    @staticmethod
    def _variant_values(data):
        return {**data.model_dump(include={"Sku", "Color", "Storage", "Price", "MinStockLevel",
                                          "IsSerialTracked", "IsActive"}),
                "VariantName": " · ".join(filter(None, [data.Color, data.Storage]))}

    def _replace_images(self, product_id, images):
        current = sorted(self.images.list_by_product(product_id), key=lambda image: image.DisplayOrder)
        has_default = any(image.IsDefault for image in images)
        desired = [(image.ImageUrl, image.IsDefault or (not has_default and index == 0))
                   for index, image in enumerate(images)]
        if [(image.ImageUrl, image.IsDefault) for image in current] == desired:
            return
        for old in current:
            self.images.delete(old)
        self.images.flush()
        for index, (url, default) in enumerate(desired):
            self.images.create({"ProductId": product_id, "ImageUrl": url, "DisplayOrder": index, "IsDefault": default})
        self.images.flush()

    def create_item(self, actor: Actor, data: CatalogItemCreate) -> CatalogItemResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            if data.ProductId is not None:
                product_id = self._product(data.ProductId, lock=True).ProductId
            else:
                shared = data.Product
                product_id = self.catalog.create_product(actor, ProductCreate(
                    **{field: getattr(shared, field) for field in CATALOG_FIELDS},
                    Slug=self._slug(shared.Name))).ProductId
                self._replace_images(product_id, shared.Images)
            variant = self.stock_items.create_variant(actor, ProductVariantCreate(
                ProductId=product_id, **self._variant_values(data)))
            return self.get_item(actor, variant.ProductVariantId)

    def update_item(self, actor: Actor, variant_id: uuid.UUID, data: CatalogVariantWrite) -> CatalogItemResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            variant, _ = self._get(variant_id, lock=True)
            values = {field: value for field, value in self._variant_values(data).items()
                      if value != getattr(variant, field)}
            if values:
                self.stock_items.update_variant(actor, variant_id, ProductVariantUpdate(**values))
            return self.get_item(actor, variant_id)

    def update_product(self, actor: Actor, product_id: uuid.UUID,
                       data: CatalogProductWrite) -> AdminProductDetailResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            product = self._product(product_id, lock=True)
            values = {field: getattr(data, field) for field in CATALOG_FIELDS
                      if getattr(data, field) != getattr(product, field)}
            if values:
                self.catalog.update_product(actor, product_id, ProductUpdate(**values))
            self._replace_images(product_id, data.Images)
            self.session.expire(product, ["images", "category", "brand"])
            return self.catalog.admin_get_product(actor, product_id)
