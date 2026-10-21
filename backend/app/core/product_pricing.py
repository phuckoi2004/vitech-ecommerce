"""Shared, read-only pricing rules. Never mutate a variant's list price or expose cost.

One automatic promotion per unit; the lowest valid price wins. Invalid/missing cost
fails closed (no automatic discount). Fixed discounts and caps apply per unit.
"""
from decimal import Decimal, ROUND_FLOOR

from sqlalchemy import and_, case, func, or_, select

from app.models import Product, ProductVariant, Promotion, PromotionCategory, PromotionProduct

CENT = Decimal("0.01")


def discount_for(promotion, base):
    amount = (base * promotion.DiscountValue / 100 if promotion.DiscountType == "Percentage"
              else promotion.DiscountValue)
    if promotion.MaxDiscountAmount is not None:
        amount = min(amount, promotion.MaxDiscountAmount)
    return max(Decimal("0"), min(base, amount)).quantize(Decimal("1"), rounding=ROUND_FLOOR)


def matches_product(promotion, product):
    products = {item.ProductId for item in promotion.promotion_products}
    categories = {item.CategoryId for item in promotion.promotion_categories}
    return not (products or categories) or product.ProductId in products or product.CategoryId in categories


def automatic_price_expression(now):
    """Correlated SQL equivalent, used BEFORE price filtering and pagination."""
    base = ProductVariant.Price
    reduction = case((Promotion.DiscountType == "Percentage", base * Promotion.DiscountValue / 100),
                     else_=Promotion.DiscountValue)
    reduction = case((and_(Promotion.MaxDiscountAmount.is_not(None), reduction > Promotion.MaxDiscountAmount),
                      Promotion.MaxDiscountAmount), else_=reduction)
    reduction = func.floor(reduction)
    candidate = base - reduction
    product_target = select(PromotionProduct.PromotionId).where(
        PromotionProduct.PromotionId == Promotion.PromotionId).correlate(Promotion).exists()
    category_target = select(PromotionCategory.PromotionId).where(
        PromotionCategory.PromotionId == Promotion.PromotionId).correlate(Promotion).exists()
    matches = or_(
        and_(~product_target, ~category_target),
        select(PromotionProduct.PromotionId).where(
            PromotionProduct.PromotionId == Promotion.PromotionId,
            PromotionProduct.ProductId == Product.ProductId).correlate(Promotion, Product).exists(),
        select(PromotionCategory.PromotionId).where(
            PromotionCategory.PromotionId == Promotion.PromotionId,
            PromotionCategory.CategoryId == Product.CategoryId).correlate(Promotion, Product).exists(),
    )
    lowest = select(func.min(candidate)).where(
        Promotion.ApplyMode == "Automatic", Promotion.Status.in_(("Scheduled", "Active")),
        Promotion.StartDate <= now, Promotion.EndDate >= now, Promotion.MinOrderValue == 0,
        reduction > 0, ProductVariant.CostPrice > 0, candidate >= ProductVariant.CostPrice,
        matches,
    ).correlate(ProductVariant, Product).scalar_subquery()
    return func.coalesce(lowest, base)
