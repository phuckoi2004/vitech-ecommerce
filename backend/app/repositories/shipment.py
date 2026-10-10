"""Repositories cho ShipmentReturns / ShipmentReturnItems (hàng của đơn hủy khi đang giao, chờ quay về kho)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import ShipmentReturn, ShipmentReturnItem

from .base import BaseRepository


class ShipmentReturnRepository(BaseRepository[ShipmentReturn]):
    model = ShipmentReturn

    def get_by_order(self, order_id: uuid.UUID) -> ShipmentReturn | None:
        return self.session.scalars(
            select(ShipmentReturn).where(ShipmentReturn.OrderId == order_id).options(selectinload(ShipmentReturn.items))
        ).one_or_none()

    def get_by_order_for_update(self, order_id: uuid.UUID) -> ShipmentReturn | None:
        """Khóa hồ sơ của đơn (FOR UPDATE) trước khi ghi nhận nhận hàng."""
        rows = self._scalars_for_update(
            select(ShipmentReturn).where(ShipmentReturn.OrderId == order_id).with_for_update()
        )
        return rows[0] if rows else None

    def list_returns(
        self, *, status: str | None = None, offset: int | None = None, limit: int | None = None
    ) -> list[ShipmentReturn]:
        conditions = [] if status is None else [ShipmentReturn.Status == status]
        return self.get_all(
            *conditions,
            order_by=(ShipmentReturn.CreatedAt, ShipmentReturn.ShipmentReturnId),
            offset=offset,
            limit=limit,
            options=(selectinload(ShipmentReturn.items),),
        )

    def count_returns(self, *, status: str | None = None) -> int:
        return self.count(*([] if status is None else [ShipmentReturn.Status == status]))


class ShipmentReturnItemRepository(BaseRepository[ShipmentReturnItem]):
    model = ShipmentReturnItem

    def list_by_return(self, shipment_return_id: uuid.UUID) -> list[ShipmentReturnItem]:
        return self.get_all(
            ShipmentReturnItem.ShipmentReturnId == shipment_return_id,
            order_by=(ShipmentReturnItem.OrderItemId, ShipmentReturnItem.ShipmentReturnItemId),
        )
