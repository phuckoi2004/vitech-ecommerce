"""Purchase-order cohorts by creation date; read-only, one row per order before aggregation."""
from sqlalchemy import case, func, select

from app.models import Product, ProductVariant, PurchaseOrder, PurchaseOrderItem, Supplier
from .statistics_report import StatisticsReportRepository


class PurchaseReportRepository:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _orders(start, end, *, supplier_id=None, category_id=None, brand_id=None, product_id=None):
        product_filters = StatisticsReportRepository._product_filters(category_id, brand_id, product_id)
        # Aggregate matching SKU lines before joining orders, preventing duplicate order counts and amounts.
        lines = (select(PurchaseOrderItem.PurchaseOrderId,
            func.sum(PurchaseOrderItem.OrderedQuantity).label('OrderedQuantity'),
            func.sum(PurchaseOrderItem.ReceivedQuantity).label('ReceivedQuantity'),
            func.sum(PurchaseOrderItem.LineTotal).label('OrderedAmount'))
            .join(ProductVariant, ProductVariant.ProductVariantId == PurchaseOrderItem.ProductVariantId)
            .join(Product, Product.ProductId == ProductVariant.ProductId)
            .where(*product_filters).group_by(PurchaseOrderItem.PurchaseOrderId).subquery())
        query = (select(PurchaseOrder.PurchaseOrderId, PurchaseOrder.PurchaseOrderCode, PurchaseOrder.CreatedAt,
            PurchaseOrder.SupplierId, Supplier.Name.label('SupplierName'), PurchaseOrder.Status,
            func.coalesce(lines.c.OrderedQuantity, 0).label('OrderedQuantity'),
            func.coalesce(lines.c.ReceivedQuantity, 0).label('ReceivedQuantity'),
            func.coalesce(lines.c.OrderedAmount, 0).label('OrderedAmount'))
            .join(Supplier, Supplier.SupplierId == PurchaseOrder.SupplierId)
            .outerjoin(lines, lines.c.PurchaseOrderId == PurchaseOrder.PurchaseOrderId)
            .where(PurchaseOrder.CreatedAt >= start, PurchaseOrder.CreatedAt < end))
        if supplier_id is not None:
            query = query.where(PurchaseOrder.SupplierId == supplier_id)
        if product_filters:
            query = query.where(lines.c.PurchaseOrderId.is_not(None))
        return query.subquery()

    @staticmethod
    def _totals(rows):
        valid = rows.c.Status.not_in(('Cancelled', 'Rejected'))
        return (
            func.count().label('TotalOrders'),
            func.sum(case((rows.c.Status.in_(('Pending', 'Approved', 'Receiving')), 1), else_=0)).label('InProgressOrders'),
            *[func.sum(case((rows.c.Status == status, 1), else_=0)).label(key) for status, key in (
                ('Completed', 'CompletedOrders'), ('Closed', 'ClosedOrders'),
                ('Cancelled', 'CancelledOrders'), ('Rejected', 'RejectedOrders'))],
            *[func.sum(case((valid, rows.c[key]), else_=0)).label(key)
              for key in ('OrderedQuantity', 'ReceivedQuantity', 'OrderedAmount')],
        )

    def report(self, start, end, intervals, *, offset, limit, **filters):
        rows = self._orders(start, end, **filters)
        totals = self._totals(rows)
        summary = dict(self.session.execute(select(*totals).select_from(rows)).mappings().one())
        summary = {key: value if value is not None else 0 for key, value in summary.items()}
        bucket = StatisticsReportRepository._bucket(rows.c.CreatedAt, intervals).label('Bucket')
        chart = self.session.execute(select(bucket, *totals).select_from(rows)
            .group_by(bucket).order_by(bucket)).mappings().all()
        suppliers = self.session.execute(select(rows.c.SupplierId, rows.c.SupplierName, *totals)
            .group_by(rows.c.SupplierId, rows.c.SupplierName)
            .order_by(totals[-1].desc(), rows.c.SupplierName, rows.c.SupplierId).limit(5)).mappings().all()
        items = self.session.execute(select(rows).order_by(rows.c.CreatedAt.desc(), rows.c.PurchaseOrderId)
            .offset(offset).limit(limit)).mappings().all()
        return summary, chart, suppliers, items
