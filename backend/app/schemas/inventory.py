"""Schemas cho nghiệp vụ kho: khai báo tồn đầu kỳ (Opening), điều chỉnh kho thủ công, cảnh báo tồn thấp.

Người thực hiện (AdjustedByUserId), số lượng/giá vốn trước-sau do server ghi; client không gửi.
"""

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from .common import Money, NonBlankText, NonNegativeInt, RequestSchema, ResponseSchema, SerialNumberValue


class StockOpeningCreate(RequestSchema):
    """Khai báo tồn đầu kỳ cho một biến thể (một lần): đặt StockQuantity = Quantity và CostPrice = UnitCost.

    SerialNumbers: serial mới cho biến thể IsSerialTracked; tổng serial Available sau khai báo phải bằng Quantity.
    """

    Quantity: NonNegativeInt
    UnitCost: Money
    Reason: NonBlankText
    SerialNumbers: list[SerialNumberValue] = Field(default_factory=list)


class StockAdjustmentCreate(RequestSchema):
    """Điều chỉnh kho thủ công: QuantityChange > 0 tăng, < 0 giảm; không được bằng 0. Giá vốn giữ nguyên.

    SerialNumbers: bắt buộc với biến thể IsSerialTracked (đúng bằng |QuantityChange|): serial mới khi tăng,
    serial đang có trong kho khi giảm. Phải rỗng với biến thể không quản lý serial.
    """

    QuantityChange: int
    Reason: NonBlankText
    SerialNumbers: list[SerialNumberValue] = Field(default_factory=list)

    @field_validator("QuantityChange")
    @classmethod
    def _not_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("QuantityChange phải khác 0")
        return value


class StockAdjustmentResponse(ResponseSchema):
    StockAdjustmentId: uuid.UUID
    ProductVariantId: uuid.UUID
    AdjustedByUserId: uuid.UUID
    AdjustmentType: str
    QuantityBefore: NonNegativeInt
    QuantityChange: int
    QuantityAfter: NonNegativeInt
    CostPriceBefore: Money
    CostPriceAfter: Money
    Reason: str
    CreatedAt: datetime


class LowStockVariantResponse(ResponseSchema):
    """Biến thể đang ở mức cảnh báo: StockQuantity <= MinStockLevel (MinStockLevel > 0)."""

    ProductVariantId: uuid.UUID
    ProductId: uuid.UUID
    Sku: str
    VariantName: str
    StockQuantity: NonNegativeInt
    MinStockLevel: NonNegativeInt
