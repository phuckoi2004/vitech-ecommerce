"""Figma sales/order reports. Read-only Staff/Admin; no refund workflows or DB changes."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.repositories.statistics_report import StatisticsReportRepository
from app.schemas.statistics import (OrderReportItem, OrderReportResponse, ReportOptionsResponse,
    ReportPoint, ReportSummary, SalesReportItem, SalesReportResponse, StatisticsPeriod)
from .actor import STAFF_OR_ADMIN, require_role
from .base import BaseService
from .exceptions import BusinessRuleError
from .statistics import statistics_period


def report_buckets(date_from, date_to, *, monthly=False):
    """Chart intervals adapt to the range; detail tables always use calendar months."""
    days = (date_to - date_from).days + 1
    buckets = []
    current = date_from
    while current <= date_to:
        if not monthly and days <= 7:
            next_day = current + timedelta(days=1)
        elif not monthly and days <= 62:
            next_day = current + timedelta(days=min(7, (date_to - current).days + 1))
        else:
            next_day = date.max if current.year == 9999 and current.month == 12 else date(current.year + current.month // 12, current.month % 12 + 1, 1)
        last = min(date_to, next_day - timedelta(days=1))
        label = (current.strftime('%d/%m') if not monthly and days <= 7 else
                 f'{current:%d/%m}–{last:%d/%m}' if not monthly and days <= 62 else f'Tháng {current.month}/{current.year}')
        buckets.append((current, last, label))
        current = last + timedelta(days=1)
    return buckets


class StatisticsReportService(BaseService):
    def __init__(self, session):
        super().__init__(session)
        self.reports = StatisticsReportRepository(session)

    def options(self, actor):
        require_role(actor, *STAFF_OR_ADMIN)
        return ReportOptionsResponse(**self.reports.options())

    def report(self, actor, kind, date_from, date_to, *, category_id=None, brand_id=None,
               product_id=None, page=1, page_size=10):
        require_role(actor, *STAFF_OR_ADMIN)
        start, end = statistics_period(date_from, date_to)
        if (date_to - date_from).days >= 366:
            raise BusinessRuleError('Mỗi lần xem báo cáo tối đa 366 ngày', code='report_period_too_long')
        if kind not in ('revenue', 'orders'):
            raise BusinessRuleError('Loại báo cáo không hợp lệ', code='invalid_report_type')
        offset, limit = self._page_args(page, page_size)
        buckets = report_buckets(date_from, date_to)
        intervals = [statistics_period(first, last) for first, last, _ in buckets]
        filters = dict(category_id=category_id, brand_id=brand_id, product_id=product_id)
        raw = (self.reports.sales_chart if kind == 'revenue' else self.reports.order_chart)(start, end, intervals, **filters)
        values = {row['Bucket']: row for row in raw}
        chart = []
        for index, (first, last, label) in enumerate(buckets):
            row = values.get(index, {})
            chart.append(ReportPoint(DateFrom=first, DateTo=last, Label=label,
                TotalOrders=row.get('TotalOrders', 0), Revenue=row.get('Revenue', Decimal('0')),
                DeliveredOrders=row.get('DeliveredOrders', 0), CancelledOrders=row.get('CancelledOrders', 0)))
        count = sum(point.TotalOrders for point in chart)
        revenue = sum((point.Revenue for point in chart), Decimal('0'))
        summary = ReportSummary(TotalOrders=count, Revenue=revenue,
            AverageOrderValue=(revenue / count).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if count else Decimal('0'),
            PeakRevenue=max((point.Revenue for point in chart), default=Decimal('0')),
            DeliveredOrders=sum(point.DeliveredOrders for point in chart),
            CancelledOrders=sum(point.CancelledOrders for point in chart))
        period = StatisticsPeriod(DateFrom=date_from, DateTo=date_to, StartsAt=start, EndsBefore=end)
        months = report_buckets(date_from, date_to, monthly=True)
        month_intervals = [statistics_period(first, last) for first, last, _ in months]
        if kind == 'orders':
            monthly_raw = raw if month_intervals == intervals else self.reports.order_chart(start, end, month_intervals, **filters)
            monthly_values = {row['Bucket']: row for row in monthly_raw}
            rows = []
            for index, (first, last, _) in enumerate(months):
                row = monthly_values.get(index)
                if row and row['TotalOrders']:
                    rows.append(OrderReportItem(Key=f'{first.year}-{first.month:02d}', DateFrom=first, DateTo=last,
                        TotalOrders=row['TotalOrders'], DeliveredOrders=row['DeliveredOrders'],
                        CancelledOrders=row['CancelledOrders']))
            return OrderReportResponse(Period=period, Summary=summary, Chart=chart,
                Items=rows[offset:offset + limit], Total=len(rows), Page=page, PageSize=page_size)
        raw_items, total = self.reports.sales_details(start, end, month_intervals, offset=offset, limit=limit, **filters)
        items = []
        for row in raw_items:
            first, last, _ = months[row['Bucket']]
            items.append(SalesReportItem(Key=f"{first.year}-{first.month:02d}:{row['ProductId']}", DateFrom=first,
                DateTo=last, ProductId=row['ProductId'], ProductName=row['ProductName'],
                CategoryName=row['CategoryName'], BrandName=row['BrandName'], Revenue=row['Revenue']))
        return SalesReportResponse(Period=period, Summary=summary, Chart=chart,
            Items=items, Total=total, Page=page, PageSize=page_size)
