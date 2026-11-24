"""Real HTTP/schema/service/repository exchange flow on isolated SQLite (never the configured database)."""
from sqlalchemy import select
from sqlalchemy.orm import Session
import pytest

from app.models import Category, Order, Product, ProductVariant, ReturnRequest
import uuid
from tests.test_service_request_progress import returns, returns_directory  # noqa: F401 - pytest fixtures


@pytest.mark.parametrize('endpoint,payload', [('accept', {}), ('advance', {'ExpectedStatus': 'Pending'})])
@pytest.mark.parametrize('raise_price', [False, True])
def test_acceptance_creates_order_in_customer_account_without_customer_post(returns, endpoint, payload, raise_price):
    client, engine, current, requests, actors, _ = returns
    if raise_price:
        with Session(engine) as session:
            variant = session.scalar(select(ProductVariant))
            variant.Price *= 2
            session.commit()
    rid = requests[1].ReturnRequestId
    path = f'/admin/return-requests/{rid}/{endpoint}'
    response = client.post(path, json=payload)
    assert response.status_code == 200, response.text
    exchange = response.json()['Exchange']
    assert exchange['OrderId'] and exchange['Committed'] and not exchange['CanChoose']
    assert client.post(path, json=payload).status_code == 409
    with Session(engine) as session:
        orders = list(session.scalars(select(Order).where(Order.SourceReturnRequestId == rid)))
        assert len(orders) == 1 and orders[0].CustomerId == actors[0].user_id
        assert orders[0].TotalAmount == 0 and orders[0].PaymentStatus == 'Paid'
        assert session.scalar(select(ProductVariant.StockQuantity)) == 4
    current['actor'] = actors[0]
    detail = client.get(f'/return-requests/{rid}')
    assert detail.status_code == 200 and detail.json()['Exchange']['OrderId'] == exchange['OrderId']


def test_customer_can_create_one_zero_order_and_staff_complete_only_after_settlement(returns):
    client, engine, current, requests, actors, _ = returns
    request_id = str(requests[0].ReturnRequestId)  # already accepted
    current['actor'] = actors[0]
    context = client.get(f'/return-requests/{request_id}/exchange')
    assert context.status_code == 200 and context.json()['OriginalInStock']
    path = f'/return-requests/{request_id}/exchange-order'
    created = client.post(path, json={})
    assert created.status_code == 200, created.text
    order = created.json()
    assert order['TotalAmount'] == '0.00' and order['PaymentStatus'] == 'Paid'
    assert order['SourceReturnRequestId'] == request_id and len(order['Items']) == 1
    assert order['Items'][0]['Quantity'] == 1
    assert client.post(path, json={}).json()['OrderId'] == order['OrderId']
    assert client.post(f'/return-requests/{request_id}/cancel').status_code == 400
    with Session(engine) as session:
        assert session.scalar(select(ProductVariant.StockQuantity)) == 4
        assert len(list(session.scalars(select(Order).where(Order.SourceReturnRequestId.is_not(None))))) == 1
    current['actor'] = actors[1]
    assert client.post(path, json={}).status_code == 403
    for state in ['Approved', 'Receiving', 'Processing']:
        result = {'DamageAssessment': 'Đã kiểm tra sản phẩm.', 'Note': 'Đã đổi sản phẩm cho khách.'} if state == 'Processing' else {}
        response = client.post(f'/admin/return-requests/{request_id}/advance', json={'ExpectedStatus': state, **result})
        assert response.status_code == 200, response.text
    with Session(engine) as session:
        assert session.get(ReturnRequest, requests[0].ReturnRequestId).Status == 'Completed'
        assert session.scalar(select(ProductVariant.StockQuantity)) == 5
    again = client.post(f'/admin/return-requests/{request_id}/advance', json={'ExpectedStatus': 'Processing'})
    assert again.status_code == 409


def test_exchange_payload_cannot_override_identity_credit_quantity_shipping_or_payment(returns):
    client, _, current, requests, actors, _ = returns
    current['actor'] = actors[0]
    path = f'/return-requests/{requests[0].ReturnRequestId}/exchange-order'
    for field in ['CustomerId', 'Quantity', 'ExchangeCreditAmount', 'TotalAmount', 'ShippingMethodId', 'PaymentMethodId']:
        response = client.post(path, json={field: 0})
        assert response.status_code == 422


def test_out_of_stock_original_allows_another_product_only_in_the_same_category(returns):
    client, engine, current, requests, actors, _ = returns
    request_id = requests[0].ReturnRequestId  # Already accepted, no replacement reserved yet.
    product_id, variant_id, other_category_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with Session(engine) as session:
        original = session.scalar(select(ProductVariant))
        original.StockQuantity = 0
        category_id = original.product.CategoryId
        category = session.get(Category, category_id)
        category_values = {c.key: getattr(category, c.key) for c in Category.__table__.columns}
        category_values.update(CategoryId=other_category_id, Slug='other-exchange-category', Name='Other category')
        session.add(Category(**category_values))
        product_values = {c.key: getattr(original.product, c.key) for c in Product.__table__.columns}
        product_values.update(ProductId=product_id, Slug='replacement-for-exchange', Name='Replacement product', CategoryId=other_category_id)
        session.add(Product(**product_values))
        variant_values = {c.key: getattr(original, c.key) for c in ProductVariant.__table__.columns}
        variant_values.update(ProductVariantId=variant_id, ProductId=product_id, Sku='EXCHANGE-OTHER', StockQuantity=2)
        session.add(ProductVariant(**variant_values))
        session.commit()
    current['actor'] = actors[0]
    context = client.get(f'/return-requests/{request_id}/exchange')
    assert context.status_code == 200, context.text
    assert context.json()['CanChoose'] and not context.json()['OriginalInStock']
    path = f'/return-requests/{request_id}/exchange-order'
    rejected = client.post(path, json={'ProductVariantId': str(variant_id)})
    assert rejected.status_code == 400 and rejected.json()['code'] == 'exchange_category_mismatch'
    with Session(engine) as session:
        assert session.scalar(select(Order).where(Order.SourceReturnRequestId == request_id)) is None
        assert session.get(ProductVariant, variant_id).StockQuantity == 2
        session.get(Product, product_id).CategoryId = category_id
        session.commit()
    created = client.post(path, json={'ProductVariantId': str(variant_id)})
    assert created.status_code == 200, created.text
    assert created.json()['SourceReturnRequestId'] == str(request_id)
    assert created.json()['Items'][0]['ProductVariantId'] == str(variant_id)
    with Session(engine) as session:
        assert session.get(ProductVariant, variant_id).StockQuantity == 1
