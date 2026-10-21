"""Read-only, bounded period reports. Aggregate and page in SQL; never load orders one by one.

Sales use historical OrderItems.LineTotal (already contains allocated discounts),
not catalog prices or payment totals. Payments are checked with EXISTS so retries
or split payments cannot multiply sales. Shipping/refunds are outside this sales report.
"""
from sqlalchemy import and_, case, exists, func, select

from app.models import (Brand, Category, Conversation, Order, OrderItem, PaymentTransaction,
    Product, ProductVariant, ReturnRequest, User, WarrantyRequest)


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

    def _order_conditions(self, start, end, **filters):
        conditions = [Order.OrderedAt >= start, Order.OrderedAt < end]
        product_filters = self._product_filters(**filters)
        if product_filters:
            conditions.append(exists(select(OrderItem.OrderItemId)
                .join(ProductVariant, ProductVariant.ProductVariantId == OrderItem.ProductVariantId)
                .join(Product, Product.ProductId == ProductVariant.ProductId)
                .where(OrderItem.OrderId == Order.OrderId, *product_filters)))
        return conditions

    def order_chart(self, start, end, intervals, **filters):
        bucket = self._bucket(Order.OrderedAt, intervals).label('Bucket')
        query = select(bucket, func.count(Order.OrderId).label('TotalOrders'),
            func.sum(case((Order.OrderStatus.in_(('Delivered', 'Completed')), 1), else_=0)).label('DeliveredOrders'),
            func.sum(case((Order.OrderStatus == 'Cancelled', 1), else_=0)).label('CancelledOrders'),
            func.sum(case((Order.OrderStatus.in_(('Pending', 'Confirmed', 'Processing', 'Shipping')), 1), else_=0)).label('InProgressOrders')
        ).where(*self._order_conditions(start, end, **filters)).group_by(bucket).order_by(bucket)
        return self.session.execute(query).mappings().all()

    def _sold_lines(self, *columns, start, end, **filters):
        """Read historical line amounts; EXISTS prevents duplicate payment joins."""
        successful_payment = exists().where(PaymentTransaction.OrderId == Order.OrderId,
            PaymentTransaction.TransactionType == 'Payment', PaymentTransaction.Status == 'Success')
        return (select(*columns).select_from(OrderItem)
            .join(Order, Order.OrderId == OrderItem.OrderId)
            .join(ProductVariant, ProductVariant.ProductVariantId == OrderItem.ProductVariantId)
            .join(Product, Product.ProductId == ProductVariant.ProductId)
            .where(Order.OrderStatus.in_(('Delivered', 'Completed')),
                Order.DeliveredAt >= start, Order.DeliveredAt < end,
                successful_payment, *self._product_filters(**filters)))

    @staticmethod
    def _sales_totals():
        return (func.sum(OrderItem.LineTotal).label('Revenue'),
            func.sum(OrderItem.Quantity).label('Quantity'),
            func.sum(OrderItem.UnitCost * OrderItem.Quantity).label('KnownCost'),
            func.sum(case((OrderItem.UnitCost <= 0, 1), else_=0)).label('LinesMissingCost'))

    def sales_chart(self, start, end, intervals, **filters):
        bucket = self._bucket(Order.DeliveredAt, intervals).label('Bucket')
        query = self._sold_lines(bucket, *self._sales_totals(),
            func.count(func.distinct(Order.OrderId)).label('TotalOrders'), start=start, end=end, **filters)
        return self.session.execute(query.group_by(bucket).order_by(bucket)).mappings().all()

    def _products(self, start, end, **filters):
        columns = (Product.ProductId, Product.Name.label('ProductName'),
            Category.Name.label('CategoryName'), Brand.Name.label('BrandName'))
        query = self._sold_lines(*columns, *self._sales_totals(), start=start, end=end, **filters)
        return (query.join(Category, Category.CategoryId == Product.CategoryId)
            .join(Brand, Brand.BrandId == Product.BrandId).group_by(*columns)).subquery()

    def sales_details(self, start, end, *, offset, limit, sort='revenue_desc', **filters):
        """One product for the entire period; aggregate before pagination/sorting."""
        grouped = self._products(start, end, **filters)
        total = int(self.session.scalar(select(func.count()).select_from(grouped)) or 0)
        profit = case((grouped.c.LinesMissingCost == 0, grouped.c.Revenue - grouped.c.KnownCost), else_=None)
        margin = case((grouped.c.Revenue > 0, profit * 100 / grouped.c.Revenue), else_=None)
        column = {'revenue': grouped.c.Revenue, 'quantity': grouped.c.Quantity,
            'cost': case((grouped.c.LinesMissingCost == 0, grouped.c.KnownCost), else_=None),
            'profit': profit, 'margin': margin, 'name': grouped.c.ProductName}[sort.rsplit('_', 1)[0]]
        direction = column.asc() if sort.endswith('_asc') else column.desc()
        query = select(grouped).order_by(direction.nulls_last(), grouped.c.ProductName, grouped.c.ProductId).offset(offset).limit(limit)
        return self.session.execute(query).mappings().all(), total

    def top_products(self, start, end, **filters):
        grouped = self._products(start, end, **filters)
        query = select(grouped).order_by(grouped.c.Revenue.desc(), grouped.c.ProductId).limit(5)
        return self.session.execute(query).mappings().all()

    def sales_lines(self, start, end, *, offset, limit, **filters):
        query = self._sold_lines(OrderItem.OrderItemId, Order.OrderId, Order.OrderCode, Order.DeliveredAt,
            Product.ProductId, OrderItem.ProductName, OrderItem.VariantInfo, OrderItem.Sku,
            OrderItem.UnitCost, OrderItem.UnitPrice, OrderItem.Quantity, OrderItem.LineTotal,
            start=start, end=end, **filters)
        total = int(self.session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        query = query.order_by(Order.DeliveredAt.desc(), Order.OrderCode, OrderItem.OrderItemId)
        return self.session.execute(query.offset(offset).limit(limit)).mappings().all(), total

    def cancelled_orders(self, start, end, *, offset, limit, **filters):
        return self._orders_by_status(start, end, ('Cancelled',), (Order.CancelReason,),
            offset=offset, limit=limit, **filters)

    def delivered_orders(self, start, end, *, offset, limit, **filters):
        return self._orders_by_status(start, end, ('Delivered', 'Completed'),
            (Order.DeliveredAt, Order.OrderStatus), offset=offset, limit=limit, **filters)

    def _orders_by_status(self, start, end, statuses, columns, *, offset, limit, **filters):
        # Match the order-report cohort: placement date and current status, regardless of payment.
        conditions = [*self._order_conditions(start, end, **filters), Order.OrderStatus.in_(statuses)]
        total = int(self.session.scalar(select(func.count(Order.OrderId)).where(*conditions)) or 0)
        query = (select(Order.OrderId, Order.OrderCode, Order.OrderedAt,
            func.coalesce(User.FullName, Order.ReceiverName).label('CustomerName'),
            Order.TotalAmount, *columns).select_from(Order)
            .outerjoin(User, User.UserId == Order.CustomerId).where(*conditions)
            .order_by(Order.OrderedAt.desc(), Order.OrderId.desc()).offset(offset).limit(limit))
        return self.session.execute(query).mappings().all(), total

    def cancellation_reasons(self, start, end, **filters):
        reason = func.coalesce(func.nullif(func.trim(Order.CancelReason), ''), 'Không ghi lý do').label('Reason')
        count = func.count(Order.OrderId).label('TotalOrders')
        query = (select(reason, count).where(*self._order_conditions(start, end, **filters),
            Order.OrderStatus == 'Cancelled').group_by(reason).order_by(count.desc(), reason).limit(10))
        return self.session.execute(query).mappings().all()

    def workload(self):
        def count(model, *conditions):
            return select(func.count()).select_from(model).where(*conditions).scalar_subquery()
        # Same waiting queue as /admin/conversations/unassigned. No message bodies loaded.
        return self.session.execute(select(
            count(Order, Order.OrderStatus == 'Pending').label('PendingOrders'),
            count(Conversation, Conversation.Status == 'Open', Conversation.Mode == 'Staff',
                Conversation.AssignedStaffId.is_(None)).label('WaitingChats'),
            count(ReturnRequest, ReturnRequest.Status == 'Pending').label('PendingReturns'),
            count(WarrantyRequest, WarrantyRequest.Status == 'New', WarrantyRequest.ReceivedAt.is_(None)).label('NewWarranties')
        )).mappings().one()

    def options(self):
        # Include inactive/deleted products so historical filters remain usable.
        categories = self.session.execute(select(Category.CategoryId.label('Id'), Category.Name).order_by(Category.Name, Category.CategoryId)).mappings().all()
        brands = self.session.execute(select(Brand.BrandId.label('Id'), Brand.Name).order_by(Brand.Name, Brand.BrandId)).mappings().all()
        products = self.session.execute(select(Product.ProductId.label('Id'), Product.Name, Product.CategoryId, Product.BrandId).order_by(Product.Name, Product.ProductId)).mappings().all()
        return {'Categories': categories, 'Brands': brands, 'Products': products}
