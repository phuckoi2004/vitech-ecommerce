"""Promotion and coupon APIs: Admin management, plus the customer's coupon preview on the cart."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.schemas import (
    AdminCouponResponse,
    AdminPromotionDetailResponse,
    AdminPromotionResponse,
    CouponCreate,
    CouponPreviewResponse,
    CouponUpdate,
    PageResponse,
    PromotionCreate,
    PromotionTargetsUpdate,
    PromotionUpdate,
)
from app.services.promotion import CouponService, PromotionService

from .dependencies import CurrentActor, InternalOnly, Page, PageSize, get_coupon_service, get_promotion_service

router = APIRouter(tags=["Khuyến mãi"])
admin_router = APIRouter(prefix="/admin", tags=["Quản lý khuyến mãi"], dependencies=[InternalOnly])

Promotions = Annotated[PromotionService, Depends(get_promotion_service)]
Coupons = Annotated[CouponService, Depends(get_coupon_service)]


@router.get("/cart/coupon-preview", response_model=CouponPreviewResponse)
def preview_cart_coupon(code: Annotated[str, Query(min_length=1, max_length=50)], service: Coupons,
                        actor: CurrentActor):
    """Checks a coupon against the selected cart lines; nothing is reserved until the order is placed."""
    return service.preview_cart_coupon(actor, code)


# ------------------------------------------------------------------ promotions (Admin)


@admin_router.get("/promotions", response_model=PageResponse[AdminPromotionResponse])
def list_promotions(service: Promotions, actor: CurrentActor,
                    status_filter: Annotated[str | None, Query(alias="status")] = None,
                    page: Page = 1, page_size: PageSize = 20):
    return service.list_promotions(actor, status=status_filter, page=page, page_size=page_size)


@admin_router.get("/promotions/{promotion_id}", response_model=AdminPromotionDetailResponse)
def get_promotion(promotion_id: uuid.UUID, service: Promotions, actor: CurrentActor):
    return service.get_promotion(actor, promotion_id)


@admin_router.post("/promotions", response_model=AdminPromotionDetailResponse, status_code=status.HTTP_201_CREATED)
def create_promotion(data: PromotionCreate, service: Promotions, actor: CurrentActor):
    return service.create_promotion(actor, data)


@admin_router.patch("/promotions/{promotion_id}", response_model=AdminPromotionDetailResponse)
def update_promotion(promotion_id: uuid.UUID, data: PromotionUpdate, service: Promotions, actor: CurrentActor):
    return service.update_promotion(actor, promotion_id, data)


@admin_router.put("/promotions/{promotion_id}/targets", response_model=AdminPromotionDetailResponse)
def update_promotion_targets(promotion_id: uuid.UUID, data: PromotionTargetsUpdate, service: Promotions,
                             actor: CurrentActor):
    return service.update_targets(actor, promotion_id, data)


@admin_router.post("/promotions/{promotion_id}/cancel", response_model=AdminPromotionDetailResponse)
def cancel_promotion(promotion_id: uuid.UUID, service: Promotions, actor: CurrentActor):
    return service.cancel_promotion(actor, promotion_id)


@admin_router.delete("/promotions/{promotion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promotion(promotion_id: uuid.UUID, service: Promotions, actor: CurrentActor):
    service.delete_promotion(actor, promotion_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ coupons (Admin)


@admin_router.get("/promotions/{promotion_id}/coupons", response_model=list[AdminCouponResponse])
def list_coupons(promotion_id: uuid.UUID, service: Coupons, actor: CurrentActor, is_active: bool | None = None):
    return service.list_coupons(actor, promotion_id, is_active=is_active)


@admin_router.get("/coupons/{coupon_id}", response_model=AdminCouponResponse)
def get_coupon(coupon_id: uuid.UUID, service: Coupons, actor: CurrentActor):
    return service.get_coupon(actor, coupon_id)


@admin_router.post("/coupons", response_model=AdminCouponResponse, status_code=status.HTTP_201_CREATED)
def create_coupon(data: CouponCreate, service: Coupons, actor: CurrentActor):
    return service.create_coupon(actor, data)


@admin_router.patch("/coupons/{coupon_id}", response_model=AdminCouponResponse)
def update_coupon(coupon_id: uuid.UUID, data: CouponUpdate, service: Coupons, actor: CurrentActor):
    return service.update_coupon(actor, coupon_id, data)


@admin_router.delete("/coupons/{coupon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coupon(coupon_id: uuid.UUID, service: Coupons, actor: CurrentActor):
    service.delete_coupon(actor, coupon_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
