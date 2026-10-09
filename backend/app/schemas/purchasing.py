"""Schemas cho Suppliers, PurchaseOrders, PurchaseOrderItems (chỉ dành cho staff/admin)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import model_validator

from .common import (
    Money,
    NonNegativeInt,
    PositiveInt,
    PurchaseOrderStatus,
    RequestSchema,
    ResponseSchema,
    relation_field,
    varchar,
)

# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------


class SupplierCreate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Email", "TaxCode", "Note"})

    SupplierCode: varchar(50)
    Name: varchar(255)
    Email: varchar(255) | None = None
    PhoneNumber: varchar(20)
    Address: varchar(500)
    TaxCode: varchar(20) | None = None
    IsActive: bool | None = None
    Note: str | None = None


class SupplierUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Email", "TaxCode", "Note"})

    SupplierCode: varchar(50) | None = None
    Name: varchar(255) | None = None
    Email: varchar(255) | None = None
    PhoneNumber: varchar(20) | None = None
    Address: varchar(500) | None = None
    TaxCode: varchar(20) | None = None
    IsActive: bool | None = None
    Note: str | None = None


class SupplierResponse(ResponseSchema):
    SupplierId: uuid.UUID
    SupplierCode: str
    Name: str
    Email: str | None
    PhoneNumber: str
    Address: str
    TaxCode: str | None
    IsActive: bool
    Note: str | None


# ---------------------------------------------------------------------------
# PurchaseOrderItems
# ---------------------------------------------------------------------------


def _check_received(ordered: int | None, received: int | None) -> None:
    """CHECK "ReceivedQuantity" <= "OrderedQuantity"."""
    if ordered is not None and received is not None and received > ordered:
        raise ValueError("ReceivedQuantity không được lớn hơn OrderedQuantity")


class PurchaseOrderItemCreate(RequestSchema):
    """LineTotal do server tính; ReceivedQuantity khởi tạo bởi server."""

    NULLABLE_FIELDS = frozenset({"Note"})

    ProductVariantId: uuid.UUID
    OrderedQuantity: PositiveInt
    UnitPrice: Money
    Note: str | None = None


class PurchaseOrderItemUpdate(RequestSchema):
    """PATCH. Kiểm tra chéo khi gửi cả hai số lượng; service kiểm tra lại với giá trị đang lưu."""

    NULLABLE_FIELDS = frozenset({"Note"})

    OrderedQuantity: PositiveInt | None = None
    ReceivedQuantity: NonNegativeInt | None = None
    UnitPrice: Money | None = None
    Note: str | None = None

    @model_validator(mode="after")
    def _check_quantities(self):
        _check_received(self.OrderedQuantity, self.ReceivedQuantity)
        return self


class PurchaseOrderItemResponse(ResponseSchema):
    PurchaseOrderItemId: uuid.UUID
    PurchaseOrderId: uuid.UUID
    ProductVariantId: uuid.UUID
    OrderedQuantity: PositiveInt
    ReceivedQuantity: NonNegativeInt
    UnitPrice: Money
    LineTotal: Money
    Note: str | None


# ---------------------------------------------------------------------------
# PurchaseOrders
# ---------------------------------------------------------------------------


class PurchaseOrderCreate(RequestSchema):
    """PurchaseOrderCode, TotalAmount, Status do server gán; CreatedByUserId lấy từ người dùng đăng nhập."""

    NULLABLE_FIELDS = frozenset({"Note"})

    SupplierId: uuid.UUID
    Note: str | None = None
    Items: list[PurchaseOrderItemCreate]


class PurchaseOrderUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Note"})

    SupplierId: uuid.UUID | None = None
    Note: str | None = None


class PurchaseOrderDecision(RequestSchema):
    """Quản trị viên duyệt / từ chối phiếu nhập (DecidedByUserId, DecidedAt do server gán)."""

    NULLABLE_FIELDS = frozenset({"RejectReason"})

    Status: Literal["Approved", "Rejected"]
    RejectReason: str | None = None


class PurchaseOrderStatusUpdate(RequestSchema):
    Status: PurchaseOrderStatus


class PurchaseOrderResponse(ResponseSchema):
    PurchaseOrderId: uuid.UUID
    PurchaseOrderCode: str
    SupplierId: uuid.UUID
    CreatedByUserId: uuid.UUID
    DecidedByUserId: uuid.UUID | None
    TotalAmount: Money
    Status: PurchaseOrderStatus
    Note: str | None
    RejectReason: str | None
    CreatedAt: datetime
    DecidedAt: datetime | None


class PurchaseOrderDetailResponse(PurchaseOrderResponse):
    Items: list[PurchaseOrderItemResponse] = relation_field("items")
