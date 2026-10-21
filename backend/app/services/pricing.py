"""Pricing without cart/order ownership. Checkout can call reserve_order_quote
inside its existing transaction; public preview never consumes a redemption.
"""
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from app.core.product_pricing import CENT, automatic_price_expression, discount_for, matches_product
from app.models import Category, Coupon, Order, Product, ProductVariant, Promotion
from app.repositories import PromotionRepository
from app.schemas.pricing import CategoryOfferResponse, PricedItem, PricingQuoteResponse, PublicCouponResponse
from .actor import Actor, CUSTOMER_ONLY, require_role
from .base import BaseService
from .exceptions import BusinessRuleError, NotFoundError
from .promotion_state import aware
from .promotion import SimpleDiscountLine, allocate_discount

ZERO = Decimal("0.00")


def in_period(promotion, now):
    return (promotion.Status in ("Scheduled", "Active")
            and aware(promotion.StartDate) <= aware(now) <= aware(promotion.EndDate))


def variant_price(variant, promotions, now):
    """Price quote for one unit. Never silently reduce a configured discount to fit cost."""
    price, chosen = variant.Price, None
    if variant.CostPrice is not None and variant.CostPrice > 0:
        for promotion in sorted(promotions, key=lambda row: str(row.PromotionId)):
            if (promotion.ApplyMode != "Automatic" or not in_period(promotion, now)
                    or promotion.MinOrderValue != 0 or not matches_product(promotion, variant.product)):
                continue
            candidate = variant.Price - discount_for(promotion, variant.Price)
            if variant.CostPrice <= candidate < price:
                price, chosen = candidate, promotion
    # Only a promotion strikes a price through: the selling price is the original price customers see. The stored
    # list price (CompareAtPrice) is kept for reference and is not shown as a discount.
    original = variant.Price
    discount = original - price
    return dict(OriginalPrice=original, SalePrice=price, DiscountAmount=discount,
                DiscountPercent=(discount / original * 100).quantize(CENT, rounding=ROUND_HALF_UP) if original else ZERO,
                AppliedPromotionId=chosen.PromotionId if chosen else None,
                PromotionName=chosen.Name if chosen else None,
                PromotionEndsAt=chosen.EndDate if chosen else None)


class PricingService(BaseService):
    def category_offers(self):
        """Homepage highlights from actual in-stock prices, including active descendants.

        Aggregate in SQL rather than downloading every product detail in the browser.
        Coupon reductions never contribute to these unconditional offer captions.
        """
        now = self.now()
        roots = list(self.session.scalars(select(Category).where(
            Category.ParentCategoryId.is_(None), Category.IsActive.is_(True)
        ).order_by(Category.DisplayOrder, Category.Name, Category.CategoryId)))
        tree = select(Category.CategoryId.label("CategoryId"), Category.CategoryId.label("RootId")).where(
            Category.ParentCategoryId.is_(None), Category.IsActive.is_(True)).cte("offer_categories", recursive=True)
        tree = tree.union(select(Category.CategoryId, tree.c.RootId).join(
            tree, Category.ParentCategoryId == tree.c.CategoryId).where(Category.IsActive.is_(True)))
        prices = select(Product.ProductId, Product.CategoryId,
                        ProductVariant.Price.label("original"),
                        automatic_price_expression(now).label("sale")).join(
            ProductVariant, ProductVariant.ProductId == Product.ProductId).where(
                Product.Status == "Active", Product.IsDeleted.is_(False),
                ProductVariant.IsActive.is_(True), ProductVariant.IsDeleted.is_(False),
                ProductVariant.StockQuantity > 0).subquery()
        reduction = prices.c.original - prices.c.sale
        rows = self.session.execute(select(
            tree.c.RootId, func.count(func.distinct(prices.c.ProductId)),
            func.max(reduction), func.max(reduction * 100 / func.nullif(prices.c.original, 0)),
        ).join(prices, prices.c.CategoryId == tree.c.CategoryId).group_by(tree.c.RootId))
        offers = {root_id: (count, amount, percent) for root_id, count, amount, percent in rows}
        return [CategoryOfferResponse(
            CategoryId=root.CategoryId, AvailableProductCount=offers.get(root.CategoryId, (0, ZERO, ZERO))[0],
            MaxDiscountAmount=offers.get(root.CategoryId, (0, ZERO, ZERO))[1],
            MaxDiscountPercent=Decimal(offers.get(root.CategoryId, (0, ZERO, ZERO))[2] or 0).quantize(CENT, rounding=ROUND_DOWN),
        ) for root in roots]

    def automatic_promotions(self, *, product=None):
        return PromotionRepository(self.session).list_automatic(self.now(), product=product)

    def public_coupons(self, *, product_id=None):
        now = self.now()
        rows = self.session.scalars(select(Coupon).join(Coupon.promotion).where(
            Promotion.ApplyMode == "Coupon", Promotion.Status.in_(("Scheduled", "Active")),
            Promotion.StartDate <= now, Promotion.EndDate >= now,
        ).options(joinedload(Coupon.promotion).selectinload(Promotion.promotion_products),
                  joinedload(Coupon.promotion).selectinload(Promotion.promotion_categories))
          .order_by(Coupon.CreatedAt.desc(), Coupon.CouponId))
        product = None
        if product_id is not None:
            from app.models import Product
            product = self.session.get(Product, product_id)
            if product is None or product.IsDeleted or product.Status != "Active":
                raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
        result = []
        for coupon in rows:
            remaining = None if coupon.UsageLimit is None else max(0, coupon.UsageLimit - coupon.UsedCount)
            if remaining == 0 or (product is not None and not matches_product(coupon.promotion, product)):
                continue
            promotion = coupon.promotion
            result.append(PublicCouponResponse(
                CouponId=coupon.CouponId, Code=coupon.Code, Name=coupon.Name,
                Description=promotion.Description, DiscountType=promotion.DiscountType,
                DiscountValue=promotion.DiscountValue, MinOrderValue=promotion.MinOrderValue,
                MaxDiscountAmount=promotion.MaxDiscountAmount, StartDate=promotion.StartDate,
                EndDate=promotion.EndDate, RemainingUses=remaining, EvaluatedAt=now))
        return result

    def quote(self, items, *, coupon_code=None, actor: Actor | None = None, lock_coupon=False):
        now = self.now()
        quantities = {}
        for item in items:
            quantities[item.ProductVariantId] = quantities.get(item.ProductVariantId, 0) + item.Quantity
        if any(quantity < 1 or quantity > 999 for quantity in quantities.values()):
            raise BusinessRuleError("Số lượng mỗi phiên bản từ 1 đến 999", code="invalid_quantity")
        variants = list(self.session.scalars(select(ProductVariant).where(
            ProductVariant.ProductVariantId.in_(quantities), ProductVariant.IsActive.is_(True),
            ProductVariant.IsDeleted.is_(False)).options(joinedload(ProductVariant.product))))
        if len(variants) != len(quantities) or any(v.product.IsDeleted or v.product.Status != "Active" for v in variants):
            raise NotFoundError("Sản phẩm không còn được bán", code="variant_not_available")
        promotions = self.automatic_promotions()
        lines = []
        by_id = {}
        for variant in sorted(variants, key=lambda row: str(row.ProductVariantId)):
            quantity = quantities[variant.ProductVariantId]
            if quantity > variant.StockQuantity:
                raise BusinessRuleError("Số lượng vượt tồn kho hiện tại", code="insufficient_stock")
            price = variant_price(variant, promotions, now)
            lines.append(PricedItem(ProductVariantId=variant.ProductVariantId, Quantity=quantity,
                                   OriginalPrice=price["OriginalPrice"], SalePrice=price["SalePrice"],
                                   AutomaticDiscount=price["DiscountAmount"] * quantity,
                                   CouponDiscount=ZERO, LineTotal=price["SalePrice"] * quantity,
                                   AppliedPromotionId=price["AppliedPromotionId"]))
            by_id[variant.ProductVariantId] = variant
        subtotal = sum((line.LineTotal for line in lines), ZERO)
        coupon = None
        if coupon_code:
            stmt = select(Coupon).where(func.lower(Coupon.Code) == coupon_code.strip().lower()).options(
                selectinload(Coupon.promotion).selectinload(Promotion.promotion_products),
                selectinload(Coupon.promotion).selectinload(Promotion.promotion_categories))
            if lock_coupon:
                stmt = stmt.with_for_update(of=Coupon).execution_options(populate_existing=True)
            coupon = self.session.scalar(stmt)
            if coupon is None or coupon.promotion.ApplyMode != "Coupon":
                raise BusinessRuleError("Mã giảm giá không hợp lệ", code="coupon_invalid")
            if not in_period(coupon.promotion, now):
                raise BusinessRuleError("Mã giảm giá đã hết hạn hoặc chưa bắt đầu", code="coupon_expired")
            if coupon.UsageLimit is not None and coupon.UsedCount >= coupon.UsageLimit:
                raise BusinessRuleError("Mã giảm giá đã hết lượt sử dụng", code="coupon_usage_exceeded")
            if actor is not None and self.session.scalar(select(Order.OrderId).where(
                    Order.CustomerId == actor.user_id, Order.CouponId == coupon.CouponId,
                    Order.OrderStatus != "Cancelled").limit(1)) is not None:
                raise BusinessRuleError("Bạn đã sử dụng mã này", code="coupon_customer_limit")
            if subtotal < coupon.promotion.MinOrderValue:
                raise BusinessRuleError("Tiền hàng sau giảm trực tiếp chưa đạt đơn tối thiểu của mã", code="coupon_min_order_value")
            eligible = [line for line in lines if matches_product(coupon.promotion, by_id[line.ProductVariantId].product)]
            base = sum((line.LineTotal for line in eligible), ZERO)
            if base <= 0:
                raise BusinessRuleError("Mã không áp dụng cho sản phẩm này", code="coupon_not_applicable")
            amount = discount_for(coupon.promotion, base)
            # Match checkout's whole-VND allocation, including legacy fractional-price handling.
            allocations = [SimpleDiscountLine(
                by_id[line.ProductVariantId].ProductId,
                by_id[line.ProductVariantId].product.CategoryId, line.LineTotal,
            ) for line in eligible]
            allocate_discount(amount, allocations)
            for line, allocation in zip(eligible, allocations):
                line.CouponDiscount = allocation.discount
                line.LineTotal -= line.CouponDiscount
        for line in lines:
            variant = by_id[line.ProductVariantId]
            if variant.CostPrice <= 0 or line.LineTotal < variant.CostPrice * line.Quantity:
                raise BusinessRuleError("Mã không áp dụng được cho các sản phẩm đã chọn" if coupon
                                        else "Không thể xác nhận giá của các sản phẩm đã chọn",
                                        code="coupon_price_floor" if coupon else "price_floor")
        return PricingQuoteResponse(
            Items=lines, OriginalSubtotal=sum((line.OriginalPrice * line.Quantity for line in lines), ZERO),
            Subtotal=subtotal, AutomaticDiscount=sum((line.AutomaticDiscount for line in lines), ZERO),
            CouponDiscount=sum((line.CouponDiscount for line in lines), ZERO),
            Total=sum((line.LineTotal for line in lines), ZERO),
            CouponId=coupon.CouponId if coupon else None, CouponCode=coupon.Code if coupon else None,
            EvaluatedAt=now)

    def reserve_order_quote(self, actor, items, *, coupon_code=None):
        """Checkout adapter: call AFTER locking cart/variants, INSIDE the order transaction.

        The caller MUST persist the order (with CouponId) before committing this same
        transaction. Rollback restores usage. Do not also call the legacy coupon applier.
        """
        self.require_enclosing_use_case()
        require_role(actor, *CUSTOMER_ONLY)
        quote = self.quote(items, coupon_code=coupon_code, actor=actor, lock_coupon=True)
        if quote.CouponId:
            coupon = self.session.get(Coupon, quote.CouponId)
            coupon.UsedCount += 1
            coupon.IsActive = coupon.UsageLimit is None or coupon.UsedCount < coupon.UsageLimit
            self.session.flush()
        return quote.model_copy(update={"PreviewOnly": False})
