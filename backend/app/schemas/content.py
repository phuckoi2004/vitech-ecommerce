"""Schemas cho NewsArticles, Banners.

Đợt 5.5 (ContentService): client không gửi trường trạng thái/quản trị.
- NewsArticles.Status đổi qua nghiệp vụ đăng/ẩn (publish_article/hide_article); bài mới luôn là Draft;
  PublishedAt do server gán khi đăng lần đầu.
- Banners.IsActive đổi qua activate_banner/deactivate_banner; banner mới theo mặc định của database (IsActive = true).
- CreatedByUserId lấy từ Admin đăng nhập.
"""

import uuid
from datetime import datetime

from pydantic import model_validator

from .common import NewsArticleStatus, RequestSchema, ResponseSchema, check_end_after_start, varchar

# ---------------------------------------------------------------------------
# NewsArticles
# ---------------------------------------------------------------------------


class NewsArticleCreate(RequestSchema):
    """Admin tạo bài viết (luôn ở trạng thái Draft). CreatedByUserId lấy từ người dùng đăng nhập."""

    NULLABLE_FIELDS = frozenset({"Summary", "ThumbnailUrl"})

    Title: varchar(255)
    Slug: varchar(300)
    Summary: str | None = None
    Content: str
    ThumbnailUrl: varchar(500) | None = None


class NewsArticleUpdate(RequestSchema):
    """Admin sửa nội dung bài viết (PATCH). Không đổi Status/PublishedAt (dùng nghiệp vụ đăng/ẩn)."""

    NULLABLE_FIELDS = frozenset({"Summary", "ThumbnailUrl"})

    Title: varchar(255) | None = None
    Slug: varchar(300) | None = None
    Summary: str | None = None
    Content: str | None = None
    ThumbnailUrl: varchar(500) | None = None


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


class AdminNewsArticleSummary(NewsArticleSummary):
    CreatedByUserId: uuid.UUID
    CreatedAt: datetime


class AdminNewsArticleResponse(NewsArticleResponse):
    CreatedByUserId: uuid.UUID


# ---------------------------------------------------------------------------
# Banners
# ---------------------------------------------------------------------------


class BannerCreate(RequestSchema):
    """Admin tạo banner. IsActive không nhận từ client (mặc định database: true; đổi qua kích hoạt/ngừng)."""

    NULLABLE_FIELDS = frozenset({"LinkUrl", "StartDate", "EndDate"})

    Title: varchar(255)
    ImageUrl: varchar(500)
    LinkUrl: varchar(500) | None = None
    DisplayOrder: int | None = None
    StartDate: datetime | None = None
    EndDate: datetime | None = None

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
