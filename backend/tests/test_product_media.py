"""Mock storage and authenticated actors; never connect to a database or Supabase."""

import re
import uuid
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_actor
from app.core.errors import AuthError
from app.core.storage import AvatarStorage, get_avatar_storage
from app.routers.catalog import admin_router
from app.routers.errors import service_error_handler
from app.services import Actor, ServiceError
from app.services.product_media import PRODUCT_IMAGE_MAX_BYTES


PNG = b"\x89PNG\r\n\x1a\n" + b"test-file"


@pytest.fixture
def uploads():
    app = FastAPI()
    app.include_router(admin_router)
    app.add_exception_handler(ServiceError, service_error_handler)

    async def storage_error(request, error):
        return JSONResponse(status_code=error.status_code, content={"detail": error.message})

    app.add_exception_handler(AuthError, storage_error)
    state = {"role": "Admin", "storage": Mock(spec=AvatarStorage)}
    actor_id = uuid.uuid4()
    state["storage"].public_url.side_effect = lambda path: "https://demo.supabase.co/storage/v1/object/public/avatars/" + path
    app.dependency_overrides[get_current_actor] = lambda: Actor(actor_id, state["role"])
    app.dependency_overrides[get_avatar_storage] = lambda: state["storage"]
    with TestClient(app) as client:
        yield client, state, actor_id


def test_upload_returns_unique_product_url_and_ignores_spoofed_content_type(uploads):
    client, state, actor_id = uploads
    first = client.post("/admin/product-image-uploads", content=PNG, headers={"Content-Type": "image/jpeg"})
    assert first.status_code == 201
    second = client.post("/admin/product-image-uploads", content=PNG)
    assert second.status_code == 201
    assert first.json()["ImageUrl"] != second.json()["ImageUrl"]
    calls = state["storage"]._call.call_args_list
    for call in calls:
        method, path, data, content_type = call.args
        assert method == "POST" and data == PNG and content_type == "image/png"
        assert re.fullmatch(rf"products/{actor_id}/[a-f0-9]{{32}}\.png", path)
    state["storage"].delete.assert_not_called()


@pytest.mark.parametrize("role", ["Customer"])
def test_only_catalog_writers_can_upload(uploads, role):
    client, state, _ = uploads
    state["role"] = role
    assert client.post("/admin/product-image-uploads", content=PNG).status_code == 403
    state["storage"]._call.assert_not_called()


def test_staff_can_stage_images_for_news_and_banners(uploads):
    client, state, _ = uploads
    state["role"] = "Staff"
    assert client.post("/admin/product-image-uploads", content=PNG).status_code == 201
    state["storage"]._call.assert_called_once()


@pytest.mark.parametrize("body,headers,status", [
    (b"", {}, 422), (b"<svg></svg>", {"Content-Type": "image/png"}, 422),
    (PNG, {"Content-Length": str(PRODUCT_IMAGE_MAX_BYTES + 1)}, 413),
    (PNG + b"0" * PRODUCT_IMAGE_MAX_BYTES, {"Content-Length": "unknown"}, 413),
], ids=["empty", "invalid-signature", "declared-too-large", "stream-too-large"])
def test_rejects_empty_invalid_and_oversized_files_before_storage(uploads, body, headers, status):
    client, state, _ = uploads
    assert client.post("/admin/product-image-uploads", content=body, headers=headers).status_code == status
    state["storage"]._call.assert_not_called()


def test_storage_unavailable_is_actionable_and_retry_upload_is_possible(uploads):
    client, state, _ = uploads
    storage = state["storage"]
    state["storage"] = None
    assert client.post("/admin/product-image-uploads", content=PNG).status_code == 503
    state["storage"] = storage
    storage._call.side_effect = OSError("sensitive remote error")
    response = client.post("/admin/product-image-uploads", content=PNG)
    assert response.status_code == 502 and "sensitive" not in response.text
    storage._call.side_effect = None
    assert client.post("/admin/product-image-uploads", content=PNG).status_code == 201
