"""Schemas cho NewsArticles, Banners."""

import uuid
from datetime import datetime

from pydantic import model_validator

from .common import NewsArticleStatus, RequestSchema, ResponseSchema, check_end_after_start, varchar

# ---------------------------------------------------------------------------
# NewsArticles
# ---------------------------------------------------------------------------


class NewsArticleCreate(RequestSchema):
    """CreatedByUserId lấy từ người dùng đăng nhập; PublishedAt do server gán khi đăng."""

    NULLABLE_FIELDS = frozenset({"Summary", "ThumbnailUrl"})

    Title: varchar(255)
    Slug: varchar(300)
    Summary: str | None = None
    Content: str
    ThumbnailUrl: varchar(500) | None = None
    Status: NewsArticleStatus


class NewsArticleUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Summary", "ThumbnailUrl"})

    Title: varchar(255) | None = None
    Slug: varchar(300) | None = None
    Summary: str | None = None
    Content: str | None = None
    ThumbnailUrl: varchar(500) | None = None
    Status: NewsArticleStatus | None = None


class NewsArticleSummary(ResponseSchema):
    """Dùng cho danh sách tin tức (không có Content)."""

    NewsArticleId: uuid.UUID
    Title: str
    Slug: str
    Summary: str | None
    ThumbnailUrl: str | None
    Status: NewsArticleStatus
    PublishedAt: datetime | None


class NewsArticleResponse(NewsArticleSummary):
    Content: str
    CreatedAt: datetime


class AdminNewsArticleResponse(NewsArticleResponse):
    CreatedByUserId: uuid.UUID


# ---------------------------------------------------------------------------
# Banners
# ---------------------------------------------------------------------------


class BannerCreate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"LinkUrl", "StartDate", "EndDate"})

    Title: varchar(255)
    ImageUrl: varchar(500)
    LinkUrl: varchar(500) | None = None
    DisplayOrder: int | None = None
    StartDate: datetime | None = None
    EndDate: datetime | None = None
    IsActive: bool | None = None

    @model_validator(mode="after")
    def _check_dates(self):
        check_end_after_start(self.StartDate, self.EndDate)
        return self


class BannerUpdate(BannerCreate):
    """PATCH. Kiểm tra chéo khi gửi cả hai mốc; service kiểm tra lại với giá trị đang lưu."""

    Title: varchar(255) | None = None
    ImageUrl: varchar(500) | None = None


class BannerResponse(ResponseSchema):
    BannerId: uuid.UUID
    Title: str
    ImageUrl: str
    LinkUrl: str | None
    DisplayOrder: int
    StartDate: datetime | None
    EndDate: datetime | None
    IsActive: bool


class AdminBannerResponse(BannerResponse):
    CreatedByUserId: uuid.UUID
    CreatedAt: datetime
