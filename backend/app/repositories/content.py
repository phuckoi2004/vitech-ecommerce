"""Repositories cho NewsArticles, Banners."""

import uuid

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
