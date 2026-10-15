"""Product parent / variant admin forms, using existing services and transactions.

New Product creation always includes its first variant. Further variants reuse the
selected ProductId. Variant edits never reparent, clone or overwrite shared metadata.
"""

import re
import unicodedata
import uuid

from app.repositories.catalog import ProductImageRepository
from app.core.catalog_media import default_variant_id, set_variant_media, technical_specifications, variant_images
from app.schemas.catalog import (AdminProductDetailResponse, ProductCreate, ProductUpdate, ProductImageResponse,
                                 ProductVariantCreate, ProductVariantUpdate)
from app.schemas.catalog_item import (CatalogItemCreate, CatalogItemResponse, CatalogProductWrite,
                                      CatalogVariantWrite)
from .actor import ADMIN_ONLY, STAFF_OR_ADMIN, Actor, require_role
from .base import BaseService
from .catalog import ProductService, ProductVariantService
from .exceptions import BusinessRuleError, NotFoundError


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
        selected, thumbnail = variant_images(product, variant_id, images)
        default_id = default_variant_id(product)
        return CatalogItemResponse(
            **self.stock_items.get_variant(actor, variant_id).model_dump(),
            **{field: getattr(product, field) for field in CATALOG_FIELDS},
            Category=product.category, Brand=product.brand, Images=images,
            ThumbnailUrl=thumbnail,
            VariantImages=[ProductImageResponse.model_validate(image).model_copy(update={"IsDefault": image.ImageUrl == thumbnail}) for image in selected],
            DefaultVariantId=default_id, IsDefaultVariant=variant_id == default_id,
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

    def _save_media(self, product, variant_id, data, *, previous_default=None):
        existing = self.images.list_by_product(product.ProductId)
        known = {image.ImageUrl for image in existing}
        order = max((image.DisplayOrder for image in existing), default=-1) + 1
        for image in data.AdditionalImages:
            if image.ImageUrl not in known:
                self.images.create({"ProductId": product.ProductId, "ImageUrl": image.ImageUrl,
                                    "DisplayOrder": order, "IsDefault": not known})
                known.add(image.ImageUrl)
                order += 1
        self.images.flush()
        urls = data.VariantImageUrls
        if urls is not None:
            available = {image.ImageUrl for image in self.images.list_by_product(product.ProductId)}
            if any(url not in available for url in urls):
                raise BusinessRuleError("Chỉ chọn ảnh từ bộ ảnh của sản phẩm này", code="variant_image_not_in_product")
        set_variant_media(product, variant_id, urls=urls,
                          default_url=data.DefaultImageUrl or (urls[0] if urls else None),
                          make_default=data.IsDefaultVariant,
                          variants=self.variants.list_by_product(product.ProductId), previous_default=previous_default)
        self.products.flush()

    def create_item(self, actor: Actor, data: CatalogItemCreate) -> CatalogItemResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            if data.ProductId is not None:
                product = self._product(data.ProductId, lock=True)
                product_id = product.ProductId
            else:
                shared = data.Product
                product_id = self.catalog.create_product(actor, ProductCreate(
                    **{field: getattr(shared, field) for field in CATALOG_FIELDS},
                    Slug=self._slug(shared.Name))).ProductId
                self._replace_images(product_id, shared.Images)
                product = self._product(product_id, lock=True)
            previous_default = default_variant_id(product, self.variants.list_by_product(product_id))
            variant = self.stock_items.create_variant(actor, ProductVariantCreate(
                ProductId=product_id, **self._variant_values(data)))
            self._save_media(product, variant.ProductVariantId, data, previous_default=previous_default)
            self.session.expire(product, ["variants"])
            return self.get_item(actor, variant.ProductVariantId)

    def update_item(self, actor: Actor, variant_id: uuid.UUID, data: CatalogVariantWrite) -> CatalogItemResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            _, parent = self._get(variant_id)
            product = self._product(parent.ProductId, lock=True)
            variant, _ = self._get(variant_id, lock=True)
            values = {field: value for field, value in self._variant_values(data).items()
                      if value != getattr(variant, field)}
            if values:
                self.stock_items.update_variant(actor, variant_id, ProductVariantUpdate(**values))
            self._save_media(product, variant_id, data)
            return self.get_item(actor, variant_id)

    def update_product(self, actor: Actor, product_id: uuid.UUID,
                       data: CatalogProductWrite) -> AdminProductDetailResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            product = self._product(product_id, lock=True)
            values = {field: getattr(data, field) for field in CATALOG_FIELDS
                      if getattr(data, field) != (technical_specifications(product.Specifications) if field == "Specifications" else getattr(product, field))}
            if values:
                self.catalog.update_product(actor, product_id, ProductUpdate(**values))
            self._replace_images(product_id, data.Images)
            self.session.expire(product, ["images", "category", "brand"])
            return self.catalog.admin_get_product(actor, product_id)
