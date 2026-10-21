"""Schemas tổng hợp và chi tiết báo cáo quản trị, dành cho Staff/Admin.

Khoảng thời gian: DateFrom/DateTo là ngày lịch Việt Nam, tính cả hai ngày; truy vấn dùng khoảng nửa mở
[StartsAt, EndsBefore) theo UTC (gồm StartsAt, không gồm EndsBefore = 00:00 ngày sau DateTo giờ Việt Nam).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from .common import ResponseSchema


class StatisticsPeriod(ResponseSchema):
    DateFrom: date
    DateTo: date
    StartsAt: datetime
    EndsBefore: datetime


class ReportOption(ResponseSchema):
    Id: uuid.UUID
    Name: str


class ReportProductOption(ReportOption):
    CategoryId: uuid.UUID
    BrandId: uuid.UUID


class ReportOptionsResponse(ResponseSchema):
    Categories: list[ReportOption]
    Brands: list[ReportOption]
    Products: list[ReportProductOption]
    Suppliers: list[ReportOption] = []


class PurchaseReportSummary(ResponseSchema):
    TotalOrders: int = 0
    InProgressOrders: int = 0
    CompletedOrders: int = 0
    ClosedOrders: int = 0
    CancelledOrders: int = 0
    RejectedOrders: int = 0
    OrderedQuantity: int = 0
    ReceivedQuantity: int = 0
    OrderedAmount: Decimal = Decimal('0')


class PurchaseReportPoint(PurchaseReportSummary):
    DateFrom: date
    DateTo: date
    Label: str


class PurchaseReportItem(ResponseSchema):
    PurchaseOrderId: uuid.UUID
    PurchaseOrderCode: str
    CreatedAt: datetime
    SupplierId: uuid.UUID
    SupplierName: str
    Status: Literal['Pending', 'Approved', 'Receiving', 'Completed', 'Closed', 'Cancelled', 'Rejected']
    OrderedQuantity: int
    ReceivedQuantity: int
    OrderedAmount: Decimal


class PurchaseSupplierSummary(PurchaseReportSummary):
    SupplierId: uuid.UUID
    SupplierName: str


class PurchaseReportResponse(ResponseSchema):
    Period: StatisticsPeriod
    Summary: PurchaseReportSummary
    Chart: list[PurchaseReportPoint]
    Items: list[PurchaseReportItem]
    Suppliers: list[PurchaseSupplierSummary]
    Total: int
    Page: int
    PageSize: int


class ReportSummary(ResponseSchema):
    TotalOrders: int = 0
    DeliveredOrders: int = 0
    CancelledOrders: int = 0
    InProgressOrders: int = 0
    Revenue: Decimal = Decimal('0')
    Quantity: int = 0
    Cost: Decimal | None = Decimal('0')
    Profit: Decimal | None = Decimal('0')
    Margin: Decimal | None = None
    LinesMissingCost: int = 0
    AverageOrderValue: Decimal = Decimal('0')
    PeakRevenue: Decimal = Decimal('0')


class ReportPoint(ReportSummary):
    DateFrom: date
    DateTo: date
    Label: str


class SalesReportItem(ResponseSchema):
    Key: str
    DateFrom: date
    DateTo: date
    ProductId: uuid.UUID
    ProductVariantId: uuid.UUID | None = None
    VariantName: str | None = None
    Sku: str | None = None
    ProductName: str
    CategoryName: str
    BrandName: str
    Revenue: Decimal
    Quantity: int = 0
    ReceivedQuantity: int = 0
    StockQuantity: int = 0
    Cost: Decimal | None = None
    Profit: Decimal | None = None
    Margin: Decimal | None = None
    LinesMissingCost: int = 0


class SalesReportLine(ResponseSchema):
    Key: str
    OrderId: uuid.UUID
    OrderCode: str
    DeliveredAt: datetime
    ProductId: uuid.UUID
    ProductName: str
    VariantInfo: str
    Sku: str
    UnitPrice: Decimal
    UnitCost: Decimal | None
    Quantity: int
    Discount: Decimal
    Revenue: Decimal
    Cost: Decimal | None
    Profit: Decimal | None


class SalesLinesResponse(ResponseSchema):
    Period: StatisticsPeriod
    Items: list[SalesReportLine]
    Total: int
    Page: int
    PageSize: int


class CancellationReason(ResponseSchema):
    Reason: str
    TotalOrders: int


class CancelledOrderItem(ResponseSchema):
    OrderId: uuid.UUID
    OrderCode: str
    OrderedAt: datetime
    CustomerName: str
    TotalAmount: Decimal
    CancelReason: str | None


class CancelledOrdersResponse(ResponseSchema):
    Period: StatisticsPeriod
    Items: list[CancelledOrderItem]
    Total: int
    Page: int
    PageSize: int


class DeliveredOrderItem(ResponseSchema):
    OrderId: uuid.UUID
    OrderCode: str
    OrderedAt: datetime
    DeliveredAt: datetime | None
    CustomerName: str
    TotalAmount: Decimal
    OrderStatus: Literal['Delivered', 'Completed']


class DeliveredOrdersResponse(ResponseSchema):
    Period: StatisticsPeriod
    Items: list[DeliveredOrderItem]
    Total: int
    Page: int
    PageSize: int


class DashboardWorkload(ResponseSchema):
    PendingOrders: int
    WaitingChats: int
    PendingReturns: int
    NewWarranties: int


class OrderReportItem(ResponseSchema):
    Key: str
    DateFrom: date
    DateTo: date
    TotalOrders: int
    DeliveredOrders: int
    CancelledOrders: int
    InProgressOrders: int = 0


class SalesReportResponse(ResponseSchema):
    Period: StatisticsPeriod
    Summary: ReportSummary
    Chart: list[ReportPoint]
    Items: list[SalesReportItem]
    TopProducts: list[SalesReportItem] = []
    Total: int
    Page: int
    PageSize: int


class OrderReportResponse(ResponseSchema):
    Period: StatisticsPeriod
    Summary: ReportSummary
    Chart: list[ReportPoint]
    Items: list[OrderReportItem]
    CancellationReasons: list[CancellationReason] = []
    Total: int
    Page: int
    PageSize: int


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
