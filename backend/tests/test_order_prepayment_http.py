"""HTTP + real SQLAlchemy storage on isolated SQLite, without external payment calls."""
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, PaymentMethod, PaymentTransaction
from app.routers import orders, payments
from app.routers.dependencies import get_order_service, get_payment_service
from app.services.order import OrderService
from app.services.payment import BankTransfer, PaymentService
from app.services.ports import QrPaymentRequest
from tests.fakes import NOW
from tests.test_service_request_progress import returns, returns_directory  # noqa: F401 - fixtures


class LocalGateway:
    def create_qr_payment(self, *, order_code, amount):
        return QrPaymentRequest(gateway_transaction_code="DEPOSIT-TEST", qr_data="https://example.test/qr",
                                response_data={"bank": "Test Bank"})


def test_verified_deposit_and_cod_balance_through_http_and_real_repositories(returns):
    client, engine, current, _, actors, original = returns
    app = client.app
    app.include_router(orders.router)
    app.include_router(orders.admin_router)
    app.include_router(payments.router)
    clock = lambda: NOW.replace(tzinfo=None)  # SQLite stores datetime without offsets.
    gateway = LocalGateway()

    def order_service():
        with Session(engine) as session:
            yield OrderService(session, clock=clock)

    def payment_service():
        with Session(engine) as session:
            yield PaymentService(session, gateway=gateway, clock=clock)

    app.dependency_overrides[get_order_service] = order_service
    app.dependency_overrides[get_payment_service] = payment_service
    order_id = uuid.uuid4()
    with Session(engine) as session:
        source = session.get(Order, original.OrderId)
        values = {column.key: getattr(source, column.key) for column in Order.__table__.columns}
        cod = session.get(PaymentMethod, source.PaymentMethodId)
        cod.Code = "COD"
        session.add(PaymentMethod(Code="QR", Name="sepay", IsActive=True))
        values.update(OrderId=order_id, OrderCode="PREPAY-HTTP", OrderStatus="Pending", PaymentStatus="Pending",
                      Subtotal=Decimal("12000000"), TotalAmount=Decimal("12000000"), DiscountAmount=0,
                      PrepaymentAmount=Decimal("2400000"), ShippingFee=0, OrderedAt=clock())
        session.add(Order(**values))
        session.commit()

    current['actor'] = actors[1]
    path = f'/admin/orders/{order_id}'
    blocked = client.post(path + '/status', json={"OrderStatus": "Confirmed"})
    assert blocked.status_code == 400 and blocked.json()['code'] == 'order_prepayment_required'
    current['actor'] = actors[0]
    qr = client.post(f'/orders/{order_id}/payments/qr')
    assert qr.status_code == 201, qr.text
    assert qr.json()['TransferAmount'] == 2400000
    with Session(engine) as session:
        service = PaymentService(session, gateway=gateway, clock=clock)
        with service.transaction():
            outcome, _ = service.apply_bank_transfer(BankTransfer(reconciliation_key="test:deposit",
                payment_code="DEPOSIT-TEST", amount=Decimal("2400000"), response_data={}))
        assert outcome == 'partially_paid'
    detail = client.get(f'/orders/{order_id}')
    assert detail.status_code == 200, detail.text
    assert detail.json()['PaymentStatus'] == 'PartiallyPaid'
    assert Decimal(detail.json()['ReceivedAmount']) == Decimal('2400000')
    assert Decimal(detail.json()['RemainingAmount']) == Decimal('9600000')
    assert client.post(f'/orders/{order_id}/payments/qr').status_code == 400
    current['actor'] = actors[1]
    for target in ('Confirmed', 'Processing', 'Shipping'):
        response = client.post(path + '/status', json={"OrderStatus": target})
        assert response.status_code == 200, response.text
    delivered = client.post(path + '/confirm-cod-delivery', json={})
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()['PaymentStatus'] == 'Paid'
    assert Decimal(delivered.json()['ReceivedAmount']) == Decimal('12000000')
    assert Decimal(delivered.json()['RemainingAmount']) == 0
    with Session(engine) as session:
        amounts = list(session.scalars(select(PaymentTransaction.Amount).where(PaymentTransaction.OrderId == order_id)))
        assert sorted(amounts) == [Decimal('2400000'), Decimal('9600000')]
    assert client.post(path + '/confirm-cod-delivery', json={}).status_code == 400
