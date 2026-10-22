"""Active status-only workflows, HTTP contracts and side effects on isolated SQLite.

No production DB is used here. SQLite proves state validation/rollback, not PostgreSQL locking.
"""
from io import StringIO

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import Notification, ProductSerial, ReturnRequest, ServiceRequestHistory, WarrantyRequest, Order, ProductVariant
import uuid
from tests.test_return_directory import directory as returns_directory
from tests.test_warranty_directory import directory as warranty_directory


@pytest.fixture
def returns(returns_directory):
    client, engine, current, rows, actors, orders = returns_directory
    Notification.__table__.create(engine)
    with Session(engine) as session:
        session.scalar(select(ProductVariant)).StockQuantity = 5
        session.commit()
    return client, engine, current, rows, actors, orders


@pytest.fixture
def warranty(warranty_directory):
    client, engine, current, rows, actors, orders = warranty_directory
    Notification.__table__.create(engine)
    return client, engine, current, rows, actors, orders


def settled_exchange(engine, request_id, source):
    with Session(engine) as session:
        original = session.get(Order, source.OrderId)
        values = {column.key: getattr(original, column.key) for column in Order.__table__.columns}
        values.update(OrderId=uuid.uuid4(), OrderCode='EX-' + uuid.uuid4().hex[:10], OrderStatus='Pending', PaymentStatus='Paid',
                      TotalAmount=0, DiscountAmount=original.Subtotal, ExchangeCreditAmount=original.Subtotal,
                      SourceReturnRequestId=request_id)
        session.add(Order(**values)); session.commit()


def test_return_forward_flow_requires_settled_exchange_before_restock(returns):
    client, engine, _, rows, _, source = returns
    with Session(engine) as session:
        session.scalar(select(ProductVariant)).StockQuantity = 0
        session.commit()
    path = '/admin/return-requests/' + str(rows[1].ReturnRequestId)
    statements = []
    def capture(_connection, _cursor, statement, _params, _context, _many):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        for old, new in [('Pending', 'Approved'), ('Approved', 'Receiving'), ('Receiving', 'Processing')]:
            response = client.post(path + '/advance', json={'ExpectedStatus': old})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body['Status'] == new and body['CustomerName'] is not None
            assert body['CompensationAmount'] is body['CompensationApprovedAt'] is body['RefundPaymentTransactionId'] is None
        blocked = client.post(path + '/advance', json={'ExpectedStatus': 'Processing'})
        assert blocked.status_code == 400 and blocked.json()['code'] == 'exchange_order_not_settled'
        settled_exchange(engine, rows[1].ReturnRequestId, source)
        response = client.post(path + '/advance', json={'ExpectedStatus': 'Processing'})
        assert response.status_code == 200 and response.json()['CompletedAt'] is not None
        with Session(engine) as session:
            assert session.scalar(select(ProductVariant.StockQuantity)) == 1
        assert client.post(path + '/advance', json={'ExpectedStatus': 'Completed'}).status_code == 400
        assert client.post(path + '/reject', json={'Reason': 'Không được mở lại'}).status_code == 400
        writes = [s for s in statements if s.lstrip().split(' ', 1)[0].upper() in ('INSERT', 'UPDATE', 'DELETE')]
        assert writes
        assert any('ProductVariants' in s for s in writes)
        assert all(not any(table in s for table in ('PaymentTransactions', 'StockAdjustments')) for s in writes)
    finally:
        event.remove(engine, 'before_cursor_execute', capture)


def test_exchange_can_complete_and_stale_click_does_not_skip_a_stage(returns):
    client, engine, _, rows, _, source = returns
    id_ = rows[1].ReturnRequestId
    with Session(engine) as session:
        session.get(ReturnRequest, id_).RequestType = 'Exchange'; session.commit()
    path = '/admin/return-requests/' + str(id_)
    assert client.post(path + '/advance', json={'ExpectedStatus': 'Pending'}).status_code == 200
    assert client.post(path + '/advance', json={'ExpectedStatus': 'Pending'}).status_code == 409
    assert client.get(path).json()['Status'] == 'Approved'
    # Acceptance now creates the settled same-SKU replacement without a customer POST.
    assert client.get(path).json()['Exchange']['Committed']
    for expected in ['Approved', 'Receiving', 'Processing']:
        response = client.post(path + '/advance', json={'ExpectedStatus': expected})
        assert response.status_code == 200, response.text
    assert response.json()['Status'] == 'Completed'


def test_staff_cannot_reject_after_acceptance_but_can_reject_pending(returns):
    client, engine, current, rows, actors, _ = returns
    path = '/admin/return-requests/' + str(rows[1].ReturnRequestId)
    for expected in ['Pending', 'Approved', 'Receiving']:
        assert client.post(path + '/advance', json={'ExpectedStatus': expected}).status_code == 200
    response = client.post(path + '/reject', json={'Reason': 'Không đáp ứng yêu cầu'})
    assert response.status_code == 400 and response.json()['code'] == 'return_rejection_not_allowed'
    path = '/admin/return-requests/' + str(rows[3].ReturnRequestId)
    response = client.post(path + '/reject', json={'Reason': 'Không đáp ứng yêu cầu'})
    assert response.status_code == 200
    assert response.json()['Status'] == 'Rejected'
    current['actor'] = actors[0]
    mine = client.get('/return-requests/' + str(rows[3].ReturnRequestId)).json()
    assert mine['DecisionReason'] == 'Không đáp ứng yêu cầu'
    assert 'Không đáp ứng yêu cầu' in str(mine['Histories'])
    assert client.post(path + '/advance', json={'ExpectedStatus': 'Rejected'}).status_code == 403
    current['actor'] = actors[1]
    assert client.post(path + '/cancel').status_code in (404, 405)
    with Session(engine) as session:
        notifications = list(session.scalars(select(Notification)))
        assert any('Không đáp ứng yêu cầu' in n.Content and n.UserId == actors[0].user_id for n in notifications)


@pytest.mark.parametrize('endpoint,body', [('refund', {}), ('confirm-refund', {}), ('approve', {'CompensationAmount': '0'}), ('inspect', {'RestockedQuantity': 1, 'DamagedQuantity': 0})])
def test_deferred_financial_endpoints_cannot_mutate_returns(returns, endpoint, body):
    client, _, _, rows, _, _ = returns
    path = '/admin/return-requests/' + str(rows[1].ReturnRequestId)
    response = client.post(path + '/' + endpoint, json=body)
    assert response.status_code == 400 and response.json()['code'] == 'service_workflow_paused'
    assert client.get(path).json()['Status'] == 'Pending'


def test_return_step_endpoints_keep_notes_and_reserve_automatic_replacement(returns):
    client, engine, current, rows, actors, _ = returns
    path = '/admin/return-requests/' + str(rows[1].ReturnRequestId)
    steps = [('accept', 'Approved', 'Đã gọi xác nhận với khách', 'Khách hẹn gửi chiều nay'),
             ('start-receiving', 'Receiving', 'Đã đặt đơn vị vận chuyển', 'Vận đơn nội bộ VD-01'),
             ('receive', 'Processing', 'Đã nhận đủ 1 sản phẩm', 'Hộp móp nhẹ')]
    statements = []
    def capture(_connection, _cursor, statement, _params, _context, _many):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        for endpoint, status, note, internal_note in steps:
            response = client.post(path + '/' + endpoint, json={'Note': note, 'InternalNote': internal_note})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body['Status'] == status
            [line] = [h for h in body['Histories'] if note in (h['Note'] or '')]
            assert (line['NewStatus'], line['InternalNote']) == (status, internal_note)
        assert body['ReceivedAt'] is not None
        assert client.post(path + '/receive', json={}).status_code == 409  # already received: a repeated click is stale
        writes = [s for s in statements if s.lstrip().split(' ', 1)[0].upper() in ('INSERT', 'UPDATE', 'DELETE')]
        assert writes
        assert all(not any(table in s for table in ('PaymentTransactions', 'StockAdjustments')) for s in writes)
        assert any('ProductVariants' in s for s in writes)
        with Session(engine) as session:
            assert session.scalar(select(ProductVariant.StockQuantity)) == 4
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    other = '/admin/return-requests/' + str(rows[3].ReturnRequestId)
    response = client.post(other + '/accept')  # the note body is optional
    assert response.status_code == 200 and response.json()['Status'] == 'Approved'
    assert 'Đã tiếp nhận yêu cầu.' in [h['Note'] for h in response.json()['Histories'] if h['NewStatus'] == 'Approved']
    current['actor'] = actors[0]
    mine = client.get('/return-requests/' + str(rows[1].ReturnRequestId)).json()
    for _, _, note, internal_note in steps:
        assert note in str(mine['Histories']) and internal_note not in str(mine)
    assert client.post(other + '/start-receiving').status_code == 403  # customers cannot drive staff steps


@pytest.mark.parametrize('result', ['Repaired', 'PartReplaced', 'NotRepairable'])
def test_warranty_result_is_required_published_to_customer_and_then_closed(warranty, result):
    client, engine, current, rows, actors, _ = warranty
    path = '/admin/warranty-requests/' + str(rows[0].WarrantyRequestId)
    for expected in ['New', 'Inspecting']:
        response = client.post(path + '/advance', json={'ExpectedStage': expected})
        assert response.status_code == 200, response.text
    assert response.json()['Status'] == 'Processing'
    assert client.post(path + '/advance', json={'ExpectedStage': 'Inspecting'}).status_code == 409
    for body in [{'ExpectedStage': 'Repairing'}, {'ExpectedStage': 'Repairing', 'ResultType': result, 'ResultNote': '   '}]:
        assert client.post(path + '/advance', json=body).status_code == 400
    assert client.post(path + '/advance', json={'ExpectedStage': 'Repairing', 'ResultType': 'ProductReplaced', 'ResultNote': 'Đổi máy'}).status_code == 422
    assert client.get(path).json()['ResultType'] is None
    response = client.post(path + '/advance', json={'ExpectedStage': 'Repairing', 'ResultType': result, 'ResultNote': 'Đã kiểm tra và ghi nhận kết quả thực tế.'})
    assert response.status_code == 200, response.text
    assert response.json()['ResultApprovedByUserId'] == str(actors[1].user_id)
    current['actor'] = actors[0]
    customer = client.get('/warranty-requests/' + str(rows[0].WarrantyRequestId)).json()
    assert customer['ResultType'] == result
    assert customer['ResultNote'] == 'Đã kiểm tra và ghi nhận kết quả thực tế.'
    assert 'InternalNote' not in str(customer)
    current['actor'] = actors[1]
    response = client.post(path + '/advance', json={'ExpectedStage': 'Finished'})
    assert response.status_code == 200 and response.json()['Status'] == 'Completed'
    assert client.post(path + '/advance', json={'ExpectedStage': 'Finished'}).status_code == 409
    assert client.post(path + '/reject', json={'Reason': 'Không được mở lại'}).status_code == 400
    with Session(engine) as session:
        assert all(s.Status == 'Sold' for s in session.scalars(select(ProductSerial)))
        assert any('Đã kiểm tra và ghi nhận' in n.Content for n in session.scalars(select(Notification)))


def test_warranty_rejection_before_reception_is_staff_action_and_terminal(warranty):
    client, _, current, rows, actors, _ = warranty
    path = '/admin/warranty-requests/' + str(rows[0].WarrantyRequestId)
    response = client.post(path + '/reject', json={'Reason': 'Khách gửi sai yêu cầu'})
    assert response.status_code == 200 and response.json()['Status'] == 'Rejected'
    assert client.post(path + '/advance', json={'ExpectedStage': 'New'}).status_code == 409
    current['actor'] = actors[0]
    detail = client.get('/warranty-requests/' + str(rows[0].WarrantyRequestId)).json()
    assert detail['EligibilityReason'] == 'Khách gửi sai yêu cầu'


def test_warranty_receive_keeps_the_step_notes_and_moves_no_serial(warranty):
    client, engine, current, rows, actors, _ = warranty
    path = '/admin/warranty-requests/' + str(rows[0].WarrantyRequestId)
    response = client.post(path + '/receive', json={'Note': 'Đã nhận máy, trầy nhẹ góc', 'InternalNote': 'Kệ B2'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['Status'] == 'New' and body['ReceivedAt'] is not None
    [step] = [h for h in body['Histories'] if 'Đã nhận máy, trầy nhẹ góc' in (h['Note'] or '')]
    assert step['InternalNote'] == 'Kệ B2' and step['ChangedByUserId'] == str(actors[1].user_id)
    assert client.post(path + '/receive').status_code == 409  # already received: a repeated click is stale
    current['actor'] = actors[0]
    customer = client.get('/warranty-requests/' + str(rows[0].WarrantyRequestId)).json()
    assert 'Đã nhận máy, trầy nhẹ góc' in str(customer['Histories'])
    assert 'Kệ B2' not in str(customer)
    with Session(engine) as session:
        assert all(s.Status == 'Sold' for s in session.scalars(select(ProductSerial)))


@pytest.mark.parametrize('kind', ['returns', 'warranty'])
@pytest.mark.parametrize('internal_note', ['Đã gọi khách xác nhận, lưu ghi âm', None])
def test_rejection_keeps_the_internal_note_for_staff_only(request, kind, internal_note):
    client, engine, current, rows, actors, _ = request.getfixturevalue(kind)
    if kind == 'returns':
        admin_path, customer_path = '/admin/return-requests/', '/return-requests/'
        request_id, reason_field = rows[1].ReturnRequestId, 'DecisionReason'
    else:
        admin_path, customer_path = '/admin/warranty-requests/', '/warranty-requests/'
        request_id, reason_field = rows[0].WarrantyRequestId, 'EligibilityReason'
    path = admin_path + str(request_id)
    body = {'Reason': 'Sản phẩm không thuộc diện hỗ trợ'}
    if internal_note:
        body['InternalNote'] = internal_note
    current['actor'] = actors[0]
    assert client.post(path + '/reject', json=body).status_code == 403  # customers cannot reject
    current['actor'] = actors[1]
    response = client.post(path + '/reject', json=body)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail['Status'] == 'Rejected'
    [line] = [h for h in detail['Histories'] if h['NewStatus'] == 'Rejected']
    assert 'Sản phẩm không thuộc diện hỗ trợ' in line['Note'] and line['InternalNote'] == internal_note
    assert line['ChangedByUserId'] == str(actors[1].user_id)
    response = client.post(path + '/reject', json={'Reason': 'Lần hai'})
    assert response.status_code == 400 and response.json()['code'] == ('return_rejection_not_allowed' if kind == 'returns' else 'service_request_closed')
    current['actor'] = actors[0]
    mine = client.get(customer_path + str(request_id)).json()
    assert mine['Status'] == 'Rejected' and mine[reason_field] == 'Sản phẩm không thuộc diện hỗ trợ'
    assert 'Sản phẩm không thuộc diện hỗ trợ' in str(mine['Histories'])
    with Session(engine) as session:
        contents = [n.Content for n in session.scalars(select(Notification))]
    assert any('Sản phẩm không thuộc diện hỗ trợ' in content for content in contents)
    if internal_note:
        assert internal_note not in str(mine) and not any(internal_note in content for content in contents)


def test_migration_sql_changes_only_the_two_approved_checks():
    from pathlib import Path
    config = Config(); config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'alembic'))
    revision = ScriptDirectory.from_config(config).get_revision('7e4c9b2d1a60')
    output = StringIO()
    context = MigrationContext.configure(dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': output})
    with Operations.context(context):
        revision.module.upgrade()
    sql = output.getvalue()
    assert sql.count('ALTER TABLE') == 3
    assert 'Completed_RequiresApproval' in sql and 'Completed_RequiresTimestamp' in sql
    assert 'Approval_NotByProposer' in sql
    assert not any(word in sql for word in ('DROP TABLE', 'ADD COLUMN', 'DELETE FROM', 'UPDATE "'))
