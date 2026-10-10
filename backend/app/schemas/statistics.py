"""Schemas kết quả thống kê quản trị (đợt 5.6). Chỉ dữ liệu tổng hợp; không có thông tin cá nhân khách hàng.

Khoảng thời gian: DateFrom/DateTo là ngày lịch Việt Nam, tính cả hai ngày; truy vấn dùng khoảng nửa mở
[StartsAt, EndsBefore) theo UTC (gồm StartsAt, không gồm EndsBefore = 00:00 ngày sau DateTo giờ Việt Nam).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from .common import ResponseSchema


class StatisticsPeriod(ResponseSchema):
    DateFrom: date
    DateTo: date
    StartsAt: datetime
    EndsBefore: datetime


class OrderStatisticsResponse(ResponseSchema):
    """Đơn đặt trong khoảng (theo OrderedAt). Completed = hoàn tất; Delivered = đã giao, chưa hoàn tất;
    InProgress = Pending + Confirmed + Processing + Shipping."""

    Period: StatisticsPeriod
    TotalOrders: int
    ByStatus: dict[str, int]
    InProgress: int
    Delivered: int
    Completed: int
    Cancelled: int


class RevenueStatisticsResponse(ResponseSchema):
    """Đơn ghi nhận doanh thu: Delivered/Completed, DeliveredAt trong khoảng, có Payment Success.

    OrderValue = Σ TotalAmount; CollectedAmount (doanh thu gộp) = Σ Payment Success; RefundedAmount = Σ Refund Success
    (mọi thời điểm, của các đơn này); NetRevenue = CollectedAmount − RefundedAmount. Không phải lợi nhuận.
    """

    Period: StatisticsPeriod
    OrderCount: int
    OrderValue: Decimal
    ShippingFee: Decimal
    CollectedAmount: Decimal
    RefundedAmount: Decimal
    NetRevenue: Decimal
    PendingRefundAmount: Decimal
    DeliveredWithoutConfirmedPayment: int
    Limitations: list[str]


class CogsStatisticsResponse(ResponseSchema):
    """Giá vốn theo snapshot OrderItems.UnitCost × Quantity của các đơn ghi nhận doanh thu.

    Cogs chỉ có giá trị khi mọi dòng đều có giá vốn (UnitCost > 0); nếu thiếu thì Cogs = None, KnownCogs là phần
    đã biết. Không tính lợi nhuận.
    """

    Period: StatisticsPeriod
    LineCount: int
    UnitCount: int
    KnownCogs: Decimal
    LinesMissingCost: int
    IsComplete: bool
    Cogs: Decimal | None
    Limitations: list[str]


class TopProductResponse(ResponseSchema):
    Rank: int
    ProductVariantId: uuid.UUID
    ProductId: uuid.UUID
    ProductName: str
    Sku: str
    VariantName: str
    QuantitySold: int
    Revenue: Decimal
    ReturnedQuantity: int


class SerialStatusCounts(ResponseSchema):
    """Available: có thể bán; Reserved: đã gán cho đơn đang đóng gói/giao; Sold: đã xuất bán; Warranty: đang bảo hành;
    Returned: đã về cửa hàng nhưng không bán được (hàng trả về hỏng, máy cũ sau đổi bảo hành); WrittenOff: đã loại khỏi
    kho qua điều chỉnh giảm."""

    Available: int = 0
    Reserved: int = 0
    Sold: int = 0
    Warranty: int = 0
    Returned: int = 0
    WrittenOff: int = 0


class InventoryVariantResponse(ResponseSchema):
    ProductVariantId: uuid.UUID
    ProductId: uuid.UUID
    ProductName: str
    Sku: str
    VariantName: str
    IsSerialTracked: bool
    StockQuantity: int
    MinStockLevel: int
    IsLowStock: bool
    Serials: SerialStatusCounts | None


class InventoryTotals(ResponseSchema):
    VariantCount: int
    StockQuantity: int
    Serials: SerialStatusCounts


class InventoryStatisticsResponse(ResponseSchema):
    Items: list[InventoryVariantResponse]
    Total: int
    Page: int
    PageSize: int
    Totals: InventoryTotals
    Limitations: list[str]
