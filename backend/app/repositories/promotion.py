"""Repositories cho Promotions, PromotionProducts, PromotionCategories, Coupons.

Không quyết định coupon có hợp lệ để áp dụng hay không (thuộc Service).
"""

import uuid
from collections.abc import Collection

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload, selectinload

from app.models import Coupon, Promotion, PromotionCategory, PromotionProduct

from .base import BaseRepository


class PromotionRepository(BaseRepository[Promotion]):
    model = Promotion

    def get_detail(self, promotion_id: uuid.UUID) -> Promotion | None:
        """Promotion kèm danh sách sản phẩm/danh mục áp dụng."""
        stmt = (
            select(Promotion)
            .where(Promotion.PromotionId == promotion_id)
            .options(selectinload(Promotion.promotion_products), selectinload(Promotion.promotion_categories))
        )
        return self.session.scalars(stmt).one_or_none()

    def list_promotions(
        self, *, status: str | None = None, offset: int | None = None, limit: int | None = None
    ) -> list[Promotion]:
        conditions = [] if status is None else [Promotion.Status == status]
        return self.get_all(
            *conditions,
            order_by=(Promotion.StartDate.desc(), Promotion.PromotionId),
            offset=offset,
            limit=limit,
        )

    def count_promotions(self, *, status: str | None = None) -> int:
        return self.count(*([] if status is None else [Promotion.Status == status]))

    def list_by_product(self, product_id: uuid.UUID, *, status: str | None = None) -> list[Promotion]:
        """Promotions gắn trực tiếp với sản phẩm (qua PromotionProducts)."""
        stmt = select(Promotion).join(PromotionProduct).where(PromotionProduct.ProductId == product_id)
        if status is not None:
            stmt = stmt.where(Promotion.Status == status)
        return list(self.session.scalars(stmt.order_by(Promotion.StartDate.desc(), Promotion.PromotionId)))

    def list_by_categories(self, category_ids: Collection[uuid.UUID], *, status: str | None = None) -> list[Promotion]:
        """Promotions gắn với một trong các danh mục (qua PromotionCategories)."""
        if not category_ids:
            return []
        stmt = (
            select(Promotion)
            .join(PromotionCategory)
            .where(PromotionCategory.CategoryId.in_(category_ids))
            .distinct()
        )
        if status is not None:
            stmt = stmt.where(Promotion.Status == status)
        return list(self.session.scalars(stmt.order_by(Promotion.StartDate.desc(), Promotion.PromotionId)))


class PromotionProductRepository(BaseRepository[PromotionProduct]):
    model = PromotionProduct

    def get(self, promotion_id: uuid.UUID, product_id: uuid.UUID) -> PromotionProduct | None:
        return self.get_by_id((promotion_id, product_id))

    def list_by_promotion(self, promotion_id: uuid.UUID) -> list[PromotionProduct]:
        return self.get_all(PromotionProduct.PromotionId == promotion_id)

    def list_by_product(self, product_id: uuid.UUID) -> list[PromotionProduct]:
        return self.get_all(PromotionProduct.ProductId == product_id)

    def delete_by_promotion(self, promotion_id: uuid.UUID) -> int:
        """Xóa toàn bộ sản phẩm áp dụng của một Promotion (dùng khi thay danh sách). Trả số dòng bị xóa."""
        result = self.session.execute(delete(PromotionProduct).where(PromotionProduct.PromotionId == promotion_id))
        return result.rowcount


class PromotionCategoryRepository(BaseRepository[PromotionCategory]):
    model = PromotionCategory

    def get(self, promotion_id: uuid.UUID, category_id: uuid.UUID) -> PromotionCategory | None:
        return self.get_by_id((promotion_id, category_id))

    def list_by_promotion(self, promotion_id: uuid.UUID) -> list[PromotionCategory]:
        return self.get_all(PromotionCategory.PromotionId == promotion_id)

    def list_by_category(self, category_id: uuid.UUID) -> list[PromotionCategory]:
        return self.get_all(PromotionCategory.CategoryId == category_id)

    def delete_by_promotion(self, promotion_id: uuid.UUID) -> int:
        """Xóa toàn bộ danh mục áp dụng của một Promotion (dùng khi thay danh sách). Trả số dòng bị xóa."""
        result = self.session.execute(delete(PromotionCategory).where(PromotionCategory.PromotionId == promotion_id))
        return result.rowcount


class CouponRepository(BaseRepository[Coupon]):
    model = Coupon

    def get_by_code(self, code: str, *, with_promotion: bool = False) -> Coupon | None:
        """Khớp chính xác Code (UNIQUE phân biệt hoa thường theo schema hiện tại)."""
        stmt = select(Coupon).where(Coupon.Code == code)
        if with_promotion:
            stmt = stmt.options(joinedload(Coupon.promotion))
        return self.session.scalars(stmt).one_or_none()

    def get_by_code_for_update(self, code: str) -> Coupon | None:
        """Khóa dòng coupon trước khi Service tăng UsedCount."""
        return self.session.scalars(select(Coupon).where(Coupon.Code == code).with_for_update()).one_or_none()

    def exists_by_code(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [Coupon.Code == code]
        if exclude_id is not None:
            conditions.append(Coupon.CouponId != exclude_id)
        return self.exists(*conditions)

    def list_by_promotion(self, promotion_id: uuid.UUID, *, is_active: bool | None = None) -> list[Coupon]:
        conditions = [Coupon.PromotionId == promotion_id]
        if is_active is not None:
            conditions.append(Coupon.IsActive.is_(is_active))
        return self.get_all(*conditions, order_by=(Coupon.CreatedAt.desc(), Coupon.CouponId))
