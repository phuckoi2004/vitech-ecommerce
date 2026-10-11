"""Repositories cho Wishlists, WishlistItems, Carts, CartItems."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Cart, CartItem, ProductVariant, Wishlist, WishlistItem

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

    def list_by_wishlist(self, wishlist_id: uuid.UUID, *, with_product: bool = False) -> list[WishlistItem]:
        """with_product=True: load sẵn Product (tránh N+1 khi hiển thị wishlist)."""
        return self.get_all(
            WishlistItem.WishlistId == wishlist_id,
            order_by=(WishlistItem.AddedAt.desc(), WishlistItem.WishlistItemId),
            options=(selectinload(WishlistItem.product),) if with_product else (),
        )


class CartRepository(BaseRepository[Cart]):
    model = Cart

    def get_by_user(self, user_id: uuid.UUID, *, with_items: bool = False) -> Cart | None:
        stmt = select(Cart).where(Cart.UserId == user_id)
        if with_items:
            stmt = stmt.options(selectinload(Cart.items))
        return self.session.scalars(stmt).one_or_none()

    def get_by_user_for_update(self, user_id: uuid.UUID) -> Cart | None:
        """Khóa giỏ trước khi đọc/ghi CartItems; checkout và mọi thao tác giỏ dùng cùng khóa này."""
        rows = self._scalars_for_update(select(Cart).where(Cart.UserId == user_id).with_for_update())
        return rows[0] if rows else None


class CartItemRepository(BaseRepository[CartItem]):
    model = CartItem

    def get_by_cart_and_variant(self, cart_id: uuid.UUID, variant_id: uuid.UUID) -> CartItem | None:
        return self._fresh_one(select(CartItem).where(
            CartItem.CartId == cart_id, CartItem.ProductVariantId == variant_id))

    def get_by_id_and_cart(self, cart_item_id: uuid.UUID, cart_id: uuid.UUID) -> CartItem | None:
        return self._fresh_one(select(CartItem).where(
            CartItem.CartItemId == cart_item_id, CartItem.CartId == cart_id))

    def _fresh_one(self, stmt) -> CartItem | None:
        # Sau khi chờ khóa Cart, identity map có thể vẫn chứa số lượng/trạng thái cũ.
        self.session.flush()
        return self.session.scalars(stmt.execution_options(populate_existing=True)).one_or_none()

    def list_by_cart(
        self, cart_id: uuid.UUID, *, is_selected: bool | None = None, with_variant: bool = False
    ) -> list[CartItem]:
        """with_variant=True: load sẵn ProductVariant và Product (tránh N+1 khi tính giỏ hàng)."""
        conditions = [CartItem.CartId == cart_id]
        if is_selected is not None:
            conditions.append(CartItem.IsSelected.is_(is_selected))
        options = (selectinload(CartItem.product_variant).selectinload(ProductVariant.product),) if with_variant else ()
        self.session.flush()
        stmt = select(CartItem).where(*conditions).order_by(CartItem.AddedAt, CartItem.CartItemId).options(*options)
        # populate_existing truyền xuống selectinload để giá/tồn và Product cũng được nạp lại.
        return list(self.session.scalars(stmt.execution_options(populate_existing=True)))
