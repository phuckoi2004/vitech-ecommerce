"""Real HTTP/schema/service/repository exchange flow on isolated SQLite (never the configured database)."""
from sqlalchemy import select
from sqlalchemy.orm import Session
import pytest

from app.models import Order, ProductVariant, ReturnRequest
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
        response = client.post(f'/admin/return-requests/{request_id}/advance', json={'ExpectedStatus': state})
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
