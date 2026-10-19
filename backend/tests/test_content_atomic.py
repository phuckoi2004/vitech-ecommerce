"""Content + availability saved atomically through HTTP on isolated SQLite.

No connection to the configured database. These checks exercise real repositories,
flushes and commits; they do not claim PostgreSQL concurrency coverage.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, DateTime, MetaData, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import Base
from app.repositories.content import BannerRepository, NewsArticleRepository
from app.routers.content import admin_router, router
from app.routers.dependencies import get_content_service
from app.routers.errors import service_error_handler
from app.services import ServiceError
from app.services.content import ContentService
from tests.fakes import Factory, InMemoryDB


@pytest.fixture
def content():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    now = {"value": datetime(2026, 10, 18, 8, tzinfo=timezone.utc)}

    @event.listens_for(engine, "connect")
    def functions(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
        connection.create_function("now", 0, lambda: now["value"].isoformat(" "))
        connection.create_function("num_nonnulls", -1, lambda *values: sum(v is not None for v in values))
        connection.create_function("btrim", 1, lambda value: value.strip() if value is not None else None)

    metadata = MetaData()
    for table in Base.metadata.tables.values():
        copied = table.to_metadata(metadata)
        for column in copied.columns:
            if isinstance(column.type, JSONB): column.type = JSON()
    metadata.create_all(engine)
    db = InMemoryDB(); factory = Factory(db)
    admin, staff, customer = factory.user("Admin"), factory.user("Staff"), factory.user()
    with engine.begin() as connection:
        for model, objects in db.tables.items():
            for obj in objects.values():
                connection.execute(metadata.tables[model.__tablename__].insert().values(
                    **{c.key: getattr(obj, c.key) for c in model.__table__.columns}))
    app = FastAPI(); app.include_router(admin_router); app.include_router(router)
    app.add_exception_handler(ServiceError, service_error_handler)
    actor = {"value": factory.actor(admin)}
    app.dependency_overrides[get_current_actor] = lambda: actor["value"]

    # SQLite drops tzinfo on reload; emulate PostgreSQL timestamptz for these HTTP tests.
    class ContentSession(Session):
        pass

    @event.listens_for(ContentSession, "loaded_as_persistent")
    def restore_utc(_session, instance):
        for column in instance.__table__.columns:
            value = getattr(instance, column.key)
            if isinstance(column.type, DateTime) and column.type.timezone and value is not None and value.tzinfo is None:
                set_committed_value(instance, column.key, value.replace(tzinfo=timezone.utc))

    def service():
        with ContentSession(engine, autoflush=False) as session:
            yield ContentService(session, clock=lambda: now["value"])

    app.dependency_overrides[get_content_service] = service
    with TestClient(app, raise_server_exceptions=False) as client:
        yield dict(client=client, engine=engine, now=now, actor=actor, factory=factory, staff=staff, customer=customer)
    engine.dispose()


def body(kind, **fields):
    default = dict(Title="Original", Slug="original", Content="Old content", Status="Draft") if kind == "news" else dict(
        Title="Original", ImageUrl="https://storage.example.test/old.png", IsActive=True)
    return {**default, **fields}


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def create(content, kind, **fields):
    row = ok(content["client"].post("/admin/" + kind, json=body(kind, **fields)), 201)
    return row, "/admin/" + kind + "/" + row["NewsArticleId" if kind == "news" else "BannerId"]


def test_article_create_publish_edit_hide_republish_and_public_visibility(content):
    client, now = content["client"], content["now"]
    row, path = create(content, "news", Status="Published")
    first_publication = row["PublishedAt"]
    assert row["Status"] == "Published" and first_publication is not None
    assert ok(client.get("/news/original"))["Content"] == "Old content"
    now["value"] += timedelta(days=1)
    updated = ok(client.patch(path, json={"Title": "New title", "Content": "New content", "Status": "Hidden"}))
    assert updated["Title"] == "New title" and updated["Status"] == "Hidden"
    assert client.get("/news/original").status_code == 404
    assert ok(client.get("/news"))["Total"] == 0
    published = ok(client.patch(path, json={"Content": "Republished content", "Status": "Published"}))
    assert published["PublishedAt"] == first_publication
    assert ok(client.get("/news/original"))["Content"] == "Republished content"
    # A retry with the already saved status is a safe no-op for publication time.
    assert ok(client.patch(path, json={"Status": "Published"}))["PublishedAt"] == first_publication


def test_inactive_banner_never_needs_a_second_deactivation_request_and_time_window_still_applies(content):
    client, now = content["client"], content["now"]["value"]
    row, path = create(content, "banners", IsActive=False)
    assert row["IsActive"] is False and ok(client.get("/banners")) == []
    updated = ok(client.patch(path, json={"Title": "New title", "IsActive": True,
        "StartDate": (now + timedelta(days=1)).isoformat(), "EndDate": (now + timedelta(days=2)).isoformat()}))
    assert updated["IsActive"] is True and updated["Title"] == "New title"
    assert ok(client.get("/banners")) == []  # not started yet
    content["now"]["value"] += timedelta(days=1)
    assert len(ok(client.get("/banners"))) == 1
    ok(client.patch(path, json={"ImageUrl": "https://storage.example.test/new.png", "IsActive": False}))
    assert ok(client.get("/banners")) == []


@pytest.mark.parametrize("kind", ["news", "banners"])
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("phase", ["flush", "commit"])
def test_late_failure_rolls_back_content_and_status_together(content, kind, operation, phase):
    client = content["client"]
    original, path = create(content, kind)
    values = body(kind, Title="Changed", **({"Slug": "changed", "Status": "Published"} if kind == "news" else {"IsActive": False}))
    if operation == "create": path = "/admin/" + kind
    repository = NewsArticleRepository if kind == "news" else BannerRepository
    flush = repository.flush

    def fail_after_flush(repo):
        flush(repo)  # fail after the SQL has already changed content and status
        raise ServiceError("Simulated persistence failure")

    failure = patch.object(repository, "flush", fail_after_flush) if phase == "flush" else patch.object(
        Session, "commit", side_effect=RuntimeError("Simulated commit failure"))
    with failure:
        response = client.post(path, json=values) if operation == "create" else client.patch(path, json=values)
    assert response.status_code >= 400
    listing = ok(client.get("/admin/" + kind))
    rows = listing["Items"] if kind == "news" else listing
    assert len(rows) == 1 and rows[0]["Title"] == original["Title"]
    original_path = "/admin/" + kind + "/" + original["NewsArticleId" if kind == "news" else "BannerId"]
    assert ok(client.get(original_path)) == original
    retried = client.post(path, json=values) if operation == "create" else client.patch(path, json=values)
    saved = ok(retried, 201 if operation == "create" else 200)
    assert saved["Title"] == "Changed"
    if kind == "news":
        assert saved["Status"] == "Published"
    else:
        assert saved["IsActive"] is False


@pytest.mark.parametrize("target", ["Draft", "INVALID", None])
def test_invalid_article_transition_or_status_does_not_save_title(content, target):
    original, path = create(content, "news", Status="Published")
    assert content["client"].patch(path, json={"Title": "Changed", "Status": target}).status_code >= 400
    assert ok(content["client"].get(path)) == original


def test_invalid_banner_period_does_not_save_content_or_availability(content):
    original, path = create(content, "banners", StartDate="2026-10-18T00:00:00Z")
    response = content["client"].patch(path, json={"Title": "Changed", "IsActive": False, "EndDate": "2026-10-17T00:00:00Z"})
    assert response.status_code >= 400
    assert ok(content["client"].get(path)) == original


@pytest.mark.parametrize("kind", ["news", "banners"])
def test_omitted_status_remains_compatible_and_explicit_null_is_rejected(content, kind):
    values = body(kind); key = "Status" if kind == "news" else "IsActive"; values.pop(key)
    original = ok(content["client"].post("/admin/" + kind, json=values), 201)
    assert original[key] == ("Draft" if kind == "news" else True)
    path = "/admin/" + kind + "/" + original["NewsArticleId" if kind == "news" else "BannerId"]
    assert ok(content["client"].patch(path, json={"Title": "Changed"}))[key] == original[key]
    assert content["client"].patch(path, json={key: None}).status_code == 422


@pytest.mark.parametrize("kind", ["news", "banners"])
@pytest.mark.parametrize("role", ["staff", "customer"])
def test_combined_save_still_requires_admin(content, kind, role):
    original, path = create(content, kind)
    content["actor"]["value"] = content["factory"].actor(content[role])
    fields = {"Status": "Published"} if kind == "news" else {"IsActive": False}
    assert content["client"].post("/admin/" + kind, json=body(kind, **fields)).status_code == 403
    assert content["client"].patch(path, json={"Title": "Changed", **fields}).status_code == 403
