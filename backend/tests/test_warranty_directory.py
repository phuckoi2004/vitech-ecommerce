"""Warranty read enrichment on isolated SQLite; never uses the configured PostgreSQL database."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import Base, Order, OrderItem, ProductSerial, ServiceRequestAttachment, ServiceRequestHistory, User, WarrantyRequest
from app.repositories.service_request import WarrantyRequestRepository
from app.routers.dependencies import get_warranty_service
from app.routers.errors import service_error_handler
from app.routers.service_requests import admin_router, router
from app.services import Actor, ServiceError
from app.services.warranty import WarrantyService
from tests.fakes import Factory, InMemoryDB


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
    models = (User, Order, OrderItem, ProductSerial, WarrantyRequest, ServiceRequestAttachment, ServiceRequestHistory)
    metadata.create_all(engine, tables=[metadata.tables[model.__tablename__] for model in models])
    db = InMemoryDB(); factory = Factory(db)
    customer, staff, admin = factory.user(), factory.user('Staff'), factory.user('Admin')
    variant = factory.variant(stock=5)
    method = factory.payment_method()
    rows, orders = [], []
    now = datetime(2026, 10, 15, 8, tzinfo=timezone.utc)
    for index, status in enumerate(['New', 'Processing', 'Rejected']):
        order = factory.order(customer, method, status='Delivered', lines=((variant, 3),))
        orders.append(order)
        item = order.items[0]
        item.ProductName, item.Sku, item.VariantInfo = f'Tên lúc mua {index}', 'SKU-HISTORICAL', 'Đen / 256 GB'
        serial = db.add(ProductSerial(ProductVariantId=variant.ProductVariantId, OrderItemId=item.OrderItemId,
            SerialNumber=['359812345678712', 'SN-LAPTOP-02', 'UNRELATED-SERIAL'][index], Status='Sold'))
        rows.append(db.add(WarrantyRequest(RequestCode=f'BH-{index}', CustomerId=customer.UserId,
            OrderItemId=item.OrderItemId, ProductSerialId=serial.ProductSerialId if index < 2 else None,
            IssueDescription='Lỗi màn hình', EligibilityStatus='Pending', Status=status,
            RequestedAt=now - timedelta(days=index))))
    with engine.begin() as connection:
        for model in (User, Order, OrderItem, ProductSerial, WarrantyRequest):
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
            yield WarrantyService(session)

    app.dependency_overrides[get_warranty_service] = service
    with TestClient(app) as client:
        yield client, engine, current, rows, actors, orders
    engine.dispose()


def test_staff_and_admin_read_exact_serial_and_historical_context(directory):
    client, _, current, rows, actors, orders = directory
    for actor in actors[1:]:
        current['actor'] = actor
        listing = client.get('/admin/warranty-requests')
        assert listing.status_code == 200, listing.text
        assert listing.json()['Total'] == 3
        for index, row in enumerate(listing.json()['Items']):
            detail = client.get('/admin/warranty-requests/' + row['WarrantyRequestId'])
            assert detail.status_code == 200, detail.text
            for value in [row, detail.json()]:
                assert value['CustomerName'] is not None
                assert value['ProductName'] == f'Tên lúc mua {index}'
                assert value['Sku'] == 'SKU-HISTORICAL'
                assert value['VariantInfo'] == 'Đen / 256 GB'
                assert value['OrderId'] == str(orders[index].OrderId)
                assert value['OrderCode'] == orders[index].OrderCode
                assert value['SerialNumber'] == ['359812345678712', 'SN-LAPTOP-02', None][index]
                assert not {'PasswordHash', 'Email', 'PhoneNumber'} & value.keys()
            assert detail.json()['Attachments'] == detail.json()['Histories'] == []
    assert client.get('/admin/warranty-requests/' + str(uuid.uuid4())).status_code == 404


def test_existing_order_pagination_and_filters_are_preserved(directory):
    client, _, _, _, _, _ = directory
    response = client.get('/admin/warranty-requests?page=2&page_size=1')
    assert response.status_code == 200, response.text
    assert response.json()['Total'] == 3
    assert response.json()['Items'][0]['RequestCode'] == 'BH-1'
    filtered = client.get('/admin/warranty-requests?status=Rejected').json()
    assert filtered['Total'] == 1
    assert filtered['Items'][0]['RequestCode'] == 'BH-2'
    assert client.get('/admin/warranty-requests?page=5').json()['Items'] == []


def test_customer_can_read_own_product_context_without_internal_fields(directory):
    client, _, current, rows, actors, orders = directory
    current['actor'] = actors[0]
    path = '/admin/warranty-requests'
    assert client.get(path).status_code == 403
    assert client.get(path + '/' + str(rows[0].WarrantyRequestId)).status_code == 403
    listing = client.get('/warranty-requests')
    detail = client.get('/warranty-requests/' + str(rows[0].WarrantyRequestId))
    assert listing.status_code == detail.status_code == 200
    for row in [*listing.json()['Items'], detail.json()]:
        assert not {'CustomerName', 'CustomerId', 'Sku', 'AssignedStaffId', 'AssignedStaffName',
                    'SupplierId', 'InternalNote', 'ResultProposedByUserId', 'ResultApprovedByUserId'} & row.keys()
        index = next(i for i, request in enumerate(rows) if str(request.WarrantyRequestId) == row['WarrantyRequestId'])
        assert row['ProductName'] == f'Tên lúc mua {index}'
        assert row['OrderCode'] == orders[index].OrderCode
        assert row['SerialNumber'] == ['359812345678712', 'SN-LAPTOP-02', None][index]


def test_context_is_batched_without_querying_an_empty_page(directory):
    _, engine, _, rows, _, _ = directory
    statements = []
    def capture(_connection, _cursor, statement, _params, _context, _many):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        with Session(engine) as session:
            repository = WarrantyRequestRepository(session)
            context = repository.get_admin_context([r.WarrantyRequestId for r in rows])
            assert len(context) == 3 and len(statements) == 1
            assert context[rows[2].WarrantyRequestId]['SerialNumber'] is None
            assert repository.get_admin_context([]) == {}
            assert len(statements) == 1
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
