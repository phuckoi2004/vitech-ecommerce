"""Review APIs: public product reviews, the customer's own reviews, and Admin moderation."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.schemas import (
    AdminReviewResponse,
    PageResponse,
    ReviewCreate,
    ReviewDeleteRequest,
    ReviewResponse,
    ReviewUpdate,
)
from app.services.review import ReviewService

from .dependencies import CurrentActor, InternalOnly, Page, PageSize, get_review_service

router = APIRouter(tags=["Đánh giá"])
admin_router = APIRouter(prefix="/admin", tags=["Quản lý đánh giá"], dependencies=[InternalOnly])

Reviews = Annotated[ReviewService, Depends(get_review_service)]


@router.get("/products/{product_id}/reviews", response_model=PageResponse[ReviewResponse])
def list_product_reviews(product_id: uuid.UUID, service: Reviews,
                         rating: Annotated[int | None, Query(ge=1, le=5)] = None,
                         page: Page = 1, page_size: PageSize = 20):
    return service.list_product_reviews(product_id, rating=rating, page=page, page_size=page_size)


@router.get("/reviews/mine", response_model=PageResponse[ReviewResponse])
def list_my_reviews(service: Reviews, actor: CurrentActor, page: Page = 1, page_size: PageSize = 20):
    return service.list_my_reviews(actor, page=page, page_size=page_size)


@router.post("/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def create_review(data: ReviewCreate, service: Reviews, actor: CurrentActor):
    return service.create_review(actor, data)


@router.patch("/reviews/{review_id}", response_model=ReviewResponse)
def update_review(review_id: uuid.UUID, data: ReviewUpdate, service: Reviews, actor: CurrentActor):
    return service.update_review(actor, review_id, data)


@admin_router.get("/products/{product_id}/reviews", response_model=PageResponse[AdminReviewResponse])
def admin_list_product_reviews(product_id: uuid.UUID, service: Reviews, actor: CurrentActor,
                               include_deleted: bool = True, page: Page = 1, page_size: PageSize = 20):
    return service.admin_list_product_reviews(actor, product_id, include_deleted=include_deleted,
                                              page=page, page_size=page_size)


@admin_router.get("/reviews/{review_id}", response_model=AdminReviewResponse)
def admin_get_review(review_id: uuid.UUID, service: Reviews, actor: CurrentActor):
    return service.admin_get_review(actor, review_id)


@admin_router.post("/reviews/{review_id}/hide", response_model=AdminReviewResponse)
def moderate_review(review_id: uuid.UUID, data: ReviewDeleteRequest, service: Reviews, actor: CurrentActor):
    """Soft-deletes (hides) a review with an optional reason; product rating is recalculated."""
    return service.moderate_review(actor, review_id, data)
