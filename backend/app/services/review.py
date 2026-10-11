"""Review service: khách hàng đánh giá dòng đơn đã giao, chỉnh sửa trong 7 ngày; Admin kiểm duyệt (ẩn/xóa mềm).

Nguồn nghiệp vụ: docs/business-requirements.md mục 11 và quyết định đợt 5.2:
- Chỉ Customer sở hữu đơn được đánh giá; đơn phải đang Delivered (trạng thái khác, kể cả Completed, bị từ chối).
- Mỗi OrderItem tối đa một review (UNIQUE OrderItemId ở database, tính cả review đã ẩn). UserId lấy từ Actor;
  ProductId suy ra từ OrderItem → ProductVariant (không nhận từ client).
- Chỉnh sửa: chủ sở hữu, trong 7 ngày tính từ CreatedAt — được sửa khi now < CreatedAt + 7 ngày (đúng tại hạn là
  hết hạn). Chỉ sửa Rating/Content; review đã ẩn không sửa được và không tự khôi phục.
- Khách hàng không xóa review. Chỉ Admin ẩn/xóa mềm (IsDeleted, DeleteReason, DeletedByUserId, DeletedAt); không
  xóa dòng; không có nghiệp vụ khôi phục.
- Products.ReviewCount/AverageRating luôn TÍNH LẠI từ các review đang hiển thị (COUNT/AVG ở database) sau mỗi thay
  đổi, trên dòng Product đã khóa (FOR UPDATE) — không cộng/trừ dồn, nên gọi lặp không trừ hai lần. Không còn review:
  ReviewCount = 0, AverageRating = 0.00 (default của cột). Làm tròn 2 chữ số ROUND_HALF_UP (numeric(3,2)).
- Thứ tự khóa: Product → Review. Hai yêu cầu đồng thời trên cùng sản phẩm chạy tuần tự; yêu cầu tạo trùng OrderItem
  bị chặn bởi kiểm tra sau khóa và UNIQUE (IntegrityError → ConflictError review_exists).
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import Product, Review
from app.repositories import (
    OrderItemRepository,
    OrderRepository,
    ProductRepository,
    ProductVariantRepository,
    ReviewImageRepository,
    ReviewRepository,
)
from app.schemas import (
    AdminReviewResponse,
    PageResponse,
    ReviewCreate,
    ReviewDeleteRequest,
    ReviewResponse,
    ReviewUpdate,
)

from .actor import ADMIN_ONLY, CUSTOMER_ONLY, Actor, require_role
from .base import BaseService, utc_now
from .exceptions import BusinessRuleError, ConflictError, NotFoundError
from .promotion import money

REVIEWABLE_ORDER_STATUS = "Delivered"
REVIEW_EDIT_WINDOW = timedelta(days=7)
CREATE_FIELDS = frozenset({"OrderItemId", "Rating", "Content", "Images"})
UPDATE_FIELDS = frozenset({"Rating", "Content"})
_NO_RATING = Decimal("0.00")


def review_edit_deadline(review: Review) -> datetime:
    """Hạn chỉnh sửa = CreatedAt + 7 ngày (CreatedAt là timestamptz); được sửa khi thời điểm hiện tại < hạn."""
    return review.CreatedAt + REVIEW_EDIT_WINDOW


class ReviewService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.reviews = ReviewRepository(session)
        self.images = ReviewImageRepository(session)
        self.order_items = OrderItemRepository(session)
        self.orders = OrderRepository(session)
        self.variants = ProductVariantRepository(session)
        self.products = ProductRepository(session)

    # ------------------------------------------------------------------ Customer

    def create_review(self, actor: Actor, data: ReviewCreate) -> ReviewResponse:
        """Customer đánh giá một dòng đơn của chính mình khi đơn đang Delivered (mỗi dòng đơn một review)."""
        require_role(actor, *CUSTOMER_ONLY)
        values = self._values(data, CREATE_FIELDS)
        rating = _check_rating(values.get("Rating"))
        content = _check_content(values.get("Content"))
        order_item_id = values.get("OrderItemId")
        with self.transaction():
            item = self.order_items.get_by_id_and_customer(order_item_id, actor.user_id) if order_item_id else None
            if item is None:  # không tồn tại hoặc thuộc đơn của khách khác: không tiết lộ
                raise NotFoundError("Không tìm thấy dòng đơn hàng", code="order_item_not_found")
            order = self.orders.get_by_id(item.OrderId)
            if order is None or order.OrderStatus != REVIEWABLE_ORDER_STATUS:
                raise BusinessRuleError(
                    "Chỉ đánh giá sản phẩm thuộc đơn hàng đã giao (Delivered)", code="review_order_not_delivered"
                )
            variant = self.variants.get_by_id(item.ProductVariantId)
            if variant is None:
                raise NotFoundError("Không tìm thấy sản phẩm của dòng đơn", code="product_not_found")
            product = self._lock_product(variant.ProductId)
            if self.reviews.exists_by_order_item(item.OrderItemId):
                raise ConflictError("Dòng đơn hàng đã được đánh giá", code="review_exists")
            review = self.reviews.create(
                {
                    "UserId": actor.user_id,
                    "ProductId": product.ProductId,
                    "OrderItemId": item.OrderItemId,
                    "Rating": rating,
                    "Content": content,
                    "IsDeleted": False,
                    "CreatedAt": self.now(),
                }
            )
            self.reviews.flush()
            for index, image in enumerate(values.get("Images") or []):
                display_order = image.DisplayOrder if image.DisplayOrder is not None else index
                self.images.create({"ReviewId": review.ReviewId, "ImageUrl": image.ImageUrl, "DisplayOrder": display_order})
            self._refresh_rating(product)
            return ReviewResponse.model_validate(self.reviews.get_detail(review.ReviewId))

    def update_review(self, actor: Actor, review_id: uuid.UUID, data: ReviewUpdate) -> ReviewResponse:
        """Chủ review sửa Rating/Content trong 7 ngày kể từ CreatedAt; review đã ẩn không sửa được."""
        require_role(actor, *CUSTOMER_ONLY)
        values = self._values(data, UPDATE_FIELDS)
        if not values:
            raise BusinessRuleError("Không có nội dung cần sửa", code="nothing_to_update")
        if "Rating" in values:
            values["Rating"] = _check_rating(values["Rating"])
        if "Content" in values:
            values["Content"] = _check_content(values["Content"])
        with self.transaction():
            review, product = self._lock_review(review_id)
            if review.UserId != actor.user_id:
                raise NotFoundError("Không tìm thấy đánh giá", code="review_not_found")
            if review.IsDeleted:
                raise BusinessRuleError("Đánh giá đã bị ẩn bởi kiểm duyệt, không thể sửa", code="review_hidden")
            if self.now() >= review_edit_deadline(review):
                raise BusinessRuleError(
                    "Đã quá thời hạn 7 ngày để chỉnh sửa đánh giá", code="review_edit_window_expired"
                )
            for field, value in values.items():
                setattr(review, field, value)
            self.reviews.flush()
            if "Rating" in values:
                self._refresh_rating(product)
            return ReviewResponse.model_validate(self.reviews.get_detail(review_id))

    def list_my_reviews(self, actor: Actor, *, page: int = 1, page_size: int = 20) -> PageResponse[ReviewResponse]:
        """Customer xem review của mình (review đã bị ẩn không hiển thị)."""
        require_role(actor, *CUSTOMER_ONLY)
        offset, limit = self._page_args(page, page_size)
        items = self.reviews.list_by_user(actor.user_id, offset=offset, limit=limit)
        return PageResponse[ReviewResponse](
            Items=[ReviewResponse.model_validate(r) for r in items],
            Total=self.reviews.count_by_user(actor.user_id),
            Page=page,
            PageSize=page_size,
        )

    # ------------------------------------------------------------------ Công khai

    def list_product_reviews(
        self, product_id: uuid.UUID, *, rating: int | None = None, page: int = 1, page_size: int = 20
    ) -> PageResponse[ReviewResponse]:
        """Review đang hiển thị của sản phẩm (không cần đăng nhập)."""
        if rating is not None:
            _check_rating(rating)
        offset, limit = self._page_args(page, page_size)
        items = self.reviews.list_by_product(product_id, rating=rating, offset=offset, limit=limit)
        return PageResponse[ReviewResponse](
            Items=[ReviewResponse.model_validate(r) for r in items],
            Total=self.reviews.count_by_product(product_id, rating=rating),
            Page=page,
            PageSize=page_size,
        )

    # ------------------------------------------------------------------ Admin

    def moderate_review(self, actor: Actor, review_id: uuid.UUID, data: ReviewDeleteRequest) -> AdminReviewResponse:
        """Admin ẩn/xóa mềm review (kiểm duyệt): ghi người thực hiện, thời điểm, lý do; loại khỏi chỉ số sản phẩm.

        Review đã ẩn thì từ chối (không ghi đè thông tin kiểm duyệt trước, không trừ chỉ số lần nữa).
        """
        require_role(actor, *ADMIN_ONLY)
        reason = (getattr(data, "DeleteReason", None) or "").strip() or None
        with self.transaction():
            review, product = self._lock_review(review_id)
            if review.IsDeleted:
                raise BusinessRuleError("Đánh giá đã được ẩn trước đó", code="review_already_hidden")
            review.IsDeleted = True
            review.DeleteReason = reason
            review.DeletedByUserId = actor.user_id
            review.DeletedAt = self.now()
            self.reviews.flush()
            self._refresh_rating(product)
            return AdminReviewResponse.model_validate(self.reviews.get_detail(review_id))

    def admin_list_product_reviews(
        self, actor: Actor, product_id: uuid.UUID, *, include_deleted: bool = True, page: int = 1, page_size: int = 20
    ) -> PageResponse[AdminReviewResponse]:
        require_role(actor, *ADMIN_ONLY)
        offset, limit = self._page_args(page, page_size)
        items = self.reviews.list_by_product(product_id, include_deleted=include_deleted, offset=offset, limit=limit)
        return PageResponse[AdminReviewResponse](
            Items=[AdminReviewResponse.model_validate(r) for r in items],
            Total=self.reviews.count_by_product(product_id, include_deleted=include_deleted),
            Page=page,
            PageSize=page_size,
        )

    def admin_get_review(self, actor: Actor, review_id: uuid.UUID) -> AdminReviewResponse:
        require_role(actor, *ADMIN_ONLY)
        review = self.reviews.get_detail(review_id)
        if review is None:
            raise NotFoundError("Không tìm thấy đánh giá", code="review_not_found")
        return AdminReviewResponse.model_validate(review)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _values(data: Any, allowed: frozenset[str]) -> dict[str, Any]:
        """Chỉ nhận các trường cho phép (schema đã chặn; chặn lại nếu schema bị bỏ qua)."""
        values = dict(data.model_dump(exclude_unset=True))
        if "Images" in values and hasattr(data, "Images"):
            values["Images"] = list(data.Images)  # giữ đối tượng schema (không phải dict) của ảnh
        not_allowed = sorted(set(values) - allowed)
        if not_allowed:
            raise BusinessRuleError(f"Không được gửi các trường: {not_allowed}", code="review_field_not_allowed")
        return values

    def _lock_product(self, product_id: uuid.UUID) -> Product:
        product = self.products.get_by_id_for_update(product_id)
        if product is None:
            raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
        return product

    def _lock_review(self, review_id: uuid.UUID) -> tuple[Review, Product]:
        """Khóa theo thứ tự chung Product → Review rồi đọc lại review đã khóa."""
        review = self.reviews.get_by_id(review_id)
        if review is None:
            raise NotFoundError("Không tìm thấy đánh giá", code="review_not_found")
        product = self._lock_product(review.ProductId)
        review = self.reviews.get_by_id_for_update(review_id)
        if review is None:
            raise NotFoundError("Không tìm thấy đánh giá", code="review_not_found")
        return review, product

    def _refresh_rating(self, product: Product) -> None:
        """Tính lại ReviewCount/AverageRating từ các review đang hiển thị (Product đã được khóa bởi caller)."""
        self.reviews.flush()
        count, average = self.reviews.rating_summary(product.ProductId)
        product.ReviewCount = count
        product.AverageRating = money(average) if count and average is not None else _NO_RATING
        self.products.flush()


def _check_rating(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise BusinessRuleError("Điểm đánh giá phải là số nguyên từ 1 đến 5", code="invalid_rating")
    return value


def _check_content(value: Any) -> str:
    content = value.strip() if isinstance(value, str) else ""
    if not content:
        raise BusinessRuleError("Nội dung đánh giá không được để trống", code="review_content_required")
    return content
