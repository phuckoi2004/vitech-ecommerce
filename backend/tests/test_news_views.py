"""Public view counting against real SQL on an isolated local SQLite database."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import DefaultClause, MetaData, create_engine, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import NewsArticle, User
from app.routers.content import router
from app.routers.dependencies import get_content_service
from app.routers.errors import service_error_handler
from app.schemas.content import NewsArticleCreate, NewsArticleUpdate
from app.services import Actor, ServiceError
from app.services.content import ContentService


@pytest.fixture
def news_api(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'news.sqlite'}", connect_args={"timeout": 15})
    metadata = MetaData()
    for model in (User, NewsArticle):
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if column.primary_key:
                column.server_default = None
            elif column.name in {"CreatedAt", "UpdatedAt"}:
                column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
    metadata.create_all(engine)
    identity = uuid.uuid4()
    actor = Actor(identity, "Admin")
    with Session(engine) as db:
        db.add(User(UserId=identity, Email="news@example.test", PhoneNumber="0901234567", PasswordHash="unused",
                    FullName="Admin", Role="Admin", AccountStatus="Active", IsEmailVerified=True))
        db.commit()
        service = ContentService(db)
        for slug in ("published", "draft", "hidden"):
            created = NewsArticle(NewsArticleId=uuid.uuid4(), CreatedByUserId=identity, Title=slug, Slug=slug,
                                  Content="Bài viết", Status="Draft", CreatedAt=datetime.now(timezone.utc))
            db.add(created)
            db.commit()
            if slug != "draft":
                service.publish_article(actor, created.NewsArticleId)
            if slug == "hidden":
                service.hide_article(actor, created.NewsArticleId)
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ServiceError, service_error_handler)

    def content_service():
        with Session(engine, autoflush=False) as db:
            yield ContentService(db)

    app.dependency_overrides[get_content_service] = content_service
    with TestClient(app) as client:
        yield client, engine, actor
    engine.dispose()


def test_page_opens_increment_and_reading_lists_or_admin_details_does_not(news_api):
    client, engine, actor = news_api
    assert client.get("/news/published").json()["ViewCount"] == 0
    assert client.get("/news").json()["Items"][0]["ViewCount"] == 0
    for expected in (1, 2, 3):
        result = client.post("/news/published/views", json={"ViewCount": 999999})
        assert result.status_code == 200 and result.json() == {"ViewCount": expected}
    assert client.get("/news/published").json()["ViewCount"] == 3
    with Session(engine) as db:
        service = ContentService(db)
        article = service.articles.get_by_slug("published")
        assert service.admin_get_article(actor, article.NewsArticleId).ViewCount == 3
        assert next(item for item in service.admin_list_articles(actor).Items if item.Slug == "published").ViewCount == 3
    assert client.get("/news/published").json()["ViewCount"] == 3


@pytest.mark.parametrize("slug", ["draft", "hidden", "unknown"])
def test_unpublished_or_unknown_articles_cannot_gain_views(news_api, slug):
    client, engine, _ = news_api
    result = client.post(f"/news/{slug}/views")
    assert result.status_code == 404 and result.json()["code"] == "news_article_not_found"
    with Session(engine) as db:
        row = ContentService(db).articles.get_by_slug(slug)
        assert row is None or row.ViewCount == 0


def test_parallel_opens_do_not_lose_counts(news_api):
    client, engine, _ = news_api

    def open_article(_):
        with Session(engine, autoflush=False) as db:
            return ContentService(db).record_article_view("published").ViewCount

    with ThreadPoolExecutor(max_workers=8) as workers:
        counts = list(workers.map(open_article, range(24)))
    assert sorted(counts) == list(range(1, 25))
    assert client.get("/news/published").json()["ViewCount"] == 24


def test_count_is_server_managed_and_cannot_be_negative(news_api):
    client, engine, _ = news_api
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        NewsArticleCreate(Title="x", Slug="x", Content="x", ViewCount=99)
    with pytest.raises(ValidationError):
        NewsArticleUpdate(ViewCount=99)
    with Session(engine) as db:
        with pytest.raises(IntegrityError):
            db.execute(update(NewsArticle).where(NewsArticle.Slug == "published").values(ViewCount=-1))
        db.rollback()
    assert client.get("/news/published").json()["ViewCount"] == 0
