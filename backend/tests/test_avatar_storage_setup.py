"""Storage setup compatibility: mocked HTTP only, never creates a real bucket."""

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from app.cli.setup_avatar_storage import _missing_bucket, setup_avatar_storage
from app.core.errors import AuthError
from app.core.storage import AvatarStorage, AVATAR_MAX_BYTES, AVATAR_EXTENSIONS


def failure(status, body):
    return urllib.error.HTTPError("https://demo.supabase.co/storage/v1/bucket/avatars", status, "error", {},
                                  io.BytesIO(json.dumps(body).encode()))


@pytest.mark.parametrize("status,body,missing", [
    (400, {"code": "NoSuchBucket", "message": "Bucket not found"}, True),
    (404, {"error": "not_found"}, True),
    (400, {"code": "InvalidRequest"}, False),
    (401, {"code": "NoSuchBucket"}, False),
    (403, {"error": "Forbidden"}, False),
])
def test_only_known_missing_bucket_responses_allow_creation(status, body, missing):
    assert _missing_bucket(failure(status, body)) is missing


def test_check_mode_reports_missing_bucket_without_writing():
    storage = AvatarStorage("https://demo.supabase.co", "sb_secret_example", "avatars")
    with patch("app.cli.setup_avatar_storage.get_avatar_storage", return_value=storage), \
         patch("app.cli.setup_avatar_storage._bucket_request", side_effect=failure(400, {"code": "NoSuchBucket"})) as request:
        with pytest.raises(AuthError, match="Chưa có bucket avatar"):
            setup_avatar_storage(check_only=True)
    assert [call.args[1] for call in request.call_args_list] == ["GET"]


def test_setup_creates_and_validates_only_after_confirmed_missing_bucket():
    storage = AvatarStorage("https://demo.supabase.co", "sb_secret_example", "avatars")
    bucket = {"id": "avatars", "public": True, "file_size_limit": AVATAR_MAX_BYTES,
              "allowed_mime_types": list(AVATAR_EXTENSIONS)}
    with patch("app.cli.setup_avatar_storage.get_avatar_storage", return_value=storage), \
         patch("app.cli.setup_avatar_storage._bucket_request", side_effect=[
             failure(400, {"code": "NoSuchBucket"}), bucket, bucket,
         ]) as request:
        setup_avatar_storage()
    assert [call.args[1] for call in request.call_args_list] == ["GET", "POST", "GET"]
    assert request.call_args_list[1].args[2] == {**bucket, "name": "avatars"}
