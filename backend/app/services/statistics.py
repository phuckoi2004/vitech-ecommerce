"""Statistics service (đợt 5.6): thống kê quản trị chỉ đọc cho Admin.

Nguồn nghiệp vụ: docs/business-requirements.md mục 15 (Admin xem số đơn, doanh thu, hàng bán; chỉ tính đơn/trạng thái
phù hợp định nghĩa doanh thu; Decimal; tránh N+1/tải toàn bảng) và quy tắc đã thống nhất ở đợt 5.1 (mục 5.6):
- Doanh thu chỉ tính đơn đã giao có xác nhận thu tiền: OrderStatus Delivered hoặc Completed (Completed là bước sau
  Delivered) và có ít nhất một Payment Success; mốc thời gian = DeliveredAt.
- Báo cáo riêng: doanh thu gộp (tiền đã thu = Σ Payment Success), tiền hoàn đã hoàn tất (Σ Refund Success; không trừ
  Refund Pending/Failed), doanh thu thuần = gộp − hoàn. Không gọi doanh thu là lợi nhuận; không tính lợi nhuận.
Khoảng thời gian: ngày lịch Việt Nam, tính cả DateFrom và DateTo → khoảng UTC nửa mở [00:00 DateFrom, 00:00 ngày sau
DateTo) (giờ Việt Nam), dùng thống nhất cho mọi truy vấn. Đơn hàng lọc theo OrderedAt; doanh thu/giá vốn/sản phẩm theo
DeliveredAt. Chỉ đọc: không đổi trạng thái đơn, thanh toán hay tồn kho. Tổng hợp trong SQL (StatisticsRepository).
Chỉ Admin (Staff "xem thống kê theo quyền được cấp" chưa có quy định cụ thể → chưa mở).
"""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.catalog import PRODUCT_SERIAL_STATUSES
from app.models.order import ORDER_STATUSES
from app.repositories import StatisticsRepository
from app.schemas import (
    CogsStatisticsResponse,
    InventoryStatisticsResponse,
    InventoryTotals,
    InventoryVariantResponse,
    OrderStatisticsResponse,
    RevenueStatisticsResponse,
    SerialStatusCounts,
    StatisticsPeriod,
    TopProductResponse,
)

from .actor import ADMIN_ONLY, Actor, require_role
from .base import BaseService, utc_now
from .exceptions import BusinessRuleError
from .warranty_period import VIETNAM_TZ

IN_PROGRESS_STATUSES = ("Pending", "Confirmed", "Processing", "Shipping")
RANK_BY = ("quantity", "revenue")
MAX_TOP_LIMIT = 100

REVENUE_LIMITATIONS = (
    "Doanh thu theo đơn đã giao (Delivered/Completed) có Payment Success, mốc DeliveredAt; không phải lợi nhuận.",
    "Tiền hoàn tính mọi Refund Success của các đơn này đến thời điểm truy vấn; Refund Pending chỉ để tham khảo.",
    "Khoản thu trùng/thừa chưa hoàn vẫn nằm trong tiền đã thu (xem đối soát thanh toán).",
)
COGS_LIMITATIONS = (
    "Giá vốn theo OrderItems.UnitCost (snapshot lúc đặt hàng); UnitCost = 0 được coi là thiếu giá vốn.",
    "Chưa trừ giá vốn của hàng trả lại đã nhập kho (chưa có quy tắc định giá lại); chưa tính chi phí máy thay thế "
    "bảo hành.",
    "Không tính lợi nhuận.",
)
INVENTORY_LIMITATIONS = (
    "StockQuantity là tồn khả dụng (có thể bán) theo ProductVariants.",
    "Trạng thái serial chỉ có với biến thể quản lý serial; hàng không serial không có dữ liệu riêng cho hàng đang giữ, "
    "trả về hay hỏng.",
    "Returned gồm cả hàng trả về hỏng và máy cũ sau đổi bảo hành (schema không tách hàng hỏng).",
)


def statistics_period(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """[00:00 date_from, 00:00 ngày sau date_to) giờ Việt Nam, đổi sang UTC."""
    for value in (date_from, date_to):
        if not isinstance(value, date) or isinstance(value, datetime):
            raise BusinessRuleError("Khoảng thời gian phải là ngày (date)", code="invalid_statistics_period")
    if date_from > date_to:
        raise BusinessRuleError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc", code="invalid_statistics_period")
    if date_to == date.max:
        raise BusinessRuleError("Ngày kết thúc vượt giới hạn", code="invalid_statistics_period")
    start = datetime.combine(date_from, time.min, tzinfo=VIETNAM_TZ).astimezone(timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=VIETNAM_TZ).astimezone(timezone.utc)
    return start, end


class StatisticsService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.stats = StatisticsRepository(session)

    def order_statistics(self, actor: Actor, date_from: date, date_to: date) -> OrderStatisticsResponse:
        """Số đơn đặt trong khoảng theo trạng thái (mọi trạng thái của enum, kể cả 0)."""
        period, start, end = self._period(actor, date_from, date_to)
        counts = self.stats.count_orders_by_status(start, end)
        by_status = {status: counts.get(status, 0) for status in ORDER_STATUSES}
        return OrderStatisticsResponse(
            Period=period,
            TotalOrders=sum(by_status.values()),
            ByStatus=by_status,
            InProgress=sum(by_status[s] for s in IN_PROGRESS_STATUSES),
            Delivered=by_status["Delivered"],
            Completed=by_status["Completed"],
            Cancelled=by_status["Cancelled"],
        )

    def revenue_statistics(self, actor: Actor, date_from: date, date_to: date) -> RevenueStatisticsResponse:
        period, start, end = self._period(actor, date_from, date_to)
        totals = self.stats.revenue_totals(start, end)
        return RevenueStatisticsResponse(
            Period=period,
            OrderCount=totals.order_count,
            OrderValue=totals.order_value,
            ShippingFee=totals.shipping_fee,
            CollectedAmount=totals.collected,
            RefundedAmount=totals.refunded,
            NetRevenue=totals.collected - totals.refunded,
            PendingRefundAmount=totals.pending_refund,
            DeliveredWithoutConfirmedPayment=self.stats.count_delivered_without_payment(start, end),
            Limitations=list(REVENUE_LIMITATIONS),
        )

    def cogs_statistics(self, actor: Actor, date_from: date, date_to: date) -> CogsStatisticsResponse:
        period, start, end = self._period(actor, date_from, date_to)
        totals = self.stats.cogs_totals(start, end)
        complete = totals.lines_missing_cost == 0
        limitations = list(COGS_LIMITATIONS)
        if not complete:
            limitations.insert(0, f"{totals.lines_missing_cost} dòng đơn chưa có giá vốn: không trả tổng giá vốn.")
        return CogsStatisticsResponse(
            Period=period,
            LineCount=totals.line_count,
            UnitCount=totals.unit_count,
            KnownCogs=totals.known_cogs,
            LinesMissingCost=totals.lines_missing_cost,
            IsComplete=complete,
            Cogs=totals.known_cogs if complete else None,
            Limitations=limitations,
        )

    def top_products(
        self, actor: Actor, date_from: date, date_to: date, *, rank_by: str = "quantity", limit: int = 10
    ) -> list[TopProductResponse]:
        """Biến thể bán chạy trong các đơn ghi nhận doanh thu (xếp theo số lượng hoặc doanh thu dòng LineTotal).

        ReturnedQuantity: số đã trả lại qua yêu cầu Return đã hoàn tất của các dòng đó (chỉ để tham khảo, không đổi
        thứ hạng). Đơn hủy và đơn chưa giao không được tính.
        """
        _, start, end = self._period(actor, date_from, date_to)
        if rank_by not in RANK_BY:
            raise BusinessRuleError("Chỉ xếp hạng theo quantity hoặc revenue", code="invalid_rank_by")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_TOP_LIMIT:
            raise BusinessRuleError(f"limit phải từ 1 đến {MAX_TOP_LIMIT}", code="invalid_limit")
        rows = self.stats.top_products(start, end, rank_by=rank_by, limit=limit)
        returned = self.stats.returned_quantities(start, end, [row.product_variant_id for row in rows])
        return [
            TopProductResponse(
                Rank=index,
                ProductVariantId=row.product_variant_id,
                ProductId=row.product_id,
                ProductName=row.product_name,
                Sku=row.sku,
                VariantName=row.variant_name,
                QuantitySold=row.quantity,
                Revenue=row.revenue,
                ReturnedQuantity=returned.get(row.product_variant_id, 0),
            )
            for index, row in enumerate(rows, start=1)
        ]

    def inventory_statistics(self, actor: Actor, *, page: int = 1, page_size: int = 50) -> InventoryStatisticsResponse:
        """Tồn khả dụng theo biến thể và số serial theo trạng thái (biến thể quản lý serial). Không đổi tồn kho."""
        require_role(actor, *ADMIN_ONLY)
        offset, limit = self._page_args(page, page_size)
        rows = self.stats.list_inventory(offset=offset, limit=limit)
        counts = self.stats.serial_status_counts([row.product_variant_id for row in rows])
        items = [
            InventoryVariantResponse(
                ProductVariantId=row.product_variant_id,
                ProductId=row.product_id,
                ProductName=row.product_name,
                Sku=row.sku,
                VariantName=row.variant_name,
                IsSerialTracked=row.is_serial_tracked,
                StockQuantity=row.stock_quantity,
                MinStockLevel=row.min_stock_level,
                # Cùng ngưỡng cảnh báo tồn thấp hiện có: MinStockLevel > 0 và StockQuantity <= MinStockLevel.
                IsLowStock=row.min_stock_level > 0 and row.stock_quantity <= row.min_stock_level,
                Serials=(_serial_counts({s: counts.get((row.product_variant_id, s), 0) for s in PRODUCT_SERIAL_STATUSES})
                         if row.is_serial_tracked else None),
            )
            for row in rows
        ]
        return InventoryStatisticsResponse(
            Items=items,
            Total=self.stats.count_inventory_variants(),
            Page=page,
            PageSize=page_size,
            Totals=InventoryTotals(
                VariantCount=self.stats.count_inventory_variants(),
                StockQuantity=self.stats.stock_total(),
                Serials=_serial_counts(self.stats.serial_status_totals()),
            ),
            Limitations=list(INVENTORY_LIMITATIONS),
        )

    def _period(self, actor: Actor, date_from: date, date_to: date) -> tuple[StatisticsPeriod, datetime, datetime]:
        require_role(actor, *ADMIN_ONLY)
        start, end = statistics_period(date_from, date_to)
        return StatisticsPeriod(DateFrom=date_from, DateTo=date_to, StartsAt=start, EndsBefore=end), start, end


def _serial_counts(counts: dict[str, int]) -> SerialStatusCounts:
    return SerialStatusCounts(**{status: counts.get(status, 0) for status in PRODUCT_SERIAL_STATUSES})
