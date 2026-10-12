"""Promotion / Coupon services.

Nguồn nghiệp vụ: docs/business-requirements.md mục 5, 6, 17 và các quyết định đã chốt:
- Admin quản lý trạng thái Promotion (Draft, Scheduled, Active, Expired, Cancelled);
  khi áp dụng kiểm tra Status = Active và StartDate <= hiện tại <= EndDate.
- Promotion đang Active: không sửa các trường ảnh hưởng điều kiện/giá trị giảm và phạm vi áp dụng.
- Không xóa Promotion/Coupon đã được dữ liệu nghiệp vụ tham chiếu; dùng Cancelled / IsActive = false.
- Coupon.Code không phân biệt hoa thường; Coupon chỉ tham chiếu Promotion.
- Coupon giảm trên các dòng thuộc Product/Category được gán cho Promotion (Promotion không gán gì = toàn đơn);
  danh mục chỉ khớp trực tiếp, không gồm danh mục con. Tiền giảm phân bổ theo tỷ lệ vào từng dòng.
- UsedCount tăng/giảm có khóa dòng coupon; không âm, không vượt UsageLimit.
Cách tính giảm giá ở đây là nguồn duy nhất, OrderService dùng lại.
"""

import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy.orm import Session

from app.models import Coupon, Order, Promotion
from app.repositories import (
    CartItemRepository,
    CartRepository,
    CategoryRepository,
    CouponRepository,
    OrderRepository,
    ProductRepository,
    PromotionCategoryRepository,
    PromotionProductRepository,
    PromotionRepository,
)
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

from .actor import ADMIN_ONLY, CUSTOMER_ONLY, Actor, require_role
from .base import BaseService, utc_now
from .catalog import is_variant_sellable
from .exceptions import BusinessRuleError, ConflictError, NotFoundError

PROMOTION_ACTIVE = "Active"
PROMOTION_CANCELLED = "Cancelled"
PERCENTAGE = "Percentage"
# Trường ảnh hưởng điều kiện/giá trị giảm: không sửa khi Promotion đang Active.
LOCKED_WHEN_ACTIVE = ("DiscountType", "DiscountValue", "MinOrderValue", "MaxDiscountAmount", "StartDate", "EndDate")

_CENT = Decimal("0.01")


# ======================================================================
# Tính giảm giá (dùng chung cho xem trước giỏ hàng và tạo đơn)
# ======================================================================


class DiscountLine(Protocol):
    """Dòng hàng tham gia tính giảm giá."""

    product_id: uuid.UUID
    category_id: uuid.UUID
    gross: Decimal
    discount: Decimal


@dataclass
class SimpleDiscountLine:
    product_id: uuid.UUID
    category_id: uuid.UUID
    gross: Decimal
    discount: Decimal = Decimal("0")


def money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def is_promotion_in_effect(promotion: Promotion, now: datetime) -> bool:
    """Promotion đang áp dụng: Status Active và now nằm trong [StartDate, EndDate]."""
    return promotion.Status == PROMOTION_ACTIVE and promotion.StartDate <= now <= promotion.EndDate


def calculate_discount(promotion: Promotion, base: Decimal) -> Decimal:
    """Percentage: base × DiscountValue / 100; FixedAmount: DiscountValue.
    Giới hạn bởi MaxDiscountAmount (nếu có) và không vượt base."""
    if promotion.DiscountType == PERCENTAGE:
        discount = money(base * promotion.DiscountValue / Decimal("100"))
    else:
        discount = money(promotion.DiscountValue)
    if promotion.MaxDiscountAmount is not None:
        discount = min(discount, promotion.MaxDiscountAmount)
    return min(discount, base)


def allocate_discount(discount: Decimal, lines: Sequence[DiscountLine]) -> None:
    """Phân bổ tiền giảm theo tỷ lệ giá trị dòng (discount <= tổng giá trị các dòng).

    Mỗi dòng nhận phần làm tròn xuống tới cent; số cent còn dư chia cho các dòng có phần lẻ lớn nhất
    còn sức chứa. Tổng phân bổ đúng bằng ``discount`` và không dòng nào bị giảm quá giá trị của nó.
    """
    base = sum((line.gross for line in lines), Decimal("0"))
    if base <= 0 or discount <= 0:
        for line in lines:
            line.discount = Decimal("0")
        return
    fractions = []
    for index, line in enumerate(lines):
        exact = discount * line.gross / base
        share = exact.quantize(_CENT, rounding=ROUND_DOWN)
        line.discount = share
        fractions.append((exact - share, index))
    remaining_cents = int((discount - sum(line.discount for line in lines)) / _CENT)
    for _, index in sorted(fractions, reverse=True):
        if remaining_cents <= 0:
            break
        line = lines[index]
        if line.discount + _CENT <= line.gross:
            line.discount += _CENT
            remaining_cents -= 1


# ======================================================================
# PromotionService
# ======================================================================


class PromotionService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.promotions = PromotionRepository(session)
        self.promotion_products = PromotionProductRepository(session)
        self.promotion_categories = PromotionCategoryRepository(session)
        self.coupons = CouponRepository(session)
        self.products = ProductRepository(session)
        self.categories = CategoryRepository(session)

    def list_promotions(
        self, actor: Actor, *, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> PageResponse[AdminPromotionResponse]:
        require_role(actor, *ADMIN_ONLY)
        offset, limit = self._page_args(page, page_size)
        items = self.promotions.list_promotions(status=status, offset=offset, limit=limit)
        return PageResponse[AdminPromotionResponse](
            Items=[AdminPromotionResponse.model_validate(p) for p in items],
            Total=self.promotions.count_promotions(status=status),
            Page=page,
            PageSize=page_size,
        )

    def get_promotion(self, actor: Actor, promotion_id: uuid.UUID) -> AdminPromotionDetailResponse:
        require_role(actor, *ADMIN_ONLY)
        promotion = self.promotions.get_detail(promotion_id)
        if promotion is None:
            raise NotFoundError("Không tìm thấy chương trình khuyến mãi", code="promotion_not_found")
        return AdminPromotionDetailResponse.model_validate(promotion)

    def create_promotion(self, actor: Actor, data: PromotionCreate) -> AdminPromotionDetailResponse:
        """Admin tạo Promotion; CreatedByUserId là Actor (không nhận từ client)."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            values = data.model_dump(exclude_unset=True, exclude={"ProductIds", "CategoryIds"})
            product_ids, category_ids = self._valid_targets(data.ProductIds, data.CategoryIds)
            promotion = self.promotions.create({**values, "CreatedByUserId": actor.user_id})
            self.promotions.flush()
            self._replace_targets(promotion.PromotionId, product_ids, category_ids)
            self.promotions.flush()
            return AdminPromotionDetailResponse.model_validate(self.promotions.get_detail(promotion.PromotionId))

    def update_promotion(self, actor: Actor, promotion_id: uuid.UUID, data: PromotionUpdate) -> AdminPromotionDetailResponse:
        """Cập nhật Promotion. Đang Active: chỉ được đổi Name, Description, Status."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            promotion = self._lock(promotion_id)
            values = data.model_dump(exclude_unset=True)
            if promotion.Status == PROMOTION_ACTIVE:
                changed = sorted(f for f in LOCKED_WHEN_ACTIVE if f in values and values[f] != getattr(promotion, f))
                if changed:
                    raise BusinessRuleError(
                        f"Không sửa {', '.join(changed)} khi khuyến mãi đang Active", code="promotion_active_locked"
                    )
            # Kiểm tra lại các CHECK với giá trị sau cập nhật (kết hợp giá trị đang lưu).
            merged = {f: values.get(f, getattr(promotion, f)) for f in ("DiscountType", "DiscountValue", "StartDate", "EndDate")}
            if merged["EndDate"] < merged["StartDate"]:
                raise BusinessRuleError("EndDate phải lớn hơn hoặc bằng StartDate", code="invalid_promotion_period")
            if merged["DiscountType"] == PERCENTAGE and merged["DiscountValue"] > 100:
                raise BusinessRuleError("Giảm theo phần trăm không quá 100", code="invalid_discount_value")
            self.promotions.update(promotion, values)
            self.promotions.flush()
            return AdminPromotionDetailResponse.model_validate(self.promotions.get_detail(promotion_id))

    def update_targets(
        self, actor: Actor, promotion_id: uuid.UUID, data: PromotionTargetsUpdate
    ) -> AdminPromotionDetailResponse:
        """Thay danh sách sản phẩm/danh mục áp dụng (trường không gửi = giữ nguyên). Không cho khi đang Active."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            promotion = self._lock(promotion_id)
            if promotion.Status == PROMOTION_ACTIVE:
                raise BusinessRuleError(
                    "Không sửa phạm vi áp dụng khi khuyến mãi đang Active", code="promotion_active_locked"
                )
            values = data.model_dump(exclude_unset=True)
            product_ids, category_ids = self._valid_targets(values.get("ProductIds") or [], values.get("CategoryIds") or [])
            if values.get("ProductIds") is not None:
                self.promotion_products.delete_by_promotion(promotion_id)
                self._replace_targets(promotion_id, product_ids, [])
            if values.get("CategoryIds") is not None:
                self.promotion_categories.delete_by_promotion(promotion_id)
                self._replace_targets(promotion_id, [], category_ids)
            self.promotions.flush()
            self.session.expire(promotion)
            return AdminPromotionDetailResponse.model_validate(self.promotions.get_detail(promotion_id))

    def cancel_promotion(self, actor: Actor, promotion_id: uuid.UUID) -> AdminPromotionDetailResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            promotion = self._lock(promotion_id)
            if promotion.Status == PROMOTION_CANCELLED:
                raise BusinessRuleError("Khuyến mãi đã bị hủy", code="promotion_already_cancelled")
            promotion.Status = PROMOTION_CANCELLED
            self.promotions.flush()
            return AdminPromotionDetailResponse.model_validate(self.promotions.get_detail(promotion_id))

    def delete_promotion(self, actor: Actor, promotion_id: uuid.UUID) -> None:
        """Xóa Promotion chưa có Coupon (FK RESTRICT). Đã có Coupon thì dùng cancel_promotion."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            promotion = self._lock(promotion_id)
            if self.coupons.list_by_promotion(promotion_id):
                raise BusinessRuleError(
                    "Khuyến mãi đã có mã giảm giá; hãy hủy (Cancelled) thay vì xóa", code="promotion_in_use"
                )
            self.promotions.delete(promotion)

    def _lock(self, promotion_id: uuid.UUID) -> Promotion:
        promotion = self.promotions.get_by_id_for_update(promotion_id)
        if promotion is None:
            raise NotFoundError("Không tìm thấy chương trình khuyến mãi", code="promotion_not_found")
        return promotion

    def _valid_targets(
        self, product_ids: Iterable[uuid.UUID], category_ids: Iterable[uuid.UUID]
    ) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
        products = list(dict.fromkeys(product_ids))
        categories = list(dict.fromkeys(category_ids))
        missing_products = [str(pid) for pid in products if self.products.get_by_id(pid) is None]
        if missing_products:
            raise NotFoundError(f"Không tìm thấy sản phẩm: {missing_products}", code="product_not_found")
        missing_categories = [str(cid) for cid in categories if self.categories.get_by_id(cid) is None]
        if missing_categories:
            raise NotFoundError(f"Không tìm thấy danh mục: {missing_categories}", code="category_not_found")
        return products, categories

    def _replace_targets(
        self, promotion_id: uuid.UUID, product_ids: Iterable[uuid.UUID], category_ids: Iterable[uuid.UUID]
    ) -> None:
        for product_id in product_ids:
            self.promotion_products.create({"PromotionId": promotion_id, "ProductId": product_id})
        for category_id in category_ids:
            self.promotion_categories.create({"PromotionId": promotion_id, "CategoryId": category_id})


# ======================================================================
# CouponService
# ======================================================================


class CouponService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.coupons = CouponRepository(session)
        self.promotions = PromotionRepository(session)
        self.promotion_products = PromotionProductRepository(session)
        self.promotion_categories = PromotionCategoryRepository(session)
        self.orders = OrderRepository(session)
        self.carts = CartRepository(session)
        self.cart_items = CartItemRepository(session)

    # ---------------------------------------------------------- Admin CRUD

    def list_coupons(
        self, actor: Actor, promotion_id: uuid.UUID, *, is_active: bool | None = None
    ) -> list[AdminCouponResponse]:
        require_role(actor, *ADMIN_ONLY)
        if self.promotions.get_by_id(promotion_id) is None:
            raise NotFoundError("Không tìm thấy chương trình khuyến mãi", code="promotion_not_found")
        return [AdminCouponResponse.model_validate(c) for c in self.coupons.list_by_promotion(promotion_id, is_active=is_active)]

    def get_coupon(self, actor: Actor, coupon_id: uuid.UUID) -> AdminCouponResponse:
        require_role(actor, *ADMIN_ONLY)
        return AdminCouponResponse.model_validate(self._get(coupon_id))

    def create_coupon(self, actor: Actor, data: CouponCreate) -> AdminCouponResponse:
        """Admin tạo Coupon; CreatedByUserId là Actor (không nhận từ client)."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            values = data.model_dump(exclude_unset=True)
            if self.promotions.get_by_id(values["PromotionId"]) is None:
                raise NotFoundError("Không tìm thấy chương trình khuyến mãi", code="promotion_not_found")
            if self.coupons.exists_by_code(values["Code"]):
                raise ConflictError("Mã giảm giá đã tồn tại", code="coupon_code_exists")
            coupon = self.coupons.create({**values, "CreatedByUserId": actor.user_id})
            self.coupons.flush()
            return AdminCouponResponse.model_validate(coupon)

    def update_coupon(self, actor: Actor, coupon_id: uuid.UUID, data: CouponUpdate) -> AdminCouponResponse:
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            # Khóa dòng: UsedCount có thể đang được đơn hàng khác cập nhật.
            coupon = self._get(coupon_id, lock=True)
            values = data.model_dump(exclude_unset=True)
            if "Code" in values and self.coupons.exists_by_code(values["Code"], coupon_id):
                raise ConflictError("Mã giảm giá đã tồn tại", code="coupon_code_exists")
            if "PromotionId" in values and self.promotions.get_by_id(values["PromotionId"]) is None:
                raise NotFoundError("Không tìm thấy chương trình khuyến mãi", code="promotion_not_found")
            if values.get("UsageLimit") is not None and values["UsageLimit"] < coupon.UsedCount:
                raise BusinessRuleError(
                    f"UsageLimit không được nhỏ hơn số lượt đã dùng ({coupon.UsedCount})", code="usage_limit_below_used"
                )
            self.coupons.update(coupon, values)
            self.coupons.flush()
            return AdminCouponResponse.model_validate(coupon)

    def delete_coupon(self, actor: Actor, coupon_id: uuid.UUID) -> None:
        """Xóa coupon chưa được đơn hàng dùng (FK RESTRICT). Đã dùng thì vô hiệu hóa bằng IsActive = false."""
        require_role(actor, *ADMIN_ONLY)
        with self.transaction():
            coupon = self._get(coupon_id, lock=True)
            if self.orders.exists(Order.CouponId == coupon_id):
                raise BusinessRuleError(
                    "Mã giảm giá đã được sử dụng; hãy vô hiệu hóa (IsActive = false)", code="coupon_in_use"
                )
            self.coupons.delete(coupon)

    # ---------------------------------------------------------- Customer

    def preview_cart_coupon(self, actor: Actor, code: str) -> CouponPreviewResponse:
        """Customer kiểm tra mã và tính thử tiền giảm trên các dòng giỏ hàng của mình đang chọn và còn mua được.

        Không khóa, không tăng UsedCount. Kết quả cuối cùng được tính lại khi tạo đơn.
        """
        require_role(actor, *CUSTOMER_ONLY)
        cart = self.carts.get_by_user(actor.user_id)
        items = self.cart_items.list_by_cart(cart.CartId, is_selected=True, with_variant=True) if cart else []
        lines = [
            SimpleDiscountLine(
                product_id=item.product_variant.ProductId,
                category_id=item.product_variant.product.CategoryId,
                gross=money(item.product_variant.Price * item.Quantity),
            )
            for item in items
            if is_variant_sellable(item.product_variant) and item.Quantity <= item.product_variant.StockQuantity
        ]
        if not lines:
            raise BusinessRuleError("Giỏ hàng chưa có sản phẩm được chọn", code="cart_empty")
        subtotal = sum((line.gross for line in lines), Decimal("0"))
        coupon = self.coupons.get_by_code(code, with_promotion=True)
        eligible, discount = self._evaluate(coupon, lines, subtotal)
        return CouponPreviewResponse(
            Code=coupon.Code,
            PromotionId=coupon.PromotionId,
            Subtotal=subtotal,
            EligibleSubtotal=sum((line.gross for line in eligible), Decimal("0")),
            DiscountAmount=discount,
        )

    # ---------------------------------------------------------- Dùng cho OrderService (trong transaction tạo/hủy đơn)

    def apply_coupon_to_order(
        self, code: str, lines: Sequence[DiscountLine], subtotal: Decimal
    ) -> tuple[Coupon, Decimal]:
        """Khóa coupon (FOR UPDATE), kiểm tra, tính và phân bổ tiền giảm vào ``lines``, tăng UsedCount.

        Chỉ gọi bên trong use case tạo đơn (không dùng trực tiếp từ Router).
        """
        self.require_enclosing_use_case()
        with self.transaction():
            coupon = self.coupons.get_by_code_for_update(code)
            eligible, discount = self._evaluate(coupon, lines, subtotal)
            allocate_discount(discount, eligible)
            coupon.UsedCount += 1
            return coupon, discount

    def release_coupon_usage(self, coupon_id: uuid.UUID) -> None:
        """Trả lại một lượt dùng khi đơn bị hủy (khóa dòng; UsedCount không âm). Chỉ gọi bên trong use case hủy đơn."""
        self.require_enclosing_use_case()
        with self.transaction():
            coupon = self.coupons.get_by_id_for_update(coupon_id)
            if coupon is not None and coupon.UsedCount > 0:
                coupon.UsedCount -= 1

    # ---------------------------------------------------------- Helpers

    def _get(self, coupon_id: uuid.UUID, *, lock: bool = False) -> Coupon:
        coupon = self.coupons.get_by_id_for_update(coupon_id) if lock else self.coupons.get_by_id(coupon_id)
        if coupon is None:
            raise NotFoundError("Không tìm thấy mã giảm giá", code="coupon_not_found")
        return coupon

    def _evaluate(
        self, coupon: Coupon | None, lines: Sequence[DiscountLine], subtotal: Decimal
    ) -> tuple[list[DiscountLine], Decimal]:
        """Kiểm tra coupon/promotion và điều kiện đơn; trả các dòng được giảm và tổng tiền giảm."""
        if coupon is None or not coupon.IsActive:
            raise BusinessRuleError("Mã giảm giá không hợp lệ", code="coupon_invalid")
        promotion = coupon.promotion
        if not is_promotion_in_effect(promotion, self.now()):
            raise BusinessRuleError("Mã giảm giá không còn hiệu lực", code="coupon_expired")
        if coupon.UsageLimit is not None and coupon.UsedCount >= coupon.UsageLimit:
            raise BusinessRuleError("Mã giảm giá đã hết lượt sử dụng", code="coupon_usage_exceeded")
        if subtotal < promotion.MinOrderValue:
            raise BusinessRuleError("Đơn hàng chưa đạt giá trị tối thiểu của mã giảm giá", code="coupon_min_order_value")
        eligible = self._eligible_lines(promotion.PromotionId, lines)
        if not eligible:
            raise BusinessRuleError("Mã giảm giá không áp dụng cho sản phẩm trong đơn", code="coupon_not_applicable")
        base = sum((line.gross for line in eligible), Decimal("0"))
        return eligible, calculate_discount(promotion, base)

    def _eligible_lines(self, promotion_id: uuid.UUID, lines: Sequence[DiscountLine]) -> list[DiscountLine]:
        """Promotion không gán Product/Category: toàn bộ dòng. Danh mục chỉ khớp trực tiếp."""
        product_ids = {p.ProductId for p in self.promotion_products.list_by_promotion(promotion_id)}
        category_ids = {c.CategoryId for c in self.promotion_categories.list_by_promotion(promotion_id)}
        if not product_ids and not category_ids:
            return list(lines)
        return [line for line in lines if line.product_id in product_ids or line.category_id in category_ids]
