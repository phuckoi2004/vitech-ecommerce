"""Repositories cho Suppliers, PurchaseOrders, PurchaseOrderItems.

Không cập nhật tồn kho hoặc CostPrice (thuộc Service).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import PurchaseOrder, PurchaseOrderItem, Supplier

from .base import BaseRepository


class SupplierRepository(BaseRepository[Supplier]):
    model = Supplier

    def get_by_code(self, supplier_code: str) -> Supplier | None:
        return self.get_one(Supplier.SupplierCode == supplier_code)

    def exists_by_code(self, supplier_code: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [Supplier.SupplierCode == supplier_code]
        if exclude_id is not None:
            conditions.append(Supplier.SupplierId != exclude_id)
        return self.exists(*conditions)

    def list_suppliers(
        self, *, is_active: bool | None = None, offset: int | None = None, limit: int | None = None
    ) -> list[Supplier]:
        conditions = [] if is_active is None else [Supplier.IsActive.is_(is_active)]
        return self.get_all(*conditions, order_by=(Supplier.Name, Supplier.SupplierId), offset=offset, limit=limit)

    def count_suppliers(self, *, is_active: bool | None = None) -> int:
        return self.count(*([] if is_active is None else [Supplier.IsActive.is_(is_active)]))


class PurchaseOrderRepository(BaseRepository[PurchaseOrder]):
    model = PurchaseOrder

    def get_by_code(self, purchase_order_code: str) -> PurchaseOrder | None:
        return self.get_one(PurchaseOrder.PurchaseOrderCode == purchase_order_code)

    def exists_by_code(self, purchase_order_code: str) -> bool:
        return self.exists(PurchaseOrder.PurchaseOrderCode == purchase_order_code)

    def get_detail(self, purchase_order_id: uuid.UUID) -> PurchaseOrder | None:
        """PurchaseOrder kèm Items (cho PurchaseOrderDetailResponse)."""
        stmt = (
            select(PurchaseOrder)
            .where(PurchaseOrder.PurchaseOrderId == purchase_order_id)
            .options(selectinload(PurchaseOrder.items))
        )
        return self.session.scalars(stmt).one_or_none()

    def _filters(self, status: str | None, supplier_id: uuid.UUID | None, created_by_user_id: uuid.UUID | None) -> list:
        conditions = []
        if status is not None:
            conditions.append(PurchaseOrder.Status == status)
        if supplier_id is not None:
            conditions.append(PurchaseOrder.SupplierId == supplier_id)
        if created_by_user_id is not None:
            conditions.append(PurchaseOrder.CreatedByUserId == created_by_user_id)
        return conditions

    def list_purchase_orders(
        self,
        *,
        status: str | None = None,
        supplier_id: uuid.UUID | None = None,
        created_by_user_id: uuid.UUID | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[PurchaseOrder]:
        return self.get_all(
            *self._filters(status, supplier_id, created_by_user_id),
            order_by=(PurchaseOrder.CreatedAt.desc(), PurchaseOrder.PurchaseOrderId),
            offset=offset,
            limit=limit,
        )

    def count_purchase_orders(
        self,
        *,
        status: str | None = None,
        supplier_id: uuid.UUID | None = None,
        created_by_user_id: uuid.UUID | None = None,
    ) -> int:
        return self.count(*self._filters(status, supplier_id, created_by_user_id))


class PurchaseOrderItemRepository(BaseRepository[PurchaseOrderItem]):
    model = PurchaseOrderItem

    def list_by_purchase_order(self, purchase_order_id: uuid.UUID) -> list[PurchaseOrderItem]:
        return self.get_all(
            PurchaseOrderItem.PurchaseOrderId == purchase_order_id,
            order_by=(PurchaseOrderItem.PurchaseOrderItemId,),
        )

    def get_by_id_and_purchase_order(
        self, purchase_order_item_id: uuid.UUID, purchase_order_id: uuid.UUID
    ) -> PurchaseOrderItem | None:
        return self.get_one(
            PurchaseOrderItem.PurchaseOrderItemId == purchase_order_item_id,
            PurchaseOrderItem.PurchaseOrderId == purchase_order_id,
        )

    def list_by_variant(self, variant_id: uuid.UUID) -> list[PurchaseOrderItem]:
        return self.get_all(
            PurchaseOrderItem.ProductVariantId == variant_id,
            order_by=(PurchaseOrderItem.PurchaseOrderItemId,),
        )
