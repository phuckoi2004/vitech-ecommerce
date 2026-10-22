"""Real JWT -> new AI endpoints -> SQLite -> fake model. No external services."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import JSON, MetaData, event, text
from sqlalchemy.orm import Session

from app.core.ai_config import AiSettings
from app.models import Conversation, Message, User
from app.services.exceptions import AiUnavailableError
from tests.sqlite_schema import AI_SIGNAL_TABLES, create_tables
from tests.test_ai_chat import FakeChatModel
from tests.test_auth_http import authorization, http_context, login, seed_user


@pytest.fixture
def ai_http(http_context, monkeypatch):
    client, engine, _ = http_context
    metadata = MetaData()
    for model in (User, Conversation, Message):
        model.__table__.to_metadata(metadata)
    metadata.tables["Messages"].c.Metadata.type = JSON()
    for index in metadata.tables["Conversations"].indexes:
        if index.name == "UX_Conversations_CustomerId_Open":
            index.dialect_options["sqlite"]["where"] = text('"Status" = \'Open\'')
    metadata.create_all(engine, tables=[metadata.tables["Conversations"], metadata.tables["Messages"]])
    create_tables(engine, AI_SIGNAL_TABLES)
    fake = FakeChatModel()
    fake.now = datetime(2026, 10, 22, 8, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.ai_chat.AiChatService.now", lambda _: fake.now)
    monkeypatch.setattr("app.routers.dependencies.get_ai_settings", lambda: AiSettings(api_key="fake"))
    monkeypatch.setattr("app.routers.dependencies.GeminiChatModel", lambda _: fake)
    owner = seed_user(engine, "Customer")
    other = seed_user(engine, "Customer")
    headers = authorization(login(client, owner["email"]).json()["access_token"])
    other_headers = authorization(login(client, other["email"]).json()["access_token"])
    started = client.post("/conversations", json={"Mode": "AI"}, headers=headers)
    assert started.status_code == 201, started.text
    cid = started.json()["ConversationId"]
    yield client, engine, cid, headers, other_headers, fake


def request_body(content="Tôi cần tư vấn laptop"):
    return {"ClientRequestId": str(uuid.uuid4()), "MessageType": "Text", "Content": content}


def test_real_jwt_http_success_replay_status_and_isolation(ai_http):
    client, engine, cid, headers, other_headers, fake = ai_http
    path = f"/conversations/{cid}/ai-messages"
    body = request_body()
    checked_out = {"count": 0}
    event.listen(engine, "checkout", lambda *_: checked_out.update(count=checked_out["count"] + 1))
    event.listen(engine, "checkin", lambda *_: checked_out.update(count=checked_out["count"] - 1))

    def waiting():
        assert checked_out["count"] == 0, "Auth/AI connection held while waiting for model"

    fake.action = waiting
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["Status"] == "Completed" and result["AiMessages"][0]["SenderType"] == "AI"
    replay = client.post(path, json=body, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["AiMessages"][0]["MessageId"] == result["AiMessages"][0]["MessageId"]
    assert len(fake.calls) == 1
    status_path = f'{path}/{body["ClientRequestId"]}'
    assert client.get(status_path, headers=headers).json()["Status"] == "Completed"
    assert client.post(path, json=request_body(), headers=other_headers).status_code == 404
    assert client.get(status_path, headers=other_headers).status_code == 404
    assert client.post(path, json=body).status_code == 401
    history = client.get(f"/conversations/{cid}", headers=headers)
    assert len(history.json()["Messages"]) == 2
    assert "AiLeaseToken" not in history.text and "AiUsage" not in history.text


def test_http_validation_failed_status_retry_after_and_safe_retry(ai_http):
    client, _, cid, headers, _, fake = ai_http
    path = f"/conversations/{cid}/ai-messages"
    for content in ("", " ", "a" * 1001):
        assert client.post(path, json=request_body(content), headers=headers).status_code == 422
    forged = request_body()
    forged["SenderType"] = "AI"
    assert client.post(path, json=forged, headers=headers).status_code == 422
    body = request_body()

    def quota():
        raise AiUnavailableError("AI hết hạn mức", code="ai_quota_exceeded", retry_after_seconds=12)

    fake.action = quota
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 503 and response.headers["Retry-After"] == "12"
    assert response.json()["code"] == "ai_quota_exceeded"
    assert client.get(f'{path}/{body["ClientRequestId"]}', headers=headers).json()["Status"] == "Failed"
    fake.action = None
    assert client.post(path, json=body, headers=headers).status_code == 503
    assert client.post(path, json=request_body("Câu hỏi khác"), headers=headers).status_code == 503
    assert len(fake.calls) == 1
    fake.now += timedelta(seconds=13)
    result = client.post(path, json=body, headers=headers)
    assert result.status_code == 200 and result.json()["Status"] == "Completed"
    assert len(client.get(f"/conversations/{cid}", headers=headers).json()["Messages"]) == 2


def test_http_pending_returns_202(ai_http):
    client, _, cid, headers, _, fake = ai_http
    path = f"/conversations/{cid}/ai-messages"
    body = request_body()

    def duplicate():
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 202 and response.json()["Status"] == "Pending"

    fake.action = duplicate
    assert client.post(path, json=body, headers=headers).status_code == 200


def test_http_cancel_is_authorized_idempotent_and_blocks_a_late_post(ai_http):
    client, _, cid, headers, other_headers, fake = ai_http
    path = f"/conversations/{cid}/ai-messages"
    body = request_body()
    stop_path = f'{path}/{body["ClientRequestId"]}/cancel'
    cancel = {"Content": body["Content"]}
    assert client.post(stop_path, json=cancel).status_code == 401
    assert client.post(stop_path, json=cancel, headers=other_headers).status_code == 404
    for invalid in ({}, {"Content": " "}, {"Content": "x" * 1001}, {**cancel, "SenderType": "AI"}):
        assert client.post(stop_path, json=invalid, headers=headers).status_code == 422
    stopped = client.post(stop_path, json=cancel, headers=headers)
    assert stopped.status_code == 200 and stopped.json()["Status"] == "Cancelled"
    repeated = client.post(stop_path, json=cancel, headers=headers)
    late = client.post(path, json=body, headers=headers)
    assert repeated.json()["CustomerMessage"]["MessageId"] == late.json()["CustomerMessage"]["MessageId"]
    assert late.json()["Status"] == "Cancelled" and not fake.calls
    assert client.get(f'{path}/{body["ClientRequestId"]}', headers=headers).json()["Status"] == "Cancelled"
    history = client.get(f"/conversations/{cid}", headers=headers)
    assert len(history.json()["Messages"]) == 1
    assert "AiCancelledAt" not in history.text and "AiLeaseToken" not in history.text
    assert client.post(stop_path, json={"Content": "Câu khác"}, headers=headers).status_code == 409
    assert client.post(path, json=request_body("Câu hỏi tiếp"), headers=headers).json()["Status"] == "Completed"


def test_http_cancel_while_model_is_running_does_not_publish_a_late_reply(ai_http):
    client, _, cid, headers, _, fake = ai_http
    path = f"/conversations/{cid}/ai-messages"
    body = request_body()

    def stop():
        cancelled = client.post(f'{path}/{body["ClientRequestId"]}/cancel', json={"Content": body["Content"]}, headers=headers)
        assert cancelled.status_code == 200 and cancelled.json()["Status"] == "Cancelled"

    fake.action = stop
    assert client.post(path, json=body, headers=headers).status_code == 409
    result = client.get(f'{path}/{body["ClientRequestId"]}', headers=headers).json()
    assert result["Status"] == "Cancelled" and not result["AiMessages"]
    assert len(client.get(f"/conversations/{cid}", headers=headers).json()["Messages"]) == 1


def test_customer_history_titles_mode_filter_and_ownership(ai_http):
    client, engine, cid, headers, other_headers, fake = ai_http
    first = "Tư vấn laptop học lập trình dưới 20 triệu"
    assert client.post(f"/conversations/{cid}/ai-messages", json=request_body(first), headers=headers).status_code == 200
    fake.now += timedelta(seconds=1)
    assert client.post(f"/conversations/{cid}/ai-messages", json=request_body("Câu hỏi tiếp theo"), headers=headers).status_code == 200
    # Seed history directly: this isolated fixture intentionally has no notification tables used by staff lifecycle.
    with Session(engine) as db:
        existing = db.get(Conversation, uuid.UUID(cid))
        existing.Status = "Closed"
        existing.ClosedAt = fake.now
        db.flush()
        db.add(Conversation(ConversationId=uuid.uuid4(), CustomerId=existing.CustomerId, Mode="Staff",
                            Status="Open", CreatedAt=fake.now))
        db.commit()
    assert client.post("/conversations", json={"Mode": "AI"}, headers=other_headers).status_code == 201
    page = client.get("/conversations?mode=AI&page_size=1", headers=headers)
    assert page.status_code == 200
    assert page.json()["Total"] == 1
    assert page.json()["Items"][0]["ConversationId"] == cid
    assert page.json()["Items"][0]["Title"] == first
    other_page = client.get("/conversations?mode=AI", headers=other_headers).json()
    assert other_page["Total"] == 1 and other_page["Items"][0]["Title"] is None
    assert first not in str(other_page)
    assert client.get("/conversations?mode=Unknown", headers=headers).status_code == 400
