"""Storage configuration checks use only synthetic keys; no network or database access."""
import base64
import json

import pytest

from app.core import storage
from app.core.errors import AuthError


def legacy_key(role):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return f'{encode({"alg": "HS256"})}.{encode({"role": role})}.synthetic-signature'


@pytest.fixture(autouse=True)
def isolated_storage_config(monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_AVATAR_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(storage, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    storage.get_avatar_storage.cache_clear()
    yield
    storage.get_avatar_storage.cache_clear()


@pytest.mark.parametrize("key", [
    "invalid-server-value", "sb_publishable_example", "sb_secret_", "sb_secret_bad\nvalue",
    "header.malformed.signature", legacy_key("anon"), legacy_key("authenticated"),
])
def test_invalid_or_public_server_key_is_an_actionable_configuration_error(monkeypatch, key):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", key)
    with pytest.raises(AuthError) as caught:
        storage.get_avatar_storage()
    assert caught.value.status_code == 503
    assert "backend/.env" in caught.value.message
    assert "SUPABASE_SECRET_KEY" in caught.value.message
    if key != "sb_secret_":  # The documented prefix is public; actual key values must stay hidden.
        assert key not in caught.value.message


@pytest.mark.parametrize("name,key,bearer", [
    ("SUPABASE_SECRET_KEY", "sb_secret_synthetic", False),
    ("SUPABASE_SERVICE_ROLE_KEY", "sb_secret_synthetic", False),
    ("SUPABASE_SERVICE_ROLE_KEY", legacy_key("service_role"), True),
])
def test_supported_server_keys_keep_the_correct_authentication_headers(monkeypatch, name, key, bearer):
    monkeypatch.setenv(name, key)
    configured = storage.get_avatar_storage()
    assert configured.bucket == "avatars"
    headers = configured.authentication_headers()
    assert headers["apikey"] == key
    assert ("Authorization" in headers) is bearer
    if bearer:
        assert headers["Authorization"] == f"Bearer {key}"
    assert key not in repr(configured)


def test_secret_setting_does_not_accept_a_legacy_jwt(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", legacy_key("service_role"))
    with pytest.raises(AuthError) as caught:
        storage.get_avatar_storage()
    assert caught.value.status_code == 503


def test_missing_key_keeps_storage_disabled(monkeypatch):
    assert storage.get_avatar_storage() is None
