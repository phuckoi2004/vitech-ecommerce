"""Support pagination, read ownership and transactional notifications on isolated SQLite."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Message, Notification
from app.routers.users import router as users_router
from app.routers.dependencies import get_notification_service
from app.services.user import NotificationService
from app.services import BusinessRuleError
from tests.test_chat_inbox import inbox  # noqa: F401 -- shared isolated fixture


def notification_routes(context):
    client, _, engine, _, _, _ = context
    client.app.include_router(users_router)
    def service():
        with Session(engine) as session:
            yield NotificationService(session)
    client.app.dependency_overrides[get_notification_service] = service


@pytest.mark.parametrize('operator_index', [2, 4])
def test_staff_or_admin_reply_notifies_only_the_customer_and_can_be_marked_read(inbox, operator_index):
    notification_routes(inbox)
    client, _, _, current, ids, actors = inbox
    current['actor'] = actors[operator_index]
    path = f'/admin/conversations/{ids[0]}'
    assert client.post(path + '/claim').status_code == 200
    assert client.post(path + '/messages', json={'MessageType': 'Text', 'Content': 'VieTech hỗ trợ bạn'}).status_code == 201
    current['actor'] = actors[0]
    assert client.get('/users/me/notifications/unread-count').json() == {'Count': 1}
    rows = client.get('/users/me/notifications').json()['Items']
    assert len(rows) == 1
    note = rows[0]
    assert note['NotificationType'] == 'Chat' and note['ReferenceType'] == 'Conversation'
    assert note['ReferenceId'] == str(ids[0])
    assert note['ActionUrl'] == f'/tu-van?conversation={ids[0]}'
    assert str(actors[operator_index].user_id) not in note['Content']
    current['actor'] = actors[1]
    assert client.get('/users/me/notifications').json()['Total'] == 0
    assert client.post(f"/users/me/notifications/{note['NotificationId']}/read").status_code == 404
    current['actor'] = actors[0]
    read = client.post(f"/users/me/notifications/{note['NotificationId']}/read")
    assert read.status_code == 200 and read.json()['IsRead'] is True and read.json()['ReadAt']
    assert client.get('/users/me/notifications/unread-count').json() == {'Count': 0}


def test_failed_customer_notification_rolls_back_the_staff_reply(inbox, monkeypatch):
    client, session, _, _, ids, _ = inbox
    path = f'/admin/conversations/{ids[0]}'
    assert client.post(path + '/claim').status_code == 200

    def fail_notification(*args, **kwargs):
        raise BusinessRuleError('Không lưu được thông báo', code='notification_failed')

    monkeypatch.setattr(NotificationService, 'notify', fail_notification)
    response = client.post(path + '/messages', json={'MessageType': 'Text', 'Content': 'Reply that must roll back'})
    assert response.status_code == 400 and response.json()['code'] == 'notification_failed'
    session.expire_all()
    assert list(session.scalars(select(Message).where(Message.Content == 'Reply that must roll back'))) == []
    assert list(session.scalars(select(Notification))) == []


def test_summary_and_cursor_windows_keep_equal_timestamps_without_full_history(inbox):
    client, session, _, _, ids, actors = inbox
    session.execute(delete(Message).where(Message.ConversationId == ids[0]))
    at = datetime(2026, 10, 16, 9, tzinfo=timezone.utc)
    rows = [Message(MessageId=uuid.UUID(f'aaaaaaaa-0000-0000-0000-{index + 1:012x}'), ConversationId=ids[0], SenderUserId=actors[0].user_id,
                    SenderType='Customer', MessageType='Text', Content=f'Message {index}', IsRead=False,
                    Metadata=None, SentAt=at) for index in range(125)]
    session.add_all(rows); session.commit()
    path = f'/admin/conversations/{ids[0]}'
    summary = client.get(path + '/summary')
    assert summary.status_code == 200
    assert summary.json()['UnreadCount'] == 125
    assert 'Messages' not in summary.json()
    newest = client.get(path + '/message-window', params={'latest': True, 'limit': 50}).json()
    assert newest['Total'] == 125
    assert [m['Content'] for m in newest['Items']] == [f'Message {i}' for i in range(75, 125)]
    before = client.get(path + '/message-window', params={
        'before_sent_at': at.isoformat(), 'before_message_id': str(rows[75].MessageId), 'limit': 50,
    }).json()
    assert [m['Content'] for m in before['Items']] == [f'Message {i}' for i in range(25, 75)]
    after = client.get(path + '/message-window', params={
        'after_sent_at': at.isoformat(), 'after_message_id': str(rows[120].MessageId),
    }).json()
    assert [m['Content'] for m in after['Items']] == [f'Message {i}' for i in range(121, 125)]
    assert client.get(path + '/message-window', params={'after_sent_at': at.isoformat()}).status_code == 400
    assert client.get(path + '/message-window', params={
        'after_sent_at': at.isoformat(), 'after_message_id': str(rows[0].MessageId), 'latest': True,
    }).status_code == 400
    assert client.get(path + '/message-window?limit=101').status_code == 422


def test_only_owner_can_mark_customer_messages_read_and_other_ids_stay_unread(inbox):
    client, session, _, current, ids, actors = inbox
    path = f'/admin/conversations/{ids[0]}'
    own = list(session.scalars(select(Message).where(Message.ConversationId == ids[0])))
    foreign = Message(ConversationId=ids[1], SenderUserId=actors[1].user_id, SenderType='Customer',
                      MessageType='Text', Content='Other customer', Metadata=None, IsRead=False)
    staff = Message(ConversationId=ids[0], SenderUserId=actors[2].user_id, SenderType='Staff',
                    MessageType='Text', Content='Reply', Metadata=None, IsRead=False)
    session.add_all([foreign, staff]); session.commit()
    body = {'MessageIds': [str(row.MessageId) for row in [*own, foreign, staff]]}
    assert client.post(path + '/read', json=body).status_code == 400  # unassigned queue
    assert client.post(path + '/claim').status_code == 200
    current['actor'] = actors[3]
    assert client.post(path + '/read', json=body).status_code == 404
    assert client.get(path + '/message-window?latest=true').status_code == 404
    current['actor'] = actors[4]
    assert client.get(path + '/summary').status_code == 200
    assert client.post(path + '/read', json=body).status_code == 400  # Admin may observe, not read for owner
    current['actor'] = actors[2]
    assert client.post(path + '/read', json=body).json() == {'Updated': 3}
    assert client.post(path + '/read', json=body).json() == {'Updated': 0}
    assert client.get(path + '/summary').json()['UnreadCount'] == 0
    session.expire_all()
    assert session.get(Message, foreign.MessageId).IsRead is False
    assert session.get(Message, staff.MessageId).IsRead is False
    assert client.post(path + '/read', json={'MessageIds': []}).status_code == 422
    current['actor'] = actors[0]
    assert client.post(path + '/read', json=body).status_code == 403


def test_closed_history_scope_and_admin_all_remain_read_only_for_other_staff(inbox):
    client, _, _, current, ids, actors = inbox
    path = f'/admin/conversations/{ids[0]}'
    assert client.post(path + '/claim').status_code == 200
    assert client.post(path + '/close').status_code == 200
    assert client.get('/admin/conversations/assigned?status=Closed').json()['Total'] == 1
    assert client.get(path + '/message-window?latest=true').status_code == 200
    current['actor'] = actors[3]
    assert client.get('/admin/conversations/assigned?status=Closed').json()['Total'] == 0
    assert client.get('/admin/conversations').status_code == 403
    current['actor'] = actors[4]
    assert client.get('/admin/conversations?status=Closed').json()['Total'] == 1
    assert client.get(path + '/message-window?latest=true').status_code == 200
    assert client.post(path + '/messages', json={'MessageType': 'Text', 'Content': 'No takeover'}).status_code == 400


def ask(client, conversation_id, content='Cần hỗ trợ'):
    response = client.post(f'/conversations/{conversation_id}/messages', json={'MessageType': 'Text', 'Content': content})
    assert response.status_code == 201


def test_new_queue_and_assigned_messages_create_notifications_without_reuse_duplicates(inbox):
    client, session, _, current, ids, actors = inbox
    current['actor'] = actors[0]
    assert client.post(f'/conversations/{ids[0]}/close').status_code == 200
    opened = client.post('/conversations', json={'Mode': 'Staff'})
    assert opened.status_code == 201
    id_ = opened.json()['ConversationId']
    # Merely opening the chat window does not page staff; the first customer message does.
    assert client.post('/conversations', json={'Mode': 'Staff'}).json()['ConversationId'] == id_
    assert list(session.scalars(select(Notification))) == []
    ask(client, id_)
    notes = list(session.scalars(select(Notification)))
    assert {note.UserId for note in notes} == {actor.user_id for actor in actors[2:]}
    assert all(note.ReferenceType == 'Conversation' and id_ in note.ActionUrl for note in notes)
    ask(client, id_, 'Còn ai không?')
    assert len(list(session.scalars(select(Notification)))) == 3
    current['actor'] = actors[2]
    assert client.post(f'/admin/conversations/{id_}/claim').status_code == 200
    current['actor'] = actors[0]
    assert client.post(f'/conversations/{id_}/messages', json={'MessageType': 'Text', 'Content': 'Question'}).status_code == 201
    notes = list(session.scalars(select(Notification)))
    assert len(notes) == 4
    new = [note for note in notes if note.Title == 'Tin nhắn mới từ khách hàng']
    assert len(new) == 1 and new[0].UserId == actors[2].user_id


def test_claim_resolves_queue_alerts_for_every_recipient_without_exposing_the_claimed_chat(inbox):
    notification_routes(inbox)
    client, session, _, current, ids, actors = inbox
    current['actor'] = actors[0]
    assert client.post(f'/conversations/{ids[0]}/close').status_code == 200
    id_ = client.post('/conversations', json={'Mode': 'Staff'}).json()['ConversationId']
    ask(client, id_)
    current['actor'] = actors[2]
    assert client.post(f'/admin/conversations/{id_}/claim').status_code == 200
    current['actor'] = actors[3]
    notes = client.get('/users/me/notifications').json()['Items']
    assert len(notes) == 1 and notes[0]['IsRead'] is True
    assert notes[0]['ReadAt'] is not None
    assert notes[0]['ActionUrl'] == '/admin/support'
    assert client.get('/users/me/notifications/unread-count').json()['Count'] == 0
    assert client.get(f'/admin/conversations/{id_}/summary').status_code == 404
    read = client.post(f"/users/me/notifications/{notes[0]['NotificationId']}/read").json()
    assert read['ActionUrl'] == '/admin/support'
    session.expire_all()
    assert all(note.IsRead for note in session.scalars(select(Notification)))


def test_customer_closing_a_waiting_chat_resolves_queue_alerts(inbox):
    client, session, _, current, ids, actors = inbox
    current['actor'] = actors[0]
    client.post(f'/conversations/{ids[0]}/close')
    id_ = client.post('/conversations', json={'Mode': 'Staff'}).json()['ConversationId']
    ask(client, id_)
    assert client.post(f'/conversations/{id_}/close').status_code == 200
    notes = list(session.scalars(select(Notification)))
    assert len(notes) == 3 and all(note.IsRead and note.ActionUrl == '/admin/support' for note in notes)


def test_read_refreshes_a_legacy_chat_link_and_never_changes_another_users_notification(inbox):
    notification_routes(inbox)
    client, session, _, current, ids, actors = inbox
    assert client.post(f'/admin/conversations/{ids[0]}/claim').status_code == 200
    notes = [Notification(UserId=actor.user_id, Title='Old queue alert', Content='Waiting',
                          NotificationType='Chat', ReferenceType='Conversation', ReferenceId=ids[0],
                          ActionUrl=f'/admin/support?conversation={ids[0]}', IsRead=False) for actor in actors[2:4]]
    session.add_all(notes); session.commit()
    current['actor'] = actors[3]
    assert client.post(f'/users/me/notifications/{notes[0].NotificationId}/read').status_code == 404
    response = client.post(f'/users/me/notifications/{notes[1].NotificationId}/read')
    assert response.status_code == 200
    assert response.json()['ActionUrl'] == '/admin/support'
    session.expire_all()
    assert session.get(Notification, notes[0].NotificationId).IsRead is False
    assert session.get(Notification, notes[1].NotificationId).IsRead is True
