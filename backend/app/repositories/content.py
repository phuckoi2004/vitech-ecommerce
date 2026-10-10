"""Repositories cho NewsArticles, Banners."""

import uuid
from datetime import datetime

from sqlalchemy import or_

from app.models import Banner, NewsArticle

from .base import BaseRepository


class NewsArticleRepository(BaseRepository[NewsArticle]):
    model = NewsArticle

    def get_by_slug(self, slug: str) -> NewsArticle | None:
        return self.get_one(NewsArticle.Slug == slug)

    def exists_by_slug(self, slug: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [NewsArticle.Slug == slug]
        if exclude_id is not None:
            conditions.append(NewsArticle.NewsArticleId != exclude_id)
        return self.exists(*conditions)

    def list_articles(
        self, *, status: str | None = None, offset: int | None = None, limit: int | None = None
    ) -> list[NewsArticle]:
        conditions = [] if status is None else [NewsArticle.Status == status]
        return self.get_all(
            *conditions,
            order_by=(NewsArticle.PublishedAt.desc().nulls_last(), NewsArticle.CreatedAt.desc(), NewsArticle.NewsArticleId),
            offset=offset,
            limit=limit,
        )

    def count_articles(self, *, status: str | None = None) -> int:
        return self.count(*([] if status is None else [NewsArticle.Status == status]))


class BannerRepository(BaseRepository[Banner]):
    model = Banner

    def list_banners(self, *, is_active: bool | None = None) -> list[Banner]:
        conditions = [] if is_active is None else [Banner.IsActive.is_(is_active)]
        return self.get_all(*conditions, order_by=(Banner.DisplayOrder, Banner.BannerId))

    def list_displayable(self, at: datetime) -> list[Banner]:
        """Banner đang hiển thị tại ``at``: IsActive và at nằm trong [StartDate, EndDate] (mốc NULL = không giới hạn)."""
        return self.get_all(
            Banner.IsActive.is_(True),
            or_(Banner.StartDate.is_(None), Banner.StartDate <= at),
            or_(Banner.EndDate.is_(None), Banner.EndDate >= at),
            order_by=(Banner.DisplayOrder, Banner.BannerId),
        )
