"""Repositories cho Promotions, PromotionProducts, PromotionCategories, Coupons.

Không quyết định coupon có hợp lệ để áp dụng hay không (thuộc Service).
"""

import uuid
from collections.abc import Collection

from sqlalchemy import case, delete, exists, func, or_, select, update
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import joinedload, selectinload

from app.models import Coupon, Promotion, PromotionCategory, PromotionProduct

from .base import BaseRepository


class PromotionRepository(BaseRepository[Promotion]):
    model = Promotion

    def synchronize(self, now, promotion_id=None) -> None:
        # Only published/scheduled programs follow the clock. Draft/Cancelled remain explicit decisions.
        status = case((Promotion.EndDate < now, "Expired"), (Promotion.StartDate > now, "Scheduled"), else_="Active")
        stmt = update(Promotion).where(
            Promotion.Status.in_(("Scheduled", "Active")), Promotion.Status != status,
        )
        if promotion_id is not None:
            stmt = stmt.where(Promotion.PromotionId == promotion_id)
        self.session.execute(stmt.values(Status=status).execution_options(synchronize_session="fetch"))

    def get_detail(self, promotion_id: uuid.UUID) -> Promotion | None:
        """Promotion kèm danh sách sản phẩm/danh mục áp dụng."""
        stmt = (
            select(Promotion)
            .where(Promotion.PromotionId == promotion_id)
            .options(joinedload(Promotion.created_by), selectinload(Promotion.promotion_products), selectinload(Promotion.promotion_categories))
        )
        return self.session.scalars(stmt).one_or_none()

    def list_promotions(
        self, *, status: str | None = None, offset: int | None = None, limit: int | None = None
    ) -> list[Promotion]:
        conditions = [] if status is None else [Promotion.Status == status]
        stmt = select(Promotion).where(*conditions).options(joinedload(Promotion.created_by)).order_by(
            Promotion.StartDate.desc(), Promotion.PromotionId)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

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

    def synchronize(self, now, promotion_id=None) -> None:
        in_period = exists(select(Promotion.PromotionId).where(
            Promotion.PromotionId == Coupon.PromotionId,
            Promotion.Status.in_(("Scheduled", "Active")),
            Promotion.StartDate <= now, Promotion.EndDate >= now,
        ))
        available = in_period & or_(Coupon.UsageLimit.is_(None), Coupon.UsedCount < Coupon.UsageLimit)
        stmt = update(Coupon).where(Coupon.IsActive.is_distinct_from(available))
        if promotion_id is not None:
            stmt = stmt.where(Coupon.PromotionId == promotion_id)
        self.session.execute(stmt.values(
            IsActive=available).execution_options(synchronize_session="fetch"))

    @staticmethod
    def _code_matches(code: str):
        # Khớp unique index UX_Coupons_Code_Lower: lower("Code").
        return func.lower(Coupon.Code) == func.lower(code)

    def get_by_code(self, code: str, *, with_promotion: bool = False) -> Coupon | None:
        """Tìm theo Code, không phân biệt hoa thường."""
        stmt = select(Coupon).where(self._code_matches(code))
        if with_promotion:
            stmt = stmt.options(joinedload(Coupon.promotion))
        return self.session.scalars(stmt).one_or_none()

    def get_by_code_for_update(self, code: str) -> Coupon | None:
        """Khóa dòng coupon trước khi Service tăng UsedCount."""
        locked = self._scalars_for_update(select(Coupon).where(self._code_matches(code)).with_for_update())
        if len(locked) > 1:
            # Không xảy ra khi có unique index UX_Coupons_Code_Lower; giữ hành vi của one_or_none().
            raise MultipleResultsFound("Nhiều coupon cùng mã")
        return locked[0] if locked else None

    def exists_by_code(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [self._code_matches(code)]
        if exclude_id is not None:
            conditions.append(Coupon.CouponId != exclude_id)
        return self.exists(*conditions)

    def list_by_promotion(self, promotion_id: uuid.UUID, *, is_active: bool | None = None) -> list[Coupon]:
        conditions = [Coupon.PromotionId == promotion_id]
        if is_active is not None:
            conditions.append(Coupon.IsActive.is_(is_active))
        return list(self.session.scalars(select(Coupon).where(*conditions).options(
            joinedload(Coupon.promotion), joinedload(Coupon.created_by),
        ).order_by(Coupon.CreatedAt.desc(), Coupon.CouponId)))
