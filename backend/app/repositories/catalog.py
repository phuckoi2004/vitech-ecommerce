"""Repositories cho Categories, Brands, Products, ProductVariants, ProductImages, ProductSerials."""

import uuid
from collections.abc import Collection
from typing import NamedTuple

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.models import (
    Brand,
    Category,
    OrderItem,
    Product,
    ProductImage,
    ProductSerial,
    ProductVariant,
    ReturnRequest,
    ShipmentReturn,
    ShipmentReturnItem,
    WarrantyRequest,
)
from app.models.service_request import RETURN_OPEN_STATUSES, WARRANTY_OPEN_STATUSES
from app.models.shipment import SHIPMENT_RETURN_AWAITING

from .base import BaseRepository

SERIAL_WRITTEN_OFF = "WrittenOff"


class SerialTrackingUsage(NamedTuple):
    """Dữ liệu của biến thể ràng buộc việc tắt IsSerialTracked (số lượng; 0 = không có)."""

    active_serials: int  # serial có Status khác WrittenOff
    order_items: int  # dòng đơn hàng của biến thể, mọi trạng thái đơn
    open_warranty_requests: int
    open_return_requests: int
    awaiting_shipment_returns: int  # phiếu hàng hoàn vận chuyển chưa nhận có dòng của biến thể


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
        name_contains: str | None = None,
    ) -> list:
        conditions = []
        if name_contains:
            # Tìm theo tên, không phân biệt hoa thường; escape ký tự đặc biệt của LIKE.
            escaped = name_contains.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(Product.Name.ilike(f"%{escaped}%", escape="\\"))
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
        name_contains: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Product]:
        """Danh sách sản phẩm (không load relationship)."""
        return self.get_all(
            *self._filters(category_ids, brand_id, status, include_deleted, name_contains),
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
        name_contains: str | None = None,
    ) -> int:
        return self.count(*self._filters(category_ids, brand_id, status, include_deleted, name_contains))


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

    @staticmethod
    def _low_stock_filters() -> list:
        # Cảnh báo khi StockQuantity <= MinStockLevel; ngưỡng 0 = không cảnh báo (business-requirements 8.5).
        return [
            ProductVariant.MinStockLevel > 0,
            ProductVariant.StockQuantity <= ProductVariant.MinStockLevel,
            ProductVariant.IsDeleted.is_(False),
        ]

    def list_low_stock(self, *, offset: int | None = None, limit: int | None = None) -> list[ProductVariant]:
        return self.get_all(
            *self._low_stock_filters(),
            order_by=(ProductVariant.StockQuantity, ProductVariant.Sku),
            offset=offset,
            limit=limit,
        )

    def count_low_stock(self) -> int:
        return self.count(*self._low_stock_filters())

    def serial_tracking_usage(self, variant_id: uuid.UUID) -> SerialTrackingUsage:
        """Đếm serial chưa loại bỏ, dòng đơn và quy trình đang mở của biến thể trong một câu SELECT (subquery vô hướng)."""
        lines = select(OrderItem.OrderItemId).where(OrderItem.ProductVariantId == variant_id)

        def count(entity, *where):
            return select(func.count()).select_from(entity).where(*where).scalar_subquery()

        stmt = select(
            count(ProductSerial, ProductSerial.ProductVariantId == variant_id,
                  ProductSerial.Status != SERIAL_WRITTEN_OFF),
            count(OrderItem, OrderItem.ProductVariantId == variant_id),
            count(WarrantyRequest, WarrantyRequest.OrderItemId.in_(lines),
                  WarrantyRequest.Status.in_(WARRANTY_OPEN_STATUSES)),
            count(ReturnRequest, ReturnRequest.OrderItemId.in_(lines), ReturnRequest.Status.in_(RETURN_OPEN_STATUSES)),
            select(func.count(ShipmentReturn.ShipmentReturnId.distinct()))
            .join(ShipmentReturnItem, ShipmentReturnItem.ShipmentReturnId == ShipmentReturn.ShipmentReturnId)
            .where(ShipmentReturnItem.OrderItemId.in_(lines), ShipmentReturn.Status == SHIPMENT_RETURN_AWAITING)
            .scalar_subquery(),
        )
        return SerialTrackingUsage(*self.session.execute(stmt).one())

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
        return self._scalars_for_update(stmt)


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

    def has_return_history(self, product_serial_id: uuid.UUID) -> bool:
        """Serial từng thuộc yêu cầu đổi/trả hoặc hồ sơ hàng hoàn vận chuyển (mọi trạng thái)."""
        stmt = select(
            or_(
                exists().where(ReturnRequest.ProductSerialId == product_serial_id),
                exists().where(ShipmentReturnItem.ProductSerialId == product_serial_id),
            )
        )
        return bool(self.session.scalar(stmt))

    def get_by_serial_number(self, serial_number: str) -> ProductSerial | None:
        return self.get_one(ProductSerial.SerialNumber == serial_number)

    def find_existing_serial_numbers(self, serial_numbers: Collection[str]) -> set[str]:
        """Các SerialNumber đã tồn tại (so khớp chính xác, phân biệt hoa thường như UNIQUE của database)."""
        if not serial_numbers:
            return set()
        stmt = select(ProductSerial.SerialNumber).where(ProductSerial.SerialNumber.in_(list(serial_numbers)))
        return set(self.session.scalars(stmt))

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

    def list_for_update(self, variant_id: uuid.UUID, *, status: str, limit: int) -> list[ProductSerial]:
        """Khóa tối đa ``limit`` serial của biến thể theo trạng thái (FOR UPDATE SKIP LOCKED).

        Bỏ qua các dòng đang bị transaction khác khóa để hai đơn xử lý đồng thời không lấy trùng serial.
        """
        stmt = (
            select(ProductSerial)
            .where(ProductSerial.ProductVariantId == variant_id, ProductSerial.Status == status)
            .order_by(ProductSerial.SerialNumber)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return self._scalars_for_update(stmt)

    def list_by_order_item(self, order_item_id: uuid.UUID) -> list[ProductSerial]:
        return self.get_all(ProductSerial.OrderItemId == order_item_id, order_by=(ProductSerial.SerialNumber,))

    def list_by_order_item_for_update(self, order_item_id: uuid.UUID) -> list[ProductSerial]:
        """Khóa các serial của một dòng đơn (thứ tự SerialNumber) trước khi đổi trạng thái/ngày bảo hành."""
        stmt = (
            select(ProductSerial)
            .where(ProductSerial.OrderItemId == order_item_id)
            .order_by(ProductSerial.SerialNumber)
            .with_for_update()
        )
        return self._scalars_for_update(stmt)

    def list_by_serial_numbers_for_update(self, serial_numbers: Collection[str]) -> list[ProductSerial]:
        """Khóa các serial theo SerialNumber (so khớp chính xác, thứ tự SerialNumber để hạn chế deadlock)."""
        if not serial_numbers:
            return []
        stmt = (
            select(ProductSerial)
            .where(ProductSerial.SerialNumber.in_(list(serial_numbers)))
            .order_by(ProductSerial.SerialNumber)
            .with_for_update()
        )
        return self._scalars_for_update(stmt)
