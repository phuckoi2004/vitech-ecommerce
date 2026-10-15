"""Report integration tests on isolated SQLite only; never connect to configured DATABASE_URL."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import Base, Brand, Category, Order, OrderItem, PaymentTransaction, Product, ProductVariant
from app.routers.errors import service_error_handler
from app.routers.statistics import admin_router, get_report_service
from app.services import Actor, ServiceError
from app.services.statistics_report import StatisticsReportService, report_buckets
from tests.fakes import Factory, InMemoryDB


@pytest.fixture
def reports(request):
    engine = create_engine('sqlite+pysqlite:///:memory:', poolclass=StaticPool, connect_args={'check_same_thread': False})
    metadata = MetaData()
    models = (Category, Brand, Product, ProductVariant, Order, OrderItem, PaymentTransaction)
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    metadata.tables['Products'].c.Specifications.type = JSON()
    metadata.tables['PaymentTransactions'].c.ResponseData.type = JSON()

    @event.listens_for(engine, 'connect')
    def functions(connection, _):
        connection.create_function('gen_random_uuid', 0, lambda: uuid.uuid4().hex)
        connection.create_function('now', 0, lambda: datetime.now(timezone.utc).isoformat(' '))
        connection.create_function('btrim', 1, lambda value: value.strip() if value is not None else None)

    metadata.create_all(engine, tables=[metadata.tables[model.__tablename__] for model in models])
    db = InMemoryDB(); f = Factory(db)
    customer, staff, admin = f.user(), f.user('Staff'), f.user('Admin')
    actors = [f.actor(user) for user in (customer, staff, admin)]
    current = {'actor': actors[1]}
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
    cancelled = f.order(customer, qr, status='Cancelled', lines=((first, 1), (other, 1)), ordered_at=time)
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
    assert len(result['Chart']) == 5
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
    assert len(sales['Chart']) == 5
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
    assert sales['Total'] == 3
    assert len([row for row in sales['Items'] if row['DateFrom'] == '2026-11-01']) == 1
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
        assert set(data) == {'Categories', 'Brands', 'Products'}
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
