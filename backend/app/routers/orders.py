"""Order APIs: checkout and order history (Customer), order processing and shipping methods (Staff/Admin).

PaymentStatus is never set directly here: it changes only through payment/COD use cases (see payments.py).
Date filters must carry a timezone (e.g. ``2026-10-01T00:00:00+07:00``); a naive value would be read as UTC.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import AwareDatetime

from app.schemas import (
    AdminOrderDetailResponse,
    AdminOrderResponse,
    AdminOrderStatusHistoryResponse,
    CodDeliveryConfirm,
    OrderAdminUpdate,
    OrderCancelRequest,
    OrderCogsResponse,
    OrderCreate,
    OrderDetailResponse,
    OrderItemResponse,
    OrderItemSerialsResponse,
    OrderSerialAssign,
    OrderStatusHistoryResponse,
    OrderStatusUpdate,
    OrderSummary,
    PageResponse,
    ShipmentReturnReceive,
    ShipmentReturnResponse,
    ShippingMethodCreate,
    ShippingMethodResponse,
    ShippingMethodUpdate,
)
from app.services.order import OrderService
from app.services.shipping_method import ShippingMethodService

from .dependencies import CurrentActor, InternalOnly, OptionalActor, Page, PageSize, get_order_service, get_shipping_method_service

router = APIRouter(tags=["Đơn hàng"])
admin_router = APIRouter(prefix="/admin", tags=["Quản lý đơn hàng"], dependencies=[InternalOnly])

Orders = Annotated[OrderService, Depends(get_order_service)]
ShippingMethods = Annotated[ShippingMethodService, Depends(get_shipping_method_service)]


# ------------------------------------------------------------------ shipping methods


@router.get("/shipping-methods", response_model=list[ShippingMethodResponse])
def list_shipping_methods(service: ShippingMethods, actor: OptionalActor, active_only: bool = True):
    return service.list_shipping_methods(actor=actor, active_only=active_only)


@router.get("/shipping-methods/{shipping_method_id}", response_model=ShippingMethodResponse)
def get_shipping_method(shipping_method_id: uuid.UUID, service: ShippingMethods, actor: OptionalActor):
    return service.get_shipping_method(shipping_method_id, actor=actor)


@admin_router.post("/shipping-methods", response_model=ShippingMethodResponse, status_code=status.HTTP_201_CREATED)
def create_shipping_method(data: ShippingMethodCreate, service: ShippingMethods, actor: CurrentActor):
    return service.create_shipping_method(actor, data)


@admin_router.patch("/shipping-methods/{shipping_method_id}", response_model=ShippingMethodResponse)
def update_shipping_method(shipping_method_id: uuid.UUID, data: ShippingMethodUpdate, service: ShippingMethods,
                           actor: CurrentActor):
    return service.update_shipping_method(actor, shipping_method_id, data)


@admin_router.delete("/shipping-methods/{shipping_method_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shipping_method(shipping_method_id: uuid.UUID, service: ShippingMethods, actor: CurrentActor):
    service.delete_shipping_method(actor, shipping_method_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ customer orders


@router.post("/orders", response_model=OrderDetailResponse, status_code=status.HTTP_201_CREATED)
def create_order(data: OrderCreate, service: Orders, actor: CurrentActor):
    return service.create_order(actor, data)


@router.get("/orders", response_model=PageResponse[OrderSummary])
def list_my_orders(service: Orders, actor: CurrentActor, order_code: str | None = None,
                   order_status: str | None = None, ordered_from: AwareDatetime | None = None,
                   ordered_to: AwareDatetime | None = None, page: Page = 1, page_size: PageSize = 20):
    """Order history; ``ordered_from``/``ordered_to`` form a half-open range [from, to)."""
    return service.search_customer_orders(actor, order_code=order_code, order_status=order_status,
                                          ordered_from=ordered_from, ordered_to=ordered_to,
                                          page=page, page_size=page_size)


@router.get("/orders/items/{order_item_id}", response_model=OrderItemResponse)
def get_my_order_item(order_item_id: uuid.UUID, service: Orders, actor: CurrentActor):
    return service.get_customer_order_item(actor, order_item_id)


@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
def get_my_order(order_id: uuid.UUID, service: Orders, actor: CurrentActor):
    return service.get_order(actor, order_id)


@router.get("/orders/{order_id}/history", response_model=list[OrderStatusHistoryResponse])
def get_my_order_history(order_id: uuid.UUID, service: Orders, actor: CurrentActor):
    return service.get_order_status_history(actor, order_id)


@router.post("/orders/{order_id}/cancel", response_model=OrderDetailResponse)
def cancel_my_order(order_id: uuid.UUID, data: OrderCancelRequest, service: Orders, actor: CurrentActor):
    return service.cancel_customer_order(actor, order_id, data)


# ------------------------------------------------------------------ order processing (Staff/Admin)


@admin_router.get("/orders", response_model=PageResponse[AdminOrderResponse])
def admin_list_orders(service: Orders, actor: CurrentActor, order_code: str | None = None,
                      customer_id: uuid.UUID | None = None, assigned_staff_id: uuid.UUID | None = None,
                      order_status: str | None = None, payment_status: str | None = None,
                      ordered_from: AwareDatetime | None = None, ordered_to: AwareDatetime | None = None,
                      page: Page = 1, page_size: PageSize = 20):
    return service.admin_list_orders(actor, order_code=order_code, customer_id=customer_id,
                                     assigned_staff_id=assigned_staff_id, order_status=order_status,
                                     payment_status=payment_status, ordered_from=ordered_from,
                                     ordered_to=ordered_to, page=page, page_size=page_size)


@admin_router.get("/orders/{order_id}", response_model=AdminOrderDetailResponse)
def admin_get_order(order_id: uuid.UUID, service: Orders, actor: CurrentActor):
    return service.admin_get_order(actor, order_id)


@admin_router.get("/orders/{order_id}/history", response_model=list[AdminOrderStatusHistoryResponse])
def admin_get_order_history(order_id: uuid.UUID, service: Orders, actor: CurrentActor):
    return service.admin_get_order_status_history(actor, order_id)


@admin_router.get("/orders/{order_id}/cogs", response_model=OrderCogsResponse)
def get_order_cogs(order_id: uuid.UUID, service: Orders, actor: CurrentActor):
    return OrderCogsResponse(OrderId=order_id, Cogs=service.get_order_cogs(actor, order_id))


@admin_router.post("/orders/{order_id}/status", response_model=AdminOrderDetailResponse)
def update_order_status(order_id: uuid.UUID, data: OrderStatusUpdate, service: Orders, actor: CurrentActor):
    return service.update_order_status(actor, order_id, data)


@admin_router.post("/orders/{order_id}/confirm-cod-delivery", response_model=AdminOrderDetailResponse)
def confirm_cod_delivery(order_id: uuid.UUID, data: CodDeliveryConfirm, service: Orders, actor: CurrentActor):
    return service.confirm_cod_delivery(actor, order_id, note=data.Note)


@admin_router.patch("/orders/{order_id}", response_model=AdminOrderDetailResponse)
def update_order_admin_info(order_id: uuid.UUID, data: OrderAdminUpdate, service: Orders, actor: CurrentActor):
    return service.update_order_admin_info(actor, order_id, data)


@admin_router.get("/orders/{order_id}/serials", response_model=list[OrderItemSerialsResponse])
def get_order_serials(order_id: uuid.UUID, service: Orders, actor: CurrentActor):
    return service.get_order_serials(actor, order_id)


@admin_router.post("/orders/{order_id}/serials", response_model=list[OrderItemSerialsResponse])
def assign_order_serials(order_id: uuid.UUID, data: OrderSerialAssign, service: Orders, actor: CurrentActor):
    return service.assign_order_serials(actor, order_id, data)


@admin_router.delete("/orders/{order_id}/serials/{serial_number}", response_model=list[OrderItemSerialsResponse])
def release_order_serial(order_id: uuid.UUID, serial_number: str, service: Orders, actor: CurrentActor):
    return service.release_order_serial(actor, order_id, serial_number)


# ------------------------------------------------------------------ shipment returns (Staff/Admin)


@admin_router.get("/shipment-returns", response_model=PageResponse[ShipmentReturnResponse])
def list_shipment_returns(service: Orders, actor: CurrentActor,
                          status_filter: Annotated[str | None, Query(alias="status")] = None,
                          page: Page = 1, page_size: PageSize = 20):
    return service.list_shipment_returns(actor, status=status_filter, page=page, page_size=page_size)


@admin_router.get("/orders/{order_id}/shipment-return", response_model=ShipmentReturnResponse)
def get_shipment_return(order_id: uuid.UUID, service: Orders, actor: CurrentActor):
    return service.get_shipment_return(actor, order_id)


@admin_router.post("/orders/{order_id}/shipment-return/receive", response_model=ShipmentReturnResponse)
def receive_shipment_return(order_id: uuid.UUID, data: ShipmentReturnReceive, service: Orders, actor: CurrentActor):
    return service.receive_shipment_return(actor, order_id, data)
