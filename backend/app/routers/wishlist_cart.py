"""Wishlist and cart APIs of the signed-in customer (ownership comes from the Actor, never from the client)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.schemas import (
    CartItemCreate,
    CartItemUpdate,
    CartSelectAll,
    CartSummaryResponse,
    WishlistDetailResponse,
    WishlistItemCreate,
    WishlistItemDetailResponse,
)
from app.services.wishlist_cart import CartService, WishlistService

from .dependencies import CurrentActor, get_cart_service, get_wishlist_service

router = APIRouter(tags=["Yêu thích và giỏ hàng"])

Wishlist = Annotated[WishlistService, Depends(get_wishlist_service)]
Cart = Annotated[CartService, Depends(get_cart_service)]


@router.get("/wishlist", response_model=WishlistDetailResponse)
def get_wishlist(service: Wishlist, actor: CurrentActor):
    return service.get_wishlist(actor)


@router.post("/wishlist/items", response_model=WishlistItemDetailResponse, status_code=status.HTTP_201_CREATED)
def add_wishlist_item(data: WishlistItemCreate, service: Wishlist, actor: CurrentActor):
    return service.add_item(actor, data)


@router.delete("/wishlist/items/{wishlist_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_wishlist_item(wishlist_item_id: uuid.UUID, service: Wishlist, actor: CurrentActor):
    service.remove_item(actor, wishlist_item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/wishlist/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_wishlist_product(product_id: uuid.UUID, service: Wishlist, actor: CurrentActor):
    service.remove_product(actor, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/cart", response_model=CartSummaryResponse)
def get_cart(service: Cart, actor: CurrentActor):
    return service.get_cart(actor)


@router.post("/cart/items", response_model=CartSummaryResponse)
def add_cart_item(data: CartItemCreate, service: Cart, actor: CurrentActor):
    """Adding a variant already in the cart increases its quantity, so the whole cart is returned."""
    return service.add_item(actor, data)


@router.patch("/cart/items/{cart_item_id}", response_model=CartSummaryResponse)
def update_cart_item(cart_item_id: uuid.UUID, data: CartItemUpdate, service: Cart, actor: CurrentActor):
    return service.update_item(actor, cart_item_id, data)


@router.put("/cart/selection", response_model=CartSummaryResponse)
def select_all_cart_items(data: CartSelectAll, service: Cart, actor: CurrentActor):
    return service.set_all_selected(actor, data.IsSelected)


@router.delete("/cart/items/{cart_item_id}", response_model=CartSummaryResponse)
def remove_cart_item(cart_item_id: uuid.UUID, service: Cart, actor: CurrentActor):
    return service.remove_item(actor, cart_item_id)
