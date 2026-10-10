"""Schemas cho ShippingMethods, Orders, OrderItems, OrderStatusHistories.

UnitCost (giá vốn tại thời điểm bán), InternalNote, AssignedStaffId chỉ có trong schema admin/staff.
"""

import uuid
from datetime import datetime

from pydantic import Field, model_validator

from .common import (
    Money,
    NonNegativeInt,
    OrderStatusValue,
    PaymentStatusValue,
    PositiveInt,
    RequestSchema,
    ResponseSchema,
    SerialNumberValue,
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
    """KHÔNG nối trực tiếp vào API như lệnh đặt PaymentStatus (đợt 5.10; hiện không Service nào dùng).

    PaymentStatus chỉ đổi qua nghiệp vụ có bằng chứng/kiểm soát: callback/webhook cổng thanh toán đã xác minh
    (PaymentService), xác nhận thu COD (OrderService.confirm_cod_delivery), hủy đơn và hoàn tiền (PaymentService).
    Đặt trực tiếp Paid/Refunded sẽ bỏ qua giao dịch PaymentTransactions và đối soát. Test tests/test_status_schema_guard
    chặn việc dùng schema này ngoài app/schemas.
    """

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

# ---------------------------------------------------------------------------
# ShipmentReturns: hàng của đơn hủy khi đang giao, chờ quay về kho
# ---------------------------------------------------------------------------


class ShipmentReturnItemReceive(RequestSchema):
    """Kết quả kiểm tra một dòng đơn KHÔNG quản lý serial: số nhập lại kho + số hỏng = số đã giao đi."""

    OrderItemId: uuid.UUID
    RestockedQuantity: NonNegativeInt
    DamagedQuantity: NonNegativeInt


class ShipmentReturnReceive(RequestSchema):
    """Staff/Admin xác nhận đã nhận lại hàng và kết quả kiểm tra thực tế (phải khai đủ mọi đơn vị hàng).

    Items: dòng đơn không quản lý serial. RestockedSerialNumbers / DamagedSerialNumbers: serial đạt (nhập lại kho)
    và serial hỏng (Returned, không nhập tồn) — mọi serial của hồ sơ phải nằm đúng một trong hai danh sách.
    """

    NULLABLE_FIELDS = frozenset({"Note"})

    Items: list[ShipmentReturnItemReceive] = Field(default_factory=list)
    RestockedSerialNumbers: list[SerialNumberValue] = Field(default_factory=list)
    DamagedSerialNumbers: list[SerialNumberValue] = Field(default_factory=list)
    Note: str | None = None


class ShipmentReturnItemResponse(ResponseSchema):
    ShipmentReturnItemId: uuid.UUID
    OrderItemId: uuid.UUID
    ProductSerialId: uuid.UUID | None
    ExpectedQuantity: int
    RestockedQuantity: int | None
    DamagedQuantity: int | None


class ShipmentReturnResponse(ResponseSchema):
    """Staff/Admin: hồ sơ hàng chờ quay về (AwaitingReturn) hoặc đã nhận lại (Received)."""

    ShipmentReturnId: uuid.UUID
    OrderId: uuid.UUID
    Status: str
    CreatedByUserId: uuid.UUID | None
    CreatedAt: datetime
    ReceivedByUserId: uuid.UUID | None
    ReceivedAt: datetime | None
    Note: str | None
    Items: list[ShipmentReturnItemResponse] = relation_field("items")

# ---------------------------------------------------------------------------
# Gán Serial/IMEI thực tế khi đóng gói
# ---------------------------------------------------------------------------


class OrderItemSerialAssign(RequestSchema):
    """Serial/IMEI Staff quét/chọn cho một dòng đơn (biến thể quản lý serial)."""

    OrderItemId: uuid.UUID
    SerialNumbers: list[SerialNumberValue] = Field(min_length=1)


class OrderSerialAssign(RequestSchema):
    Items: list[OrderItemSerialAssign] = Field(min_length=1)


class OrderItemSerialsResponse(ResponseSchema):
    """Serial/IMEI đang gắn với một dòng đơn (Reserved khi đóng gói, Sold sau khi giao)."""

    OrderItemId: uuid.UUID
    ProductVariantId: uuid.UUID
    Sku: str
    Quantity: int
    IsSerialTracked: bool
    SerialNumbers: list[str]
