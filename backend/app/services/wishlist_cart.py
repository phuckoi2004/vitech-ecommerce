"""Wishlist / Cart services.

Nguồn nghiệp vụ: docs/business-requirements.md mục 4.
- Mỗi người dùng có một Wishlist và một Cart (UNIQUE UserId); tạo khi dùng lần đầu.
- Mọi thao tác nhận Actor (Customer) do Router dựng từ JWT và chỉ tác động lên Wishlist/Cart của chính Actor.
- Cart không giữ chỗ (reserve) và không thay đổi tồn kho; tồn kho xử lý ở Order.
- Giá và tổng tiền do server tính từ dữ liệu hiện tại.
"""

import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Cart, CartItem, Wishlist
from app.repositories import (
    CartItemRepository,
    CartRepository,
    ProductRepository,
    ProductVariantRepository,
    WishlistItemRepository,
    WishlistRepository,
)
from app.schemas import (
    CartItemCreate,
    CartItemUpdate,
    CartLineResponse,
    CartSummaryResponse,
    WishlistDetailResponse,
    WishlistItemCreate,
    WishlistItemDetailResponse,
)

from .actor import CUSTOMER_ONLY, Actor, require_role
from .base import BaseService, utc_now
from .catalog import is_product_sellable, is_variant_sellable
from .exceptions import BusinessRuleError, ConflictError, NotFoundError

_CENT = Decimal("0.01")


class WishlistService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.wishlists = WishlistRepository(session)
        self.items = WishlistItemRepository(session)
        self.products = ProductRepository(session)

    def get_wishlist(self, actor: Actor) -> WishlistDetailResponse:
        """Xem wishlist; ẩn các sản phẩm đã bị xóa (dòng wishlist vẫn được giữ)."""
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            wishlist = self._get_or_create(actor.user_id)
            items = self.items.list_by_wishlist(wishlist.WishlistId, with_product=True)
            return WishlistDetailResponse(
                WishlistId=wishlist.WishlistId,
                CreatedAt=wishlist.CreatedAt,
                Items=[WishlistItemDetailResponse.model_validate(i) for i in items if not i.product.IsDeleted],
            )

    def add_item(self, actor: Actor, data: WishlistItemCreate) -> WishlistItemDetailResponse:
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            product = self.products.get_by_id(data.ProductId)
            if not is_product_sellable(product):
                raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
            wishlist = self._get_or_create(actor.user_id)
            if self.items.get_by_wishlist_and_product(wishlist.WishlistId, data.ProductId) is not None:
                raise ConflictError("Sản phẩm đã có trong danh sách yêu thích", code="wishlist_item_exists")
            item = self.items.create({"WishlistId": wishlist.WishlistId, "ProductId": data.ProductId})
            self.items.flush()
            return WishlistItemDetailResponse.model_validate(item)

    def remove_item(self, actor: Actor, wishlist_item_id: uuid.UUID) -> None:
        """Xóa dòng wishlist (không ảnh hưởng Product)."""
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            wishlist = self.wishlists.get_by_user(actor.user_id)
            item = self.items.get_by_id(wishlist_item_id) if wishlist else None
            if item is None or item.WishlistId != wishlist.WishlistId:
                raise NotFoundError("Không tìm thấy sản phẩm trong danh sách yêu thích", code="wishlist_item_not_found")
            self.items.delete(item)

    def remove_product(self, actor: Actor, product_id: uuid.UUID) -> None:
        """Xóa sản phẩm khỏi wishlist theo ProductId."""
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            wishlist = self.wishlists.get_by_user(actor.user_id)
            item = self.items.get_by_wishlist_and_product(wishlist.WishlistId, product_id) if wishlist else None
            if item is None:
                raise NotFoundError("Không tìm thấy sản phẩm trong danh sách yêu thích", code="wishlist_item_not_found")
            self.items.delete(item)

    def _get_or_create(self, user_id: uuid.UUID) -> Wishlist:
        wishlist = self.wishlists.get_by_user(user_id)
        if wishlist is not None:
            return wishlist
        try:
            with self.session.begin_nested():
                wishlist = self.wishlists.create({"UserId": user_id})
                self.wishlists.flush()
        except IntegrityError:
            # Request khác vừa tạo wishlist cho cùng user (UNIQUE UserId).
            wishlist = self.wishlists.get_by_user(user_id)
            if wishlist is None:
                raise
        return wishlist


class CartService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.carts = CartRepository(session)
        self.items = CartItemRepository(session)
        self.variants = ProductVariantRepository(session)

    # ------------------------------------------------------------------ xem

    def get_cart(self, actor: Actor) -> CartSummaryResponse:
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            return self._summary(self._get_or_create(actor.user_id))

    # ------------------------------------------------------------------ thêm / sửa / xóa

    def add_item(self, actor: Actor, data: CartItemCreate) -> CartSummaryResponse:
        """Thêm biến thể vào giỏ; nếu đã có thì cộng dồn Quantity (không tạo dòng trùng)."""
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            variant = self.variants.get_by_id(data.ProductVariantId)
            if not is_variant_sellable(variant):
                raise NotFoundError("Không tìm thấy sản phẩm hoặc sản phẩm không còn bán", code="variant_not_available")
            cart = self._get_or_create(actor.user_id)
            item = self.items.get_by_cart_and_variant(cart.CartId, variant.ProductVariantId)
            quantity = data.Quantity + (item.Quantity if item else 0)
            self._ensure_stock(variant.StockQuantity, quantity)
            if item is None:
                values = {
                    "CartId": cart.CartId,
                    "ProductVariantId": variant.ProductVariantId,
                    "Quantity": quantity,
                    "UnitPrice": variant.Price,
                }
                if data.IsSelected is not None:
                    values["IsSelected"] = data.IsSelected
                self.items.create(values)
            else:
                item.Quantity = quantity
                item.UnitPrice = variant.Price
                if data.IsSelected is not None:
                    item.IsSelected = data.IsSelected
            self.items.flush()
            return self._summary(cart)

    def update_item(self, actor: Actor, cart_item_id: uuid.UUID, data: CartItemUpdate) -> CartSummaryResponse:
        """Cập nhật số lượng và/hoặc chọn/bỏ chọn một dòng trong giỏ của chính người dùng."""
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            cart, item = self._get_owned_item(actor.user_id, cart_item_id)
            values = data.model_dump(exclude_unset=True)
            if "Quantity" in values:
                variant = self.variants.get_by_id(item.ProductVariantId)
                if not is_variant_sellable(variant):
                    raise BusinessRuleError("Sản phẩm không còn bán", code="variant_not_available")
                self._ensure_stock(variant.StockQuantity, values["Quantity"])
            self.items.update(item, values)
            self.items.flush()
            return self._summary(cart)

    def set_all_selected(self, actor: Actor, is_selected: bool) -> CartSummaryResponse:
        """Chọn hoặc bỏ chọn toàn bộ dòng trong giỏ."""
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            cart = self._get_or_create(actor.user_id)
            for item in self.items.list_by_cart(cart.CartId):
                item.IsSelected = is_selected
            self.items.flush()
            return self._summary(cart)

    def remove_item(self, actor: Actor, cart_item_id: uuid.UUID) -> CartSummaryResponse:
        require_role(actor, *CUSTOMER_ONLY)
        with self.transaction():
            cart, item = self._get_owned_item(actor.user_id, cart_item_id)
            self.items.delete(item)
            self.items.flush()
            return self._summary(cart)

    # ------------------------------------------------------------------ helpers

    def _get_or_create(self, user_id: uuid.UUID) -> Cart:
        cart = self.carts.get_by_user(user_id)
        if cart is not None:
            return cart
        try:
            with self.session.begin_nested():
                cart = self.carts.create({"UserId": user_id})
                self.carts.flush()
        except IntegrityError:
            # Request khác vừa tạo cart cho cùng user (UNIQUE UserId).
            cart = self.carts.get_by_user(user_id)
            if cart is None:
                raise
        return cart

    def _get_owned_item(self, user_id: uuid.UUID, cart_item_id: uuid.UUID) -> tuple[Cart, CartItem]:
        cart = self.carts.get_by_user(user_id)
        item = self.items.get_by_id_and_cart(cart_item_id, cart.CartId) if cart else None
        if item is None:
            raise NotFoundError("Không tìm thấy sản phẩm trong giỏ hàng", code="cart_item_not_found")
        return cart, item

    @staticmethod
    def _ensure_stock(stock_quantity: int, quantity: int) -> None:
        """Số lượng trong giỏ không vượt tồn kho hiện tại (chỉ kiểm tra, không giữ chỗ)."""
        if quantity > stock_quantity:
            raise BusinessRuleError(
                f"Số lượng vượt tồn kho hiện có ({stock_quantity})", code="insufficient_stock"
            )

    def _summary(self, cart: Cart) -> CartSummaryResponse:
        """Tính giỏ hàng từ giá, trạng thái bán và tồn kho hiện tại."""
        lines = []
        selected_quantity = 0
        selected_subtotal = Decimal("0")
        for item in self.items.list_by_cart(cart.CartId, with_variant=True):
            variant = item.product_variant
            line_total = (variant.Price * item.Quantity).quantize(_CENT)
            available = is_variant_sellable(variant) and item.Quantity <= variant.StockQuantity
            if item.IsSelected and available:
                selected_quantity += item.Quantity
                selected_subtotal += line_total
            lines.append(
                CartLineResponse(
                    CartItemId=item.CartItemId,
                    ProductVariantId=variant.ProductVariantId,
                    ProductId=variant.ProductId,
                    ProductName=variant.product.Name,
                    VariantName=variant.VariantName,
                    Sku=variant.Sku,
                    Quantity=item.Quantity,
                    UnitPrice=item.UnitPrice,
                    CurrentPrice=variant.Price,
                    LineTotal=line_total,
                    IsSelected=item.IsSelected,
                    IsAvailable=available,
                    StockQuantity=variant.StockQuantity,
                    AddedAt=item.AddedAt,
                )
            )
        return CartSummaryResponse(
            CartId=cart.CartId,
            CreatedAt=cart.CreatedAt,
            UpdatedAt=cart.UpdatedAt,
            Items=lines,
            SelectedQuantity=selected_quantity,
            SelectedSubtotal=selected_subtotal.quantize(_CENT),
        )
