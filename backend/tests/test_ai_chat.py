"""AI turns on isolated SQLite + FakeChatModel; no Gemini or shared database calls.

These test durable state transitions, not PostgreSQL's actual row-lock scheduling.
"""

import uuid
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import JSON, MetaData, create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.ai_config import AiSettings
from app.core.auth_state import MemoryStateStore
from app.integrations.ai import ChatCompletion
from app.models import Conversation, Message, User
from app.schemas.ai_chat import AiMessageCancel, AiMessageCreate
from app.services.actor import Actor
from app.services.ai_chat import AiChatService
from app.services.exceptions import AiUnavailableError, BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError, TooManyRequestsError
from tests.sqlite_schema import AI_SIGNAL_TABLES, create_tables


class FakeChatModel:
    def __init__(self):
        self.calls = []
        self.action = None

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        if self.action:
            self.action()
        return ChatCompletion(json.dumps({"intent": "clarify", "clarification": "category"}), "fake-model", 10, 20)


@pytest.fixture
def ai():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def functions(connection, _):
        connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat(" "))
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)

    counters = {"connections": 0}
    event.listen(engine, "checkout", lambda *_: counters.update(connections=counters["connections"] + 1))
    event.listen(engine, "checkin", lambda *_: counters.update(connections=counters["connections"] - 1))
    metadata = MetaData()
    for model in (User, Conversation, Message):
        model.__table__.to_metadata(metadata)
    metadata.tables["Messages"].c.Metadata.type = JSON()
    for index in metadata.tables["Conversations"].indexes:
        if index.name == "UX_Conversations_CustomerId_Open":
            index.dialect_options["sqlite"]["where"] = text('"Status" = \'Open\'')
    metadata.create_all(engine)
    create_tables(engine, AI_SIGNAL_TABLES)
    users = [uuid.uuid4(), uuid.uuid4()]
    cid = uuid.uuid4()
    with Session(engine) as db:
        db.add_all([User(UserId=id_, Email=f"{id_}@example.test", PhoneNumber=f"09{i:08d}",
                         PasswordHash="test-only", FullName="Customer", Role="Customer", AccountStatus="Active")
                    for i, id_ in enumerate(users)])
        db.add(Conversation(ConversationId=cid, CustomerId=users[0], Mode="AI", Status="Open"))
        db.commit()
    clock = SimpleNamespace(now=datetime(2026, 10, 22, 8, tzinfo=timezone.utc))
    model = FakeChatModel()
    state = MemoryStateStore()
    sessions = []

    def service(settings=None):
        session = Session(engine, autoflush=False)
        sessions.append(session)
        return AiChatService(session, settings=settings or AiSettings(api_key="test-only", timeout_seconds=20),
                             model=model, state=state, clock=lambda: clock.now)

    def rows():
        with Session(engine) as db:
            return list(db.scalars(select(Message).order_by(Message.SentAt, Message.MessageId)))

    yield SimpleNamespace(engine=engine, cid=cid, actor=Actor(users[0], "Customer"), other=Actor(users[1], "Customer"),
                          service=service, model=model, state=state, clock=clock, counters=counters, rows=rows)
    for session in sessions:
        session.close()
    engine.dispose()


def payload(content="Xin tư vấn laptop dưới 20 triệu", request_id=None):
    return AiMessageCreate(ClientRequestId=request_id or uuid.uuid4(), Content=content)


def test_success_replay_history_and_no_checked_out_connection_while_waiting(ai):
    svc = ai.service()
    ai.model.action = lambda: (pytest.fail("DB connection held while waiting") if ai.counters["connections"] else None)
    data = payload()
    first = svc.ask(ai.actor, ai.cid, data)
    repeated = svc.ask(ai.actor, ai.cid, data)
    assert first.Status == repeated.Status == "Completed"
    assert first.CustomerMessage.MessageId == repeated.CustomerMessage.MessageId
    assert first.AiMessages[0].MessageId == repeated.AiMessages[0].MessageId
    assert len(ai.model.calls) == 1 and len(ai.rows()) == 2
    assert first.AiMessages[0].SenderType == "AI" and first.AiMessages[0].SenderUserId is None
    assert "AiLeaseToken" not in first.model_dump_json() and "AiUsage" not in first.model_dump_json()
    ai.clock.now += timedelta(seconds=1)
    svc.ask(ai.actor, ai.cid, payload("Tôi muốn laptop"))
    history = ai.model.calls[-1]
    assert [m["role"] for m in history] == ["system", "user", "assistant", "user"]
    assert history[1]["content"] == data.Content


def test_pending_replay_different_id_busy_and_fencing(ai):
    data = payload()

    def while_waiting():
        other = ai.service()
        assert other.ask(ai.actor, ai.cid, data).Status == "Pending"
        with pytest.raises(ConflictError, match="câu hỏi trước"):
            other.ask(ai.actor, ai.cid, payload("Câu khác"))
        status = other.get_status(ai.actor, ai.cid, data.ClientRequestId)
        assert status.Status == "Pending" and not status.AiMessages

    ai.model.action = while_waiting
    result = ai.service().ask(ai.actor, ai.cid, data)
    assert result.Status == "Completed" and len(ai.model.calls) == 1


def test_same_uuid_changed_content_rejected(ai):
    data = payload()
    svc = ai.service()
    svc.ask(ai.actor, ai.cid, data)
    with pytest.raises(ConflictError) as error:
        svc.ask(ai.actor, ai.cid, payload("Câu khác", data.ClientRequestId))
    assert error.value.code == "ai_request_content_conflict"
    assert len(ai.rows()) == 2


def test_cancel_before_original_post_is_terminal_idempotent_and_keeps_the_question(ai):
    svc, data = ai.service(), payload()
    cancel = AiMessageCancel(Content=data.Content)
    stopped = svc.cancel(ai.actor, ai.cid, data.ClientRequestId, cancel)
    assert stopped.Status == "Cancelled" and not stopped.AiMessages
    repeated = svc.cancel(ai.actor, ai.cid, data.ClientRequestId, cancel)
    late_post = svc.ask(ai.actor, ai.cid, data)
    assert repeated.CustomerMessage.MessageId == late_post.CustomerMessage.MessageId == stopped.CustomerMessage.MessageId
    assert late_post.Status == "Cancelled" and not ai.model.calls
    assert svc.get_status(ai.actor, ai.cid, data.ClientRequestId).Status == "Cancelled"
    assert len(ai.rows()) == 1 and ai.rows()[0].Content == data.Content
    with pytest.raises(ConflictError):
        svc.cancel(ai.actor, ai.cid, data.ClientRequestId, AiMessageCancel(Content="Câu khác"))
    with pytest.raises(ConflictError):
        svc.ask(ai.actor, ai.cid, payload("Câu khác", data.ClientRequestId))
    assert svc.ask(ai.actor, ai.cid, payload("Câu hỏi tiếp theo")).Status == "Completed"


def test_cancel_during_inference_blocks_late_answer_without_affecting_a_new_turn(ai):
    data = payload()

    def cancel_while_waiting():
        stopped = ai.service().cancel(ai.actor, ai.cid, data.ClientRequestId, AiMessageCancel(Content=data.Content))
        assert stopped.Status == "Cancelled"
        ai.model.action = None
        assert ai.service().ask(ai.actor, ai.cid, payload("Câu hỏi mới")).Status == "Completed"

    ai.model.action = cancel_while_waiting
    with pytest.raises(ConflictError):
        ai.service().ask(ai.actor, ai.cid, data)
    stopped = ai.service().get_status(ai.actor, ai.cid, data.ClientRequestId)
    assert stopped.Status == "Cancelled" and not stopped.AiMessages
    assert len(ai.rows()) == 3 and len(ai.model.calls) == 2


def test_cancel_after_completion_returns_the_saved_answer(ai):
    svc, data = ai.service(), payload()
    completed = svc.ask(ai.actor, ai.cid, data)
    stopped = svc.cancel(ai.actor, ai.cid, data.ClientRequestId, AiMessageCancel(Content=data.Content))
    assert stopped.Status == "Completed" and stopped.AiMessages[0].MessageId == completed.AiMessages[0].MessageId
    assert len(ai.model.calls) == 1


def test_cancel_is_allowed_during_provider_cooldown(ai):
    svc, data = ai.service(), payload()

    def quota():
        raise AiUnavailableError("Quota", code="ai_quota_exceeded", retry_after_seconds=60)

    ai.model.action = quota
    with pytest.raises(AiUnavailableError):
        svc.ask(ai.actor, ai.cid, data)
    assert svc.cancel(ai.actor, ai.cid, data.ClientRequestId, AiMessageCancel(Content=data.Content)).Status == "Cancelled"
    assert svc.ask(ai.actor, ai.cid, data).Status == "Cancelled"
    assert len(ai.model.calls) == 1


def test_cancel_checks_ownership_role_mode_and_closed_conversation(ai):
    svc, data = ai.service(), payload()
    cancel = AiMessageCancel(Content=data.Content)
    with pytest.raises(NotFoundError):
        svc.cancel(ai.other, ai.cid, data.ClientRequestId, cancel)
    for actor in (None, Actor(uuid.uuid4(), "Staff"), Actor(uuid.uuid4(), "Admin")):
        with pytest.raises(PermissionDeniedError):
            svc.cancel(actor, ai.cid, data.ClientRequestId, cancel)
    with Session(ai.engine) as db:
        db.get(Conversation, ai.cid).Mode = "Staff"
        db.commit()
    with pytest.raises(BusinessRuleError):
        svc.cancel(ai.actor, ai.cid, data.ClientRequestId, cancel)
    with Session(ai.engine) as db:
        row = db.get(Conversation, ai.cid)
        row.Mode, row.Status = "AI", "Closed"
        db.commit()
    with pytest.raises(BusinessRuleError):
        svc.cancel(ai.actor, ai.cid, data.ClientRequestId, cancel)
    assert not ai.rows() and not ai.model.calls


def test_failure_retry_reuses_customer_message_and_limits_attempts(ai):
    data = payload()

    def fail():
        raise AiUnavailableError("Timeout")

    ai.model.action = fail
    svc = ai.service()
    with pytest.raises(AiUnavailableError):
        svc.ask(ai.actor, ai.cid, data)
    failed = svc.get_status(ai.actor, ai.cid, data.ClientRequestId)
    assert failed.Status == "Failed" and len(ai.rows()) == 1
    ai.model.action = None
    result = svc.ask(ai.actor, ai.cid, data)
    assert result.Status == "Completed" and result.CustomerMessage.MessageId == failed.CustomerMessage.MessageId
    assert len(ai.rows()) == 2
    ai.model.action = fail
    data2 = payload("Lượt lỗi")
    for _ in range(3):
        with pytest.raises(AiUnavailableError):
            svc.ask(ai.actor, ai.cid, data2)
    with pytest.raises(ConflictError) as error:
        svc.ask(ai.actor, ai.cid, data2)
    assert error.value.code == "ai_retry_limit"


def test_failure_records_model_and_safe_diagnostics_without_question_or_provider_message(ai, caplog):
    data = payload("private-customer-question")

    def fail():
        raise AiUnavailableError("private-provider-error-message")

    ai.model.action = fail
    with caplog.at_level("WARNING", logger="app.services.ai_chat"), pytest.raises(AiUnavailableError):
        ai.service().ask(ai.actor, ai.cid, data)
    assert "model=gemini-3.5-flash-lite" in caplog.text and "code=ai_unavailable" in caplog.text
    assert "private-customer-question" not in caplog.text and "private-provider-error-message" not in caplog.text
    assert ai.rows()[0].Metadata["AiModel"] == "gemini-3.5-flash-lite"
    response = ai.service().get_status(ai.actor, ai.cid, data.ClientRequestId)
    assert "AiModel" not in response.model_dump_json()


def test_stale_worker_cannot_overwrite_reclaimed_request(ai):
    data = payload()

    def reclaim():
        ai.clock.now += timedelta(seconds=121)
        ai.model.action = None
        replacement = ai.service().ask(ai.actor, ai.cid, data)
        assert replacement.Status == "Completed"

    ai.model.action = reclaim
    with pytest.raises(ConflictError) as error:
        ai.service().ask(ai.actor, ai.cid, data)
    assert error.value.code == "ai_request_superseded"
    assert len(ai.rows()) == 2
    assert ai.service().get_status(ai.actor, ai.cid, data.ClientRequestId).Status == "Completed"


def test_expired_different_request_is_released(ai):
    old = payload()
    svc = ai.service()
    svc._prepare(ai.actor, ai.cid, old)
    svc.session.close()
    ai.clock.now += timedelta(seconds=121)
    result = svc.ask(ai.actor, ai.cid, payload("Câu mới"))
    assert result.Status == "Completed"
    assert svc.get_status(ai.actor, ai.cid, old.ClientRequestId).Status == "Failed"


def test_close_during_inference_does_not_save_ai_reply(ai):
    def close():
        with Session(ai.engine) as db:
            db.get(Conversation, ai.cid).Status = "Closed"
            db.commit()
    ai.model.action = close
    data = payload()
    with pytest.raises(ConflictError):
        ai.service().ask(ai.actor, ai.cid, data)
    assert len(ai.rows()) == 1 and ai.rows()[0].Metadata["AiProcessingStatus"] == "Failed"


def test_authorization_mode_status_and_unknown_request(ai):
    svc = ai.service()
    for actor in (ai.other,):
        with pytest.raises(NotFoundError):
            svc.ask(actor, ai.cid, payload())
        with pytest.raises(NotFoundError):
            svc.get_status(actor, ai.cid, uuid.uuid4())
    for actor in (None, Actor(uuid.uuid4(), "Staff"), Actor(uuid.uuid4(), "Admin")):
        with pytest.raises(PermissionDeniedError):
            svc.ask(actor, ai.cid, payload())
    with pytest.raises(NotFoundError):
        svc.get_status(ai.actor, ai.cid, uuid.uuid4())
    with Session(ai.engine) as db:
        db.get(Conversation, ai.cid).Mode = "Staff"
        db.commit()
    with pytest.raises(BusinessRuleError) as error:
        svc.ask(ai.actor, ai.cid, payload())
    assert error.value.code == "conversation_not_ai_mode" and not ai.model.calls
    with Session(ai.engine) as db:
        row = db.get(Conversation, ai.cid)
        row.Mode, row.Status = "AI", "Closed"
        db.commit()
    with pytest.raises(BusinessRuleError) as error:
        svc.ask(ai.actor, ai.cid, payload())
    assert error.value.code == "conversation_closed"


@pytest.mark.parametrize("content", ["", "   ", "a" * 1001])
def test_input_validation(content):
    with pytest.raises(ValidationError):
        payload(content)


def test_rate_limit_and_completed_replay_does_not_consume_quota(ai):
    svc = ai.service(replace(AiSettings(), requests_per_minute=1))
    data = payload()
    svc.ask(ai.actor, ai.cid, data)
    assert svc.ask(ai.actor, ai.cid, data).Status == "Completed"
    with pytest.raises(TooManyRequestsError):
        svc.ask(ai.actor, ai.cid, payload("Câu mới"))
    assert len(ai.rows()) == 2
    ai.clock.now += timedelta(seconds=61)
    assert svc.ask(ai.actor, ai.cid, payload("Câu mới")).Status == "Completed"


def test_context_keeps_only_complete_pairs_and_redacts_contact_details(ai):
    svc = ai.service(replace(AiSettings(), context_max_turns=1))
    svc.ask(ai.actor, ai.cid, payload("Email me@example.test, số 0912345678"))
    history = ai.model.calls[-1]
    assert "me@example.test" not in str(history) and "0912345678" not in str(history)
    ai.clock.now += timedelta(seconds=1)
    svc.ask(ai.actor, ai.cid, payload("Câu thứ hai"))
    ai.clock.now += timedelta(seconds=1)
    svc.ask(ai.actor, ai.cid, payload("Câu thứ ba"))
    assert len(ai.model.calls[-1]) == 4
    assert ai.model.calls[-1][1]["content"] == "Câu thứ hai"


def test_database_uniqueness_guards(ai):
    svc = ai.service()
    data = payload()
    svc.ask(ai.actor, ai.cid, data)
    question = next(m for m in ai.rows() if m.SenderType == "Customer")
    with Session(ai.engine) as db:
        db.add(Message(MessageId=uuid.uuid4(), ConversationId=ai.cid, SenderUserId=ai.actor.user_id,
                       SenderType="Customer", MessageType="Text", Content="Duplicate", SentAt=ai.clock.now,
                       Metadata={"ClientRequestId": str(data.ClientRequestId)}, IsRead=False))
        with pytest.raises(IntegrityError):
            db.commit()
    with Session(ai.engine) as db:
        db.add(Message(MessageId=uuid.uuid4(), ConversationId=ai.cid, SenderUserId=None, SenderType="AI",
                       MessageType="Text", Content="Duplicate", SentAt=ai.clock.now,
                       Metadata={"ReplyToMessageId": str(question.MessageId)}, IsRead=False))
        with pytest.raises(IntegrityError):
            db.commit()


def test_pending_index_rejects_two_different_requests(ai):
    with Session(ai.engine) as db:
        for _ in range(2):
            db.add(Message(MessageId=uuid.uuid4(), ConversationId=ai.cid, SenderUserId=ai.actor.user_id,
                           SenderType="Customer", MessageType="Text", Content="Pending", SentAt=ai.clock.now,
                           Metadata={"ClientRequestId": str(uuid.uuid4()), "AiProcessingStatus": "Pending"}, IsRead=False))
        with pytest.raises(IntegrityError):
            db.commit()


def test_failed_final_commit_rolls_back_reply_and_preserves_retry(ai):
    svc = ai.service()
    count = {"commits": 0}

    @event.listens_for(svc.session, "before_commit")
    def fail_final_commit(_):
        count["commits"] += 1
        if count["commits"] == 2:
            raise RuntimeError("simulated commit failure")

    data = payload()
    with pytest.raises(RuntimeError):
        svc.ask(ai.actor, ai.cid, data)
    assert len(ai.rows()) == 1 and ai.rows()[0].Metadata["AiProcessingStatus"] == "Failed"
    assert svc.ask(ai.actor, ai.cid, data).Status == "Completed"
    assert len(ai.rows()) == 2
