"""Internal inbox HTTP/SQL checks on isolated in-memory SQLite; not a PostgreSQL locking test."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import Conversation, Message, Notification, User
from app.repositories.chat import ConversationRepository
from app.routers.chat import admin_router, router
from app.routers.dependencies import get_chat_service
from app.routers.errors import service_error_handler
from app.services import Actor, ServiceError
from app.services.chat import ChatService


@pytest.fixture
def inbox():
    engine = create_engine('sqlite+pysqlite:///:memory:', poolclass=StaticPool, connect_args={'check_same_thread': False})

    @event.listens_for(engine, 'connect')
    def functions(connection, _):
        connection.create_function('gen_random_uuid', 0, lambda: uuid.uuid4().hex)
        connection.create_function('now', 0, lambda: datetime.now(timezone.utc).isoformat(' '))

    metadata = MetaData()
    for model in (User, Conversation, Message, Notification):
        model.__table__.to_metadata(metadata)
    # SQLite test DDL only; production mapping and schema remain PostgreSQL JSONB.
    metadata.tables['Messages'].c.Metadata.type = JSON()
    for index in metadata.tables['Conversations'].indexes:
        if index.name == 'UX_Conversations_CustomerId_Open':
            index.dialect_options['sqlite']['where'] = text('"Status" = \'Open\'')
    metadata.create_all(engine)
    with Session(engine) as session:
        users = [User(Email=f'{role}{index}@example.test', PhoneNumber=f'090123456{index}', PasswordHash='test-only-secret', FullName=f'{role} {index}', Role=role, AccountStatus='Active') for index, role in enumerate(['Customer', 'Customer', 'Staff', 'Staff', 'Admin'])]
        session.add_all(users); session.flush()
        now = datetime(2026, 10, 14, 8, tzinfo=timezone.utc)
        rows = [Conversation(CustomerId=user.UserId, Mode='Staff', Status='Open', CreatedAt=now) for user in users[:2]]
        session.add_all(rows); session.flush()
        messages = [Message(MessageId=uuid.UUID(f'aaaaaaaa-0000-0000-0000-{index + 1:012d}'), ConversationId=rows[0].ConversationId, SenderUserId=users[0].UserId, SenderType='Customer', MessageType='Text', Content=text, Metadata=None, IsRead=False, SentAt=now + timedelta(minutes=index // 2)) for index, text in enumerate(['Cũ hơn', 'Cùng thời gian, UUID lớn hơn', 'Tin gần nhất'])]
        session.add_all(messages); session.commit()
        ids = [row.ConversationId for row in rows]
        actors = [Actor(user.UserId, user.Role) for user in users]
        current = {'actor': actors[2]}
        app = FastAPI(); app.include_router(admin_router); app.include_router(router)
        app.add_exception_handler(ServiceError, service_error_handler)
        app.dependency_overrides[get_current_actor] = lambda: current['actor']

        def service():
            with Session(engine) as request_session:
                yield ChatService(request_session)

        app.dependency_overrides[get_chat_service] = service
        with TestClient(app) as client:
            yield client, session, engine, current, ids, actors
    engine.dispose()


def test_staff_queue_exposes_only_customer_context_and_latest_message(inbox):
    client, _, _, _, ids, _ = inbox
    response = client.get('/admin/conversations/unassigned')
    assert response.status_code == 200, response.text
    rows = {row['ConversationId']: row for row in response.json()['Items']}
    first, second = rows[str(ids[0])], rows[str(ids[1])]
    assert (first['CustomerName'], first['CustomerEmail']) == ('Customer 0', 'Customer0@example.test')
    assert first['LastMessage']['Content'] == 'Tin gần nhất'
    assert second['LastMessage'] is None
    assert 'Messages' not in first
    assert 'PasswordHash' not in response.text and 'test-only-secret' not in response.text
    detail = client.get('/admin/conversations/' + str(ids[0])).json()
    assert detail['CustomerName'] == first['CustomerName']
    assert detail['LastMessage'] == first['LastMessage']
    assert len(detail['Messages']) == 3


def test_latest_message_tie_uses_uuid_and_context_queries_are_batched(inbox):
    _, session, engine, _, ids, actors = inbox
    now = datetime(2026, 10, 14, 8, 2, tzinfo=timezone.utc)
    session.add_all([Message(MessageId=uuid.UUID(f'aaaaaaaa-0000-0000-0000-{i:012d}'), ConversationId=ids[1], SenderUserId=actors[1].user_id, SenderType='Customer', MessageType='Text', Content=str(i), Metadata=None, IsRead=False, SentAt=now) for i in [11, 10]])
    session.commit()
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', capture)
    try:
        context = ConversationRepository(session).get_support_context(ids)
        assert len(statements) == 2
        assert context[ids[1]][2].Content == '11'
        assert 'row_number() OVER' in statements[1]
        assert 'message_rank' in statements[1]
        statements.clear()
        assert ConversationRepository(session).get_support_context([]) == {}
        assert statements == []
    finally:
        event.remove(engine, 'before_cursor_execute', capture)


def test_claimed_context_is_private_to_owner_or_admin_and_cannot_be_taken_over(inbox):
    client, session, _, current, ids, actors = inbox
    path = '/admin/conversations/' + str(ids[0])
    claimed = client.post(path + '/claim')
    assert claimed.status_code == 200
    assert claimed.json()['CustomerName'] == 'Customer 0'
    current['actor'] = actors[3]
    assert client.get(path).status_code == 404
    assert client.post(path + '/claim').status_code == 409
    current['actor'] = actors[4]
    assert client.get(path).status_code == 200
    assert client.post(path + '/claim').status_code == 409
    assert client.post(path + '/messages', json={'MessageType': 'Text', 'Content': 'Không được trả lời thay'}).json()['code'] == 'conversation_not_assigned_to_you'
    assert client.post(path + '/close').json()['code'] == 'conversation_not_assigned_to_you'
    assert client.get('/admin/conversations/assigned?status=Open').json()['Total'] == 0
    current['actor'] = actors[2]
    assigned = client.get('/admin/conversations/assigned?status=Open').json()
    assert assigned['Total'] == 1 and assigned['Items'][0]['CustomerEmail'] == 'Customer0@example.test'
    assert client.post(path + '/messages', json={'MessageType': 'Text', 'Content': 'Nhân viên phụ trách trả lời'}).status_code == 201
    assert client.post(path + '/close').status_code == 200
    assert client.get('/admin/conversations/assigned?status=Open').json()['Total'] == 0
    assert client.post(path + '/messages', json={'MessageType': 'Text', 'Content': 'Đã đóng'}).json()['code'] == 'conversation_closed'
    session.expire_all()
    assert session.get(Conversation, ids[0]).AssignedStaffId == actors[2].user_id
    assert len(list(session.scalars(select(Message).where(Message.ConversationId == ids[0])))) == 4


def test_customer_responses_never_expose_internal_enrichment(inbox):
    client, _, _, current, ids, actors = inbox
    current['actor'] = actors[0]
    assert client.get('/admin/conversations/unassigned').status_code == 403
    for url in ['/conversations', '/conversations/' + str(ids[0])]:
        response = client.get(url)
        assert response.status_code == 200
        body = response.json()
        rows = body['Items'] if 'Items' in body else [body]
        assert rows
        for row in rows:
            assert not {'CustomerName', 'CustomerEmail', 'LastMessage', 'AssignedStaffId'} & row.keys()
    current['actor'] = actors[1]
    assert client.get('/conversations/' + str(ids[0])).status_code == 404


def test_conversation_lock_always_refreshes_existing_session_state():
    class RecordingSession:
        def __init__(self):
            self.calls = []

        def flush(self):
            self.calls.append('flush')

        def get(self, model, id_, **options):
            self.calls.append((model, id_, options))

    session = RecordingSession()
    id_ = uuid.uuid4()
    ConversationRepository(session).get_by_id_for_update(id_)
    assert session.calls == ['flush', (Conversation, id_, {'with_for_update': True, 'populate_existing': True})]


def test_admin_sees_every_customer_being_helped_and_who_is_helping(inbox):
    client, _, _, current, ids, actors = inbox
    assert client.post(f'/admin/conversations/{ids[0]}/claim').status_code == 200  # Staff 2 takes the first chat
    mine = client.get('/admin/conversations/assigned', params={'status': 'Open'}).json()['Items']
    assert [(row['ConversationId'], row['AssignedStaffName']) for row in mine] == [(str(ids[0]), 'Staff 2')]
    assert client.get('/admin/conversations/active').status_code == 403  # Staff only see their own chats
    current['actor'] = actors[4]
    active = client.get('/admin/conversations/active')
    assert active.status_code == 200, active.text
    rows = active.json()['Items']
    assert [(row['ConversationId'], row['CustomerName'], row['AssignedStaffName']) for row in rows] == [
        (str(ids[0]), 'Customer 0', 'Staff 2')]
    queue = client.get('/admin/conversations/unassigned').json()['Items']
    assert [(row['ConversationId'], row['AssignedStaffName']) for row in queue] == [(str(ids[1]), None)]
