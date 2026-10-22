"""Report integration tests on isolated SQLite only; never connect to configured DATABASE_URL."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine, event, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import (Base, Brand, Category, Conversation, Message, Order, OrderItem, PaymentTransaction,
    Product, ProductVariant, PurchaseOrder, PurchaseOrderItem, PurchaseReceipt, PurchaseReceiptItem,
    Supplier, StockAdjustment, ReturnRequest, User, WarrantyRequest)
from app.routers.errors import service_error_handler
from app.routers.statistics import admin_router, get_report_service
from app.services import Actor, ServiceError
from app.services.statistics_report import StatisticsReportService, report_buckets
from tests.fakes import Factory, InMemoryDB


@pytest.fixture
def reports(request):
    engine = create_engine('sqlite+pysqlite:///:memory:', poolclass=StaticPool, connect_args={'check_same_thread': False})
    metadata = MetaData()
    models = (User, Category, Brand, Product, ProductVariant, Order, OrderItem, PaymentTransaction,
              Conversation, Message, ReturnRequest, WarrantyRequest, Supplier, PurchaseOrder, PurchaseOrderItem,
              PurchaseReceipt, PurchaseReceiptItem, StockAdjustment)
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    metadata.tables['Products'].c.Specifications.type = JSON()
    metadata.tables['PaymentTransactions'].c.ResponseData.type = JSON()
    metadata.tables['Messages'].c.Metadata.type = JSON()

    @event.listens_for(engine, 'connect')
    def functions(connection, _):
        connection.create_function('gen_random_uuid', 0, lambda: uuid.uuid4().hex)
        connection.create_function('now', 0, lambda: datetime.now(timezone.utc).isoformat(' '))
        connection.create_function('btrim', 1, lambda value: value.strip() if value is not None else None)

    metadata.create_all(engine, tables=[metadata.tables[model.__tablename__] for model in models])
    db = InMemoryDB(); f = Factory(db)
    customer, staff, admin = f.user(), f.user('Staff'), f.user('Admin')
    actors = [f.actor(user) for user in (customer, staff, admin)]
    current = {'actor': actors[1], 'engine': engine}
    first, other = f.variant(price='100.00'), f.variant(price='200.00')
    # Two SKUs under the same parent product, both present on the same order.
    sibling = f.variant(price='50.00')
    sibling.ProductId, sibling.product = first.ProductId, first.product
    qr = f.payment_method()
    time = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    delivered = f.order(customer, qr, status='Delivered', total='245.00',
        lines=((first, 2), (sibling, 1)), ordered_at=time)
    delivered.DeliveredAt = time
    # Allocated discount is already in the historical line amount.
    delivered.items[0].DiscountAmount = Decimal('5.00')
    delivered.items[0].LineTotal = Decimal('195.00')
    f.payment(delivered, amount='200', gateway_code='PAY-1')
    f.payment(delivered, amount='45', gateway_code='PAY-2')
    cancelled = f.order(customer, qr, status='Cancelled', lines=((first, 1), (sibling, 1), (other, 1)), ordered_at=time)
    pending = f.order(customer, qr, lines=((first, 1),), ordered_at=time)
    unpaid = f.order(customer, qr, status='Completed', lines=((other, 1),), ordered_at=time)
    unpaid.DeliveredAt = time
    f.payment(unpaid, status='Failed', gateway_code='PAY-FAILED')
    # 00:00 Vietnam belongs to October; the preceding second is September.
    edge = f.order(customer, qr, status='Completed', lines=((other, 1),),
        ordered_at=datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc))
    edge.DeliveredAt = edge.OrderedAt
    f.payment(edge, gateway_code='PAY-EDGE')
    outside = f.order(customer, qr, status='Delivered', lines=((first, 1),),
        ordered_at=datetime(2026, 9, 30, 16, 59, 59, tzinfo=timezone.utc))
    outside.DeliveredAt = outside.OrderedAt
    f.payment(outside, gateway_code='PAY-OUTSIDE')
    # Waiting chats count only staff chats the customer has written in, not ones merely opened.
    db.add(Conversation(CustomerId=customer.UserId, Mode='Staff', Status='Open', CreatedAt=time))
    asked = db.add(Conversation(CustomerId=f.user().UserId, Mode='Staff', Status='Open', CreatedAt=time))
    db.add(Message(ConversationId=asked.ConversationId, SenderUserId=asked.CustomerId, SenderType='Customer',
                   MessageType='Text', Content='Cần tư vấn', IsRead=False, SentAt=time))
    if getattr(request, 'param', None) == 'monthly':
        for variant, timestamp in ((first, datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)),
                                   (other, datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc))):
            later = f.order(customer, qr, status='Completed', lines=((variant, 1),), ordered_at=timestamp)
            later.DeliveredAt = timestamp
            f.payment(later, gateway_code='PAY-' + str(later.OrderId))
    # Historical sales must survive current price changes and product soft deletion.
    first.Price, first.product.IsDeleted = Decimal('99999.00'), True
    with engine.begin() as connection:
        for model in models:
            for obj in db.rows(model):
                connection.execute(metadata.tables[model.__tablename__].insert().values(
                    **{column.key: getattr(obj, column.key) for column in model.__table__.columns}))
    app = FastAPI(); app.include_router(admin_router)
    app.add_exception_handler(ServiceError, service_error_handler)
    app.dependency_overrides[get_current_actor] = lambda: current['actor']

    def service():
        with Session(engine) as session:
            yield StatisticsReportService(session)
    app.dependency_overrides[get_report_service] = service
    statements = []
    @event.listens_for(engine, 'before_cursor_execute')
    def record(_, __, statement, ___, ____, _____):
        statements.append(statement)
    with TestClient(app) as client:
        yield client, current, actors, first, other, statements
    engine.dispose()


PERIOD = {'date_from': '2026-10-01', 'date_to': '2026-10-31'}


def fetch(client, kind, **query):
    response = client.get('/admin/statistics/reports/' + kind, params={**PERIOD, **query})
    assert response.status_code == 200, response.text
    return response.json()


def test_sales_snapshot_discounts_distinct_orders_and_payment_exists(reports):
    client, _, _, first, _, statements = reports
    result = fetch(client, 'revenue')
    assert Decimal(result['Summary']['Revenue']) == Decimal('445.00')
    assert result['Summary']['TotalOrders'] == 2
    assert Decimal(result['Summary']['AverageOrderValue']) == Decimal('222.50')
    assert Decimal(result['Summary']['PeakRevenue']) == Decimal('445.00')
    assert len(result['Chart']) == 31
    assert result['Total'] == 2
    row = next(row for row in result['Items'] if row['ProductId'] == str(first.ProductId))
    assert Decimal(row['Revenue']) == Decimal('245.00')
    assert row['CategoryName'] and row['BrandName']
    assert result['Period']['StartsAt'] == '2026-09-30T17:00:00Z'
    assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)


def test_orders_count_once_with_multiple_lines_and_product_filters_combine(reports):
    client, _, _, first, other, _ = reports
    result = fetch(client, 'orders')
    assert result['Summary']['TotalOrders'] == 5
    assert result['Summary']['DeliveredOrders'] == 3
    assert result['Summary']['CancelledOrders'] == 1
    result = fetch(client, 'orders', product_id=str(first.ProductId))
    assert result['Summary']['TotalOrders'] == 3
    assert result['Summary']['DeliveredOrders'] == 1
    assert result['Summary']['CancelledOrders'] == 1
    result = fetch(client, 'revenue', category_id=str(first.product.CategoryId), brand_id=str(other.product.BrandId))
    assert result['Summary']['TotalOrders'] == 0
    assert result['Items'] == []


def test_sales_filter_and_pagination_do_not_limit_summary_or_chart(reports):
    client, _, _, first, _, statements = reports
    page1 = fetch(client, 'revenue', page_size=1)
    page2 = fetch(client, 'revenue', page_size=1, page=2)
    assert page1['Total'] == page2['Total'] == 2
    assert page1['Summary'] == page2['Summary']
    assert page1['Chart'] == page2['Chart']
    assert page1['Items'][0]['Key'] != page2['Items'][0]['Key']
    assert any('LIMIT' in sql and 'OFFSET' in sql for sql in statements)
    result = fetch(client, 'revenue', product_id=str(first.ProductId))
    assert result['Total'] == 1 and Decimal(result['Summary']['Revenue']) == Decimal('245.00')
    assert result['Summary']['TotalOrders'] == 1


def test_daily_inclusive_boundaries_and_empty_month(reports):
    client, _, _, _, _, _ = reports
    result = fetch(client, 'revenue', date_to='2026-10-01')
    assert len(result['Chart']) == 1
    assert result['Summary']['TotalOrders'] == 2
    result = fetch(client, 'orders', date_from='2026-11-01', date_to='2026-11-30')
    assert result['Summary']['TotalOrders'] == 0
    assert result['Items'] == [] and result['Total'] == 0
    assert all(point['TotalOrders'] == 0 for point in result['Chart'])


@pytest.mark.parametrize('reports', ['monthly'], indirect=True)
def test_detail_tables_merge_weeks_into_months_with_same_filters(reports):
    client, _, _, first, _, _ = reports
    sales = fetch(client, 'revenue')
    assert len(sales['Chart']) == 31
    assert sales['Total'] == 2  # one row per product/month, even when sold in several weeks
    first_row = next(row for row in sales['Items'] if row['ProductId'] == str(first.ProductId))
    assert Decimal(first_row['Revenue']) == Decimal('345.00')
    assert first_row['DateFrom'] == '2026-10-01' and first_row['DateTo'] == '2026-10-31'
    assert sum(Decimal(row['Revenue']) for row in sales['Items']) == Decimal(sales['Summary']['Revenue'])
    orders = fetch(client, 'orders')
    assert orders['Total'] == 1
    assert orders['Items'][0]['TotalOrders'] == orders['Summary']['TotalOrders'] == 6
    assert orders['Items'][0]['DeliveredOrders'] == 4
    for kind in ('revenue', 'orders'):
        filtered = fetch(client, kind, date_from='2026-10-08', product_id=str(first.ProductId))
        assert filtered['Total'] == 1
        assert filtered['Summary']['TotalOrders'] == 1
        assert filtered['Items'][0]['DateFrom'] == '2026-10-08'
        if kind == 'revenue':
            assert Decimal(filtered['Items'][0]['Revenue']) == Decimal('100.00')
        else:
            assert filtered['Items'][0]['TotalOrders'] == 1


@pytest.mark.parametrize('reports', ['monthly'], indirect=True)
def test_monthly_details_split_at_vietnam_month_boundary_and_page_after_grouping(reports):
    client, _, _, _, _, _ = reports
    sales = fetch(client, 'revenue', date_to='2026-11-30')
    assert sales['Total'] == 2  # one product across the entire range, including several months
    assert all(row['DateFrom'] == '2026-10-01' and row['DateTo'] == '2026-11-30' for row in sales['Items'])
    assert sum(Decimal(row['Revenue']) for row in sales['Items']) == Decimal('745.00')
    orders = fetch(client, 'orders', date_to='2026-11-30', page_size=1, page=2)
    assert orders['Total'] == 2 and orders['Summary']['TotalOrders'] == 7
    assert len(orders['Items']) == 1
    assert orders['Items'][0]['DateFrom'] == '2026-11-01'
    assert orders['Items'][0]['TotalOrders'] == 1


def test_staff_admin_options_are_minimal_and_keep_historical_products(reports):
    client, current, actors, first, _, _ = reports
    for actor in actors[1:]:
        current['actor'] = actor
        response = client.get('/admin/statistics/report-options')
        assert response.status_code == 200
        data = response.json()
        assert set(data) == {'Categories', 'Brands', 'Products', 'Suppliers'}
        historical = next(row for row in data['Products'] if row['Id'] == str(first.ProductId))
        assert set(historical) == {'Id', 'Name', 'CategoryId', 'BrandId'}
        assert fetch(client, 'revenue')['Summary']['TotalOrders'] == 2


def test_permissions_and_invalid_query_inputs(reports):
    client, current, actors, _, _, _ = reports
    for path in ('/report-options', '/reports/orders', '/reports/revenue'):
        current['actor'] = actors[0]
        assert client.get('/admin/statistics' + path, params=PERIOD).status_code == 403
    current['actor'] = actors[1]
    for query in ({'product_id': 'invalid'}, {'page': 0}, {'page_size': 101}, {'date_from': 'bad'}):
        assert client.get('/admin/statistics/reports/orders', params={**PERIOD, **query}).status_code == 422
    for query in ({'date_to': '2026-09-01'}, {'date_to': '2028-10-31'}):
        assert client.get('/admin/statistics/reports/orders', params={**PERIOD, **query}).status_code == 400


def test_bucket_partition_is_complete_no_overlap_at_leap_year_or_year_change():
    for start, end in ((date(2024, 2, 1), date(2024, 2, 29)),
                       (date(2025, 12, 15), date(2026, 3, 2)),
                       (date(2026, 10, 1), date(2026, 10, 7))):
        buckets = report_buckets(start, end)
        assert buckets[0][0] == start and buckets[-1][1] == end
        assert sum((last - first).days + 1 for first, last, _ in buckets) == (end - start).days + 1
        assert all((right[0] - left[1]).days == 1 for left, right in zip(buckets, buckets[1:]))


def test_import_price_snapshot_profit_and_sorting(reports):
    client, current, _, first, _, _ = reports
    initial = fetch(client, 'revenue')
    assert Decimal(initial['Summary']['Cost']) == Decimal('280000')
    assert Decimal(initial['Summary']['Profit']) == Decimal('445') - Decimal('280000')
    assert sum(row['Quantity'] for row in initial['Items']) == initial['Summary']['Quantity'] == 4
    assert sum(Decimal(row['Cost']) for row in initial['Items']) == Decimal(initial['Summary']['Cost'])
    # New catalog import prices never rewrite historical order snapshots.
    with current['engine'].begin() as connection:
        connection.execute(update(ProductVariant).where(ProductVariant.ProductId == first.ProductId).values(CostPrice=999999))
    assert fetch(client, 'revenue')['Summary'] == initial['Summary']
    asc = fetch(client, 'revenue', sort='revenue_asc', page_size=1)
    desc = fetch(client, 'revenue', sort='revenue_desc', page_size=1)
    assert Decimal(asc['Items'][0]['Revenue']) < Decimal(desc['Items'][0]['Revenue'])
    assert asc['Summary'] == desc['Summary']
    assert initial['TopProducts'][0]['ProductId'] == desc['Items'][0]['ProductId']


def test_missing_import_price_is_unknown_at_every_level(reports):
    client, current, _, first, _, _ = reports
    with current['engine'].begin() as connection:
        connection.execute(update(OrderItem).where(OrderItem.ProductVariantId == first.ProductVariantId).values(UnitCost=0))
    result = fetch(client, 'revenue')
    assert result['Summary']['Cost'] is None and result['Summary']['Profit'] is None
    assert result['Summary']['Margin'] is None and result['Summary']['LinesMissingCost'] == 1
    product = next(row for row in result['Items'] if row['ProductId'] == str(first.ProductId))
    assert product['Cost'] is None and product['Profit'] is None
    assert any(row['Cost'] is not None for row in result['Items'])
    assert result['Chart'][0]['Profit'] is None
    lines = client.get('/admin/statistics/reports/revenue/lines', params={**PERIOD, 'product_id': str(first.ProductId)}).json()
    missing = next(row for row in lines['Items'] if row['UnitCost'] is None)
    assert missing['Cost'] is None and missing['Profit'] is None


def test_product_drilldown_keeps_snapshots_and_filters_and_pages_in_sql(reports):
    client, _, _, first, other, statements = reports
    query = {**PERIOD, 'product_id': str(first.ProductId), 'page_size': 1}
    pages = [client.get('/admin/statistics/reports/revenue/lines', params={**query, 'page': page}) for page in (1, 2)]
    assert all(response.status_code == 200 for response in pages)
    rows = [response.json()['Items'][0] for response in pages]
    assert all(response.json()['Total'] == 2 for response in pages)
    assert rows[0]['Key'] != rows[1]['Key'] and rows[0]['OrderId'] == rows[1]['OrderId']
    assert sum(Decimal(row['Revenue']) for row in rows) == Decimal('245')
    for row in rows:
        assert Decimal(row['UnitPrice']) * row['Quantity'] - Decimal(row['Discount']) == Decimal(row['Revenue'])
        assert Decimal(row['UnitCost']) == Decimal('70000')
    empty = client.get('/admin/statistics/reports/revenue/lines', params={**query, 'brand_id': str(other.product.BrandId)})
    assert empty.status_code == 200 and empty.json()['Total'] == 0
    assert any('LIMIT' in sql and 'OFFSET' in sql for sql in statements)


def test_workload_and_cancellation_reasons_are_read_only(reports):
    client, _, _, _, _, statements = reports
    response = client.get('/admin/statistics/workload')
    assert response.status_code == 200
    assert response.json() == {'PendingOrders': 1, 'WaitingChats': 1, 'PendingReturns': 0, 'NewWarranties': 0}
    report = fetch(client, 'orders')
    assert report['Summary']['InProgressOrders'] == 1
    assert sum(item['TotalOrders'] for item in report['CancellationReasons']) == 1
    assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)


def test_new_report_endpoints_validate_and_reject_customers(reports):
    client, current, actors, first, _, _ = reports
    path = '/admin/statistics/reports/revenue/lines'
    assert client.get(path, params=PERIOD).status_code == 422
    assert client.get(path, params={**PERIOD, 'product_id': 'bad'}).status_code == 422
    assert client.get(path, params={**PERIOD, 'product_id': str(first.ProductId), 'variant_id': 'bad'}).status_code == 422
    assert client.get('/admin/statistics/reports/revenue', params={**PERIOD, 'group_by': 'bad'}).status_code == 422
    assert client.get('/admin/statistics/reports/revenue', params={**PERIOD, 'sort': 'unsafe'}).status_code == 422
    current['actor'] = actors[0]
    assert client.get(path, params={**PERIOD, 'product_id': str(first.ProductId)}).status_code == 403
    assert client.get('/admin/statistics/workload').status_code == 403


def test_dashboard_month_series_matches_the_same_month_report(reports):
    client, _, _, _, _, _ = reports
    series = fetch(client, 'revenue', date_from='2026-05-01', date_to='2026-10-21')
    current = fetch(client, 'revenue', date_to='2026-10-21')
    point = next(point for point in series['Chart'] if point['DateFrom'] == '2026-10-01')
    for key in ('Revenue', 'Cost', 'Profit', 'TotalOrders', 'Quantity', 'LinesMissingCost', 'Margin'):
        assert point[key] == current['Summary'][key]


def test_cancelled_order_details_match_report_filters_without_duplicate_skus(reports):
    client, current, actors, first, other, statements = reports
    with current['engine'].begin() as connection:
        connection.execute(update(Order).where(Order.OrderStatus == 'Cancelled').values(
            CancelReason='Đổi nhu cầu mua hàng', ShippingFee=Decimal('30'), TotalAmount=Decimal('380')))
    for actor in actors[1:]:
        current['actor'] = actor
        for filters in ({}, {'product_id': str(first.ProductId)},
                        {'category_id': str(first.product.CategoryId), 'brand_id': str(first.product.BrandId)},
                        {'product_id': str(other.ProductId)},
                        {'product_id': str(first.ProductId), 'brand_id': str(other.product.BrandId)}):
            summary = fetch(client, 'orders', **filters)
            statements.clear()
            details = fetch(client, 'orders/cancelled', **filters)
            assert details['Total'] == summary['Summary']['CancelledOrders']
            assert len(details['Items']) == details['Total']
            assert len(statements) == 2
            assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
            if details['Total']:
                [row] = details['Items']
                assert set(row) == {'OrderId', 'OrderCode', 'OrderedAt', 'CustomerName', 'TotalAmount', 'CancelReason'}
                assert row['CustomerName'] == 'User 1'
                assert row['CancelReason'] == 'Đổi nhu cầu mua hàng'
                assert Decimal(row['TotalAmount']) == Decimal('380')  # whole order, including shipping


def test_cancelled_order_pages_use_placement_dates_and_stable_sql_pagination(reports):
    client, current, _, _, _, statements = reports
    # Delivery/payment dates do not decide the scope of the orders report.
    with current['engine'].begin() as connection:
        connection.execute(update(Order).values(OrderStatus='Cancelled',
            DeliveredAt=datetime(2020, 1, 1, tzinfo=timezone.utc), CancelReason=None))
    statements.clear()
    pages = [fetch(client, 'orders/cancelled', page=page, page_size=2) for page in (1, 2, 3)]
    assert [len(page['Items']) for page in pages] == [2, 2, 1]
    assert all(page['Total'] == 5 for page in pages)
    rows = [row for page in pages for row in page['Items']]
    assert len({row['OrderId'] for row in rows}) == 5
    assert rows[-1]['OrderedAt'].startswith('2026-09-30T17:00:00')
    assert all(row['CancelReason'] is None for row in rows)
    assert rows[:2] == fetch(client, 'orders/cancelled', page_size=2)['Items']
    assert fetch(client, 'orders/cancelled', page=4, page_size=2)['Items'] == []
    assert any('LIMIT' in sql and 'OFFSET' in sql for sql in statements)
    empty = fetch(client, 'orders/cancelled', date_from='2026-11-01', date_to='2026-11-30')
    assert empty['Total'] == 0 and empty['Items'] == []


@pytest.mark.parametrize('query,code', [({'product_id': 'bad'}, 422), ({'page': 0}, 422),
    ({'page_size': 101}, 422), ({'date_from': 'bad'}, 422),
    ({'date_to': '2026-09-01'}, 400), ({'date_to': '2028-10-31'}, 400)])
@pytest.mark.parametrize('kind', ['cancelled', 'delivered'])
def test_order_detail_validation_and_customer_access(reports, query, code, kind):
    client, current, actors, _, _, _ = reports
    path = '/admin/statistics/reports/orders/' + kind
    assert client.get(path, params={**PERIOD, **query}).status_code == code
    current['actor'] = actors[0]
    assert client.get(path, params=PERIOD).status_code == 403


def test_delivered_details_match_order_summary_including_unpaid_completed_orders(reports):
    client, current, actors, first, other, statements = reports
    assert fetch(client, 'revenue')['Summary']['TotalOrders'] == 2
    for actor in actors[1:]:
        current['actor'] = actor
        for filters, expected in (({}, 3), ({'product_id': str(first.ProductId)}, 1),
                ({'category_id': str(first.product.CategoryId), 'brand_id': str(first.product.BrandId)}, 1),
                ({'product_id': str(other.ProductId)}, 2),
                ({'product_id': str(first.ProductId), 'brand_id': str(other.product.BrandId)}, 0)):
            summary = fetch(client, 'orders', **filters)
            statements.clear()
            details = fetch(client, 'orders/delivered', **filters)
            assert details['Total'] == summary['Summary']['DeliveredOrders'] == expected
            assert len(details['Items']) == expected
            assert len({row['OrderId'] for row in details['Items']}) == expected
            assert len(statements) == 2
            assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
            for row in details['Items']:
                assert set(row) == {'OrderId', 'OrderCode', 'OrderedAt', 'DeliveredAt',
                                   'CustomerName', 'TotalAmount', 'OrderStatus'}
                assert row['CustomerName'] == 'User 1'
                assert row['OrderStatus'] in ('Delivered', 'Completed')
            if filters == {'product_id': str(first.ProductId)}:
                # Multiple matching SKUs and payment retries still produce one whole-order row.
                assert Decimal(details['Items'][0]['TotalAmount']) == Decimal('245')


def test_delivered_details_use_placement_dates_even_without_delivery_timestamp(reports):
    client, current, _, _, _, statements = reports
    with current['engine'].begin() as connection:
        connection.execute(update(Order).values(OrderStatus='Delivered', DeliveredAt=None))
    statements.clear()
    pages = [fetch(client, 'orders/delivered', page=page, page_size=2) for page in (1, 2, 3)]
    assert [len(page['Items']) for page in pages] == [2, 2, 1]
    assert all(page['Total'] == 5 for page in pages)
    rows = [row for page in pages for row in page['Items']]
    assert len({row['OrderId'] for row in rows}) == 5
    assert rows[-1]['OrderedAt'].startswith('2026-09-30T17:00:00')
    assert all(row['DeliveredAt'] is None for row in rows)
    assert rows[:2] == fetch(client, 'orders/delivered', page_size=2)['Items']
    assert fetch(client, 'orders/delivered', page=4, page_size=2)['Items'] == []
    assert any('LIMIT' in sql and 'OFFSET' in sql for sql in statements)
    empty = fetch(client, 'orders/delivered', date_from='2026-11-01', date_to='2026-11-30')
    assert empty['Total'] == 0 and empty['Items'] == []
    with current['engine'].begin() as connection:
        connection.execute(update(Order).values(DeliveredAt=datetime(2020, 1, 1, tzinfo=timezone.utc)))
    assert fetch(client, 'orders/delivered')['Total'] == 5
