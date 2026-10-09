"""Repositories cho Wishlists, WishlistItems, Carts, CartItems."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Cart, CartItem, Wishlist, WishlistItem

from .base import BaseRepository


class WishlistRepository(BaseRepository[Wishlist]):
    model = Wishlist

    def get_by_user(self, user_id: uuid.UUID, *, with_items: bool = False) -> Wishlist | None:
        stmt = select(Wishlist).where(Wishlist.UserId == user_id)
        if with_items:
            stmt = stmt.options(selectinload(Wishlist.items))
        return self.session.scalars(stmt).one_or_none()


class WishlistItemRepository(BaseRepository[WishlistItem]):
    model = WishlistItem

    def get_by_wishlist_and_product(self, wishlist_id: uuid.UUID, product_id: uuid.UUID) -> WishlistItem | None:
        return self.get_one(WishlistItem.WishlistId == wishlist_id, WishlistItem.ProductId == product_id)

    def list_by_wishlist(self, wishlist_id: uuid.UUID) -> list[WishlistItem]:
        return self.get_all(
            WishlistItem.WishlistId == wishlist_id,
            order_by=(WishlistItem.AddedAt.desc(), WishlistItem.WishlistItemId),
        )


class CartRepository(BaseRepository[Cart]):
    model = Cart

    def get_by_user(self, user_id: uuid.UUID, *, with_items: bool = False) -> Cart | None:
        stmt = select(Cart).where(Cart.UserId == user_id)
        if with_items:
            stmt = stmt.options(selectinload(Cart.items))
        return self.session.scalars(stmt).one_or_none()


class CartItemRepository(BaseRepository[CartItem]):
    model = CartItem

    def get_by_cart_and_variant(self, cart_id: uuid.UUID, variant_id: uuid.UUID) -> CartItem | None:
        return self.get_one(CartItem.CartId == cart_id, CartItem.ProductVariantId == variant_id)

    def get_by_id_and_cart(self, cart_item_id: uuid.UUID, cart_id: uuid.UUID) -> CartItem | None:
        return self.get_one(CartItem.CartItemId == cart_item_id, CartItem.CartId == cart_id)

    def list_by_cart(self, cart_id: uuid.UUID, *, is_selected: bool | None = None) -> list[CartItem]:
        conditions = [CartItem.CartId == cart_id]
        if is_selected is not None:
            conditions.append(CartItem.IsSelected.is_(is_selected))
        return self.get_all(*conditions, order_by=(CartItem.AddedAt, CartItem.CartItemId))
