"""Category image API persistence using an isolated, in-memory database."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_actor, get_optional_actor
from app.main import app
from app.models import Category
from app.routers.dependencies import get_category_service
from app.services.actor import Actor
from app.services.catalog import CategoryService


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def uuid_default(connection, _):
        connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)

    Category.__table__.create(engine)

    def service():
        with Session(engine) as session:
            yield CategoryService(session)

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_category_service] = service
    app.dependency_overrides[get_current_actor] = lambda: Actor(uuid.uuid4(), "Admin")
    app.dependency_overrides[get_optional_actor] = lambda: None
    try:
        with TestClient(app) as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


@pytest.mark.parametrize("image", [{}, {"ImageUrl": None}, {"ImageUrl": "https://cdn.example.com/phone.png"}])
def test_create_and_public_reads_with_or_without_optional_image(client, image):
    response = client.post("/admin/categories", json={"Name": "Điện thoại", "Slug": "dien-thoai", **image})
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["ImageUrl"] == image.get("ImageUrl")
    assert client.get("/categories").json() == [row]
    assert client.get(f"/categories/{row['CategoryId']}").json() == row
    assert client.get("/categories/slug/dien-thoai").json() == row


def test_patch_can_add_replace_preserve_and_clear_image(client):
    row = client.post("/admin/categories", json={"Name": "Điện thoại", "Slug": "dien-thoai"}).json()
    url = f"/admin/categories/{row['CategoryId']}"
    for image in ("https://cdn.example.com/first.png", "https://cdn.example.com/second.png"):
        response = client.patch(url, json={"ImageUrl": image})
        assert response.status_code == 200, response.text
        assert response.json()["ImageUrl"] == image
    assert client.patch(url, json={"Name": "Tên mới"}).json()["ImageUrl"] == image
    assert client.patch(url, json={"ImageUrl": None}).json()["ImageUrl"] is None
    assert client.get("/categories").json()[0]["ImageUrl"] is None


def test_image_length_limit_applies_to_create_and_update(client):
    body = {"Name": "Điện thoại", "Slug": "dien-thoai"}
    image = "https://cdn.example.com/" + "x" * 500
    assert client.post("/admin/categories", json={**body, "ImageUrl": image}).status_code == 422
    row = client.post("/admin/categories", json=body).json()
    assert client.patch(f"/admin/categories/{row['CategoryId']}", json={"ImageUrl": image}).status_code == 422
