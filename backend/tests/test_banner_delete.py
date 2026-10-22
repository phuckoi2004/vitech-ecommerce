"""Banner deletion through real routes/service on an isolated, in-memory database."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor
from app.models import Banner, User
from app.routers.content import admin_router, router
from app.routers.dependencies import get_content_service
from app.routers.errors import service_error_handler
from app.services import Actor, ServiceError
from app.services.content import ContentService


@pytest.fixture
def banners():
    engine = create_engine('sqlite+pysqlite:///:memory:', poolclass=StaticPool, connect_args={'check_same_thread': False})

    @event.listens_for(engine, 'connect')
    def functions(connection, _):
        connection.create_function('gen_random_uuid', 0, lambda: uuid.uuid4().hex)
        connection.create_function('now', 0, lambda: datetime.now(timezone.utc).isoformat(' '))

    metadata = MetaData()
    for model in (User, Banner):
        model.__table__.to_metadata(metadata)
    metadata.create_all(engine)
    with Session(engine) as session:
        author = User(Email='banner@example.test', PhoneNumber='0901234567', PasswordHash='test-only', FullName='Banner author', Role='Admin', AccountStatus='Active')
        session.add(author); session.flush()
        first = Banner(CreatedByUserId=author.UserId, Title='Selected', ImageUrl='https://storage.example.test/banner.png', DisplayOrder=1, IsActive=True)
        sibling = Banner(CreatedByUserId=author.UserId, Title='Sibling', ImageUrl=first.ImageUrl, DisplayOrder=2, IsActive=True)
        session.add_all([first, sibling]); session.commit()
        app = FastAPI(); app.include_router(admin_router); app.include_router(router)
        app.add_exception_handler(ServiceError, service_error_handler)
        state = {'role': 'Admin'}
        app.dependency_overrides[get_current_actor] = lambda: Actor(author.UserId, state['role'])
        app.dependency_overrides[get_content_service] = lambda: ContentService(session)
        with TestClient(app) as client:
            yield client, session, first.BannerId, sibling.BannerId, author.UserId, state
    engine.dispose()


@pytest.mark.parametrize('active', [True, False])
def test_delete_only_selected_banner_and_preserve_shared_image_and_creator(banners, active):
    client, session, selected, sibling, author, _ = banners
    session.get(Banner, selected).IsActive = active
    session.commit()
    response = client.delete('/admin/banners/' + str(selected))
    assert response.status_code == 204 and not response.content
    assert client.get('/admin/banners/' + str(selected)).status_code == 404
    assert [row['BannerId'] for row in client.get('/admin/banners').json()] == [str(sibling)]
    assert [row['BannerId'] for row in client.get('/banners').json()] == [str(sibling)]
    assert session.get(Banner, sibling).ImageUrl == 'https://storage.example.test/banner.png'
    assert session.get(User, author).FullName == 'Banner author'


@pytest.mark.parametrize('role', ['Customer'])
def test_other_roles_cannot_delete_banners(banners, role):
    client, session, selected, _, _, state = banners
    state['role'] = role
    assert client.delete('/admin/banners/' + str(selected)).status_code == 403
    assert session.scalar(select(func.count()).select_from(Banner)) == 2


def test_unknown_repeated_and_invalid_ids_do_not_delete_other_banners(banners):
    client, session, selected, _, _, _ = banners
    assert client.delete('/admin/banners/' + str(uuid.uuid4())).status_code == 404
    assert client.delete('/admin/banners/invalid-id').status_code == 422
    assert session.scalar(select(func.count()).select_from(Banner)) == 2
    assert client.delete('/admin/banners/' + str(selected)).status_code == 204
    assert client.delete('/admin/banners/' + str(selected)).status_code == 404
    assert session.scalar(select(func.count()).select_from(Banner)) == 1
