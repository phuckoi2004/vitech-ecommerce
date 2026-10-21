"""Opt-in chat and content HTTP flows with real JWTs and PostgreSQL persistence.

Reuses the protected, migrated, disposable database fixture from
test_postgres_integration; its setup and teardown truncate the test database.
These flows use the actual services/repositories, without fake actors or rows.
Chat stores its transcript in Messages; neither chat nor content currently emits
notifications or a separate status-history record. Content has no delete route:
articles are hidden and banners are deactivated through their supported APIs.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.postgres_safety import POSTGRES_TESTS_ENABLED
from tests.test_postgres_integration import (
    new_customer,
    ok,
    pg as pg,
    team as team,
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_TESTS_ENABLED,
    reason="opt-in chat/content tests require the protected TEST_DATABASE_URL",
)


def test_chat_claim_transcript_ownership_and_close_persist_in_postgres(pg, team):
    client, staff = pg.client, team["staff"]
    customer, headers = new_customer(pg)
    _, stranger = new_customer(pg)
    rival_staff = pg.login(pg.seed_user("Staff"))
    conversation = ok(client.post("/conversations", headers=headers, json={"Mode": "Staff"}), 201)
    conversation_id = conversation["ConversationId"]
    public_path = f"/conversations/{conversation_id}"
    internal_path = f"/admin/conversations/{conversation_id}"
    assert conversation["CustomerId"] == customer["id"]
    assert conversation["Status"] == "Open" and "AssignedStaffId" not in conversation

    # Reopening the same mode reuses the row; switching mode cannot create a
    # second open conversation (the real DB also has the partial unique index).
    reused = ok(client.post("/conversations", headers=headers, json={"Mode": "Staff"}), 201)
    assert reused["ConversationId"] == conversation_id
    rejected_mode = client.post("/conversations", headers=headers, json={"Mode": "AI"})
    assert rejected_mode.status_code == 400, rejected_mode.text
    assert rejected_mode.json()["code"] == "open_conversation_exists"
    assert pg.scalar('select count(*) from "Conversations" where "CustomerId" = :id '
                     'and "Status" = \'Open\'', id=customer["id"]) == 1
    for suffix in ("", "/messages"):
        assert client.get(public_path + suffix, headers=stranger).status_code == 404
    assert client.post(public_path + "/messages", headers=stranger,
                       json={"MessageType": "Text", "Content": "Unauthorized"}).status_code == 404
    assert client.post(public_path + "/close", headers=stranger).status_code == 404
    assert client.get(internal_path, headers=headers).status_code == 403
    assert client.post(internal_path + "/claim", headers=headers).status_code == 403

    queue = ok(client.get("/admin/conversations/unassigned", headers=staff))
    assert conversation_id in {row["ConversationId"] for row in queue["Items"]}
    claimed = ok(client.post(internal_path + "/claim", headers=staff))
    assert claimed["AssignedStaffId"] == team["staff_id"]
    assert ok(client.post(internal_path + "/claim", headers=staff))["AssignedStaffId"] == team["staff_id"]
    conflict = client.post(internal_path + "/claim", headers=rival_staff)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "conversation_already_claimed"
    assert client.get(internal_path, headers=rival_staff).status_code == 404
    assert pg.scalar('select cast("AssignedStaffId" as text) from "Conversations" '
                     'where "ConversationId" = :id', id=conversation_id) == team["staff_id"]

    customer_message = ok(client.post(public_path + "/messages", headers=headers, json={
        "MessageType": "Text", "Content": "  Please help with my order  "}), 201)
    assert customer_message["SenderUserId"] == customer["id"]
    assert customer_message["SenderType"] == "Customer"
    assert customer_message["Content"] == "Please help with my order"
    staff_message = ok(client.post(internal_path + "/messages", headers=staff, json={
        "MessageType": "Text", "Content": "I can help with that"}), 201)
    assert staff_message["SenderUserId"] == team["staff_id"]
    assert staff_message["SenderType"] == "Staff"
    assert client.post(public_path + "/messages", headers=headers, json={
        "MessageType": "Text", "Content": "Forged sender", "SenderType": "Staff",
        "SenderUserId": team["staff_id"]}).status_code == 422

    public_messages = ok(client.get(public_path + "/messages", headers=headers))
    transcript = {message["MessageId"]: message for message in public_messages["Items"]}
    assert public_messages["Total"] == 2
    assert transcript[staff_message["MessageId"]]["SenderUserId"] is None
    assert transcript[customer_message["MessageId"]]["SenderUserId"] == customer["id"]
    internal = ok(client.get(internal_path, headers=staff))
    assert internal["AssignedStaffId"] == team["staff_id"]
    assert next(message for message in internal["Messages"]
                if message["MessageId"] == staff_message["MessageId"])["SenderUserId"] == team["staff_id"]
    # The response model narrows even an authenticated staff member who calls
    # the customer route: the internal staff identity remains private.
    narrowed = ok(client.get(public_path, headers=staff))
    assert "AssignedStaffId" not in narrowed
    assert next(message for message in narrowed["Messages"]
                if message["MessageId"] == staff_message["MessageId"])["SenderUserId"] is None
    assert pg.scalar('select count(*) from "Messages" where "ConversationId" = :id',
                     id=conversation_id) == 2
    assert pg.scalar('select "Content" from "Messages" where "MessageId" = :id',
                     id=customer_message["MessageId"]) == "Please help with my order"
    assert pg.scalar('select cast("SenderUserId" as text) from "Messages" where "MessageId" = :id',
                     id=staff_message["MessageId"]) == team["staff_id"]

    closed = ok(client.post(internal_path + "/close", headers=staff))
    assert closed["Status"] == "Closed" and closed["ClosedAt"] is not None
    assert pg.scalar('select "Status" from "Conversations" where "ConversationId" = :id',
                     id=conversation_id) == "Closed"
    assert pg.scalar('select "ClosedAt" from "Conversations" where "ConversationId" = :id',
                     id=conversation_id) == datetime.fromisoformat(closed["ClosedAt"])
    rejected_message = client.post(public_path + "/messages", headers=headers,
                                   json={"MessageType": "Text", "Content": "Too late"})
    assert rejected_message.status_code == 400, rejected_message.text
    assert rejected_message.json()["code"] == "conversation_closed"
    assert pg.scalar('select count(*) from "Messages" where "ConversationId" = :id',
                     id=conversation_id) == 2
    assert ok(client.get(public_path, headers=headers))["Status"] == "Closed"
    next_conversation = ok(client.post("/conversations", headers=headers, json={"Mode": "Staff"}), 201)
    assert next_conversation["ConversationId"] != conversation_id
    assert pg.scalar('select count(*) from "Conversations" where "CustomerId" = :id',
                     id=customer["id"]) == 2


def test_news_publish_hide_republish_and_internal_permissions_persist_in_postgres(pg, team):
    client, admin, staff = pg.client, team["admin"], team["staff"]
    _, outsider = new_customer(pg)
    tag = uuid.uuid4().hex
    slug = f"postgres-news-{tag}"
    payload = {"Title": f"News {tag}", "Slug": slug, "Summary": "Initial summary",
               "Content": "Initial article body", "ThumbnailUrl": "https://cdn.example.com/news.jpg"}
    article = ok(client.post("/admin/news", headers=admin, json=payload), 201)
    article_id = article["NewsArticleId"]
    internal_path, public_path = f"/admin/news/{article_id}", f"/news/{slug}"
    assert article["Status"] == "Draft" and article["PublishedAt"] is None
    assert article["CreatedByUserId"] == team["admin_id"]
    assert pg.scalar('select "Status" from "NewsArticles" where "NewsArticleId" = :id',
                     id=article_id) == "Draft"
    assert pg.scalar('select cast("CreatedByUserId" as text) from "NewsArticles" '
                     'where "NewsArticleId" = :id', id=article_id) == team["admin_id"]
    assert client.get(public_path).status_code == 404
    assert article_id not in {row["NewsArticleId"] for row in ok(client.get("/news"))["Items"]}
    assert client.get(internal_path, headers=outsider).status_code == 403
    assert client.post("/admin/news", headers=outsider,
                       json={**payload, "Slug": f"{slug}-forbidden"}).status_code == 403
    assert client.patch(internal_path, headers=outsider, json={"Title": "Forbidden edit"}).status_code == 403
    assert client.post(internal_path + "/publish", headers=outsider).status_code == 403
    assert pg.scalar('select "Title" from "NewsArticles" where "NewsArticleId" = :id',
                     id=article_id) == payload["Title"]
    assert pg.scalar('select count(*) from "NewsArticles" where "Slug" = :slug',
                     slug=f"{slug}-forbidden") == 0

    published = ok(client.post(internal_path + "/publish", headers=admin))
    published_at = datetime.fromisoformat(published["PublishedAt"])
    assert published["Status"] == "Published"
    public = ok(client.get(public_path))
    assert public["Content"] == payload["Content"] and "CreatedByUserId" not in public
    assert article_id in {row["NewsArticleId"] for row in ok(client.get("/news"))["Items"]}
    updated = ok(client.patch(internal_path, headers=admin,
                              json={"Title": f"Updated {tag}", "Content": "Updated article body", "Summary": None}))
    assert updated["Status"] == "Published" and datetime.fromisoformat(updated["PublishedAt"]) == published_at
    assert pg.scalar('select "Content" from "NewsArticles" where "NewsArticleId" = :id',
                     id=article_id) == "Updated article body"
    assert pg.scalar('select "Summary" from "NewsArticles" where "NewsArticleId" = :id',
                     id=article_id) is None
    duplicate = client.post("/admin/news", headers=admin, json=payload)
    assert duplicate.status_code == 409, duplicate.text
    assert client.patch(internal_path, headers=admin, json={"Status": "Draft"}).status_code == 422

    assert client.post(internal_path + "/hide", headers=outsider).status_code == 403
    hidden = ok(client.post(internal_path + "/hide", headers=admin))
    assert hidden["Status"] == "Hidden"
    assert client.get(public_path).status_code == 404
    assert article_id not in {row["NewsArticleId"] for row in ok(client.get("/news"))["Items"]}
    assert pg.scalar('select "Status" from "NewsArticles" where "NewsArticleId" = :id',
                     id=article_id) == "Hidden"
    assert pg.scalar('select "PublishedAt" from "NewsArticles" where "NewsArticleId" = :id',
                     id=article_id) == published_at
    republished = ok(client.post(internal_path + "/publish", headers=staff))
    assert datetime.fromisoformat(republished["PublishedAt"]) == published_at
    assert ok(client.get(public_path))["Content"] == "Updated article body"
    assert pg.scalar('select count(*) from "NewsArticles" where "Slug" = :slug', slug=slug) == 1


def test_banner_visibility_dates_activation_and_internal_permissions_persist_in_postgres(pg, team):
    client, admin, staff = pg.client, team["admin"], team["staff"]
    _, outsider = new_customer(pg)
    tag = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    payload = {"Title": f"Banner {tag}", "ImageUrl": "https://cdn.example.com/banner.jpg",
               "LinkUrl": f"/news/banner-{tag}", "DisplayOrder": 7,
               "StartDate": (now - timedelta(days=1)).isoformat(),
               "EndDate": (now + timedelta(days=3)).isoformat()}
    banner = ok(client.post("/admin/banners", headers=admin, json=payload), 201)
    banner_id = banner["BannerId"]
    path = f"/admin/banners/{banner_id}"
    assert banner["IsActive"] is True and banner["CreatedByUserId"] == team["admin_id"]
    assert pg.scalar('select "IsActive" from "Banners" where "BannerId" = :id', id=banner_id) is True
    assert pg.scalar('select cast("CreatedByUserId" as text) from "Banners" where "BannerId" = :id',
                     id=banner_id) == team["admin_id"]
    public = next(row for row in ok(client.get("/banners")) if row["BannerId"] == banner_id)
    assert "CreatedByUserId" not in public and "CreatedAt" not in public
    assert ok(client.get(path, headers=admin))["Title"] == payload["Title"]
    assert client.get(path, headers=outsider).status_code == 403
    assert client.post("/admin/banners", headers=outsider,
                       json={**payload, "Title": f"Forbidden {tag}"}).status_code == 403
    assert client.patch(path, headers=outsider, json={"Title": "Forbidden edit"}).status_code == 403
    assert client.post(path + "/deactivate", headers=outsider).status_code == 403
    assert pg.scalar('select count(*) from "Banners" where "Title" = :title', title=f"Forbidden {tag}") == 0

    # An active banner scheduled in the future must be absent from the public
    # SQL-filtered list; the same stored row becomes visible when its dates fit.
    future_start = now + timedelta(days=1)
    updated = ok(client.patch(path, headers=admin, json={
        "Title": f"Updated {tag}", "LinkUrl": "https://example.com/promotion",
        "StartDate": future_start.isoformat()}))
    assert updated["IsActive"] is True
    assert banner_id not in {row["BannerId"] for row in ok(client.get("/banners"))}
    assert pg.scalar('select "StartDate" from "Banners" where "BannerId" = :id', id=banner_id) == future_start
    assert pg.scalar('select "Title" from "Banners" where "BannerId" = :id', id=banner_id) == f"Updated {tag}"
    assert pg.scalar('select "LinkUrl" from "Banners" where "BannerId" = :id',
                     id=banner_id) == "https://example.com/promotion"
    ok(client.patch(path, headers=admin, json={"StartDate": (now - timedelta(days=1)).isoformat()}))
    assert banner_id in {row["BannerId"] for row in ok(client.get("/banners"))}
    invalid_dates = client.patch(path, headers=admin, json={"EndDate": (now - timedelta(days=2)).isoformat()})
    assert invalid_dates.status_code == 400, invalid_dates.text
    assert pg.scalar('select "EndDate" from "Banners" where "BannerId" = :id',
                     id=banner_id) == datetime.fromisoformat(payload["EndDate"])

    assert ok(client.post(path + "/deactivate", headers=admin))["IsActive"] is False
    assert pg.scalar('select "IsActive" from "Banners" where "BannerId" = :id', id=banner_id) is False
    assert banner_id not in {row["BannerId"] for row in ok(client.get("/banners"))}
    assert client.post(path + "/activate", headers=outsider).status_code == 403
    assert client.patch(path, headers=admin, json={"IsActive": False}).status_code == 200
    assert pg.scalar('select "IsActive" from "Banners" where "BannerId" = :id', id=banner_id) is False
    assert ok(client.post(path + "/activate", headers=staff))["IsActive"] is True
    assert banner_id in {row["BannerId"] for row in ok(client.get("/banners"))}
    assert pg.scalar('select count(*) from "Banners" where "BannerId" = :id', id=banner_id) == 1
