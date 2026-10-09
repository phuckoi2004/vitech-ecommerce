"""Schemas cho Reviews, ReviewImages.

Mỗi OrderItem có tối đa một Review (OrderItemId UNIQUE). Không có IsVerifiedPurchase.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import Field

from .common import RequestSchema, ResponseSchema, relation_field, varchar
from .user import UserSummary

# CHECK "Rating" BETWEEN 1 AND 5
RatingValue = Annotated[int, Field(ge=1, le=5)]


class ReviewImageCreate(RequestSchema):
    ImageUrl: varchar(500)
    DisplayOrder: int | None = None


class ReviewImageResponse(ResponseSchema):
    ReviewImageId: uuid.UUID
    ImageUrl: str
    DisplayOrder: int


class ReviewCreate(RequestSchema):
    """Khách hàng đánh giá một dòng đơn hàng.

    UserId lấy từ người dùng đăng nhập; ProductId do server lấy từ OrderItem
    (OrderItems → ProductVariants → Products) để tránh lệch dữ liệu.
    """

    OrderItemId: uuid.UUID
    Rating: RatingValue
    Content: str
    Images: list[ReviewImageCreate] = Field(default_factory=list)


class ReviewUpdate(RequestSchema):
    Rating: RatingValue | None = None
    Content: str | None = None


class ReviewDeleteRequest(RequestSchema):
    """Staff/admin xóa mềm (kiểm duyệt) bình luận."""

    NULLABLE_FIELDS = frozenset({"DeleteReason"})

    DeleteReason: str | None = None


class ReviewResponse(ResponseSchema):
    """Hiển thị công khai trên trang sản phẩm."""

    ReviewId: uuid.UUID
    ProductId: uuid.UUID
    Rating: RatingValue
    Content: str
    CreatedAt: datetime
    UpdatedAt: datetime
    User: UserSummary = relation_field("user")
    Images: list[ReviewImageResponse] = relation_field("images")


class AdminReviewResponse(ReviewResponse):
    UserId: uuid.UUID
    OrderItemId: uuid.UUID
    IsDeleted: bool
    DeleteReason: str | None
    DeletedByUserId: uuid.UUID | None
    DeletedAt: datetime | None
