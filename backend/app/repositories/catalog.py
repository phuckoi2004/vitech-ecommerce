"""Repositories cho Categories, Brands, Products, ProductVariants, ProductImages, ProductSerials."""

import uuid
from collections.abc import Collection

from sqlalchemy import exists, select
from sqlalchemy.orm import joinedload, selectinload

from app.models import Brand, Category, Product, ProductImage, ProductSerial, ProductVariant

from .base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    model = Category

    def get_by_slug(self, slug: str) -> Category | None:
        return self.get_one(Category.Slug == slug)

    def exists_by_slug(self, slug: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [Category.Slug == slug]
        if exclude_id is not None:
            conditions.append(Category.CategoryId != exclude_id)
        return self.exists(*conditions)

    def list_categories(
        self, *, is_active: bool | None = None, parent_id: uuid.UUID | None = None, roots_only: bool = False
    ) -> list[Category]:
        """roots_only=True: chỉ danh mục gốc (ParentCategoryId IS NULL); parent_id: con trực tiếp."""
        conditions = []
        if is_active is not None:
            conditions.append(Category.IsActive.is_(is_active))
        if roots_only:
            conditions.append(Category.ParentCategoryId.is_(None))
        elif parent_id is not None:
            conditions.append(Category.ParentCategoryId == parent_id)
        return self.get_all(*conditions, order_by=(Category.DisplayOrder, Category.Name, Category.CategoryId))

    def has_children(self, category_id: uuid.UUID) -> bool:
        return self.exists(Category.ParentCategoryId == category_id)

    def has_products(self, category_id: uuid.UUID) -> bool:
        return bool(self.session.scalar(select(exists().where(Product.CategoryId == category_id))))


class BrandRepository(BaseRepository[Brand]):
    model = Brand

    def get_by_slug(self, slug: str) -> Brand | None:
        return self.get_one(Brand.Slug == slug)

    def exists_by_slug(self, slug: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [Brand.Slug == slug]
        if exclude_id is not None:
            conditions.append(Brand.BrandId != exclude_id)
        return self.exists(*conditions)

    def list_brands(self, *, is_active: bool | None = None) -> list[Brand]:
        conditions = [] if is_active is None else [Brand.IsActive.is_(is_active)]
        return self.get_all(*conditions, order_by=(Brand.Name, Brand.BrandId))

    def has_products(self, brand_id: uuid.UUID) -> bool:
        return bool(self.session.scalar(select(exists().where(Product.BrandId == brand_id))))


class ProductRepository(BaseRepository[Product]):
    model = Product

    def get_by_slug(self, slug: str) -> Product | None:
        return self.get_one(Product.Slug == slug)

    def exists_by_slug(self, slug: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [Product.Slug == slug]
        if exclude_id is not None:
            conditions.append(Product.ProductId != exclude_id)
        return self.exists(*conditions)

    @staticmethod
    def _detail_options() -> tuple:
        return (
            joinedload(Product.category),
            joinedload(Product.brand),
            selectinload(Product.variants),
            selectinload(Product.images),
        )

    def get_detail(self, product_id: uuid.UUID) -> Product | None:
        """Product kèm Category, Brand, Variants, Images (cho ProductDetailResponse)."""
        stmt = select(Product).where(Product.ProductId == product_id).options(*self._detail_options())
        return self.session.scalars(stmt).one_or_none()

    def get_detail_by_slug(self, slug: str) -> Product | None:
        stmt = select(Product).where(Product.Slug == slug).options(*self._detail_options())
        return self.session.scalars(stmt).one_or_none()

    def _filters(
        self,
        category_ids: Collection[uuid.UUID] | None,
        brand_id: uuid.UUID | None,
        status: str | None,
        include_deleted: bool,
    ) -> list:
        conditions = []
        if category_ids:
            conditions.append(Product.CategoryId.in_(category_ids))
        if brand_id is not None:
            conditions.append(Product.BrandId == brand_id)
        if status is not None:
            conditions.append(Product.Status == status)
        if not include_deleted:
            conditions.append(Product.IsDeleted.is_(False))
        return conditions

    def list_products(
        self,
        *,
        category_ids: Collection[uuid.UUID] | None = None,
        brand_id: uuid.UUID | None = None,
        status: str | None = None,
        include_deleted: bool = False,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Product]:
        """Danh sách sản phẩm (không load relationship)."""
        return self.get_all(
            *self._filters(category_ids, brand_id, status, include_deleted),
            order_by=(Product.CreatedAt.desc(), Product.ProductId),
            offset=offset,
            limit=limit,
        )

    def count_products(
        self,
        *,
        category_ids: Collection[uuid.UUID] | None = None,
        brand_id: uuid.UUID | None = None,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        return self.count(*self._filters(category_ids, brand_id, status, include_deleted))


class ProductVariantRepository(BaseRepository[ProductVariant]):
    model = ProductVariant

    def get_by_sku(self, sku: str) -> ProductVariant | None:
        return self.get_one(ProductVariant.Sku == sku)

    def exists_by_sku(self, sku: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [ProductVariant.Sku == sku]
        if exclude_id is not None:
            conditions.append(ProductVariant.ProductVariantId != exclude_id)
        return self.exists(*conditions)

    def list_by_product(self, product_id: uuid.UUID, *, include_deleted: bool = False) -> list[ProductVariant]:
        conditions = [ProductVariant.ProductId == product_id]
        if not include_deleted:
            conditions.append(ProductVariant.IsDeleted.is_(False))
        return self.get_all(*conditions, order_by=(ProductVariant.VariantName, ProductVariant.ProductVariantId))

    def get_many_by_ids(self, variant_ids: Collection[uuid.UUID], *, with_product: bool = False) -> list[ProductVariant]:
        if not variant_ids:
            return []
        options = (joinedload(ProductVariant.product),) if with_product else ()
        return self.get_all(ProductVariant.ProductVariantId.in_(variant_ids), options=options)

    def get_many_by_ids_for_update(self, variant_ids: Collection[uuid.UUID]) -> list[ProductVariant]:
        """Khóa các biến thể (theo thứ tự id để tránh deadlock) trước khi Service thay đổi tồn kho."""
        if not variant_ids:
            return []
        stmt = (
            select(ProductVariant)
            .where(ProductVariant.ProductVariantId.in_(variant_ids))
            .order_by(ProductVariant.ProductVariantId)
            .with_for_update()
        )
        return list(self.session.scalars(stmt))


class ProductImageRepository(BaseRepository[ProductImage]):
    model = ProductImage

    def list_by_product(self, product_id: uuid.UUID) -> list[ProductImage]:
        return self.get_all(
            ProductImage.ProductId == product_id,
            order_by=(ProductImage.DisplayOrder, ProductImage.ProductImageId),
        )

    def list_default_by_product(self, product_id: uuid.UUID) -> list[ProductImage]:
        return self.get_all(ProductImage.ProductId == product_id, ProductImage.IsDefault.is_(True))


class ProductSerialRepository(BaseRepository[ProductSerial]):
    model = ProductSerial

    def get_by_serial_number(self, serial_number: str) -> ProductSerial | None:
        return self.get_one(ProductSerial.SerialNumber == serial_number)

    def exists_by_serial_number(self, serial_number: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [ProductSerial.SerialNumber == serial_number]
        if exclude_id is not None:
            conditions.append(ProductSerial.ProductSerialId != exclude_id)
        return self.exists(*conditions)

    def list_by_variant(
        self,
        variant_id: uuid.UUID,
        *,
        status: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[ProductSerial]:
        conditions = [ProductSerial.ProductVariantId == variant_id]
        if status is not None:
            conditions.append(ProductSerial.Status == status)
        return self.get_all(
            *conditions, order_by=(ProductSerial.SerialNumber,), offset=offset, limit=limit
        )

    def count_by_variant(self, variant_id: uuid.UUID, *, status: str | None = None) -> int:
        conditions = [ProductSerial.ProductVariantId == variant_id]
        if status is not None:
            conditions.append(ProductSerial.Status == status)
        return self.count(*conditions)

    def list_by_order_item(self, order_item_id: uuid.UUID) -> list[ProductSerial]:
        return self.get_all(ProductSerial.OrderItemId == order_item_id, order_by=(ProductSerial.SerialNumber,))
