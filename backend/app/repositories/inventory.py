"""Repository cho StockAdjustments và StockAdjustmentSerials (lịch sử Opening/điều chỉnh kho). Chỉ ghi thêm."""

import uuid
from collections.abc import Collection
from typing import Any, NoReturn

from sqlalchemy import select

from app.models import StockAdjustment, StockAdjustmentSerial
from app.models.inventory import ADJUSTMENT_OPENING

from .base import BaseRepository


class StockAdjustmentRepository(BaseRepository[StockAdjustment]):
    model = StockAdjustment

    def has_opening(self, variant_id: uuid.UUID) -> bool:
        return self.exists(
            StockAdjustment.ProductVariantId == variant_id, StockAdjustment.AdjustmentType == ADJUSTMENT_OPENING
        )

    def _filters(self, variant_id: uuid.UUID | None, adjustment_type: str | None) -> list:
        conditions = []
        if variant_id is not None:
            conditions.append(StockAdjustment.ProductVariantId == variant_id)
        if adjustment_type is not None:
            conditions.append(StockAdjustment.AdjustmentType == adjustment_type)
        return conditions

    def list_adjustments(
        self,
        *,
        variant_id: uuid.UUID | None = None,
        adjustment_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[StockAdjustment]:
        return self.get_all(
            *self._filters(variant_id, adjustment_type),
            order_by=(StockAdjustment.CreatedAt.desc(), StockAdjustment.StockAdjustmentId),
            offset=offset,
            limit=limit,
        )

    def count_adjustments(self, *, variant_id: uuid.UUID | None = None, adjustment_type: str | None = None) -> int:
        return self.count(*self._filters(variant_id, adjustment_type))

    # Lịch sử không được sửa/xóa (database trigger cũng chặn).
    def update(self, obj: StockAdjustment, values: Any) -> NoReturn:
        raise PermissionError("StockAdjustments chỉ được ghi thêm")

    def delete(self, obj: StockAdjustment) -> NoReturn:
        raise PermissionError("StockAdjustments chỉ được ghi thêm")


class StockAdjustmentSerialRepository(BaseRepository[StockAdjustmentSerial]):
    """Serial thuộc phiếu điều chỉnh (In/Out). Chỉ ghi thêm (database trigger cũng chặn sửa/xóa)."""

    model = StockAdjustmentSerial

    def list_by_adjustment(self, adjustment_id: uuid.UUID) -> list[StockAdjustmentSerial]:
        return self.get_all(StockAdjustmentSerial.StockAdjustmentId == adjustment_id)

    def list_by_serial(self, serial_id: uuid.UUID) -> list[StockAdjustmentSerial]:
        return self.get_all(StockAdjustmentSerial.ProductSerialId == serial_id)

    def linked_serial_ids(self, serial_ids: Collection[uuid.UUID], direction: str) -> set[uuid.UUID]:
        """Các serial (trong ``serial_ids``) đã có liên kết theo chiều ``direction``."""
        if not serial_ids:
            return set()
        stmt = select(StockAdjustmentSerial.ProductSerialId).where(
            StockAdjustmentSerial.ProductSerialId.in_(list(serial_ids)), StockAdjustmentSerial.Direction == direction
        )
        return set(self.session.scalars(stmt))

    def update(self, obj: StockAdjustmentSerial, values: Any) -> NoReturn:
        raise PermissionError("StockAdjustmentSerials chỉ được ghi thêm")

    def delete(self, obj: StockAdjustmentSerial) -> NoReturn:
        raise PermissionError("StockAdjustmentSerials chỉ được ghi thêm")
