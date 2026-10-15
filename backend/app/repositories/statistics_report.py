"""Read-only, bounded period reports. Aggregate and page in SQL, never fetch individual orders.

Sales use historical OrderItems.LineTotal (already contains allocated discounts),
not catalog prices or payment totals. Payments are checked with EXISTS so retries
or split payments cannot multiply sales. Shipping/refunds are outside this sales report.
"""
from sqlalchemy import and_, case, exists, func, select

from app.models import Brand, Category, Order, OrderItem, PaymentTransaction, Product, ProductVariant


class StatisticsReportRepository:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _product_filters(category_id=None, brand_id=None, product_id=None):
        return tuple(column == value for column, value in (
            (Product.CategoryId, category_id), (Product.BrandId, brand_id), (Product.ProductId, product_id)
        ) if value is not None)

    @staticmethod
    def _bucket(column, intervals):
        return case(*[(and_(column >= start, column < end), index)
                      for index, (start, end) in enumerate(intervals)], else_=-1)

    def order_chart(self, start, end, intervals, **filters):
        bucket = self._bucket(Order.OrderedAt, intervals).label('Bucket')
        conditions = [Order.OrderedAt >= start, Order.OrderedAt < end]
        product_filters = self._product_filters(**filters)
        if product_filters:
            conditions.append(exists(select(OrderItem.OrderItemId)
                .join(ProductVariant, ProductVariant.ProductVariantId == OrderItem.ProductVariantId)
                .join(Product, Product.ProductId == ProductVariant.ProductId)
                .where(OrderItem.OrderId == Order.OrderId, *product_filters)))
        query = select(bucket, func.count(Order.OrderId).label('TotalOrders'),
            func.sum(case((Order.OrderStatus.in_(('Delivered', 'Completed')), 1), else_=0)).label('DeliveredOrders'),
            func.sum(case((Order.OrderStatus == 'Cancelled', 1), else_=0)).label('CancelledOrders')
        ).where(*conditions).group_by(bucket).order_by(bucket)
        return self.session.execute(query).mappings().all()

    def _sales_query(self, start, end, intervals, *, details=False, **filters):
        bucket = self._bucket(Order.DeliveredAt, intervals).label('Bucket')
        columns = [bucket, func.sum(OrderItem.LineTotal).label('Revenue')]
        groups = [bucket]
        if details:
            columns += [Product.ProductId, Product.Name.label('ProductName'),
                        Category.Name.label('CategoryName'), Brand.Name.label('BrandName')]
            groups += [Product.ProductId, Product.Name, Category.Name, Brand.Name]
        else:
            columns += [func.count(func.distinct(Order.OrderId)).label('TotalOrders')]
        successful_payment = exists().where(PaymentTransaction.OrderId == Order.OrderId,
            PaymentTransaction.TransactionType == 'Payment', PaymentTransaction.Status == 'Success')
        query = (select(*columns).select_from(OrderItem)
            .join(Order, Order.OrderId == OrderItem.OrderId)
            .join(ProductVariant, ProductVariant.ProductVariantId == OrderItem.ProductVariantId)
            .join(Product, Product.ProductId == ProductVariant.ProductId)
            .where(Order.OrderStatus.in_(('Delivered', 'Completed')),
                Order.DeliveredAt >= start, Order.DeliveredAt < end,
                successful_payment, *self._product_filters(**filters)))
        if details:
            query = query.join(Category, Category.CategoryId == Product.CategoryId).join(Brand, Brand.BrandId == Product.BrandId)
        # Deleted/hidden catalog records still participate in historical sales.
        return query.group_by(*groups)

    def sales_chart(self, start, end, intervals, **filters):
        query = self._sales_query(start, end, intervals, **filters)
        return self.session.execute(query.order_by(query.selected_columns.Bucket)).mappings().all()

    def sales_details(self, start, end, intervals, *, offset, limit, **filters):
        grouped = self._sales_query(start, end, intervals, details=True, **filters).subquery()
        total = int(self.session.scalar(select(func.count()).select_from(grouped)) or 0)
        query = select(grouped).order_by(grouped.c.Bucket, grouped.c.ProductName, grouped.c.ProductId).offset(offset).limit(limit)
        return self.session.execute(query).mappings().all(), total

    def options(self):
        # Include inactive/deleted products so historical filters remain usable.
        categories = self.session.execute(select(Category.CategoryId.label('Id'), Category.Name).order_by(Category.Name, Category.CategoryId)).mappings().all()
        brands = self.session.execute(select(Brand.BrandId.label('Id'), Brand.Name).order_by(Brand.Name, Brand.BrandId)).mappings().all()
        products = self.session.execute(select(Product.ProductId.label('Id'), Product.Name, Product.CategoryId, Product.BrandId).order_by(Product.Name, Product.ProductId)).mappings().all()
        return {'Categories': categories, 'Brands': brands, 'Products': products}
