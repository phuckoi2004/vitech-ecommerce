"""Repositories cho Reviews, ReviewImages.

Không quyết định khách hàng có được đánh giá hay không (thuộc Service).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.models import Review, ReviewImage

from .base import BaseRepository


class ReviewRepository(BaseRepository[Review]):
    model = Review

    @staticmethod
    def _display_options() -> tuple:
        # ReviewResponse nhúng User (UserSummary) và Images.
        return (joinedload(Review.user), selectinload(Review.images))

    def get_detail(self, review_id: uuid.UUID) -> Review | None:
        stmt = select(Review).where(Review.ReviewId == review_id).options(*self._display_options())
        return self.session.scalars(stmt).one_or_none()

    def get_by_order_item(self, order_item_id: uuid.UUID) -> Review | None:
        return self.get_one(Review.OrderItemId == order_item_id)

    def exists_by_order_item(self, order_item_id: uuid.UUID) -> bool:
        """Kiểm tra trên mọi dòng (kể cả IsDeleted), giống phạm vi UNIQUE của OrderItemId."""
        return self.exists(Review.OrderItemId == order_item_id)

    def list_by_product(
        self,
        product_id: uuid.UUID,
        *,
        rating: int | None = None,
        include_deleted: bool = False,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Review]:
        conditions = [Review.ProductId == product_id]
        if rating is not None:
            conditions.append(Review.Rating == rating)
        if not include_deleted:
            conditions.append(Review.IsDeleted.is_(False))
        return self.get_all(
            *conditions,
            order_by=(Review.CreatedAt.desc(), Review.ReviewId),
            offset=offset,
            limit=limit,
            options=self._display_options(),
        )

    def count_by_product(
        self, product_id: uuid.UUID, *, rating: int | None = None, include_deleted: bool = False
    ) -> int:
        conditions = [Review.ProductId == product_id]
        if rating is not None:
            conditions.append(Review.Rating == rating)
        if not include_deleted:
            conditions.append(Review.IsDeleted.is_(False))
        return self.count(*conditions)

    def list_by_user(
        self,
        user_id: uuid.UUID,
        *,
        include_deleted: bool = False,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Review]:
        conditions = [Review.UserId == user_id]
        if not include_deleted:
            conditions.append(Review.IsDeleted.is_(False))
        return self.get_all(
            *conditions,
            order_by=(Review.CreatedAt.desc(), Review.ReviewId),
            offset=offset,
            limit=limit,
            options=self._display_options(),
        )


class ReviewImageRepository(BaseRepository[ReviewImage]):
    model = ReviewImage

    def list_by_review(self, review_id: uuid.UUID) -> list[ReviewImage]:
        return self.get_all(
            ReviewImage.ReviewId == review_id,
            order_by=(ReviewImage.DisplayOrder, ReviewImage.ReviewImageId),
        )
