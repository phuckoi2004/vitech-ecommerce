"""Read-only return directory checks against isolated in-memory SQLite, never the configured DB."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import Base, Order, OrderItem, ProductSerial, ReturnRequest, ServiceRequestAttachment, ServiceRequestHistory, User
from app.repositories.service_request import ReturnRequestRepository
from app.routers.dependencies import get_return_service
from app.routers.errors import service_error_handler
from app.routers.service_requests import admin_router, router
from app.services import Actor, ServiceError
from app.services.returns import ReturnService
from tests.fakes import Factory, InMemoryDB
from app.models import Product, ProductVariant, Category, Brand, Promotion, PromotionCategory, PromotionProduct, ShippingMethod, PaymentMethod, OrderStatusHistory, Review


@pytest.fixture
def directory():
    engine = create_engine('sqlite+pysqlite:///:memory:', poolclass=StaticPool, connect_args={'check_same_thread': False})

    @event.listens_for(engine, 'connect')
    def functions(connection, _):
        connection.create_function('gen_random_uuid', 0, lambda: uuid.uuid4().hex)
        connection.create_function('now', 0, lambda: datetime.now(timezone.utc).isoformat(' '))
        connection.create_function('num_nonnulls', -1, lambda *values: sum(value is not None for value in values))

    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    # Only the test DDL uses generic JSON; the application mapping is unchanged.
    from sqlalchemy.dialects.postgresql import JSONB
    for table in metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
    models = (User, Order, OrderItem, ProductSerial, ReturnRequest, ServiceRequestAttachment, ServiceRequestHistory,
              Category, Brand, Product, ProductVariant, Promotion, PromotionCategory, PromotionProduct, ShippingMethod, PaymentMethod, OrderStatusHistory, Review)
    metadata.create_all(engine, tables=[metadata.tables[model.__tablename__] for model in models])
    db = InMemoryDB(); factory = Factory(db)
    customer, staff, admin = factory.user(), factory.user('Staff'), factory.user('Admin')
    # Directory-only scenarios have no original replacement available. Stocked acceptance
    # and automatic-order side effects are covered by the progress/exchange fixtures.
    variant = factory.variant(stock=0)
    order = factory.order(customer, factory.payment_method(), status='Delivered', lines=((variant, 3),))
    for method in db.rows(ShippingMethod):
        method.Code = 'STANDARD'
    item = order.items[0]
    item.ProductName, item.Sku, item.VariantInfo = 'Tên sản phẩm lúc mua', 'SKU-HISTORICAL', 'Đen / 256 GB'
    now = datetime(2026, 10, 15, 8, tzinfo=timezone.utc)
    rows = []
    for index, (status, days) in enumerate([('Approved', 0), ('Pending', 4), ('Rejected', 1), ('Pending', 2)]):
        rows.append(db.add(ReturnRequest(RequestCode=f'RT-{index}', CustomerId=customer.UserId,
            OrderItemId=item.OrderItemId, RequestType='Return', Quantity=1, Reason='Lỗi màn hình',
            Status=status, RequestedAt=now - timedelta(days=days))))
    with engine.begin() as connection:
        for model in models:
            for obj in db.rows(model):
                connection.execute(metadata.tables[model.__tablename__].insert().values(
                    **{column.key: getattr(obj, column.key) for column in model.__table__.columns}))
    actors = [Actor(user.UserId, user.Role) for user in [customer, staff, admin]]
    current = {'actor': actors[1]}
    app = FastAPI(); app.include_router(admin_router); app.include_router(router)
    app.add_exception_handler(ServiceError, service_error_handler)
    app.dependency_overrides[get_current_actor] = lambda: current['actor']

    def service():
        with Session(engine) as session:
            yield ReturnService(session)

    app.dependency_overrides[get_return_service] = service
    with TestClient(app) as client:
        yield client, engine, current, rows, actors, order
    engine.dispose()


def test_pending_priority_is_global_before_pagination_and_opt_in(directory):
    client, _, _, _, _, _ = directory
    path = '/admin/return-requests'
    def codes(query):
        response = client.get(path, params=query)
        assert response.status_code == 200, response.text
        assert response.json()['Total'] == 4
        return [r['RequestCode'] for r in response.json()['Items']]
    assert codes({'page_size': 2}) == ['RT-0', 'RT-2']
    assert codes({'pending_first': True, 'page_size': 2}) == ['RT-3', 'RT-1']
    assert codes({'pending_first': True, 'page_size': 2, 'page': 2}) == ['RT-0', 'RT-2']
    filtered = client.get(path, params={'pending_first': True, 'status': 'Rejected'}).json()
    assert filtered['Total'] == 1 and filtered['Items'][0]['RequestCode'] == 'RT-2'
    assert client.get(path, params={'pending_first': 'invalid'}).status_code == 422


def test_staff_and_admin_receive_historical_order_context_without_user_secrets(directory):
    client, _, current, rows, actors, order = directory
    for actor in actors[1:]:
        current['actor'] = actor
        listing = client.get('/admin/return-requests')
        detail = client.get('/admin/return-requests/' + str(rows[0].ReturnRequestId))
        assert listing.status_code == detail.status_code == 200
        for row in [*listing.json()['Items'], detail.json()]:
            assert row['CustomerName'] is not None
            assert row['ProductName'] == 'Tên sản phẩm lúc mua'
            assert row['Sku'] == 'SKU-HISTORICAL'
            assert row['VariantInfo'] == 'Đen / 256 GB'
            assert row['OrderCode'] == order.OrderCode
            assert row['OrderId'] == str(order.OrderId)
            assert not {'PasswordHash', 'Email', 'PhoneNumber'} & row.keys()
        assert detail.json()['Attachments'] == [] and detail.json()['Histories'] == []
    assert client.get('/admin/return-requests/' + str(uuid.uuid4())).status_code == 404


def test_customer_reads_own_product_context_without_internal_fields(directory):
    client, _, current, rows, actors, order = directory
    current['actor'] = actors[0]
    assert client.get('/admin/return-requests?pending_first=true').status_code == 403
    assert client.get('/admin/return-requests/' + str(rows[0].ReturnRequestId)).status_code == 403
    response = client.get('/return-requests')
    assert response.status_code == 200
    assert response.json()['Total'] == 4
    detail = client.get('/return-requests/' + str(rows[0].ReturnRequestId))
    assert detail.status_code == 200
    for row in [*response.json()['Items'], detail.json()]:
        assert not {'CustomerName', 'CustomerId', 'Sku', 'AssignedStaffId', 'AssignedStaffName',
                    'CompensationBasis', 'CompensationApprovedByUserId', 'InternalNote'} & row.keys()
        assert row['ProductName'] == 'Tên sản phẩm lúc mua'
        assert row['OrderId'] == str(order.OrderId)
        assert row['OrderCode'] == order.OrderCode
        assert row['SerialNumber'] is None


def test_customer_context_reads_the_exact_requested_device(directory):
    client, engine, current, rows, actors, order = directory
    current['actor'] = actors[0]
    serial_id, unrelated_id = uuid.uuid4(), uuid.uuid4()
    item = order.items[0]
    with engine.begin() as connection:
        connection.execute(ProductSerial.__table__.insert(), [
            {'ProductSerialId': serial_id, 'ProductVariantId': item.ProductVariantId,
             'OrderItemId': item.OrderItemId, 'SerialNumber': 'EXACT-REQUESTED-IMEI', 'Status': 'Sold'},
            {'ProductSerialId': unrelated_id, 'ProductVariantId': item.ProductVariantId,
             'OrderItemId': item.OrderItemId, 'SerialNumber': 'OTHER-DEVICE-SAME-LINE', 'Status': 'Sold'},
        ])
        connection.execute(ReturnRequest.__table__.update().where(ReturnRequest.ReturnRequestId == rows[0].ReturnRequestId)
                           .values(ProductSerialId=serial_id))
    detail = client.get('/return-requests/' + str(rows[0].ReturnRequestId))
    assert detail.status_code == 200, detail.text
    assert detail.json()['SerialNumber'] == 'EXACT-REQUESTED-IMEI'
    assert 'OTHER-DEVICE-SAME-LINE' not in detail.text
    listing = client.get('/return-requests').json()['Items']
    assert next(row for row in listing if row['ReturnRequestId'] == str(rows[0].ReturnRequestId))['SerialNumber'] == 'EXACT-REQUESTED-IMEI'


def test_customer_cannot_read_another_customers_enriched_request(directory):
    client, _, current, rows, _, _ = directory
    current['actor'] = Actor(uuid.uuid4(), 'Customer')
    assert client.get('/return-requests').json()['Items'] == []
    assert client.get('/return-requests/' + str(rows[0].ReturnRequestId)).status_code == 404


def test_context_is_batched_and_empty_page_does_not_query(directory):
    _, engine, _, rows, _, _ = directory
    statements = []
    def capture(_connection, _cursor, statement, _params, _context, _many):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        with Session(engine) as session:
            repository = ReturnRequestRepository(session)
            assert len(repository.get_admin_context([r.ReturnRequestId for r in rows])) == 4
            assert len(statements) == 1
            assert repository.get_admin_context([]) == {}
            assert len(statements) == 1
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
