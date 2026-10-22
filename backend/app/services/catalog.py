"""Catalog services: Category, Brand, Product, ProductVariant, ProductImage, ProductSerial.

Nguồn nghiệp vụ: docs/business-requirements.md mục 1, 3, 8 (tồn kho), 17 (concurrency).
- Customer: tìm kiếm/xem sản phẩm (chỉ sản phẩm đủ điều kiện bán).
- Admin: thêm, sửa, xóa/ẩn danh mục, thương hiệu, sản phẩm, hình ảnh, biến thể, Serial/IMEI.
- Staff/Admin: xem dữ liệu quản trị (sản phẩm đã ẩn/xóa, biến thể kèm giá vốn, Serial/IMEI).
- Khách (không đăng nhập): chỉ xem dữ liệu đang hoạt động; xem dữ liệu không hoạt động cần Staff/Admin.
- Không xóa dữ liệu đang bị ràng buộc khi database dùng RESTRICT.
- StockQuantity/CostPrice không sửa qua CRUD biến thể (chỉ qua đơn hàng, nhận hàng, InventoryService).
- Cảnh báo tồn thấp khi tồn vừa giảm xuống StockQuantity <= MinStockLevel (MinStockLevel > 0).
Quy ước tham số: ``actor`` là tham số đầu tiên khi bắt buộc đăng nhập; ``actor=None`` (keyword) ở use case công khai.
"""

import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session
from app.core.catalog_facets import ProductFacts, facet_group
from app.core.catalog_media import default_variant_id, merge_specifications, variant_images
from app.core.search_text import fold, words as search_words

from app.models import Category, Product, ProductImage, ProductSerial, ProductVariant
from app.repositories import (
    BrandRepository,
    CategoryRepository,
    ProductImageRepository,
    ProductRepository,
    ProductSerialRepository,
    ProductVariantRepository,
    PromotionCategoryRepository,
    PromotionRepository,
    UserRepository,
    WarrantyRequestRepository,
)
from app.repositories.catalog import PRODUCT_SORTS
from app.services.promotion_state import promotion_status
from app.schemas.catalog_filters import (
    CategoryFiltersResponse,
    FilterBrandResponse,
    FilterCategoryResponse,
    FilterFacetResponse,
    FilterOptionResponse,
    PriceRangeResponse,
    SearchFiltersResponse,
    SearchSuggestionsResponse,
    SuggestedProductResponse,
    SuggestedSearchResponse,
)
from app.schemas import (
    AdminProductDetailResponse,
    AdminProductListResponse,
    AdminProductResponse,
    AdminProductVariantResponse,
    AdminProductVariantListResponse,
    BrandCreate,
    BrandResponse,
    BrandUpdate,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    PageResponse,
    ProductCreate,
    ProductDetailResponse,
    ProductImageCreate,
    ProductImageResponse,
    ProductImageUpdate,
    ProductSerialCreate,
    ProductSerialResponse,
    ProductSerialUpdate,
    ProductSummary,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
)

from .actor import ADMIN_ONLY, STAFF_OR_ADMIN, Actor, require_role
from .base import BaseService, utc_now
from .exceptions import BusinessRuleError, ConflictError, NotFoundError
from .user import NotificationService
from .warranty_period import validate_warranty_months

# Sản phẩm đủ điều kiện hiển thị/bán cho Customer.
SELLABLE_PRODUCT_STATUS = "Active"
NEW_ARRIVAL_DAYS = 30  # "Hàng mới về" on the category page
SUGGESTION_POOL = 40  # most relevant matches the search box suggestions are drawn from
SUGGESTED_SEARCHES = 6
SUGGESTED_PRODUCTS = 5
SERIAL_AVAILABLE = "Available"
# Không sửa qua CRUD biến thể (business decision: chỉ qua nghiệp vụ kho).
INVENTORY_FIELDS = ("StockQuantity", "CostPrice")
LOW_STOCK_NOTIFICATION_TYPE = "LowStock"


def require_internal_view(actor: Actor | None, active_only: bool) -> None:
    """Xem cả dữ liệu không hoạt động (active_only=False) cần Staff/Admin; khách chỉ xem dữ liệu đang hoạt động."""
    if not active_only:
        require_role(actor, *STAFF_OR_ADMIN)


def reject_inventory_fields(values: Mapping) -> None:
    """Chặn mass assignment StockQuantity/CostPrice kể cả khi Schema bị bỏ qua (model_construct, dict)."""
    present = sorted(field for field in INVENTORY_FIELDS if field in values)
    if present:
        raise BusinessRuleError(
            f"Không cập nhật {', '.join(present)} qua CRUD biến thể; dùng nhận hàng/khai báo tồn đầu kỳ/điều chỉnh kho",
            code="inventory_field_not_editable",
        )


def normalize_serial_number(value: str) -> str:
    """Serial/IMEI: bỏ khoảng trắng đầu/cuối, giữ nguyên hoa/thường, không kiểm tra Luhn; không rỗng, tối đa 100 ký tự."""
    serial = (value or "").strip()
    if not serial:
        raise BusinessRuleError("Serial/IMEI không được rỗng", code="invalid_serial_number")
    if len(serial) > 100:
        raise BusinessRuleError("Serial/IMEI tối đa 100 ký tự", code="invalid_serial_number")
    return serial


def crossed_low_stock(variant: ProductVariant, before: int) -> bool:
    """Tồn vừa chuyển sang trạng thái cảnh báo (trước > ngưỡng, sau <= ngưỡng); ngưỡng 0 không cảnh báo."""
    threshold = variant.MinStockLevel
    return threshold > 0 and before > threshold and variant.StockQuantity <= threshold


def is_product_sellable(product: Product | None) -> bool:
    """Sản phẩm đang bán: tồn tại, chưa xóa và Status = Active."""
    return product is not None and not product.IsDeleted and product.Status == SELLABLE_PRODUCT_STATUS


def is_variant_sellable(variant: ProductVariant | None) -> bool:
    """Biến thể đang bán: tồn tại, chưa xóa, đang hoạt động và thuộc sản phẩm đang bán."""
    return (
        variant is not None
        and not variant.IsDeleted
        and variant.IsActive
        and is_product_sellable(variant.product)
    )


class CategoryService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.categories = CategoryRepository(session)
        self.promotions = PromotionRepository(session)
        self.promotion_categories = PromotionCategoryRepository(session)

    def list_categories(
        self,
        *,
        actor: Actor | None = None,
        active_only: bool = False,
        parent_id: uuid.UUID | None = None,
        roots_only: bool = False,
    ) -> list[CategoryResponse]:
        require_internal_view(actor, active_only)
        items = self.categories.list_categories(
            is_active=True if active_only else None, parent_id=parent_id, roots_only=roots_only
        )
        return [CategoryResponse.model_validate(c) for c in items]

    def get_category(
        self, category_id: uuid.UUID, *, actor: Actor | None = None, active_only: bool = False
    ) -> CategoryResponse:
        require_internal_view(actor, active_only)
        return CategoryResponse.model_validate(self._get(category_id, active_only=active_only))

    def get_category_by_slug(
        self, slug: str, *, actor: Actor | None = None, active_only: bool = False
    ) -> CategoryResponse:
        require_internal_view(actor, active_only)
        category = self.categories.get_by_slug(slug)
        if category is None or (active_only and not category.IsActive):
            raise NotFoundError("Không tìm thấy danh mục", code="category_not_found")
        return CategoryResponse.model_validate(category)

    def create_category(self, actor: Actor, data: CategoryCreate) -> CategoryResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            values = data.model_dump(exclude_unset=True)
            self._ensure_slug_unique(values["Slug"])
            if values.get("ParentCategoryId") is not None:
                self._get(values["ParentCategoryId"])
            category = self.categories.create(values)
            self.categories.flush()
            self._join_parent_promotions(category)
            return CategoryResponse.model_validate(category)

    def update_category(self, actor: Actor, category_id: uuid.UUID, data: CategoryUpdate) -> CategoryResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            category = self._get(category_id)
            values = data.model_dump(exclude_unset=True)
            if "Slug" in values:
                self._ensure_slug_unique(values["Slug"], exclude_id=category_id)
            if values.get("ParentCategoryId") is not None and values["ParentCategoryId"] != category.ParentCategoryId:
                self._ensure_valid_parent(category_id, values["ParentCategoryId"])
            moved = values.get("ParentCategoryId") not in (None, category.ParentCategoryId)
            self.categories.update(category, values)
            self.categories.flush()
            if moved:
                self._join_parent_promotions(category)
            return CategoryResponse.model_validate(category)

    def delete_category(self, actor: Actor, category_id: uuid.UUID) -> None:
        """Remove from every directory, retaining foreign keys and product/history records."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            category = self._get(category_id)
            self.categories.update(category, {"IsDeleted": True, "IsActive": False})

    def _get(self, category_id: uuid.UUID, *, active_only: bool = False) -> Category:
        category = self.categories.get_by_id(category_id)
        if category is None or (active_only and not category.IsActive):
            raise NotFoundError("Không tìm thấy danh mục", code="category_not_found")
        return category

    def _ensure_slug_unique(self, slug: str, exclude_id: uuid.UUID | None = None) -> None:
        if self.categories.exists_by_slug(slug, exclude_id):
            raise ConflictError("Slug danh mục đã tồn tại", code="category_slug_exists")

    def _join_parent_promotions(self, category: Category) -> None:
        """Promotions match a category exactly, so choosing a category in admin stores it with all its sub-categories.
        A sub-category created (or moved) under it later joins those promotions as well, with its own sub-categories."""
        ancestors: list[uuid.UUID] = []
        node = self.categories.get_by_id(category.ParentCategoryId) if category.ParentCategoryId else None
        while node is not None and node.CategoryId not in ancestors:
            ancestors.append(node.CategoryId)
            node = self.categories.get_by_id(node.ParentCategoryId) if node.ParentCategoryId else None
        promotion_ids = {row.PromotionId for ancestor in ancestors for row in self.promotion_categories.list_by_category(ancestor)}
        if not promotion_ids:
            return
        subtree = [category.CategoryId]
        for parent_id in subtree:
            subtree.extend(child.CategoryId for child in self.categories.list_categories(parent_id=parent_id)
                           if child.CategoryId not in subtree)
        now = self.now()
        for promotion_id in sorted(promotion_ids):
            promotion = self.promotions.get_by_id(promotion_id)
            if promotion is None or promotion_status(promotion, now) in ("Cancelled", "Expired"):
                continue
            for category_id in subtree:
                if self.promotion_categories.get(promotion_id, category_id) is None:
                    self.promotion_categories.create({"PromotionId": promotion_id, "CategoryId": category_id})
        self.promotion_categories.flush()

    def _ensure_valid_parent(self, category_id: uuid.UUID, parent_id: uuid.UUID) -> None:
        """Danh mục cha phải tồn tại và không được là chính nó hoặc danh mục con/cháu của nó."""
        parent = self._get(parent_id)
        seen: set[uuid.UUID] = set()
        node: Category | None = parent
        while node is not None and node.CategoryId not in seen:
            if node.CategoryId == category_id:
                raise BusinessRuleError("Quan hệ cha/con tạo vòng lặp", code="category_cycle")
            seen.add(node.CategoryId)
            node = self.categories.get_by_id(node.ParentCategoryId) if node.ParentCategoryId else None


class BrandService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.brands = BrandRepository(session)

    def list_brands(self, *, actor: Actor | None = None, active_only: bool = False) -> list[BrandResponse]:
        require_internal_view(actor, active_only)
        return [BrandResponse.model_validate(b) for b in self.brands.list_brands(is_active=True if active_only else None)]

    def get_brand(self, brand_id: uuid.UUID, *, actor: Actor | None = None, active_only: bool = False) -> BrandResponse:
        require_internal_view(actor, active_only)
        brand = self.brands.get_by_id(brand_id)
        if brand is None or (active_only and not brand.IsActive):
            raise NotFoundError("Không tìm thấy thương hiệu", code="brand_not_found")
        return BrandResponse.model_validate(brand)

    def get_brand_by_slug(self, slug: str, *, actor: Actor | None = None, active_only: bool = False) -> BrandResponse:
        require_internal_view(actor, active_only)
        brand = self.brands.get_by_slug(slug)
        if brand is None or (active_only and not brand.IsActive):
            raise NotFoundError("Không tìm thấy thương hiệu", code="brand_not_found")
        return BrandResponse.model_validate(brand)

    def create_brand(self, actor: Actor, data: BrandCreate) -> BrandResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            values = data.model_dump(exclude_unset=True)
            if self.brands.exists_by_slug(values["Slug"]):
                raise ConflictError("Slug thương hiệu đã tồn tại", code="brand_slug_exists")
            brand = self.brands.create(values)
            self.brands.flush()
            return BrandResponse.model_validate(brand)

    def update_brand(self, actor: Actor, brand_id: uuid.UUID, data: BrandUpdate) -> BrandResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            brand = self._get(brand_id)
            values = data.model_dump(exclude_unset=True)
            if "Slug" in values and self.brands.exists_by_slug(values["Slug"], brand_id):
                raise ConflictError("Slug thương hiệu đã tồn tại", code="brand_slug_exists")
            self.brands.update(brand, values)
            self.brands.flush()
            return BrandResponse.model_validate(brand)

    def delete_brand(self, actor: Actor, brand_id: uuid.UUID) -> None:
        """Soft delete independently of IsActive; retain product references."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            brand = self._get(brand_id)
            self.brands.update(brand, {"IsDeleted": True, "IsActive": False})

    def _get(self, brand_id: uuid.UUID):
        brand = self.brands.get_by_id(brand_id)
        if brand is None:
            raise NotFoundError("Không tìm thấy thương hiệu", code="brand_not_found")
        return brand


class ProductService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.products = ProductRepository(session)
        self.categories = CategoryRepository(session)
        self.brands = BrandRepository(session)

    # ---------------------------------------------------------- Customer

    def search_products(
        self,
        *,
        keyword: str | None = None,
        category_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        include_descendants: bool = False,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        sort: str | None = None,
        in_stock: bool = False,
        new_arrivals: bool = False,
        specs: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
        match_variant_price: bool = False,
        excluded_brand_ids: list[uuid.UUID] | None = None,
    ) -> PageResponse[ProductSummary]:
        """Tìm kiếm/xem danh sách sản phẩm đang bán (Status Active, chưa xóa).

        ``specs`` ("<tiêu chí>:<lựa chọn>", xem GET /categories/{id}/filters) cần ``category_id``: cùng tiêu chí là
        HOẶC, khác tiêu chí là VÀ. ``new_arrivals``: sản phẩm tạo trong NEW_ARRIVAL_DAYS ngày gần nhất.
        ``keyword``: mọi từ đều phải có trong tên, hãng hoặc danh mục, không phân biệt dấu (app/core/search_text.py);
        không chỉ định ``sort`` thì có từ khóa xếp theo độ liên quan, không có thì mới nhất trước.
        """
        if min_price is not None and max_price is not None and min_price > max_price:
            raise BusinessRuleError("Giá tối thiểu phải nhỏ hơn hoặc bằng giá tối đa", code="invalid_price_range")
        sort = sort or ("relevance" if keyword and keyword.strip() else "newest")
        if sort not in PRODUCT_SORTS:
            raise BusinessRuleError("Kiểu sắp xếp không hợp lệ", code="invalid_sort")
        offset, limit = self._page_args(page, page_size)
        now = self.now()
        category_ids = [category_id] if category_id else None
        if category_id and include_descendants:
            category_ids = self.categories.visible_tree_ids(category_id)
            if not category_ids:
                return PageResponse[ProductSummary](Items=[], Total=0, Page=page, PageSize=page_size)
        product_ids = None
        if specs:
            if category_id is None:
                raise BusinessRuleError("Lọc theo thông số cần chọn danh mục", code="invalid_filter")
            selected = self._selected_options(category_id, specs)
            product_ids = [row.ProductId for row in self.products.listing_facts(
                category_ids=category_ids, status=SELLABLE_PRODUCT_STATUS, pricing_at=now)
                if self._matches(row, selected)]
            if not product_ids:
                return PageResponse[ProductSummary](Items=[], Total=0, Page=page, PageSize=page_size)
        filters = {
            "category_ids": category_ids,
            "brand_id": brand_id,
            "status": SELLABLE_PRODUCT_STATUS,
            "name_contains": keyword.strip() if keyword and keyword.strip() else None,
            "pricing_at": now,
            "min_price": min_price,
            "max_price": max_price,
            "product_ids": product_ids,
            "in_stock": in_stock,
            "created_since": now - timedelta(days=NEW_ARRIVAL_DAYS) if new_arrivals else None,
        }
        if match_variant_price:
            filters["match_variant_price"] = True
        if excluded_brand_ids:
            filters["excluded_brand_ids"] = excluded_brand_ids
        items = self.products.list_products(**filters, sort=sort, offset=offset, limit=limit)
        return PageResponse[ProductSummary](
            Items=[ProductSummary.model_validate(p) for p in items],
            Total=self.products.count_products(**filters),
            Page=page,
            PageSize=page_size,
        )

    def category_filters(self, category_id: uuid.UUID) -> CategoryFiltersResponse:
        """Brands, price ranges and specification criteria that have products on sale in the category tree."""
        category = self.categories.get_by_id(category_id)
        if category is None or not category.IsActive:
            raise NotFoundError("Không tìm thấy danh mục", code="category_not_found")
        group = facet_group(self._root_slug(category))
        rows = self.products.listing_facts(category_ids=self.categories.visible_tree_ids(category_id),
                                           status=SELLABLE_PRODUCT_STATUS, pricing_at=self.now())
        facts = [ProductFacts.of(row.Name, row.Specifications, row.Storages) for row in rows]

        per_brand: dict[uuid.UUID, int] = {}
        for row in rows:
            per_brand[row.BrandId] = per_brand.get(row.BrandId, 0) + 1
        brands = [FilterBrandResponse(BrandId=brand.BrandId, Name=brand.Name, Slug=brand.Slug,
                                      ProductCount=per_brand[brand.BrandId])
                  for brand in self.brands.list_brands(is_active=True) if brand.BrandId in per_brand]
        brands.sort(key=lambda brand: -brand.ProductCount)  # stable: equal counts keep name order

        prices = []
        for price_range in group.price_ranges:
            count = sum(1 for row in rows if row.Price is not None
                        and (price_range.min_price is None or row.Price >= price_range.min_price)
                        and (price_range.max_price is None or row.Price <= price_range.max_price))
            if count:
                prices.append(PriceRangeResponse(Value=price_range.value, Label=price_range.label, ProductCount=count,
                                                 MinPrice=price_range.min_price, MaxPrice=price_range.max_price))

        facets = []
        for facet in group.facets:
            options = [FilterOptionResponse(Value=option.value, Label=option.label, ProductCount=count)
                       for option in facet.options if (count := sum(1 for item in facts if option.matches(item)))]
            if options:
                facets.append(FilterFacetResponse(Key=facet.key, Label=facet.label, Options=options))
        return CategoryFiltersResponse(Brands=brands, PriceRanges=prices, Facets=facets)

    def search_filters(
        self,
        *,
        keyword: str | None = None,
        category_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        in_stock: bool = False,
    ) -> SearchFiltersResponse:
        """Root categories and brands of the products GET /products finds with the same filters, most products first.

        ``category_id`` covers its visible children, like ``include_descendants``. Category counts ignore the chosen
        category and brand counts the chosen brand; a product counts under a root only while its whole path is visible.
        """
        if min_price is not None and max_price is not None and min_price > max_price:
            raise BusinessRuleError("Giá tối thiểu phải nhỏ hơn hoặc bằng giá tối đa", code="invalid_price_range")
        filters = {
            "status": SELLABLE_PRODUCT_STATUS,
            "name_contains": keyword.strip() if keyword and keyword.strip() else None,
            "pricing_at": self.now(),
            "min_price": min_price,
            "max_price": max_price,
            "in_stock": in_stock,
        }

        all_categories = {category.CategoryId: category for category in self.categories.list_categories()}
        per_root: dict[uuid.UUID, int] = {}
        for owner_id, count in self.products.count_products_per("category", brand_id=brand_id, **filters).items():
            root = self._visible_root(owner_id, all_categories)
            if root is not None:
                per_root[root.CategoryId] = per_root.get(root.CategoryId, 0) + count
        roots = sorted((all_categories[root_id] for root_id in per_root),
                       key=lambda root: (-per_root[root.CategoryId], root.DisplayOrder, root.Name))
        categories = [FilterCategoryResponse(CategoryId=root.CategoryId, Name=root.Name, Slug=root.Slug,
                                             ProductCount=per_root[root.CategoryId]) for root in roots]

        category_ids = self.categories.visible_tree_ids(category_id) if category_id else None
        # A hidden or unknown category has no visible tree, so it finds nothing (as GET /products does).
        per_brand = {} if category_ids == [] else self.products.count_products_per(
            "brand", category_ids=category_ids, **filters)
        brands = [FilterBrandResponse(BrandId=brand.BrandId, Name=brand.Name, Slug=brand.Slug,
                                      ProductCount=per_brand[brand.BrandId])
                  for brand in self.brands.list_brands(is_active=True) if brand.BrandId in per_brand]
        brands.sort(key=lambda brand: -brand.ProductCount)  # stable: equal counts keep name order
        return SearchFiltersResponse(Categories=categories, Brands=brands)

    def search_suggestions(self, keyword: str | None) -> SearchSuggestionsResponse:
        """What the box under the search field offers while the customer types, as CellphoneS does.

        Searches (“Có phải bạn muốn tìm”): categories and root category + brand pairs of the most relevant matches,
        most matches first. A root category needs a typed word in its name; a sub-category needs all typed words, some
        beyond its root's name. Products (“Sản phẩm gợi ý”): the first matches with the image and price their product
        card shows.
        """
        text = keyword.strip() if keyword else ""
        if not text:
            return SearchSuggestionsResponse(Searches=[], Products=[])
        found = self.products.list_products(status=SELLABLE_PRODUCT_STATUS, name_contains=text, sort="relevance",
                                            limit=SUGGESTION_POOL)
        categories = {category.CategoryId: category for category in self.categories.list_categories()}
        brands = {brand.BrandId: brand for brand in self.brands.list_brands(is_active=True)}
        typed = set(search_words(fold(text)))

        groups: dict[tuple, list] = {}  # (category, brand or None) → [products found, first product]; dicts keep order
        for product in found:
            root = self._visible_root(product.CategoryId, categories)
            if root is None:
                continue
            brand, own = brands.get(product.BrandId), categories[product.CategoryId]
            in_root = set(fold(root.Name).split())
            keys = []
            # A sub-category the words narrow down to ("laptop gaming" → Laptop gaming, not every Laptop child).
            if own is not root and typed <= set(fold(own.Name).split()) and not typed <= in_root:
                keys.append((own.CategoryId, None))
            if typed & in_root:
                keys.append((root.CategoryId, None))
            if brand:
                keys.append((root.CategoryId, brand.BrandId))
            for key in keys:
                groups.setdefault(key, [0, product])[0] += 1
        # Sub-categories, then root categories, then category + brand; within each, most products first (stable:
        # with equal counts the more relevant one stays first).
        chosen = sorted(groups.items(), key=lambda item: (
            item[0][1] is not None, categories[item[0][0]].ParentCategoryId is None, -item[1][0]))[:SUGGESTED_SEARCHES]
        shown = found[:SUGGESTED_PRODUCTS]
        media = {product.ProductId: product for product in self.products.list_with_media(
            {product.ProductId for product in shown} | {first.ProductId for _, (_, first) in chosen})}
        searches = [SuggestedSearchResponse(
            Label=categories[category_id].Name + (f" {brands[brand_id].Name}" if brand_id else ""),
            CategorySlug=categories[category_id].Slug, BrandId=brand_id, ImageUrl=self._card_image(media[first.ProductId]),
        ) for (category_id, brand_id), (_, first) in chosen]

        from .pricing import PricingService, variant_price
        promotions, now = PricingService(self.session, clock=self._clock).automatic_promotions(), self.now()
        products = []
        for summary in shown:
            product = media[summary.ProductId]
            prices = [variant_price(variant, promotions, now) for variant in product.variants
                      if variant.IsActive and not variant.IsDeleted]
            cheapest = min(prices, key=lambda price: price["SalePrice"], default=None)
            products.append(SuggestedProductResponse(
                ProductId=product.ProductId, Name=product.Name, Slug=product.Slug, ImageUrl=self._card_image(product),
                Price=cheapest["SalePrice"] if cheapest else None,
                OriginalPrice=cheapest["OriginalPrice"] if cheapest and cheapest["OriginalPrice"] > cheapest["SalePrice"]
                else None))
        return SearchSuggestionsResponse(Searches=searches, Products=products)

    @staticmethod
    def _card_image(product: Product) -> str | None:
        """The photo a product card opens with: the default variant's main image."""
        visible = [variant for variant in product.variants if variant.IsActive and not variant.IsDeleted]
        return variant_images(product, default_variant_id(product, visible))[1]

    @staticmethod
    def _visible_root(category_id: uuid.UUID, categories: Mapping[uuid.UUID, Category]) -> Category | None:
        """The top category above ``category_id`` when it and every parent are active; None otherwise."""
        category, seen = categories.get(category_id), set()
        while category is not None and category.IsActive and category.CategoryId not in seen:
            if category.ParentCategoryId is None:
                return category
            seen.add(category.CategoryId)
            category = categories.get(category.ParentCategoryId)
        return None

    def _root_slug(self, category: Category) -> str:
        seen = {category.CategoryId}
        while category.ParentCategoryId is not None:
            parent = self.categories.get_by_id(category.ParentCategoryId)
            if parent is None or parent.CategoryId in seen:  # malformed cyclic data
                break
            seen.add(parent.CategoryId)
            category = parent
        return category.Slug

    def _selected_options(self, category_id: uuid.UUID, specs: list[str]) -> list[list]:
        """``spec`` values grouped by criterion; an unknown criterion or option is an error, not ignored."""
        category = self.categories.get_by_id(category_id)
        if category is None:
            raise NotFoundError("Không tìm thấy danh mục", code="category_not_found")
        group = facet_group(self._root_slug(category))
        selected: dict[str, list] = {}
        for spec in specs:
            key, _, value = spec.partition(":")
            facet = group.facet(key)
            chosen = facet.option(value) if facet else None
            if chosen is None:
                raise BusinessRuleError(f"Bộ lọc không hợp lệ: {spec}", code="invalid_filter")
            if chosen not in selected.setdefault(key, []):
                selected[key].append(chosen)
        return list(selected.values())

    @staticmethod
    def _matches(row, selected: list[list]) -> bool:
        facts = ProductFacts.of(row.Name, row.Specifications, row.Storages)
        return all(any(option.matches(facts) for option in options) for options in selected)

    def get_product_detail(self, product_id: uuid.UUID) -> ProductDetailResponse:
        return self._customer_detail(self.products.get_detail(product_id))

    def get_product_detail_by_slug(self, slug: str) -> ProductDetailResponse:
        return self._customer_detail(self.products.get_detail_by_slug(slug))

    def get_product_details(self, product_ids: list[uuid.UUID]) -> dict[uuid.UUID, ProductDetailResponse]:
        """get_product_detail for many products in a fixed number of queries; products not on sale are omitted."""
        from app.core.product_pricing import matches_product

        from .pricing import PricingService
        products = [p for p in self.products.list_details(product_ids) if is_product_sellable(p)]
        if not products:
            return {}
        promotions = PricingService(self.session, clock=self._clock).automatic_promotions()
        return {p.ProductId: self._customer_detail(p, promotions=[x for x in promotions if matches_product(x, p)])
                for p in products}

    def _customer_detail(self, product: Product | None, *, promotions=None) -> ProductDetailResponse:
        if not is_product_sellable(product):
            raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
        response = ProductDetailResponse.model_validate(product)
        # Chỉ hiển thị biến thể đang bán.
        visible = {v.ProductVariantId for v in product.variants if is_variant_sellable(v)}
        response.Variants = [v for v in response.Variants if v.ProductVariantId in visible]
        from .pricing import PricingService, variant_price
        if promotions is None:
            promotions = PricingService(self.session, clock=self._clock).automatic_promotions(product=product)
        now = self.now()
        variants = {v.ProductVariantId: v for v in product.variants}
        for variant in response.Variants:
            for key, value in variant_price(variants[variant.ProductVariantId], promotions, now).items():
                setattr(variant, key, value)
        self._detail_media(response, product)
        return response

    @staticmethod
    def _detail_media(response, product):
        visible = {variant.ProductVariantId for variant in response.Variants if not getattr(variant, "IsDeleted", False)}
        response.DefaultVariantId = default_variant_id(product, [v for v in product.variants if v.ProductVariantId in visible])
        for variant_id in visible:
            images, thumbnail = variant_images(product, variant_id)
            response.VariantImages[variant_id] = [ProductImageResponse.model_validate(image).model_copy(
                update={"IsDefault": image.ImageUrl == thumbnail}) for image in images]

    # ---------------------------------------------------------- Admin / Staff

    def admin_list_products(
        self,
        actor: Actor,
        *,
        keyword: str | None = None,
        category_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        status: str | None = None,
        include_deleted: bool = False,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        stock: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[AdminProductListResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        if min_price is not None and max_price is not None and min_price > max_price:
            raise BusinessRuleError("Giá tối thiểu phải nhỏ hơn hoặc bằng giá tối đa", code="invalid_price_range")
        offset, limit = self._page_args(page, page_size)
        filters = {
            "category_ids": [category_id] if category_id else None,
            "brand_id": brand_id,
            "status": status,
            "include_deleted": include_deleted,
            "keyword": keyword.strip() if keyword and keyword.strip() else None,
            "min_price": min_price, "max_price": max_price, "stock": stock,
        }
        items = self.products.list_admin_catalog(**filters, offset=offset, limit=limit)
        return PageResponse[AdminProductListResponse](
            Items=[self._admin_list_item(p) for p in items],
            Total=self.products.count_admin_catalog(**filters),
            Page=page,
            PageSize=page_size,
        )

    @staticmethod
    def _admin_list_item(product: Product) -> AdminProductListResponse:
        variants = [v for v in product.variants if not v.IsDeleted]
        images = sorted(product.images, key=lambda image: (not image.IsDefault, image.DisplayOrder,
                                                            str(image.ProductImageId)))
        quantity = sum(v.StockQuantity for v in variants)
        return AdminProductListResponse(
            **AdminProductResponse.model_validate(product).model_dump(),
            Category=product.category, Brand=product.brand,
            Skus=sorted(v.Sku for v in variants),
            ThumbnailUrl=images[0].ImageUrl if images else None,
            MinPrice=min((v.Price for v in variants), default=None),
            MaxPrice=max((v.Price for v in variants), default=None),
            StockQuantity=quantity,
            IsLowStock=quantity > 0 and any(v.MinStockLevel > 0 and v.StockQuantity <= v.MinStockLevel
                                           for v in variants),
        )

    def admin_get_product(self, actor: Actor, product_id: uuid.UUID) -> AdminProductDetailResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        product = self.products.get_detail(product_id)
        if product is None:
            raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
        response = AdminProductDetailResponse.model_validate(product)
        self._detail_media(response, product)
        return response

    def create_product(self, actor: Actor, data: ProductCreate) -> AdminProductResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            values = data.model_dump(exclude_unset=True)
            self._ensure_references(values)
            validate_warranty_months(values.get("WarrantyMonths"))  # chặn cả khi schema bị bỏ qua
            if self.products.exists_by_slug(values["Slug"]):
                raise ConflictError("Slug sản phẩm đã tồn tại", code="product_slug_exists")
            product = self.products.create(values)
            self.products.flush()
            return AdminProductResponse.model_validate(product)

    def update_product(self, actor: Actor, product_id: uuid.UUID, data: ProductUpdate) -> AdminProductResponse:
        """Cập nhật thông tin; ẩn sản phẩm bằng cách đổi Status."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            product = self.products.get_by_id_for_update(product_id)
            if product is None or product.IsDeleted:
                raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
            values = data.model_dump(exclude_unset=True)
            if "Specifications" in values:
                values["Specifications"] = merge_specifications(product.Specifications, values["Specifications"])
            self._ensure_references(values)
            if "WarrantyMonths" in values:
                validate_warranty_months(values["WarrantyMonths"])
            if "Slug" in values and self.products.exists_by_slug(values["Slug"], product_id):
                raise ConflictError("Slug sản phẩm đã tồn tại", code="product_slug_exists")
            self.products.update(product, values)
            self.products.flush()
            return AdminProductResponse.model_validate(product)

    def delete_product(self, actor: Actor, product_id: uuid.UUID) -> None:
        """Xóa mềm (IsDeleted = true); Products được tham chiếu bởi OrderItems/Reviews nên không xóa dòng."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            self._get_active(product_id).IsDeleted = True

    def _get_active(self, product_id: uuid.UUID) -> Product:
        product = self.products.get_by_id(product_id)
        if product is None or product.IsDeleted:
            raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
        return product

    def _ensure_references(self, values: Mapping) -> None:
        if "CategoryId" in values and self.categories.get_by_id(values["CategoryId"]) is None:
            raise NotFoundError("Không tìm thấy danh mục", code="category_not_found")
        if "BrandId" in values and self.brands.get_by_id(values["BrandId"]) is None:
            raise NotFoundError("Không tìm thấy thương hiệu", code="brand_not_found")


class ProductVariantService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.variants = ProductVariantRepository(session)
        self.products = ProductRepository(session)
        self.users = UserRepository(session)
        self.notifications = NotificationService(session, clock=clock)

    def search_variants(self, actor: Actor, *, keyword: str | None = None,
                        category_id: uuid.UUID | None = None, brand_id: uuid.UUID | None = None,
                        status: str | None = None, min_price: Decimal | None = None,
                        max_price: Decimal | None = None, stock: str | None = None,
                        page: int = 1, page_size: int = 20) -> PageResponse[AdminProductVariantListResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        if min_price is not None and max_price is not None and min_price > max_price:
            raise BusinessRuleError("Giá tối thiểu phải nhỏ hơn hoặc bằng giá tối đa", code="invalid_price_range")
        offset, limit = self._page_args(page, page_size)
        filters = {"keyword": keyword.strip() if keyword and keyword.strip() else None,
                   "category_id": category_id, "brand_id": brand_id, "status": status,
                   "min_price": min_price, "max_price": max_price, "stock": stock}
        variants = self.variants.list_catalog(**filters, offset=offset, limit=limit)
        items = []
        for variant in variants:
            product = variant.product
            _, thumbnail = variant_images(product, variant.ProductVariantId)
            items.append(AdminProductVariantListResponse(
                **AdminProductVariantResponse.model_validate(variant).model_dump(),
                Name=product.Name, Status=product.Status, Category=product.category, Brand=product.brand,
                ThumbnailUrl=thumbnail,
                IsLowStock=variant.StockQuantity > 0 and variant.MinStockLevel > 0
                and variant.StockQuantity <= variant.MinStockLevel,
            ))
        return PageResponse[AdminProductVariantListResponse](Items=items,
                    Total=self.variants.count_catalog(**filters), Page=page, PageSize=page_size)

    def list_variants(
        self, actor: Actor, product_id: uuid.UUID, *, include_deleted: bool = False
    ) -> list[AdminProductVariantResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        items = self.variants.list_by_product(product_id, include_deleted=include_deleted)
        return [AdminProductVariantResponse.model_validate(v) for v in items]

    def get_variant(self, actor: Actor, variant_id: uuid.UUID) -> AdminProductVariantResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        variant = self.variants.get_by_id(variant_id)
        if variant is None:
            raise NotFoundError("Không tìm thấy biến thể", code="variant_not_found")
        return AdminProductVariantResponse.model_validate(variant)

    def create_variant(self, actor: Actor, data: ProductVariantCreate) -> AdminProductVariantResponse:
        """Biến thể mới có StockQuantity = 0, CostPrice = 0 (default database); tồn/giá vốn đặt qua nghiệp vụ kho."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            values = data.model_dump(exclude_unset=True)
            reject_inventory_fields(values)
            values.setdefault("IsSerialTracked", True)
            product = self.products.get_by_id(values["ProductId"])
            if product is None or product.IsDeleted:
                raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
            if self.variants.exists_by_sku(values["Sku"]):
                raise ConflictError("SKU đã tồn tại", code="sku_exists")
            if values.get("CompareAtPrice") is not None and values["CompareAtPrice"] < values["Price"]:
                raise BusinessRuleError("Giá niêm yết phải lớn hơn hoặc bằng giá bán", code="invalid_compare_price")
            variant = self.variants.create(values)
            self.variants.flush()
            return AdminProductVariantResponse.model_validate(variant)

    def update_variant(
        self, actor: Actor, variant_id: uuid.UUID, data: ProductVariantUpdate
    ) -> AdminProductVariantResponse:
        """Cập nhật thông tin biến thể. Không sửa StockQuantity/CostPrice.

        Bật/tắt IsSerialTracked chỉ khi tồn kho bằng 0 (tránh tồn kho hiện có không khớp số serial).
        Tắt IsSerialTracked còn yêu cầu biến thể chưa từng được dùng với serial (``_ensure_serial_tracking_unused``).
        """
        require_role(actor, *ADMIN_ONLY)
        values = data.model_dump(exclude_unset=True)
        reject_inventory_fields(values)
        with self.transaction():
            # Khóa dòng khi đổi IsSerialTracked để đọc tồn kho nhất quán với đơn hàng/nhập hàng đồng thời.
            variant = self._get_active(variant_id, lock="IsSerialTracked" in values)
            comparison = values.get("CompareAtPrice", variant.CompareAtPrice)
            if comparison is not None and comparison < values.get("Price", variant.Price):
                raise BusinessRuleError("Giá niêm yết phải lớn hơn hoặc bằng giá bán", code="invalid_compare_price")
            if "Sku" in values and self.variants.exists_by_sku(values["Sku"], variant_id):
                raise ConflictError("SKU đã tồn tại", code="sku_exists")
            if "IsSerialTracked" in values and values["IsSerialTracked"] != variant.IsSerialTracked and variant.StockQuantity != 0:
                raise BusinessRuleError(
                    "Chỉ bật/tắt quản lý Serial/IMEI khi tồn kho bằng 0", code="serial_tracking_change_requires_zero_stock"
                )
            if variant.IsSerialTracked and values.get("IsSerialTracked") is False:
                self._ensure_serial_tracking_unused(variant)
            self.variants.update(variant, values)
            self.variants.flush()
            return AdminProductVariantResponse.model_validate(variant)

    def delete_variant(self, actor: Actor, variant_id: uuid.UUID) -> None:
        """Xóa mềm (IsDeleted = true); biến thể được tham chiếu bởi OrderItems/PurchaseOrderItems/ProductSerials."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            self._get_active(variant_id).IsDeleted = True

    def change_stock(self, deltas: Mapping[uuid.UUID, int]) -> dict[uuid.UUID, int]:
        """Cộng/trừ tồn kho cho nhiều biến thể trong cùng transaction (dùng nội bộ cho Order/Purchasing).

        Khóa các dòng theo thứ tự ProductVariantId (tránh deadlock) trước khi đọc/ghi.
        Không cho tồn kho âm (CHECK StockQuantity >= 0). Không đổi CostPrice. Trả về tồn kho mới theo biến thể.
        Chỉ gọi bên trong một use case (không dùng trực tiếp từ Router).
        Tồn vừa giảm xuống mức cảnh báo thì thông báo Staff/Admin (cùng transaction).
        """
        self.require_enclosing_use_case()
        changes = {variant_id: delta for variant_id, delta in deltas.items() if delta != 0}
        with self.transaction():
            if not changes:
                return {}
            locked = {v.ProductVariantId: v for v in self.variants.get_many_by_ids_for_update(changes.keys())}
            missing = set(changes) - set(locked)
            if missing:
                raise NotFoundError(f"Không tìm thấy biến thể: {sorted(map(str, missing))}", code="variant_not_found")
            short = [str(vid) for vid, delta in changes.items() if locked[vid].StockQuantity + delta < 0]
            if short:
                raise BusinessRuleError(f"Không đủ tồn kho: {sorted(short)}", code="insufficient_stock")
            for variant_id, delta in changes.items():
                before = locked[variant_id].StockQuantity
                locked[variant_id].StockQuantity = before + delta
                self.alert_if_low_stock(locked[variant_id], before)
            self.variants.flush()
            return {variant_id: locked[variant_id].StockQuantity for variant_id in changes}

    def alert_if_low_stock(self, variant: ProductVariant, before: int) -> bool:
        """Thông báo Staff/Admin đang hoạt động khi tồn vừa giảm xuống StockQuantity <= MinStockLevel.

        Chỉ gửi khi chuyển trạng thái (trước > ngưỡng), nên không lặp lại khi tồn tiếp tục giảm hoặc khi đọc dữ liệu.
        Tham gia transaction của use case gọi nó.
        """
        self.require_enclosing_use_case()
        if not crossed_low_stock(variant, before):
            return False
        content = (
            f"Biến thể {variant.Sku} còn {variant.StockQuantity} (ngưỡng cảnh báo {variant.MinStockLevel})."
        )
        for role in STAFF_OR_ADMIN:
            for user in self.users.list_users(role=role, account_status="Active"):
                self.notifications.notify(
                    user.UserId,
                    title="Cảnh báo tồn kho thấp",
                    content=content,
                    notification_type=LOW_STOCK_NOTIFICATION_TYPE,
                    reference_type="ProductVariant",
                    reference_id=variant.ProductVariantId,
                )
        return True

    def _ensure_serial_tracking_unused(self, variant: ProductVariant) -> None:
        """Chặn tắt IsSerialTracked khi biến thể còn serial chưa loại bỏ, có dòng đơn hoặc quy trình đang mở.

        OrderItems không lưu biến thể có quản lý serial lúc bán, và ProductSerials.OrderItemId chỉ giữ liên kết hiện tại
        (bị gỡ khi hủy đơn/hàng hoàn/trả hàng): không phân biệt được dòng đơn nào từng gắn serial, nên mọi dòng đơn
        của biến thể đều chặn. Không xóa/đổi trạng thái serial hay lịch sử. Biến thể đã bị khóa dòng bởi caller.
        """
        usage = self.variants.serial_tracking_usage(variant.ProductVariantId)
        reasons = [
            text
            for count, text in (
                (usage.active_serials, f"còn {usage.active_serials} serial chưa loại bỏ (trạng thái khác WrittenOff)"),
                (usage.order_items, f"đã có {usage.order_items} dòng đơn hàng cần giữ lịch sử gán serial"),
                (usage.open_warranty_requests, f"{usage.open_warranty_requests} yêu cầu bảo hành đang mở"),
                (usage.open_return_requests, f"{usage.open_return_requests} yêu cầu đổi/trả đang mở"),
                (usage.awaiting_shipment_returns, f"{usage.awaiting_shipment_returns} phiếu hàng hoàn chưa nhận"),
            )
            if count
        ]
        if reasons:
            raise BusinessRuleError(
                "Không thể tắt quản lý Serial/IMEI: " + "; ".join(reasons)
                + ". Hãy tạo biến thể mới nếu cần bán không theo serial",
                code="serial_tracking_in_use",
            )

    def _get_active(self, variant_id: uuid.UUID, *, lock: bool = False) -> ProductVariant:
        variant = self.variants.get_by_id_for_update(variant_id) if lock else self.variants.get_by_id(variant_id)
        if variant is None or variant.IsDeleted:
            raise NotFoundError("Không tìm thấy biến thể", code="variant_not_found")
        return variant


class ProductImageService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.images = ProductImageRepository(session)
        self.products = ProductRepository(session)

    def list_images(self, product_id: uuid.UUID) -> list[ProductImageResponse]:
        # Public image reads follow the same boundary as product detail reads.
        if not is_product_sellable(self.products.get_by_id(product_id)):
            raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
        return [ProductImageResponse.model_validate(i) for i in self.images.list_by_product(product_id)]

    def add_image(self, actor: Actor, product_id: uuid.UUID, data: ProductImageCreate) -> ProductImageResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            product = self.products.get_by_id(product_id)
            if product is None or product.IsDeleted:
                raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
            values = data.model_dump(exclude_unset=True)
            if values.get("IsDefault"):
                self._clear_default(product_id)
            image = self.images.create({**values, "ProductId": product_id})
            self.images.flush()
            return ProductImageResponse.model_validate(image)

    def update_image(
        self, actor: Actor, product_id: uuid.UUID, image_id: uuid.UUID, data: ProductImageUpdate
    ) -> ProductImageResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            image = self._get_owned(product_id, image_id)
            values = data.model_dump(exclude_unset=True)
            if values.get("IsDefault"):
                self._clear_default(product_id, keep=image)
            self.images.update(image, values)
            self.images.flush()
            return ProductImageResponse.model_validate(image)

    def delete_image(self, actor: Actor, product_id: uuid.UUID, image_id: uuid.UUID) -> None:
        """ProductImages không có IsDeleted và không bị bảng khác tham chiếu: xóa dòng."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            self.images.delete(self._get_owned(product_id, image_id))

    def _get_owned(self, product_id: uuid.UUID, image_id: uuid.UUID) -> ProductImage:
        image = self.images.get_by_id(image_id)
        if image is None or image.ProductId != product_id:
            raise NotFoundError("Không tìm thấy ảnh sản phẩm", code="product_image_not_found")
        return image

    def _clear_default(self, product_id: uuid.UUID, keep: ProductImage | None = None) -> None:
        """Mỗi sản phẩm chỉ có một ảnh mặc định."""
        for other in self.images.list_default_by_product(product_id):
            if other is not keep:
                other.IsDefault = False


class ProductSerialService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.serials = ProductSerialRepository(session)
        self.warranty_requests = WarrantyRequestRepository(session)

    def list_serials(
        self, actor: Actor, variant_id: uuid.UUID, *, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> PageResponse[ProductSerialResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        offset, limit = self._page_args(page, page_size)
        items = self.serials.list_by_variant(variant_id, status=status, offset=offset, limit=limit)
        return PageResponse[ProductSerialResponse](
            Items=[ProductSerialResponse.model_validate(s) for s in items],
            Total=self.serials.count_by_variant(variant_id, status=status),
            Page=page,
            PageSize=page_size,
        )

    def get_serial(self, actor: Actor, serial_id: uuid.UUID) -> ProductSerialResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        return ProductSerialResponse.model_validate(self._get(serial_id))

    def get_by_serial_number(self, actor: Actor, serial_number: str) -> ProductSerialResponse:
        require_role(actor, *STAFF_OR_ADMIN)
        serial = self.serials.get_by_serial_number(normalize_serial_number(serial_number))
        if serial is None:
            raise NotFoundError("Không tìm thấy Serial/IMEI", code="serial_not_found")
        return ProductSerialResponse.model_validate(serial)

    def create_serial(self, actor: Actor, data: ProductSerialCreate) -> ProductSerialResponse:
        """Không tạo Serial/IMEI qua CRUD: chỉ qua nhận hàng, khai báo tồn đầu kỳ hoặc điều chỉnh tăng tồn
        (InventoryService) để số serial khả dụng luôn khớp tồn kho và có dấu vết nghiệp vụ."""
        require_role(actor, *ADMIN_ONLY)
        raise BusinessRuleError(
            "Serial/IMEI chỉ được tạo khi nhận hàng, khai báo tồn đầu kỳ hoặc điều chỉnh tăng tồn",
            code="serial_manual_create_not_allowed",
        )

    def update_serial(self, actor: Actor, serial_id: uuid.UUID, data: ProductSerialUpdate) -> ProductSerialResponse:
        """Admin sửa số Serial/IMEI nhập nhầm: chỉ serial Available, chưa gắn dòng đơn, chưa có lịch sử bảo hành,
        đổi/trả hay hàng hoàn vận chuyển (serial đã bán rồi trả về/nhập lại tồn vẫn giữ số gốc — đợt 5.10);
        số mới không trùng (UNIQUE SerialNumber). Không sửa Status/OrderItemId/ngày bảo hành qua CRUD."""
        require_role(actor, *ADMIN_ONLY)
        values = data.model_dump(exclude_unset=True)
        not_editable = sorted(set(values) - {"SerialNumber"})
        if not_editable:  # schema chỉ có SerialNumber; chặn cả khi schema bị bỏ qua
            raise BusinessRuleError(
                f"Không được sửa trực tiếp các trường: {not_editable}", code="serial_field_not_editable"
            )
        if not values.get("SerialNumber"):
            raise BusinessRuleError("Phải nhập Serial/IMEI mới", code="serial_number_required")
        new_number = normalize_serial_number(values["SerialNumber"])
        with self.transaction():
            # Khóa dòng: Status/OrderItemId của serial có thể bị đơn hàng/kho thay đổi đồng thời.
            serial = self._get(serial_id, lock=True)
            if serial.Status != SERIAL_AVAILABLE or serial.OrderItemId is not None:
                raise BusinessRuleError(
                    "Chỉ sửa được Serial/IMEI đang Available và chưa gắn đơn hàng", code="serial_not_editable"
                )
            if self.warranty_requests.list_by_product_serial(serial_id) or self.serials.has_return_history(serial_id):
                raise BusinessRuleError(
                    "Serial/IMEI đã có lịch sử bảo hành/đổi trả/hàng hoàn, không sửa số", code="serial_has_history"
                )
            if self.serials.exists_by_serial_number(new_number, serial_id):
                raise ConflictError("Serial/IMEI đã tồn tại", code="serial_exists")
            serial.SerialNumber = new_number
            self.serials.flush()
            return ProductSerialResponse.model_validate(serial)

    def delete_serial(self, actor: Actor, serial_id: uuid.UUID) -> None:
        """Không xóa cứng Serial/IMEI (giữ lịch sử kho/bán/bảo hành); hàng rời kho: điều chỉnh giảm (WrittenOff)."""
        require_role(actor, *ADMIN_ONLY)
        raise BusinessRuleError(
            "Không xóa Serial/IMEI; dùng điều chỉnh giảm tồn để loại khỏi kho", code="serial_delete_not_allowed"
        )

    def _get(self, serial_id: uuid.UUID, *, lock: bool = False) -> ProductSerial:
        serial = self.serials.get_by_id_for_update(serial_id) if lock else self.serials.get_by_id(serial_id)
        if serial is None:
            raise NotFoundError("Không tìm thấy Serial/IMEI", code="serial_not_found")
        return serial
