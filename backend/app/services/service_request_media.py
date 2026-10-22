"""Stage customer evidence using the existing image-storage configuration and bucket policy."""

import uuid

from app.core.errors import AuthError
from app.core.storage import AVATAR_EXTENSIONS, AVATAR_MAX_BYTES, AvatarStorage, detect_image_type

from .actor import CUSTOMER_ONLY, Actor, require_role

EVIDENCE_MAX_BYTES = AVATAR_MAX_BYTES


class ServiceRequestMediaService:
    def __init__(self, storage: AvatarStorage | None):
        self.storage = storage

    def upload_image(self, actor: Actor, data: bytes) -> str:
        require_role(actor, *CUSTOMER_ONLY)
        if not data:
            raise AuthError(422, "Vui lòng chọn ảnh minh chứng.")
        if len(data) > EVIDENCE_MAX_BYTES:
            raise AuthError(413, "Ảnh minh chứng tối đa 2 MB.")
        content_type = detect_image_type(data)
        if content_type is None:
            raise AuthError(422, "Ảnh minh chứng phải là JPG, PNG hoặc WEBP.")
        if self.storage is None:
            raise AuthError(503, "Chưa cấu hình kho ảnh. Vui lòng thử lại sau hoặc gửi yêu cầu không kèm ảnh.")
        path = f"service-requests/{actor.user_id}/{uuid.uuid4().hex}.{AVATAR_EXTENSIONS[content_type]}"
        try:
            self.storage._call("POST", path, data, content_type)
        except OSError:
            raise AuthError(502, "Không tải được ảnh minh chứng. Vui lòng thử lại.") from None
        return self.storage.public_url(path)
