"""Schemas cho Suppliers, PurchaseOrders, PurchaseOrderItems (chỉ dành cho staff/admin)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, computed_field, model_validator

from .common import (
    Money,
    NonBlankText,
    NonNegativeInt,
    PositiveInt,
    PurchaseOrderStatus,
    RequestSchema,
    ResponseSchema,
    SerialNumberValue,
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

    @computed_field
    @property
    def MissingQuantity(self) -> int:
        """Số còn thiếu = OrderedQuantity − ReceivedQuantity (phiếu Closed: số nhà cung cấp giao thiếu)."""
        return self.OrderedQuantity - self.ReceivedQuantity


# ---------------------------------------------------------------------------
# PurchaseOrders
# ---------------------------------------------------------------------------


class PurchaseOrderCreate(RequestSchema):
    """PurchaseOrderCode, TotalAmount, Status do server gán; CreatedByUserId lấy từ người dùng đăng nhập."""

    NULLABLE_FIELDS = frozenset({"Note"})

    SupplierId: uuid.UUID
    Note: str | None = None
    Items: list[PurchaseOrderItemCreate] = Field(min_length=1)


class PurchaseOrderUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Note"})

    SupplierId: uuid.UUID | None = None
    Note: str | None = None


class PurchaseOrderDecision(RequestSchema):
    """Admin duyệt / từ chối phiếu nhập do Staff lập (DecidedByUserId, DecidedAt do server gán).

    Từ chối bắt buộc có RejectReason không rỗng (đã bỏ khoảng trắng đầu/cuối); duyệt thì không có RejectReason.
    """

    NULLABLE_FIELDS = frozenset({"RejectReason"})

    Status: Literal["Approved", "Rejected"]
    RejectReason: NonBlankText | None = None

    @model_validator(mode="after")
    def _reason_matches_decision(self):
        if self.Status == "Rejected" and self.RejectReason is None:
            raise ValueError("Từ chối phiếu nhập phải có RejectReason")
        if self.Status == "Approved" and self.RejectReason is not None:
            raise ValueError("RejectReason chỉ dùng khi từ chối")
        return self


class PurchaseOrderStatusUpdate(RequestSchema):
    """KHÔNG nối trực tiếp vào API như lệnh đặt Status phiếu nhập (đợt 5.10; hiện không Service nào dùng).

    Trạng thái phiếu chỉ đổi qua nghiệp vụ của PurchaseOrderService: gửi/duyệt/từ chối (PurchaseOrderDecision), nhận
    hàng (Receiving/Completed cùng tồn kho, giá vốn, serial), hủy, đóng phiếu nhận thiếu (Closed có lý do). Đặt trực tiếp
    Approved/Completed/Closed sẽ bỏ qua phê duyệt, nhập kho và lịch sử. Test tests/test_status_schema_guard chặn việc
    dùng schema này ngoài app/schemas.
    """

    Status: PurchaseOrderStatus


class PurchaseOrderReceiveItem(RequestSchema):
    """Số lượng thực nhận thêm trong lần nhận hàng này cho một dòng phiếu nhập.

    SerialNumbers: bắt buộc với biến thể IsSerialTracked (đúng bằng Quantity), phải rỗng với biến thể khác.
    """

    PurchaseOrderItemId: uuid.UUID
    Quantity: PositiveInt
    SerialNumbers: list[SerialNumberValue] = Field(default_factory=list)


class PurchaseOrderReceive(RequestSchema):
    """Một lần nhận hàng (có thể gồm nhiều dòng); xử lý trong một transaction và ghi lịch sử PurchaseReceipts."""

    NULLABLE_FIELDS = frozenset({"Note"})

    Items: list[PurchaseOrderReceiveItem] = Field(min_length=1)
    Note: str | None = None


class PurchaseOrderClose(RequestSchema):
    """Admin đóng phiếu còn thiếu hàng (nhà cung cấp giao thiếu); lý do bắt buộc."""

    Reason: NonBlankText


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
    ClosedByUserId: uuid.UUID | None
    ClosedAt: datetime | None
    CloseReason: str | None


class PurchaseOrderDetailResponse(PurchaseOrderResponse):
    Items: list[PurchaseOrderItemResponse] = relation_field("items")


# ---------------------------------------------------------------------------
# PurchaseReceipts (lịch sử nhận hàng; chỉ đọc)
# ---------------------------------------------------------------------------


class PurchaseReceiptItemResponse(ResponseSchema):
    PurchaseOrderItemId: uuid.UUID
    Quantity: PositiveInt
    UnitPrice: Money


class PurchaseReceiptResponse(ResponseSchema):
    PurchaseReceiptId: uuid.UUID
    PurchaseOrderId: uuid.UUID
    ReceivedByUserId: uuid.UUID
    ReceivedAt: datetime
    Note: str | None
    Items: list[PurchaseReceiptItemResponse] = relation_field("items")
