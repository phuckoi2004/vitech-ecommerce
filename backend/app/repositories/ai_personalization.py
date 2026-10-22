"""Automatic shopping signals for AI turns: allowlisted brand/category pairs only; no ORM user/order DTO leaves here."""
from sqlalchemy import select

from app.models import Brand, Category, Order, OrderItem, Product, ProductVariant, Wishlist, WishlistItem


class AiPersonalizationRepository:
    def __init__(self, session):
        self.session = session

    def interests(self, user_id, source):
        """Up to five newest distinct visible brand/category pairs from the wishlist or delivered orders."""
        columns = (Brand.BrandId, Brand.Name, Category.CategoryId, Category.Name)
        if source == "wishlist":
            query = (select(*columns).select_from(WishlistItem).join(Wishlist)
                     .join(Product, Product.ProductId == WishlistItem.ProductId)
                     .where(Wishlist.UserId == user_id).order_by(WishlistItem.AddedAt.desc(), WishlistItem.WishlistItemId))
        else:
            query = (select(*columns).select_from(OrderItem).join(Order)
                     .join(ProductVariant, ProductVariant.ProductVariantId == OrderItem.ProductVariantId)
                     .join(Product, Product.ProductId == ProductVariant.ProductId)
                     .where(Order.CustomerId == user_id, Order.OrderStatus.in_(("Delivered", "Completed")))
                     .order_by(Order.OrderedAt.desc(), Order.OrderId.desc(), OrderItem.OrderItemId))
        rows = self.session.execute(query.join(Brand, Brand.BrandId == Product.BrandId)
            .join(Category, Category.CategoryId == Product.CategoryId)
            .where(Product.Status == "Active", Product.IsDeleted.is_(False), Brand.IsActive.is_(True),
                   Brand.IsDeleted.is_(False), Category.IsActive.is_(True), Category.IsDeleted.is_(False)).limit(20)).all()
        hints = []
        for brand_id, brand, category_id, category in rows:
            hint = {"BrandId": str(brand_id), "Brand": brand, "CategoryId": str(category_id), "Category": category}
            if hint not in hints:
                hints.append(hint)
            if len(hints) == 5:
                break
        return hints

    def purchased_product_ids(self, user_id):
        """Products in delivered orders; only lets the history score avoid pushing a re-purchase."""
        rows = self.session.scalars(select(ProductVariant.ProductId).select_from(OrderItem).join(Order)
            .join(ProductVariant, ProductVariant.ProductVariantId == OrderItem.ProductVariantId)
            .where(Order.CustomerId == user_id, Order.OrderStatus.in_(("Delivered", "Completed")))
            .distinct().limit(50))
        return [str(product_id) for product_id in rows]
