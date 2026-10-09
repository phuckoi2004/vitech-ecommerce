"""Schemas cho ShippingMethods, Orders, OrderItems, OrderStatusHistories.

UnitCost (giá vốn tại thời điểm bán), InternalNote, AssignedStaffId chỉ có trong schema admin/staff.
"""

import uuid
from datetime import datetime

from pydantic import model_validator

from .common import (
    Money,
    OrderStatusValue,
    PaymentStatusValue,
    PositiveInt,
    RequestSchema,
    ResponseSchema,
    relation_field,
    varchar,
)

# ---------------------------------------------------------------------------
# ShippingMethods
# ---------------------------------------------------------------------------


class ShippingMethodCreate(RequestSchema):
    Code: varchar(50)
    Name: varchar(255)
    BaseFee: Money
    EstimatedDays: int
    IsActive: bool | None = None


class ShippingMethodUpdate(RequestSchema):
    Code: varchar(50) | None = None
    Name: varchar(255) | None = None
    BaseFee: Money | None = None
    EstimatedDays: int | None = None
    IsActive: bool | None = None


class ShippingMethodResponse(ResponseSchema):
    ShippingMethodId: uuid.UUID
    Code: str
    Name: str
    BaseFee: Money
    EstimatedDays: int
    IsActive: bool


# ---------------------------------------------------------------------------
# Orders - request
# ---------------------------------------------------------------------------


class OrderCreate(RequestSchema):
    """Khách hàng đặt hàng từ các CartItems đang được chọn (IsSelected).

    - Thông tin người nhận: truyền AddressId (server chụp lại từ Addresses) hoặc truyền đủ
      ReceiverName, ReceiverPhone, ShippingAddress.
    - CouponCode là Coupons.Code; server tra ra CouponId.
    - OrderCode, Subtotal, ShippingFee, DiscountAmount, TotalAmount, OrderStatus, PaymentStatus do server tính.
    """

    NULLABLE_FIELDS = frozenset({"AddressId", "CouponCode", "CustomerNote"})

    ShippingMethodId: uuid.UUID
    PaymentMethodId: uuid.UUID
    AddressId: uuid.UUID | None = None
    ReceiverName: varchar(255) | None = None
    ReceiverPhone: varchar(20) | None = None
    ShippingAddress: varchar(500) | None = None
    CouponCode: varchar(50) | None = None
    CustomerNote: str | None = None

    @model_validator(mode="after")
    def _receiver_required(self):
        # ReceiverName/ReceiverPhone/ShippingAddress là NOT NULL trong Orders.
        if self.AddressId is None and not (self.ReceiverName and self.ReceiverPhone and self.ShippingAddress):
            raise ValueError("Cần AddressId hoặc đủ ReceiverName, ReceiverPhone, ShippingAddress")
        return self


class OrderCancelRequest(RequestSchema):
    NULLABLE_FIELDS = frozenset({"CancelReason"})

    CancelReason: str | None = None


class OrderStatusUpdate(RequestSchema):
    """Staff/admin đổi trạng thái đơn; server ghi OrderStatusHistories và các mốc thời gian."""

    NULLABLE_FIELDS = frozenset({"Note", "CancelReason"})

    OrderStatus: OrderStatusValue
    Note: str | None = None
    CancelReason: str | None = None


class OrderPaymentStatusUpdate(RequestSchema):
    PaymentStatus: PaymentStatusValue


class OrderAdminUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"AssignedStaffId", "InternalNote"})

    AssignedStaffId: uuid.UUID | None = None
    InternalNote: str | None = None


# ---------------------------------------------------------------------------
# Orders - response
# ---------------------------------------------------------------------------


class OrderItemResponse(ResponseSchema):
    """Dành cho khách hàng: không có UnitCost."""

    OrderItemId: uuid.UUID
    ProductVariantId: uuid.UUID
    ProductName: str
    Sku: str
    VariantInfo: str
    WarrantyMonths: int
    Quantity: PositiveInt
    UnitPrice: Money
    DiscountAmount: Money
    LineTotal: Money


class AdminOrderItemResponse(OrderItemResponse):
    UnitCost: Money


class OrderStatusHistoryResponse(ResponseSchema):
    OrderStatusHistoryId: uuid.UUID
    OldStatus: OrderStatusValue | None
    NewStatus: OrderStatusValue
    Note: str | None
    ChangedAt: datetime


class AdminOrderStatusHistoryResponse(OrderStatusHistoryResponse):
    ChangedByUserId: uuid.UUID | None


class OrderSummary(ResponseSchema):
    """Dùng cho danh sách đơn hàng."""

    OrderId: uuid.UUID
    OrderCode: str
    TotalAmount: Money
    OrderStatus: OrderStatusValue
    PaymentStatus: PaymentStatusValue
    OrderedAt: datetime


class OrderResponse(OrderSummary):
    """Dành cho khách hàng: không có InternalNote, AssignedStaffId."""

    AddressId: uuid.UUID | None
    ShippingMethodId: uuid.UUID
    PaymentMethodId: uuid.UUID
    CouponId: uuid.UUID | None
    Subtotal: Money
    ShippingFee: Money
    DiscountAmount: Money
    ReceiverName: str
    ReceiverPhone: str
    ShippingAddress: str
    CustomerNote: str | None
    CancelReason: str | None
    ConfirmedAt: datetime | None
    ShippedAt: datetime | None
    DeliveredAt: datetime | None
    CompletedAt: datetime | None
    CancelledAt: datetime | None


class OrderDetailResponse(OrderResponse):
    Items: list[OrderItemResponse] = relation_field("items")
    StatusHistories: list[OrderStatusHistoryResponse] = relation_field("status_histories")


class AdminOrderResponse(OrderResponse):
    CustomerId: uuid.UUID
    AssignedStaffId: uuid.UUID | None
    InternalNote: str | None


class AdminOrderDetailResponse(AdminOrderResponse):
    Items: list[AdminOrderItemResponse] = relation_field("items")
    StatusHistories: list[AdminOrderStatusHistoryResponse] = relation_field("status_histories")
