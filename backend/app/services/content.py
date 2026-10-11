"""Content service (đợt 5.5): tin tức (NewsArticles) và banner quảng cáo (Banners).

Nguồn nghiệp vụ: docs/business-requirements.md mục 2 (Admin quản lý quảng cáo/nội dung) và mục 15 (quản lý theo các
trường/trạng thái hiện có; chỉ hiển thị nội dung đang hoạt động/được xuất bản; không thêm trạng thái hay trường lịch
xuất bản), docs/database-schema.md 3.35–3.36.

Tin tức (Status: Draft = nháp, Published = đã đăng, Hidden = đã ẩn):
- Chỉ Admin tạo/sửa/đổi trạng thái và xem bài chưa đăng. Bài mới luôn Draft; client không gửi Status/PublishedAt.
- Đăng: Draft/Hidden → Published; PublishedAt = thời điểm đăng lần đầu (đăng lại sau khi ẩn giữ nguyên PublishedAt).
- Ẩn: Published → Hidden. Chưa có căn cứ cho: đưa bài về Draft, xóa bài, hẹn giờ đăng → chưa triển khai.
- Công khai (không cần đăng nhập): chỉ bài Published, xem theo Slug.
Banner:
- Chỉ Admin tạo/sửa/kích hoạt/ngừng và xem toàn bộ. Banner mới theo mặc định database (IsActive = true).
- Công khai: IsActive và thời điểm hiện tại nằm trong [StartDate, EndDate] (mốc để trống = không giới hạn; cùng quy
  ước với khuyến mãi), sắp theo DisplayOrder. Chưa có căn cứ cho xóa banner → chưa triển khai (ngừng bằng IsActive).
Kiểm tra dữ liệu (kỹ thuật): Title/Slug/Content không rỗng; Slug không chứa khoảng trắng, không trùng (UNIQUE);
ảnh (ImageUrl, ThumbnailUrl) phải là URL https; LinkUrl là URL https hoặc đường dẫn nội bộ bắt đầu bằng "/";
StartDate/EndDate có múi giờ, EndDate >= StartDate (kể cả khi chỉ sửa một mốc).
"""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import Banner, NewsArticle
from app.models.content import NEWS_ARTICLE_STATUSES
from app.repositories import BannerRepository, NewsArticleRepository
from app.schemas import (
    AdminBannerResponse,
    AdminNewsArticleResponse,
    AdminNewsArticleSummary,
    BannerCreate,
    BannerResponse,
    BannerUpdate,
    NewsArticleCreate,
    NewsArticleResponse,
    NewsArticleSummary,
    NewsArticleUpdate,
    PageResponse,
)

from .actor import ADMIN_ONLY, Actor, require_role
from .base import BaseService, utc_now
from .exceptions import BusinessRuleError, ConflictError, NotFoundError

ARTICLE_DRAFT = "Draft"
ARTICLE_PUBLISHED = "Published"
ARTICLE_HIDDEN = "Hidden"
PUBLISHABLE_STATUSES = (ARTICLE_DRAFT, ARTICLE_HIDDEN)
URL_MAX_LENGTH = 500

ARTICLE_FIELDS = frozenset({"Title", "Slug", "Summary", "Content", "ThumbnailUrl"})
BANNER_FIELDS = frozenset({"Title", "ImageUrl", "LinkUrl", "DisplayOrder", "StartDate", "EndDate"})


class ContentService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.articles = NewsArticleRepository(session)
        self.banners = BannerRepository(session)

    # ================================================================== Tin tức: công khai

    def list_published_articles(self, *, page: int = 1, page_size: int = 20) -> PageResponse[NewsArticleSummary]:
        """Danh sách bài đã đăng (không cần đăng nhập), mới đăng trước."""
        offset, limit = self._page_args(page, page_size)
        items = self.articles.list_articles(status=ARTICLE_PUBLISHED, offset=offset, limit=limit)
        return PageResponse[NewsArticleSummary](
            Items=[NewsArticleSummary.model_validate(a) for a in items],
            Total=self.articles.count_articles(status=ARTICLE_PUBLISHED),
            Page=page,
            PageSize=page_size,
        )

    def get_published_article(self, slug: str) -> NewsArticleResponse:
        """Bài đã đăng theo Slug; bài nháp/đã ẩn coi như không tồn tại."""
        article = self.articles.get_by_slug(slug) if isinstance(slug, str) else None
        if article is None or article.Status != ARTICLE_PUBLISHED:
            raise NotFoundError("Không tìm thấy bài viết", code="news_article_not_found")
        return NewsArticleResponse.model_validate(article)

    # ================================================================== Tin tức: Admin

    def admin_list_articles(
        self, actor: Actor, *, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> PageResponse[AdminNewsArticleSummary]:
        require_role(actor, *ADMIN_ONLY)
        if status is not None and status not in NEWS_ARTICLE_STATUSES:
            raise BusinessRuleError("Trạng thái bài viết không hợp lệ", code="invalid_article_status")
        offset, limit = self._page_args(page, page_size)
        items = self.articles.list_articles(status=status, offset=offset, limit=limit)
        return PageResponse[AdminNewsArticleSummary](
            Items=[AdminNewsArticleSummary.model_validate(a) for a in items],
            Total=self.articles.count_articles(status=status),
            Page=page,
            PageSize=page_size,
        )

    def admin_get_article(self, actor: Actor, article_id: uuid.UUID) -> AdminNewsArticleResponse:
        require_role(actor, *ADMIN_ONLY)
        return AdminNewsArticleResponse.model_validate(self._get_article(article_id))

    def create_article(self, actor: Actor, data: NewsArticleCreate) -> AdminNewsArticleResponse:
        """Admin tạo bài viết ở trạng thái Draft."""
        require_role(actor, *ADMIN_ONLY)
        values = self._article_values(_allowed(data, ARTICLE_FIELDS, code="article_field_not_allowed"), creating=True)
        with self.transaction():
            self._ensure_slug_unique(values["Slug"])
            article = self.articles.create(
                {**values, "CreatedByUserId": actor.user_id, "Status": ARTICLE_DRAFT, "PublishedAt": None,
                 "CreatedAt": self.now()}
            )
            self.articles.flush()
            return AdminNewsArticleResponse.model_validate(article)

    def update_article(self, actor: Actor, article_id: uuid.UUID, data: NewsArticleUpdate) -> AdminNewsArticleResponse:
        """Admin sửa nội dung bài viết (mọi trạng thái); không đổi Status/PublishedAt."""
        require_role(actor, *ADMIN_ONLY)
        values = self._article_values(_allowed(data, ARTICLE_FIELDS, code="article_field_not_allowed"), creating=False)
        if not values:
            raise BusinessRuleError("Không có nội dung cần sửa", code="nothing_to_update")
        with self.transaction():
            article = self._lock_article(article_id)
            if "Slug" in values and values["Slug"] != article.Slug:
                self._ensure_slug_unique(values["Slug"], exclude_id=article_id)
            self.articles.update(article, values)
            self.articles.flush()
            return AdminNewsArticleResponse.model_validate(article)

    def publish_article(self, actor: Actor, article_id: uuid.UUID) -> AdminNewsArticleResponse:
        """Đăng bài: Draft/Hidden → Published. PublishedAt = thời điểm đăng lần đầu (đăng lại giữ nguyên)."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            article = self._lock_article(article_id)
            if article.Status not in PUBLISHABLE_STATUSES:
                raise BusinessRuleError("Bài viết đã được đăng", code="invalid_article_transition")
            article.Status = ARTICLE_PUBLISHED
            if article.PublishedAt is None:
                article.PublishedAt = self.now()
            self.articles.flush()
            return AdminNewsArticleResponse.model_validate(article)

    def hide_article(self, actor: Actor, article_id: uuid.UUID) -> AdminNewsArticleResponse:
        """Ẩn bài đang đăng: Published → Hidden (không xóa, giữ PublishedAt)."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            article = self._lock_article(article_id)
            if article.Status != ARTICLE_PUBLISHED:
                raise BusinessRuleError("Chỉ ẩn được bài đang đăng", code="invalid_article_transition")
            article.Status = ARTICLE_HIDDEN
            self.articles.flush()
            return AdminNewsArticleResponse.model_validate(article)

    # ================================================================== Banner: công khai

    def list_display_banners(self) -> list[BannerResponse]:
        """Banner đang hiển thị (không cần đăng nhập): IsActive và trong khung [StartDate, EndDate]."""
        return [BannerResponse.model_validate(b) for b in self.banners.list_displayable(self.now())]

    # ================================================================== Banner: Admin

    def admin_list_banners(self, actor: Actor, *, is_active: bool | None = None) -> list[AdminBannerResponse]:
        require_role(actor, *ADMIN_ONLY)
        return [AdminBannerResponse.model_validate(b) for b in self.banners.list_banners(is_active=is_active)]

    def admin_get_banner(self, actor: Actor, banner_id: uuid.UUID) -> AdminBannerResponse:
        require_role(actor, *ADMIN_ONLY)
        return AdminBannerResponse.model_validate(self._get_banner(banner_id))

    def create_banner(self, actor: Actor, data: BannerCreate) -> AdminBannerResponse:
        """Admin tạo banner; IsActive theo mặc định của database (true)."""
        require_role(actor, *ADMIN_ONLY)
        values = self._banner_values(_allowed(data, BANNER_FIELDS, code="banner_field_not_allowed"), creating=True)
        _check_period(values.get("StartDate"), values.get("EndDate"))
        with self.transaction():
            banner = self.banners.create({**values, "CreatedByUserId": actor.user_id, "CreatedAt": self.now()})
            self.banners.flush()
            return AdminBannerResponse.model_validate(banner)

    def update_banner(self, actor: Actor, banner_id: uuid.UUID, data: BannerUpdate) -> AdminBannerResponse:
        """Admin sửa banner (PATCH); khung thời gian kiểm tra với giá trị đang lưu; không đổi IsActive."""
        require_role(actor, *ADMIN_ONLY)
        values = self._banner_values(_allowed(data, BANNER_FIELDS, code="banner_field_not_allowed"), creating=False)
        if not values:
            raise BusinessRuleError("Không có nội dung cần sửa", code="nothing_to_update")
        with self.transaction():
            banner = self._lock_banner(banner_id)
            _check_period(values.get("StartDate", banner.StartDate), values.get("EndDate", banner.EndDate))
            self.banners.update(banner, values)
            self.banners.flush()
            return AdminBannerResponse.model_validate(banner)

    def activate_banner(self, actor: Actor, banner_id: uuid.UUID) -> AdminBannerResponse:
        return self._set_banner_active(actor, banner_id, True)

    def deactivate_banner(self, actor: Actor, banner_id: uuid.UUID) -> AdminBannerResponse:
        return self._set_banner_active(actor, banner_id, False)

    # ================================================================== helpers

    def _set_banner_active(self, actor: Actor, banner_id: uuid.UUID, active: bool) -> AdminBannerResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            banner = self._lock_banner(banner_id)
            if banner.IsActive == active:
                raise BusinessRuleError("Banner đã ở trạng thái này", code="banner_status_unchanged")
            banner.IsActive = active
            self.banners.flush()
            return AdminBannerResponse.model_validate(banner)

    def _get_article(self, article_id: uuid.UUID) -> NewsArticle:
        article = self.articles.get_by_id(article_id)
        if article is None:
            raise NotFoundError("Không tìm thấy bài viết", code="news_article_not_found")
        return article

    def _lock_article(self, article_id: uuid.UUID) -> NewsArticle:
        article = self.articles.get_by_id_for_update(article_id)
        if article is None:
            raise NotFoundError("Không tìm thấy bài viết", code="news_article_not_found")
        return article

    def _get_banner(self, banner_id: uuid.UUID) -> Banner:
        banner = self.banners.get_by_id(banner_id)
        if banner is None:
            raise NotFoundError("Không tìm thấy banner", code="banner_not_found")
        return banner

    def _lock_banner(self, banner_id: uuid.UUID) -> Banner:
        banner = self.banners.get_by_id_for_update(banner_id)
        if banner is None:
            raise NotFoundError("Không tìm thấy banner", code="banner_not_found")
        return banner

    def _ensure_slug_unique(self, slug: str, exclude_id: uuid.UUID | None = None) -> None:
        if self.articles.exists_by_slug(slug, exclude_id):
            raise ConflictError("Slug bài viết đã tồn tại", code="news_article_slug_exists")

    @staticmethod
    def _article_values(values: dict[str, Any], *, creating: bool) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for field, code, message in (("Title", "article_title_required", "Cần tiêu đề bài viết"),
                                     ("Content", "article_content_required", "Cần nội dung bài viết")):
            if creating or field in values:
                cleaned[field] = _required_text(values.get(field), code=code, message=message)
        if creating or "Slug" in values:
            cleaned["Slug"] = _slug(values.get("Slug"))
        if "Summary" in values:
            cleaned["Summary"] = _optional_text(values["Summary"])
        if "ThumbnailUrl" in values:
            cleaned["ThumbnailUrl"] = (_https_url(values["ThumbnailUrl"], code="invalid_thumbnail_url")
                                       if values["ThumbnailUrl"] is not None else None)
        return cleaned

    @staticmethod
    def _banner_values(values: dict[str, Any], *, creating: bool) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        if creating or "Title" in values:
            cleaned["Title"] = _required_text(values.get("Title"), code="banner_title_required",
                                              message="Cần tiêu đề banner")
        if creating or "ImageUrl" in values:
            cleaned["ImageUrl"] = _https_url(values.get("ImageUrl"), code="invalid_banner_image_url")
        if "LinkUrl" in values:
            cleaned["LinkUrl"] = _link_url(values["LinkUrl"]) if values["LinkUrl"] is not None else None
        if "DisplayOrder" in values:
            order = values["DisplayOrder"]
            if isinstance(order, bool) or not isinstance(order, int):
                raise BusinessRuleError("Thứ tự hiển thị phải là số nguyên", code="invalid_display_order")
            cleaned["DisplayOrder"] = order
        for field in ("StartDate", "EndDate"):
            if field in values:
                cleaned[field] = values[field]
        return cleaned


def _allowed(data: Any, allowed: frozenset[str], *, code: str) -> dict[str, Any]:
    """Chỉ nhận các trường cho phép (schema đã chặn; chặn lại nếu schema bị bỏ qua)."""
    values = dict(data.model_dump(exclude_unset=True))
    not_allowed = sorted(set(values) - allowed)
    if not_allowed:
        raise BusinessRuleError(f"Không được gửi các trường: {not_allowed}", code=code)
    return values


def _required_text(value: Any, *, code: str, message: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise BusinessRuleError(message, code=code)
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BusinessRuleError("Tóm tắt phải là chuỗi ký tự", code="invalid_summary")
    return value.strip() or None


def _slug(value: Any) -> str:
    slug = value.strip() if isinstance(value, str) else ""
    if not slug or len(slug) > 300 or any(ch.isspace() for ch in slug):
        raise BusinessRuleError("Slug không được rỗng, tối đa 300 ký tự và không chứa khoảng trắng", code="invalid_slug")
    return slug


def _https_url(value: Any, *, code: str) -> str:
    url = value.strip() if isinstance(value, str) else ""
    parsed = urlparse(url)
    if (not url or len(url) > URL_MAX_LENGTH or any(ch.isspace() for ch in url)
            or parsed.scheme != "https" or not parsed.netloc):
        raise BusinessRuleError("Địa chỉ ảnh phải là URL https hợp lệ", code=code)
    return url


def _link_url(value: Any) -> str:
    """URL https hoặc đường dẫn nội bộ ("/san-pham/..."); chặn javascript:, data:, http: và "//host"."""
    url = value.strip() if isinstance(value, str) else ""
    if url.startswith("/") and not url.startswith("//"):
        if len(url) > URL_MAX_LENGTH or any(ch.isspace() for ch in url):
            raise BusinessRuleError("Đường dẫn banner không hợp lệ", code="invalid_banner_link_url")
        return url
    return _https_url(url, code="invalid_banner_link_url")


def _check_period(start: datetime | None, end: datetime | None) -> None:
    for moment in (start, end):
        if moment is not None and (not isinstance(moment, datetime) or moment.tzinfo is None):
            raise BusinessRuleError("Thời điểm hiển thị phải có múi giờ", code="invalid_banner_period")
    if start is not None and end is not None and end < start:
        raise BusinessRuleError("Thời điểm kết thúc phải sau hoặc bằng thời điểm bắt đầu", code="invalid_banner_period")
