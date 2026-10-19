"""Avatar files in Supabase Storage through its REST API (no extra dependency)."""

import base64
import binascii
import json
import os
import re
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from .errors import AuthError


AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _is_server_key(key: str) -> bool:
    """Reject placeholders/public keys before upload; Supabase still verifies the key itself."""
    if re.fullmatch(r"sb_secret_[A-Za-z0-9_-]+", key):
        return True
    parts = key.split(".")
    if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts):
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (ValueError, binascii.Error):
        return False
    return isinstance(payload, dict) and payload.get("role") == "service_role"


def detect_image_type(data: bytes) -> str | None:
    """Trust the file signature, not the client's Content-Type."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True)
class AvatarStorage:
    url: str
    service_key: str = field(repr=False)
    bucket: str
    timeout: int = 15

    def public_url(self, path: str) -> str:
        bucket = urllib.parse.quote(self.bucket, safe="")
        return f"{self.url}/storage/v1/object/public/{bucket}/{path}"

    def path_of(self, public_url: str | None, user_id: uuid.UUID) -> str | None:
        """Only canonical uploads in this user's directory may be deleted."""
        prefix = self.public_url(f"{user_id}/")
        if public_url and public_url.startswith(prefix):
            filename = public_url[len(prefix):]
            # Match upload's generated names exactly; never normalize client-supplied paths.
            if re.fullmatch(r"[a-f0-9]{32}\.(?:jpg|png|webp)", filename):
                return f"{user_id}/{filename}"
        return None

    def authentication_headers(self) -> dict[str, str]:
        headers = {"apikey": self.service_key}
        # New Supabase secret keys are API keys, not JWTs. The legacy
        # service_role JWT remains valid in both headers.
        if not self.service_key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {self.service_key}"
        return headers

    def _call(self, method: str, path: str, data: bytes | None = None, content_type: str | None = None) -> None:
        headers = self.authentication_headers()
        if content_type:
            headers.update({"Content-Type": content_type, "Cache-Control": "max-age=31536000"})
        bucket = urllib.parse.quote(self.bucket, safe="")
        target = f"{self.url}/storage/v1/object/{bucket}/{urllib.parse.quote(path)}"
        request = urllib.request.Request(target, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            response.read()

    def upload(self, user_id: uuid.UUID, data: bytes, content_type: str) -> str:
        # A new name per upload, so browsers and CDNs never serve the previous picture.
        path = f"{user_id}/{uuid.uuid4().hex}.{AVATAR_EXTENSIONS[content_type]}"
        try:
            self._call("POST", path, data, content_type)
        except OSError:
            raise AuthError(502, "Không tải được ảnh lên kho lưu trữ. Vui lòng thử lại sau.") from None
        return path

    def delete(self, path: str) -> None:
        try:
            self._call("DELETE", path)
        except OSError:
            pass  # A leftover file costs storage only; the profile already points elsewhere.


@lru_cache(maxsize=1)
def get_avatar_storage() -> AvatarStorage | None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    secret_key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
    key = secret_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return None
    if (secret_key and not secret_key.startswith("sb_secret_")) or not _is_server_key(key):
        raise AuthError(503, "Khóa Supabase Storage không hợp lệ. Cấu hình SUPABASE_SECRET_KEY dạng sb_secret_... "
                        "hoặc SUPABASE_SERVICE_ROLE_KEY dạng JWT service_role trong backend/.env.")
    try:
        parsed = urllib.parse.urlsplit(url)
        parsed.port
    except ValueError:
        raise AuthError(503, "SUPABASE_URL của kho avatar phải là URL gốc HTTPS của dự án.") from None
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (not parsed.hostname or (parsed.scheme != "https" and not local_http)
            or any(char.isspace() for char in url) or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise AuthError(503, "SUPABASE_URL của kho avatar phải là URL gốc HTTPS của dự án.")
    return AvatarStorage(url, key, os.getenv("SUPABASE_AVATAR_BUCKET", "avatars").strip() or "avatars")
