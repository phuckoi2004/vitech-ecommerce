"""Schemas cho Wishlists, WishlistItems, Carts, CartItems.

Wishlist/Cart thuộc người dùng đăng nhập (1-1), nên không nhận UserId từ client.
"""

import uuid
from datetime import datetime

from .common import Money, PositiveInt, RequestSchema, ResponseSchema, relation_field

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
