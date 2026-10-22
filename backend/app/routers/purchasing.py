"""Purchasing and inventory APIs (Staff/Admin): suppliers, purchase orders, receiving and stock adjustments.

Approval steps (decide, close) and stock adjustments are Admin-only inside the Services.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.schemas import (
    LowStockVariantResponse,
    PageResponse,
    PurchaseOrderClose,
    PurchaseOrderCreate,
    PurchaseOrderDecision,
    PurchaseOrderDetailResponse,
    PurchaseOrderItemCreate,
    PurchaseOrderItemUpdate,
    PurchaseOrderReceive,
    PurchaseOrderResponse,
    PurchaseOrderUpdate,
    PurchaseReceiptResponse,
    StockAdjustmentCreate,
    StockAdjustmentResponse,
    StockOpeningCreate,
    StockQuantityUpdate,
    StockQuantityResponse,
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)
from app.services.inventory import InventoryService
from app.services.purchasing import PurchaseOrderService, SupplierService

from .dependencies import (
    CurrentActor,
    InternalOnly,
    Page,
    PageSize,
    get_inventory_service,
    get_purchase_order_service,
    get_supplier_service,
)

admin_router = APIRouter(prefix="/admin", tags=["Nhập hàng và kho"], dependencies=[InternalOnly])

Suppliers = Annotated[SupplierService, Depends(get_supplier_service)]
PurchaseOrders = Annotated[PurchaseOrderService, Depends(get_purchase_order_service)]
Inventory = Annotated[InventoryService, Depends(get_inventory_service)]


# ------------------------------------------------------------------ suppliers


@admin_router.get("/suppliers", response_model=PageResponse[SupplierResponse])
def list_suppliers(service: Suppliers, actor: CurrentActor, active_only: bool = False,
                   page: Page = 1, page_size: PageSize = 20):
    return service.list_suppliers(actor, active_only=active_only, page=page, page_size=page_size)


@admin_router.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
def get_supplier(supplier_id: uuid.UUID, service: Suppliers, actor: CurrentActor):
    return service.get_supplier(actor, supplier_id)


@admin_router.post("/suppliers", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(data: SupplierCreate, service: Suppliers, actor: CurrentActor):
    return service.create_supplier(actor, data)


@admin_router.patch("/suppliers/{supplier_id}", response_model=SupplierResponse)
def update_supplier(supplier_id: uuid.UUID, data: SupplierUpdate, service: Suppliers, actor: CurrentActor):
    return service.update_supplier(actor, supplier_id, data)


@admin_router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(supplier_id: uuid.UUID, service: Suppliers, actor: CurrentActor):
    service.delete_supplier(actor, supplier_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ purchase orders


@admin_router.get("/purchase-orders", response_model=PageResponse[PurchaseOrderResponse])
def list_purchase_orders(service: PurchaseOrders, actor: CurrentActor, code: str | None = None,
                         status_filter: Annotated[str | None, Query(alias="status")] = None,
                         supplier_id: uuid.UUID | None = None, created_by_user_id: uuid.UUID | None = None,
                         page: Page = 1, page_size: PageSize = 20):
    return service.list_purchase_orders(actor, code=code, status=status_filter, supplier_id=supplier_id,
                                        created_by_user_id=created_by_user_id, page=page, page_size=page_size)


@admin_router.get("/purchase-orders/{purchase_order_id}", response_model=PurchaseOrderDetailResponse)
def get_purchase_order(purchase_order_id: uuid.UUID, service: PurchaseOrders, actor: CurrentActor):
    return service.get_purchase_order(actor, purchase_order_id)


@admin_router.post("/purchase-orders", response_model=PurchaseOrderDetailResponse,
                   status_code=status.HTTP_201_CREATED)
def create_purchase_order(data: PurchaseOrderCreate, service: PurchaseOrders, actor: CurrentActor):
    return service.create_purchase_order(actor, data)


@admin_router.patch("/purchase-orders/{purchase_order_id}", response_model=PurchaseOrderDetailResponse)
def update_purchase_order(purchase_order_id: uuid.UUID, data: PurchaseOrderUpdate, service: PurchaseOrders,
                          actor: CurrentActor):
    return service.update_purchase_order(actor, purchase_order_id, data)


@admin_router.post("/purchase-orders/{purchase_order_id}/items", response_model=PurchaseOrderDetailResponse)
def add_purchase_order_item(purchase_order_id: uuid.UUID, data: PurchaseOrderItemCreate, service: PurchaseOrders,
                            actor: CurrentActor):
    return service.add_item(actor, purchase_order_id, data)


@admin_router.patch("/purchase-orders/{purchase_order_id}/items/{purchase_order_item_id}",
                    response_model=PurchaseOrderDetailResponse)
def update_purchase_order_item(purchase_order_id: uuid.UUID, purchase_order_item_id: uuid.UUID,
                               data: PurchaseOrderItemUpdate, service: PurchaseOrders, actor: CurrentActor):
    return service.update_item(actor, purchase_order_id, purchase_order_item_id, data)


@admin_router.delete("/purchase-orders/{purchase_order_id}/items/{purchase_order_item_id}",
                     response_model=PurchaseOrderDetailResponse)
def remove_purchase_order_item(purchase_order_id: uuid.UUID, purchase_order_item_id: uuid.UUID,
                               service: PurchaseOrders, actor: CurrentActor):
    return service.remove_item(actor, purchase_order_id, purchase_order_item_id)


@admin_router.post("/purchase-orders/{purchase_order_id}/decision", response_model=PurchaseOrderDetailResponse)
def decide_purchase_order(purchase_order_id: uuid.UUID, data: PurchaseOrderDecision, service: PurchaseOrders,
                          actor: CurrentActor):
    return service.decide_purchase_order(actor, purchase_order_id, data)


@admin_router.delete("/purchase-orders/{purchase_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order(purchase_order_id: uuid.UUID, service: PurchaseOrders, actor: CurrentActor):
    service.delete_purchase_order(actor, purchase_order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post("/purchase-orders/{purchase_order_id}/receive", response_model=PurchaseOrderDetailResponse)
def receive_purchase_order(purchase_order_id: uuid.UUID, data: PurchaseOrderReceive, service: PurchaseOrders,
                           actor: CurrentActor):
    return service.receive_items(actor, purchase_order_id, data)


@admin_router.post("/purchase-orders/{purchase_order_id}/close", response_model=PurchaseOrderDetailResponse)
def close_purchase_order(purchase_order_id: uuid.UUID, data: PurchaseOrderClose, service: PurchaseOrders,
                         actor: CurrentActor):
    return service.close_purchase_order(actor, purchase_order_id, data)


@admin_router.get("/purchase-orders/{purchase_order_id}/receipts", response_model=list[PurchaseReceiptResponse])
def list_purchase_receipts(purchase_order_id: uuid.UUID, service: PurchaseOrders, actor: CurrentActor):
    return service.list_receipts(actor, purchase_order_id)


# ------------------------------------------------------------------ inventory


@admin_router.get("/inventory/low-stock", response_model=PageResponse[LowStockVariantResponse])
def list_low_stock(service: Inventory, actor: CurrentActor, page: Page = 1, page_size: PageSize = 20):
    return service.list_low_stock(actor, page=page, page_size=page_size)


@admin_router.get("/inventory/adjustments", response_model=PageResponse[StockAdjustmentResponse])
def list_stock_adjustments(service: Inventory, actor: CurrentActor, variant_id: uuid.UUID | None = None,
                           adjustment_type: str | None = None, page: Page = 1, page_size: PageSize = 20):
    return service.list_adjustments(actor, variant_id=variant_id, adjustment_type=adjustment_type,
                                    page=page, page_size=page_size)


@admin_router.post("/variants/{variant_id}/stock-opening", response_model=StockAdjustmentResponse,
                   status_code=status.HTTP_201_CREATED)
def declare_stock_opening(variant_id: uuid.UUID, data: StockOpeningCreate, service: Inventory, actor: CurrentActor):
    return service.declare_opening(actor, variant_id, data)


@admin_router.post("/variants/{variant_id}/stock-adjustments", response_model=StockAdjustmentResponse,
                   status_code=status.HTTP_201_CREATED)
def adjust_stock(variant_id: uuid.UUID, data: StockAdjustmentCreate, service: Inventory, actor: CurrentActor):
    return service.adjust_stock(actor, variant_id, data)


@admin_router.patch("/variants/{variant_id}/stock", response_model=StockQuantityResponse)
def set_stock_quantity(variant_id: uuid.UUID, data: StockQuantityUpdate, service: Inventory, actor: CurrentActor):
    """Direct quantity edit, Admin-only; does not create an adjustment/history record."""
    return service.set_stock_quantity(actor, variant_id, data)
