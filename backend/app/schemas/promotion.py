"""Schemas cho Promotions, PromotionProducts, PromotionCategories, Coupons.

Promotion là nơi duy nhất quản lý thông tin giảm giá (DiscountType, DiscountValue, MinOrderValue,
MaxDiscountAmount, StartDate, EndDate). Coupon chỉ lưu mã và tham chiếu Promotion.
"""

import uuid
from datetime import datetime

from pydantic import Field, model_validator

from .common import (
    DiscountTypeValue,
    Money,
    NonNegativeInt,
    PromotionStatus,
    RequestSchema,
    ResponseSchema,
    check_end_after_start,
    relation_field,
    varchar,
)


def _check_percentage(discount_type: str | None, discount_value) -> None:
    """CHECK "DiscountType" <> 'Percentage' OR "DiscountValue" <= 100."""
    if discount_type == "Percentage" and discount_value is not None and discount_value > 100:
        raise ValueError("DiscountValue không được lớn hơn 100 khi DiscountType là Percentage")


# ---------------------------------------------------------------------------
# Promotions
# ---------------------------------------------------------------------------


class PromotionCreate(RequestSchema):
    """CreatedByUserId lấy từ người dùng đăng nhập.

    ProductIds/CategoryIds tạo các dòng PromotionProducts/PromotionCategories.
    """

    NULLABLE_FIELDS = frozenset({"Description", "MaxDiscountAmount"})

    Name: varchar(255)
    Description: str | None = None
    DiscountType: DiscountTypeValue
    DiscountValue: Money
    MinOrderValue: Money
    MaxDiscountAmount: Money | None = None
    StartDate: datetime
    EndDate: datetime
    Status: PromotionStatus
    ProductIds: list[uuid.UUID] = Field(default_factory=list)
    CategoryIds: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_constraints(self):
        _check_percentage(self.DiscountType, self.DiscountValue)
        check_end_after_start(self.StartDate, self.EndDate)
        return self


class PromotionUpdate(RequestSchema):
    """PATCH. Chỉ kiểm tra chéo khi cả hai field cùng được gửi;
    service phải kiểm tra lại với giá trị đang lưu trong database."""

    NULLABLE_FIELDS = frozenset({"Description", "MaxDiscountAmount"})

    Name: varchar(255) | None = None
    Description: str | None = None
    DiscountType: DiscountTypeValue | None = None
    DiscountValue: Money | None = None
    MinOrderValue: Money | None = None
    MaxDiscountAmount: Money | None = None
    StartDate: datetime | None = None
    EndDate: datetime | None = None
    Status: PromotionStatus | None = None

    @model_validator(mode="after")
    def _check_constraints(self):
        _check_percentage(self.DiscountType, self.DiscountValue)
        check_end_after_start(self.StartDate, self.EndDate)
        return self


class PromotionTargetsUpdate(RequestSchema):
    """Thay toàn bộ danh sách sản phẩm/danh mục áp dụng (PromotionProducts/PromotionCategories)."""

    ProductIds: list[uuid.UUID] | None = None
    CategoryIds: list[uuid.UUID] | None = None


class PromotionProductResponse(ResponseSchema):
    ProductId: uuid.UUID


class PromotionCategoryResponse(ResponseSchema):
    CategoryId: uuid.UUID


class PromotionResponse(ResponseSchema):
    PromotionId: uuid.UUID
    Name: str
    Description: str | None
    DiscountType: DiscountTypeValue
    DiscountValue: Money
    MinOrderValue: Money
    MaxDiscountAmount: Money | None
    StartDate: datetime
    EndDate: datetime
    Status: PromotionStatus


class AdminPromotionResponse(PromotionResponse):
    CreatedByUserId: uuid.UUID
    CreatedAt: datetime


class AdminPromotionDetailResponse(AdminPromotionResponse):
    Products: list[PromotionProductResponse] = relation_field("promotion_products")
    Categories: list[PromotionCategoryResponse] = relation_field("promotion_categories")


# ---------------------------------------------------------------------------
# Coupons
# ---------------------------------------------------------------------------


class CouponCreate(RequestSchema):
    """CreatedByUserId lấy từ người dùng đăng nhập; UsedCount do hệ thống tăng."""

    NULLABLE_FIELDS = frozenset({"UsageLimit"})

    PromotionId: uuid.UUID
    Code: varchar(50)
    Name: varchar(255)
    UsageLimit: NonNegativeInt | None = None
    IsActive: bool | None = None


class CouponUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"UsageLimit"})

    PromotionId: uuid.UUID | None = None
    Code: varchar(50) | None = None
    Name: varchar(255) | None = None
    UsageLimit: NonNegativeInt | None = None
    IsActive: bool | None = None


class CouponResponse(ResponseSchema):
    """Thông tin coupon kèm điều kiện giảm giá của Promotion."""

    CouponId: uuid.UUID
    Code: str
    Name: str
    IsActive: bool
    Promotion: PromotionResponse = relation_field("promotion")


class AdminCouponResponse(ResponseSchema):
    CouponId: uuid.UUID
    PromotionId: uuid.UUID
    CreatedByUserId: uuid.UUID
    Code: str
    Name: str
    UsageLimit: NonNegativeInt | None
    UsedCount: NonNegativeInt
    IsActive: bool
    CreatedAt: datetime
