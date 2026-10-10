"""Schemas cho Wishlists, WishlistItems, Carts, CartItems.

Wishlist/Cart thuộc người dùng đăng nhập (1-1), nên không nhận UserId từ client.
"""

import uuid
from datetime import datetime

from .catalog import ProductSummary
from .common import Money, NonNegativeInt, PositiveInt, RequestSchema, ResponseSchema, relation_field

# ---------------------------------------------------------------------------
# Wishlist
# ---------------------------------------------------------------------------


class WishlistItemCreate(RequestSchema):
    ProductId: uuid.UUID


class WishlistItemResponse(ResponseSchema):
    WishlistItemId: uuid.UUID
    ProductId: uuid.UUID
    AddedAt: datetime


class WishlistResponse(ResponseSchema):
    WishlistId: uuid.UUID
    CreatedAt: datetime
    Items: list[WishlistItemResponse] = relation_field("items")


class WishlistItemDetailResponse(WishlistItemResponse):
    """Dòng wishlist kèm thông tin sản phẩm để hiển thị."""

    Product: ProductSummary = relation_field("product")


class WishlistDetailResponse(ResponseSchema):
    WishlistId: uuid.UUID
    CreatedAt: datetime
    Items: list[WishlistItemDetailResponse]


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


class CartItemCreate(RequestSchema):
    """UnitPrice do server lấy từ ProductVariants.Price, không nhận từ client."""

    ProductVariantId: uuid.UUID
    Quantity: PositiveInt
    IsSelected: bool | None = None


class CartItemUpdate(RequestSchema):
    Quantity: PositiveInt | None = None
    IsSelected: bool | None = None


class CartItemResponse(ResponseSchema):
    CartItemId: uuid.UUID
    ProductVariantId: uuid.UUID
    Quantity: PositiveInt
    UnitPrice: Money
    IsSelected: bool
    AddedAt: datetime


class CartResponse(ResponseSchema):
    CartId: uuid.UUID
    CreatedAt: datetime
    UpdatedAt: datetime
    Items: list[CartItemResponse] = relation_field("items")


class CartLineResponse(ResponseSchema):
    """Dòng giỏ hàng tính theo dữ liệu hiện tại (giá, trạng thái bán, tồn kho).

    UnitPrice: giá lúc thêm vào giỏ; CurrentPrice: giá bán hiện tại; LineTotal = CurrentPrice × Quantity.
    IsAvailable: biến thể còn bán và Quantity không vượt tồn kho hiện tại.
    """

    CartItemId: uuid.UUID
    ProductVariantId: uuid.UUID
    ProductId: uuid.UUID
    ProductName: str
    VariantName: str
    Sku: str
    Quantity: PositiveInt
    UnitPrice: Money
    CurrentPrice: Money
    LineTotal: Money
    IsSelected: bool
    IsAvailable: bool
    StockQuantity: NonNegativeInt
    AddedAt: datetime


class CartSummaryResponse(ResponseSchema):
    """Giỏ hàng kèm tổng tiền tính ở server; SelectedSubtotal chỉ gồm dòng được chọn và còn khả dụng."""

    CartId: uuid.UUID
    CreatedAt: datetime
    UpdatedAt: datetime
    Items: list[CartLineResponse]
    SelectedQuantity: NonNegativeInt
    SelectedSubtotal: Money
