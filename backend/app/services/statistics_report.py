"""Read-only sales reports, using existing order snapshots."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.repositories.statistics_report import StatisticsReportRepository
from app.repositories.purchase_report import PurchaseReportRepository
from app.schemas.statistics import PurchaseReportResponse, PurchaseReportPoint, PurchaseReportSummary
from app.schemas.statistics import (CancellationReason, CancelledOrderItem, CancelledOrdersResponse,
    DeliveredOrderItem, DeliveredOrdersResponse,
    DashboardWorkload, OrderReportItem, OrderReportResponse,
    ReportOptionsResponse, ReportPoint, ReportSummary, SalesLinesResponse, SalesReportItem, SalesReportLine,
    SalesReportResponse, StatisticsPeriod)
from .actor import STAFF_OR_ADMIN, require_role
from .base import BaseService
from .exceptions import BusinessRuleError
from .statistics import statistics_period

ZERO = Decimal('0')
SORTS = {f'{key}_{direction}' for key in ('revenue', 'quantity', 'cost', 'profit', 'margin', 'name')
         for direction in ('asc', 'desc')}


def report_buckets(date_from, date_to, *, monthly=False):
    """Up to 31 days: daily; longer periods: calendar months. Dates are Vietnam dates."""
    daily = not monthly and (date_to - date_from).days < 31
    buckets = []
    current = date_from
    while current <= date_to:
        next_day = (current + timedelta(days=1) if daily else date.max if current.year == 9999 and current.month == 12 else
            date(current.year + current.month // 12, current.month % 12 + 1, 1))
        last = min(date_to, next_day - timedelta(days=1))
        label = current.strftime('%d/%m') if daily else f'Tháng {current.month}/{current.year}'
        buckets.append((current, last, label))
        current = last + timedelta(days=1)
    return buckets


def sales_amounts(row):
    """Unknown import prices make cost/profit unknown, never artificially profitable."""
    revenue = row.get('Revenue') or ZERO
    missing = row.get('LinesMissingCost') or 0
    cost = None if missing else row.get('KnownCost') or ZERO
    profit = None if cost is None else revenue - cost
    margin = ((profit / revenue * 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
              if profit is not None and revenue > 0 else None)
    return dict(Revenue=revenue, Quantity=row.get('Quantity') or 0, Cost=cost, Profit=profit,
                Margin=margin, LinesMissingCost=missing)


class StatisticsReportService(BaseService):
    def __init__(self, session):
        super().__init__(session)
        self.reports = StatisticsReportRepository(session)

    def options(self, actor):
        require_role(actor, *STAFF_OR_ADMIN)
        return ReportOptionsResponse(**self.reports.options())

    def workload(self, actor):
        require_role(actor, *STAFF_OR_ADMIN)
        return DashboardWorkload(**self.reports.workload())

    def purchases(self, actor, date_from, date_to, *, supplier_id=None, category_id=None,
                  brand_id=None, product_id=None, page=1, page_size=10):
        period, start, end = self._period(actor, date_from, date_to)
        offset, limit = self._page_args(page, page_size)
        buckets = report_buckets(date_from, date_to)
        intervals = [statistics_period(first, last) for first, last, _ in buckets]
        summary, raw, suppliers, items = PurchaseReportRepository(self.session).report(
            start, end, intervals, offset=offset, limit=limit, supplier_id=supplier_id,
            category_id=category_id, brand_id=brand_id, product_id=product_id)
        values = {row['Bucket']: {key: value for key, value in row.items() if key != 'Bucket'} for row in raw}
        chart = [PurchaseReportPoint(DateFrom=first, DateTo=last, Label=label, **values.get(index, {}))
                 for index, (first, last, label) in enumerate(buckets)]
        return PurchaseReportResponse(Period=period, Summary=PurchaseReportSummary(**summary), Chart=chart,
            Items=items, Suppliers=suppliers, Total=summary['TotalOrders'], Page=page, PageSize=page_size)

    @staticmethod
    def _period(actor, date_from, date_to):
        require_role(actor, *STAFF_OR_ADMIN)
        start, end = statistics_period(date_from, date_to)
        if (date_to - date_from).days >= 366:
            raise BusinessRuleError('Mỗi lần xem báo cáo tối đa 366 ngày', code='report_period_too_long')
        return StatisticsPeriod(DateFrom=date_from, DateTo=date_to, StartsAt=start, EndsBefore=end), start, end

    def report(self, actor, kind, date_from, date_to, *, category_id=None, brand_id=None,
               product_id=None, page=1, page_size=10, sort='revenue_desc', group_by='product'):
        period, start, end = self._period(actor, date_from, date_to)
        if kind not in ('revenue', 'orders'):
            raise BusinessRuleError('Loại báo cáo không hợp lệ', code='invalid_report_type')
        if group_by not in ('product', 'variant'):
            raise BusinessRuleError('Cách gộp báo cáo không hợp lệ', code='invalid_report_group')
        if sort not in SORTS:
            raise BusinessRuleError('Cách sắp xếp không hợp lệ', code='invalid_report_sort')
        offset, limit = self._page_args(page, page_size)
        buckets = report_buckets(date_from, date_to)
        intervals = [statistics_period(first, last) for first, last, _ in buckets]
        filters = dict(category_id=category_id, brand_id=brand_id, product_id=product_id)
        raw = (self.reports.sales_chart if kind == 'revenue' else self.reports.order_chart)(start, end, intervals, **filters)
        values = {row['Bucket']: row for row in raw}
        chart = []
        for index, (first, last, label) in enumerate(buckets):
            row = values.get(index, {})
            chart.append(ReportPoint(DateFrom=first, DateTo=last, Label=label, **sales_amounts(row),
                TotalOrders=row.get('TotalOrders', 0), DeliveredOrders=row.get('DeliveredOrders', 0),
                CancelledOrders=row.get('CancelledOrders', 0), InProgressOrders=row.get('InProgressOrders', 0)))
        count = sum(point.TotalOrders for point in chart)
        revenue = sum((point.Revenue for point in chart), ZERO)
        amounts = sales_amounts(dict(Revenue=revenue, Quantity=sum(point.Quantity for point in chart),
            KnownCost=sum((point.Cost or ZERO for point in chart), ZERO),
            LinesMissingCost=sum(point.LinesMissingCost for point in chart)))
        summary = ReportSummary(TotalOrders=count, **amounts,
            AverageOrderValue=(revenue / count).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if count else ZERO,
            PeakRevenue=max((point.Revenue for point in chart), default=ZERO),
            DeliveredOrders=sum(point.DeliveredOrders for point in chart),
            CancelledOrders=sum(point.CancelledOrders for point in chart),
            InProgressOrders=sum(point.InProgressOrders for point in chart))
        if kind == 'orders':
            months = report_buckets(date_from, date_to, monthly=True)
            month_intervals = [statistics_period(first, last) for first, last, _ in months]
            monthly_raw = raw if month_intervals == intervals else self.reports.order_chart(start, end, month_intervals, **filters)
            monthly_values = {row['Bucket']: row for row in monthly_raw}
            rows = []
            for index, (first, last, _) in enumerate(months):
                row = monthly_values.get(index)
                if row and row['TotalOrders']:
                    rows.append(OrderReportItem(Key=f'{first.year}-{first.month:02d}', DateFrom=first, DateTo=last,
                        TotalOrders=row['TotalOrders'], DeliveredOrders=row['DeliveredOrders'],
                        CancelledOrders=row['CancelledOrders'], InProgressOrders=row['InProgressOrders']))
            return OrderReportResponse(Period=period, Summary=summary, Chart=chart,
                Items=rows[offset:offset + limit], Total=len(rows), Page=page, PageSize=page_size,
                CancellationReasons=[CancellationReason(**row) for row in self.reports.cancellation_reasons(start, end, **filters)])

        by_variant = group_by == 'variant'
        rows, total = self.reports.sales_details(start, end, offset=offset, limit=limit, sort=sort, by_variant=by_variant, **filters)
        top_rows = self.reports.top_products(start, end, **filters)
        quantities = self.reports.product_quantities(
            {row['ProductVariantId'] for row in rows} if by_variant else {row['ProductId'] for row in [*rows, *top_rows]},
            start, end, by_variant=by_variant)
        top_quantities = self.reports.product_quantities({row['ProductId'] for row in top_rows}, start, end) if by_variant else quantities
        def product(row):
            variant_id = row.get('ProductVariantId')
            counts = quantities.get(variant_id, {}) if variant_id else top_quantities.get(row['ProductId'], {})
            return SalesReportItem(Key=str(variant_id or row['ProductId']), DateFrom=date_from, DateTo=date_to,
                ProductId=row['ProductId'], ProductName=row['ProductName'], CategoryName=row['CategoryName'],
                BrandName=row['BrandName'], ProductVariantId=variant_id, VariantName=row.get('VariantName'),
                Sku=row.get('Sku'), **sales_amounts(row), **counts)
        return SalesReportResponse(Period=period, Summary=summary, Chart=chart,
            Items=[product(row) for row in rows], TopProducts=[product(row) for row in top_rows],
            Total=total, Page=page, PageSize=page_size)

    def cancelled_orders(self, actor, date_from, date_to, *, category_id=None, brand_id=None,
                         product_id=None, page=1, page_size=10):
        period, start, end = self._period(actor, date_from, date_to)
        offset, limit = self._page_args(page, page_size)
        rows, total = self.reports.cancelled_orders(start, end, offset=offset, limit=limit,
            category_id=category_id, brand_id=brand_id, product_id=product_id)
        return CancelledOrdersResponse(Period=period, Items=[CancelledOrderItem(**row) for row in rows],
            Total=total, Page=page, PageSize=page_size)

    def delivered_orders(self, actor, date_from, date_to, *, category_id=None, brand_id=None,
                         product_id=None, page=1, page_size=10):
        period, start, end = self._period(actor, date_from, date_to)
        offset, limit = self._page_args(page, page_size)
        rows, total = self.reports.delivered_orders(start, end, offset=offset, limit=limit,
            category_id=category_id, brand_id=brand_id, product_id=product_id)
        return DeliveredOrdersResponse(Period=period, Items=[DeliveredOrderItem(**row) for row in rows],
            Total=total, Page=page, PageSize=page_size)

    def lines(self, actor, date_from, date_to, *, product_id, category_id=None, brand_id=None, page=1, page_size=10, variant_id=None):
        period, start, end = self._period(actor, date_from, date_to)
        offset, limit = self._page_args(page, page_size)
        rows, total = self.reports.sales_lines(start, end, offset=offset, limit=limit,
            product_id=product_id, category_id=category_id, brand_id=brand_id, variant_id=variant_id)
        items = []
        for row in rows:
            cost = row['UnitCost'] * row['Quantity'] if row['UnitCost'] > 0 else None
            items.append(SalesReportLine(Key=str(row['OrderItemId']), OrderId=row['OrderId'], OrderCode=row['OrderCode'],
                DeliveredAt=row['DeliveredAt'], ProductId=row['ProductId'], ProductName=row['ProductName'],
                VariantInfo=row['VariantInfo'], Sku=row['Sku'], Quantity=row['Quantity'], UnitPrice=row['UnitPrice'],
                UnitCost=row['UnitCost'] if row['UnitCost'] > 0 else None,
                Discount=row['UnitPrice'] * row['Quantity'] - row['LineTotal'], Revenue=row['LineTotal'],
                Cost=cost, Profit=row['LineTotal'] - cost if cost is not None else None))
        return SalesLinesResponse(Period=period, Items=items, Total=total, Page=page, PageSize=page_size)
