"""Customer evidence upload tests use fake storage, never the configured bucket."""

import uuid
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_actor
from app.core.errors import AuthError
from app.core.storage import AvatarStorage, get_avatar_storage
from app.routers.errors import service_error_handler
from app.routers.service_requests import router
from app.services import Actor, ServiceError
from app.services.service_request_media import EVIDENCE_MAX_BYTES

PNG = b'\x89PNG\r\n\x1a\n' + b'evidence-test'


@pytest.fixture
def uploads():
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ServiceError, service_error_handler)

    async def storage_error(request, error):
        return JSONResponse(status_code=error.status_code, content={'detail': error.message})

    app.add_exception_handler(AuthError, storage_error)
    state = {'role': 'Customer', 'storage': Mock(spec=AvatarStorage)}
    actor_id = uuid.uuid4()
    state['storage'].public_url.side_effect = lambda path: 'https://demo.supabase.co/storage/v1/object/public/avatars/' + path
    def actor():
        if state.get('anonymous'):
            raise AuthError(401, 'Vui lòng đăng nhập.')
        return Actor(actor_id, state['role'])

    app.dependency_overrides[get_current_actor] = actor
    app.dependency_overrides[get_avatar_storage] = lambda: state['storage']
    with TestClient(app) as client:
        yield client, state, actor_id


def test_upload_uses_unique_customer_namespace_and_detects_actual_type(uploads):
    client, state, actor_id = uploads
    first = client.post('/service-request-image-uploads', content=PNG, headers={'Content-Type': 'video/mp4'})
    second = client.post('/service-request-image-uploads', content=PNG)
    assert first.status_code == second.status_code == 201
    assert first.json()['FileType'] == 'Image'
    assert first.json()['FileUrl'] != second.json()['FileUrl']
    method, path, data, content_type = state['storage']._call.call_args.args
    assert method == 'POST' and data == PNG and content_type == 'image/png'
    assert path.startswith(f'service-requests/{actor_id}/') and path.endswith('.png')


def test_anonymous_upload_is_refused_before_storage(uploads):
    client, state, _ = uploads
    state['anonymous'] = True
    assert client.post('/service-request-image-uploads', content=PNG).status_code == 401
    state['storage']._call.assert_not_called()


@pytest.mark.parametrize('role', ['Staff', 'Admin'])
def test_only_customers_can_stage_evidence(uploads, role):
    client, state, _ = uploads
    state['role'] = role
    assert client.post('/service-request-image-uploads', content=PNG).status_code == 403
    state['storage']._call.assert_not_called()


@pytest.mark.parametrize('body,headers,status', [
    (b'', {}, 422), (b'<svg></svg>', {'Content-Type': 'image/png'}, 422),
    (PNG, {'Content-Length': str(EVIDENCE_MAX_BYTES + 1)}, 413),
    (PNG + b'0' * EVIDENCE_MAX_BYTES, {'Content-Length': 'unknown'}, 413),
], ids=['empty', 'invalid-signature', 'declared-too-large', 'stream-too-large'])
def test_invalid_and_oversized_files_never_reach_storage(uploads, body, headers, status):
    client, state, _ = uploads
    assert client.post('/service-request-image-uploads', content=body, headers=headers).status_code == status
    state['storage']._call.assert_not_called()


def test_missing_storage_and_remote_failure_allow_retry_without_leaking_details(uploads):
    client, state, _ = uploads
    storage = state['storage']
    state['storage'] = None
    assert client.post('/service-request-image-uploads', content=PNG).status_code == 503
    state['storage'] = storage
    storage._call.side_effect = OSError('private-storage-error')
    failed = client.post('/service-request-image-uploads', content=PNG)
    assert failed.status_code == 502 and 'private-storage-error' not in failed.text
    storage._call.side_effect = None
    assert client.post('/service-request-image-uploads', content=PNG).status_code == 201
