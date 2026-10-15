"""Content APIs: published news and displayable banners (public), content management (Admin)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

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
from app.services.content import ContentService

from .dependencies import CurrentActor, InternalOnly, Page, PageSize, get_content_service

router = APIRouter(tags=["Nội dung"])
admin_router = APIRouter(prefix="/admin", tags=["Quản lý nội dung"], dependencies=[InternalOnly])

Content = Annotated[ContentService, Depends(get_content_service)]


# ------------------------------------------------------------------ public


@router.get("/news", response_model=PageResponse[NewsArticleSummary])
def list_news(service: Content, page: Page = 1, page_size: PageSize = 20):
    return service.list_published_articles(page=page, page_size=page_size)


@router.get("/news/{slug}", response_model=NewsArticleResponse)
def get_news(slug: str, service: Content):
    return service.get_published_article(slug)


@router.get("/banners", response_model=list[BannerResponse])
def list_banners(service: Content):
    return service.list_display_banners()


# ------------------------------------------------------------------ news (Admin)


@admin_router.get("/news", response_model=PageResponse[AdminNewsArticleSummary])
def admin_list_news(service: Content, actor: CurrentActor,
                    status_filter: Annotated[str | None, Query(alias="status")] = None,
                    page: Page = 1, page_size: PageSize = 20):
    return service.admin_list_articles(actor, status=status_filter, page=page, page_size=page_size)


@admin_router.get("/news/{article_id}", response_model=AdminNewsArticleResponse)
def admin_get_news(article_id: uuid.UUID, service: Content, actor: CurrentActor):
    return service.admin_get_article(actor, article_id)


@admin_router.post("/news", response_model=AdminNewsArticleResponse, status_code=status.HTTP_201_CREATED)
def create_news(data: NewsArticleCreate, service: Content, actor: CurrentActor):
    return service.create_article(actor, data)


@admin_router.patch("/news/{article_id}", response_model=AdminNewsArticleResponse)
def update_news(article_id: uuid.UUID, data: NewsArticleUpdate, service: Content, actor: CurrentActor):
    return service.update_article(actor, article_id, data)


@admin_router.post("/news/{article_id}/publish", response_model=AdminNewsArticleResponse)
def publish_news(article_id: uuid.UUID, service: Content, actor: CurrentActor):
    return service.publish_article(actor, article_id)


@admin_router.post("/news/{article_id}/hide", response_model=AdminNewsArticleResponse)
def hide_news(article_id: uuid.UUID, service: Content, actor: CurrentActor):
    return service.hide_article(actor, article_id)


@admin_router.delete("/news/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_news(article_id: uuid.UUID, service: Content, actor: CurrentActor):
    service.delete_article(actor, article_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ banners (Admin)


@admin_router.get("/banners", response_model=list[AdminBannerResponse])
def admin_list_banners(service: Content, actor: CurrentActor, is_active: bool | None = None):
    return service.admin_list_banners(actor, is_active=is_active)


@admin_router.get("/banners/{banner_id}", response_model=AdminBannerResponse)
def admin_get_banner(banner_id: uuid.UUID, service: Content, actor: CurrentActor):
    return service.admin_get_banner(actor, banner_id)


@admin_router.post("/banners", response_model=AdminBannerResponse, status_code=status.HTTP_201_CREATED)
def create_banner(data: BannerCreate, service: Content, actor: CurrentActor):
    return service.create_banner(actor, data)


@admin_router.patch("/banners/{banner_id}", response_model=AdminBannerResponse)
def update_banner(banner_id: uuid.UUID, data: BannerUpdate, service: Content, actor: CurrentActor):
    return service.update_banner(actor, banner_id, data)


@admin_router.post("/banners/{banner_id}/activate", response_model=AdminBannerResponse)
def activate_banner(banner_id: uuid.UUID, service: Content, actor: CurrentActor):
    return service.activate_banner(actor, banner_id)


@admin_router.post("/banners/{banner_id}/deactivate", response_model=AdminBannerResponse)
def deactivate_banner(banner_id: uuid.UUID, service: Content, actor: CurrentActor):
    return service.deactivate_banner(actor, banner_id)


@admin_router.delete("/banners/{banner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_banner(banner_id: uuid.UUID, service: Content, actor: CurrentActor):
    service.delete_banner(actor, banner_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
