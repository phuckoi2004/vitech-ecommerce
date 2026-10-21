"""Repositories cho Categories, Brands, Products, ProductVariants, ProductImages, ProductSerials."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from collections.abc import Collection
from typing import Literal, NamedTuple

from sqlalchemy import String, and_, case, cast, exists, func, or_, select
from sqlalchemy.orm import aliased, joinedload, selectinload

from app.core.search_text import fold, folded, is_marked, like_pattern, words as search_words

from app.models import (
    Brand,
    Category,
    Order,
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


PRODUCT_SORTS = ("newest", "relevance", "popular", "best_selling", "price_asc", "price_desc", "discount")


def _visible_variant_of_product():
    return (ProductVariant.ProductId == Product.ProductId, ProductVariant.IsActive.is_(True),
            ProductVariant.IsDeleted.is_(False))


def lowest_price_expression(pricing_at=None):
    """The "from" price customers see: the lowest automatic-promotion price among visible variants."""
    from app.core.product_pricing import automatic_price_expression
    return select(func.min(automatic_price_expression(pricing_at or datetime.now(timezone.utc)))).where(
        *_visible_variant_of_product()).correlate(Product).scalar_subquery()


def best_discount_expression(pricing_at=None):
    """The largest share an automatic promotion takes off a visible variant's selling price."""
    from app.core.product_pricing import automatic_price_expression
    original = ProductVariant.Price
    sale = automatic_price_expression(pricing_at or datetime.now(timezone.utc))
    return select(func.max((original - sale) / original)).where(
        *_visible_variant_of_product(), original > 0).correlate(Product).scalar_subquery()


def _search_text():
    """"name brand category parent-category" of a product, what a customer's search words are matched in."""
    parent = aliased(Category)
    brand = select(Brand.Name).where(Brand.BrandId == Product.BrandId).correlate(Product).scalar_subquery()
    category = (select(Category.Name + " " + func.coalesce(parent.Name, ""))
                .select_from(Category).outerjoin(parent, parent.CategoryId == Category.ParentCategoryId)
                .where(Category.CategoryId == Product.CategoryId).correlate(Product).scalar_subquery())
    return Product.Name + " " + func.coalesce(brand, "") + " " + func.coalesce(category, "")


class ListingFacts(NamedTuple):
    """A sellable product as the category filters read it (catalog_facets.ProductFacts plus brand and price)."""

    ProductId: uuid.UUID
    BrandId: uuid.UUID
    Name: str
    Specifications: dict | None
    Price: Decimal | None
    Storages: tuple[str, ...]


class SerialTrackingUsage(NamedTuple):
    """Dữ liệu của biến thể ràng buộc việc tắt IsSerialTracked (số lượng; 0 = không có)."""

    active_serials: int  # serial có Status khác WrittenOff
    order_items: int  # dòng đơn hàng của biến thể, mọi trạng thái đơn
    open_warranty_requests: int
    open_return_requests: int
    awaiting_shipment_returns: int  # phiếu hàng hoàn vận chuyển chưa nhận có dòng của biến thể


class CategoryRepository(BaseRepository[Category]):
    model = Category

    def get_by_id(self, obj_id: uuid.UUID) -> Category | None:
        return self.get_one(Category.CategoryId == obj_id, Category.IsDeleted.is_(False))

    def get_by_slug(self, slug: str) -> Category | None:
        return self.get_one(Category.Slug == slug, Category.IsDeleted.is_(False))

    def exists_by_slug(self, slug: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [Category.Slug == slug]
        if exclude_id is not None:
            conditions.append(Category.CategoryId != exclude_id)
        return self.exists(*conditions)

    def list_categories(
        self, *, is_active: bool | None = None, parent_id: uuid.UUID | None = None, roots_only: bool = False
    ) -> list[Category]:
        """roots_only=True: chỉ danh mục gốc (ParentCategoryId IS NULL); parent_id: con trực tiếp."""
        conditions = [Category.IsDeleted.is_(False)]
        if is_active is not None:
            conditions.append(Category.IsActive.is_(is_active))
        if roots_only:
            conditions.append(Category.ParentCategoryId.is_(None))
        elif parent_id is not None:
            conditions.append(Category.ParentCategoryId == parent_id)
        return self.get_all(*conditions, order_by=(Category.DisplayOrder, Category.Name, Category.CategoryId))

    def has_children(self, category_id: uuid.UUID) -> bool:
        return self.exists(Category.ParentCategoryId == category_id)

    def visible_tree_ids(self, category_id: uuid.UUID) -> list[uuid.UUID]:
        """Root and active descendants; UNION also terminates on malformed cyclic data."""
        tree = select(Category.CategoryId).where(
            Category.CategoryId == category_id, Category.IsActive.is_(True), Category.IsDeleted.is_(False)
        ).cte("visible_category_tree", recursive=True)
        tree = tree.union(select(Category.CategoryId).join(
            tree, Category.ParentCategoryId == tree.c.CategoryId
        ).where(Category.IsActive.is_(True), Category.IsDeleted.is_(False)))
        return list(self.session.scalars(select(tree.c.CategoryId)))

    def has_products(self, category_id: uuid.UUID) -> bool:
        return bool(self.session.scalar(select(exists().where(Product.CategoryId == category_id))))


class BrandRepository(BaseRepository[Brand]):
    model = Brand

    def get_by_id(self, obj_id: uuid.UUID) -> Brand | None:
        return self.get_one(Brand.BrandId == obj_id, Brand.IsDeleted.is_(False))

    def get_by_slug(self, slug: str) -> Brand | None:
        return self.get_one(Brand.Slug == slug, Brand.IsDeleted.is_(False))

    def exists_by_slug(self, slug: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [Brand.Slug == slug]
        if exclude_id is not None:
            conditions.append(Brand.BrandId != exclude_id)
        return self.exists(*conditions)

    def list_brands(self, *, is_active: bool | None = None) -> list[Brand]:
        conditions = [Brand.IsDeleted.is_(False)]
        if is_active is not None:
            conditions.append(Brand.IsActive.is_(is_active))
        return self.get_all(*conditions, order_by=(Brand.Name, Brand.BrandId))

    def has_products(self, brand_id: uuid.UUID) -> bool:
        return bool(self.session.scalar(select(exists().where(Product.BrandId == brand_id))))


class ProductRepository(BaseRepository[Product]):
    model = Product

    def admin_catalog_filters(self, *, keyword: str | None = None, min_price: Decimal | None = None,
                              max_price: Decimal | None = None, stock: str | None = None, **filters) -> list:
        conditions = self._filters(**filters)
        variants = [ProductVariant.ProductId == Product.ProductId, ProductVariant.IsDeleted.is_(False)]
        if keyword:
            escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            matches = [Product.Name.ilike(pattern, escape="\\"),
                       cast(Product.ProductId, String).ilike(pattern, escape="\\"),
                       exists().where(*variants, ProductVariant.Sku.ilike(pattern, escape="\\"))]
            try:
                matches.append(Product.ProductId == uuid.UUID(keyword))
            except ValueError:
                pass
            conditions.append(or_(*matches))
        price = select(func.min(ProductVariant.Price)).where(*variants).correlate(Product).scalar_subquery()
        quantity = select(func.coalesce(func.sum(ProductVariant.StockQuantity), 0)).where(*variants) \
            .correlate(Product).scalar_subquery()
        low = exists().where(*variants, ProductVariant.MinStockLevel > 0,
                             ProductVariant.StockQuantity <= ProductVariant.MinStockLevel)
        if min_price is not None:
            conditions.append(price >= min_price)
        if max_price is not None:
            conditions.append(price <= max_price)
        if stock == "in_stock":
            conditions.append(quantity > 0)
        elif stock == "out_of_stock":
            conditions.append(quantity == 0)
        elif stock == "low_stock":
            conditions.extend([quantity > 0, low])
        return conditions

    def list_admin_catalog(self, *, offset: int, limit: int, **filters) -> list[Product]:
        # Load relationships in batches for the current page; never one API/database query per product.
        return self.get_all(*self.admin_catalog_filters(**filters),
                            order_by=(Product.CreatedAt.desc(), Product.ProductId), offset=offset, limit=limit,
                            options=self._detail_options())

    def count_admin_catalog(self, **filters) -> int:
        return self.count(*self.admin_catalog_filters(**filters))

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

    def list_with_media(self, product_ids: Collection[uuid.UUID]) -> list[Product]:
        """Products with their variants and images, in no particular order."""
        if not product_ids:
            return []
        stmt = select(Product).where(Product.ProductId.in_(product_ids)).options(
            selectinload(Product.variants), selectinload(Product.images))
        return list(self.session.scalars(stmt))

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
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        pricing_at=None,
        product_ids: Collection[uuid.UUID] | None = None,
        in_stock: bool = False,
        created_since=None,
    ) -> list:
        conditions = []
        if product_ids is not None:
            conditions.append(Product.ProductId.in_(product_ids))
        if in_stock:
            conditions.append(exists().where(*_visible_variant_of_product(), ProductVariant.StockQuantity > 0))
        if created_since is not None:
            conditions.append(Product.CreatedAt >= created_since)
        if name_contains:
            # Every word, in any order, in the name, brand or category ("dien thoai samsung"). A word typed with marks
            # must keep them ("cơ" is not "có"); one typed without its space still matches ("iphone17").
            raw = func.lower(_search_text())
            plain = folded(_search_text())
            for word in search_words(name_contains):
                text = raw if is_marked(word) else plain
                pattern = like_pattern(word)
                conditions.append(or_(text.like(pattern, escape="\\"), func.replace(text, " ", "").like(pattern, escape="\\")))
        if category_ids:
            conditions.append(Product.CategoryId.in_(category_ids))
        if brand_id is not None:
            conditions.append(Product.BrandId == brand_id)
        if status is not None:
            conditions.append(Product.Status == status)
        if not include_deleted:
            conditions.append(Product.IsDeleted.is_(False))
        if min_price is not None or max_price is not None:
            # Match the "from" price shown to customers, using only visible variants.
            price = lowest_price_expression(pricing_at)
            if min_price is not None:
                conditions.append(price >= min_price)
            if max_price is not None:
                conditions.append(price <= max_price)
        return conditions

    def list_products(
        self,
        *,
        category_ids: Collection[uuid.UUID] | None = None,
        brand_id: uuid.UUID | None = None,
        status: str | None = None,
        include_deleted: bool = False,
        name_contains: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        pricing_at=None,
        product_ids: Collection[uuid.UUID] | None = None,
        in_stock: bool = False,
        created_since=None,
        sort: str = "newest",
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Product]:
        """Danh sách sản phẩm (không load relationship). Thứ tự luôn kết thúc bằng ngày tạo và ID để phân trang ổn định."""
        return self.get_all(
            *self._filters(category_ids, brand_id, status, include_deleted, name_contains, min_price, max_price,
                           pricing_at, product_ids, in_stock, created_since),
            order_by=self._order(sort, pricing_at, name_contains),
            offset=offset,
            limit=limit,
        )

    @staticmethod
    def _order(sort: str, pricing_at, keyword: str | None = None) -> tuple:
        newest = (Product.CreatedAt.desc(), Product.ProductId)
        if sort == "relevance" and keyword and search_words(keyword):
            # The whole phrase in the name first, then every word in the name, then matches via brand/category.
            name = folded(Product.Name)
            in_name = and_(*(name.like(like_pattern(fold(word)), escape="\\") for word in search_words(keyword)))
            rank = case((name.like(like_pattern(fold(keyword)), escape="\\"), 0), (in_name, 1), else_=2)
            return (rank, *newest)
        if sort == "popular":
            return ((Product.SoldQuantity + Product.ReviewCount).desc(), Product.AverageRating.desc(), *newest)
        if sort == "best_selling":
            return (Product.SoldQuantity.desc(), *newest)
        if sort in ("price_asc", "price_desc"):
            price = lowest_price_expression(pricing_at)
            return (price.asc().nulls_last() if sort == "price_asc" else price.desc().nulls_last(), *newest)
        if sort == "discount":
            return (best_discount_expression(pricing_at).desc().nulls_last(), *newest)
        return newest

    def count_products(
        self,
        *,
        category_ids: Collection[uuid.UUID] | None = None,
        brand_id: uuid.UUID | None = None,
        status: str | None = None,
        include_deleted: bool = False,
        name_contains: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        pricing_at=None,
        product_ids: Collection[uuid.UUID] | None = None,
        in_stock: bool = False,
        created_since=None,
    ) -> int:
        return self.count(*self._filters(category_ids, brand_id, status, include_deleted, name_contains, min_price,
                                         max_price, pricing_at, product_ids, in_stock, created_since))

    def count_products_per(
        self,
        field: Literal["category", "brand"],
        *,
        category_ids: Collection[uuid.UUID] | None = None,
        brand_id: uuid.UUID | None = None,
        status: str | None = None,
        name_contains: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        pricing_at=None,
        in_stock: bool = False,
    ) -> dict[uuid.UUID, int]:
        """Matching non-deleted products per CategoryId or BrandId, with the same filters as count_products."""
        column = Product.CategoryId if field == "category" else Product.BrandId
        rows = self.session.execute(
            select(column, func.count()).where(*self._filters(
                category_ids, brand_id, status, False, name_contains, min_price, max_price, pricing_at, None, in_stock
            )).group_by(column)
        )
        return dict(rows.all())

    def listing_facts(self, *, category_ids: Collection[uuid.UUID], status: str, pricing_at=None) -> list[ListingFacts]:
        """Every non-deleted product of the categories with what the listing filters read, in two queries
        (products with their "from" price, then visible variants' storage) rather than one per product."""
        rows = self.session.execute(
            select(Product.ProductId, Product.BrandId, Product.Name, Product.Specifications,
                   lowest_price_expression(pricing_at))
            .where(*self._filters(category_ids, None, status, False))
            .order_by(Product.CreatedAt.desc(), Product.ProductId)
        ).all()
        storages: dict[uuid.UUID, list[str]] = {}
        if rows:
            for product_id, storage in self.session.execute(
                select(ProductVariant.ProductId, ProductVariant.Storage).where(
                    ProductVariant.ProductId.in_([row[0] for row in rows]), ProductVariant.IsActive.is_(True),
                    ProductVariant.IsDeleted.is_(False), ProductVariant.Storage.is_not(None),
                ).order_by(ProductVariant.ProductId, ProductVariant.Sku)
            ):
                storages.setdefault(product_id, []).append(storage)
        return [ListingFacts(*row, tuple(storages.get(row[0], ()))) for row in rows]


class ProductVariantRepository(BaseRepository[ProductVariant]):
    model = ProductVariant

    @staticmethod
    def _catalog_filters(*, keyword: str | None = None, category_id: uuid.UUID | None = None,
                         brand_id: uuid.UUID | None = None, status: str | None = None,
                         min_price: Decimal | None = None, max_price: Decimal | None = None,
                         stock: str | None = None) -> list:
        conditions = [ProductVariant.IsDeleted.is_(False), Product.IsDeleted.is_(False)]
        if keyword:
            escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conditions.append(or_(Product.Name.ilike(pattern, escape="\\"),
                                  ProductVariant.VariantName.ilike(pattern, escape="\\"),
                                  ProductVariant.Sku.ilike(pattern, escape="\\")))
        if category_id is not None:
            conditions.append(Product.CategoryId == category_id)
        if brand_id is not None:
            conditions.append(Product.BrandId == brand_id)
        if status == "Active":
            conditions.extend([Product.Status == "Active", ProductVariant.IsActive.is_(True)])
        elif status == "Inactive":
            conditions.append(or_(Product.Status == "Inactive",
                                  and_(Product.Status == "Active", ProductVariant.IsActive.is_(False))))
        elif status is not None:
            conditions.append(Product.Status == status)
        if min_price is not None:
            conditions.append(ProductVariant.Price >= min_price)
        if max_price is not None:
            conditions.append(ProductVariant.Price <= max_price)
        if stock == "in_stock":
            conditions.append(ProductVariant.StockQuantity > 0)
        elif stock == "out_of_stock":
            conditions.append(ProductVariant.StockQuantity == 0)
        elif stock == "low_stock":
            conditions.extend([ProductVariant.StockQuantity > 0, ProductVariant.MinStockLevel > 0,
                               ProductVariant.StockQuantity <= ProductVariant.MinStockLevel])
        return conditions

    def list_catalog(self, *, offset: int, limit: int, **filters) -> list[ProductVariant]:
        stmt = (select(ProductVariant).join(ProductVariant.product)
                .where(*self._catalog_filters(**filters))
                .options(joinedload(ProductVariant.product).joinedload(Product.category),
                         joinedload(ProductVariant.product).joinedload(Product.brand),
                         joinedload(ProductVariant.product).selectinload(Product.images))
                .order_by(Product.CreatedAt.desc(), Product.ProductId, ProductVariant.Sku,
                          ProductVariant.ProductVariantId).offset(offset).limit(limit))
        return list(self.session.scalars(stmt))

    def count_catalog(self, **filters) -> int:
        stmt = (select(func.count()).select_from(ProductVariant).join(ProductVariant.product)
                .where(*self._catalog_filters(**filters)))
        return self.session.scalar(stmt) or 0

    def get_by_id_for_update(self, id_: uuid.UUID, *, with_product: bool = False) -> ProductVariant | None:
        """Khóa biến thể; luồng giỏ hàng còn nạp lại Product để kiểm tra trạng thái bán hiện tại."""
        if not with_product:
            return super().get_by_id_for_update(id_)
        stmt = (select(ProductVariant).where(ProductVariant.ProductVariantId == id_)
                .options(selectinload(ProductVariant.product)).with_for_update(of=ProductVariant))
        rows = self._scalars_for_update(stmt)
        return rows[0] if rows else None

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

    def count_available(self, variant_id: uuid.UUID) -> int:
        return self.count(ProductSerial.ProductVariantId == variant_id,
                          ProductSerial.Status == "Available", ProductSerial.OrderItemId.is_(None))

    def count_unassigned_order_units(self, variant_id: uuid.UUID) -> int:
        """Only pending orders still share the unbound pool; confirmed devices have already been allocated."""
        reserved = select(func.count(ProductSerial.ProductSerialId)).where(
            ProductSerial.OrderItemId == OrderItem.OrderItemId,
            ProductSerial.Status == "Reserved",
        ).correlate(OrderItem).scalar_subquery()
        stmt = select(func.coalesce(func.sum(func.greatest(OrderItem.Quantity - reserved, 0)), 0)).join(
            Order, Order.OrderId == OrderItem.OrderId
        ).where(OrderItem.ProductVariantId == variant_id,
                Order.OrderStatus == "Pending")
        return int(self.session.scalar(stmt) or 0)

    def list_available_for_update(self, variant_id: uuid.UUID, *, limit: int,
                                  random: bool = False) -> list[ProductSerial]:
        stmt = select(ProductSerial).where(
            ProductSerial.ProductVariantId == variant_id,
            ProductSerial.Status == "Available", ProductSerial.OrderItemId.is_(None),
        ).order_by(func.random() if random else ProductSerial.SerialNumber).limit(limit).with_for_update(skip_locked=True)
        return self._scalars_for_update(stmt)

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
