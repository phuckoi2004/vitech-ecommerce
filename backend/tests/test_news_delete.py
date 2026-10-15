"""News deletion with real service/repository on isolated in-memory SQLite only."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine, event, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import NewsArticle, User
from app.routers.content import admin_router, router
from app.routers.dependencies import get_content_service
from app.routers.errors import service_error_handler
from app.services import Actor, ServiceError
from app.services.content import ContentService


@pytest.fixture
def news():
    engine = create_engine('sqlite+pysqlite:///:memory:', poolclass=StaticPool, connect_args={'check_same_thread': False})

    @event.listens_for(engine, 'connect')
    def functions(connection, _):
        connection.create_function('gen_random_uuid', 0, lambda: uuid.uuid4().hex)
        connection.create_function('now', 0, lambda: datetime.now(timezone.utc).isoformat(' '))

    metadata = MetaData()
    for model in (User, NewsArticle):
        model.__table__.to_metadata(metadata)
    metadata.create_all(engine)
    with Session(engine) as session:
        author = User(Email='news@example.test', PhoneNumber='0901234567', PasswordHash='test-only', FullName='Người tạo', Role='Admin', AccountStatus='Active')
        session.add(author); session.flush()
        first = NewsArticle(CreatedByUserId=author.UserId, Title='Bài đã đăng', Slug='bai-da-dang', Content='Nội dung', Status='Published', PublishedAt=datetime.now(timezone.utc))
        sibling = NewsArticle(CreatedByUserId=author.UserId, Title='Bài khác', Slug='bai-khac', Content='Nội dung khác', Status='Draft')
        session.add_all([first, sibling]); session.commit()
        app = FastAPI(); app.include_router(admin_router); app.include_router(router)
        app.add_exception_handler(ServiceError, service_error_handler)
        state = {'role': 'Admin'}
        app.dependency_overrides[get_current_actor] = lambda: Actor(author.UserId, state['role'])
        app.dependency_overrides[get_content_service] = lambda: ContentService(session)
        with TestClient(app) as client:
            yield client, session, first.NewsArticleId, sibling.NewsArticleId, author.UserId, state
    engine.dispose()


def test_delete_removes_selected_article_from_admin_and_public_reads_only(news):
    client, session, selected, sibling, author, _ = news
    response = client.delete('/admin/news/' + str(selected))
    assert response.status_code == 204 and not response.content
    assert client.get('/admin/news/' + str(selected)).status_code == 404
    assert client.get('/news/bai-da-dang').status_code == 404
    assert client.get('/admin/news').json()['Total'] == 1
    assert client.get('/admin/news/' + str(sibling)).status_code == 200
    assert session.get(User, author).FullName == 'Người tạo'


@pytest.mark.parametrize('role', ['Staff', 'Customer'])
def test_other_roles_cannot_delete_even_an_existing_article(news, role):
    client, session, selected, _, _, state = news
    state['role'] = role
    assert client.delete('/admin/news/' + str(selected)).status_code == 403
    assert session.scalar(select(func.count()).select_from(NewsArticle)) == 2


def test_unknown_and_repeated_deletion_return_not_found(news):
    client, _, selected, _, _, _ = news
    assert client.delete('/admin/news/' + str(uuid.uuid4())).status_code == 404
    assert client.delete('/admin/news/' + str(selected)).status_code == 204
    assert client.delete('/admin/news/' + str(selected)).status_code == 404
