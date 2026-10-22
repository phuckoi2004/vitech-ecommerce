"""Stage product images in the existing public image bucket; no catalog/DB writes."""

import uuid

from app.core.errors import AuthError
from app.core.storage import AVATAR_EXTENSIONS, AVATAR_MAX_BYTES, AvatarStorage, detect_image_type

from .actor import STAFF_OR_ADMIN, Actor, require_role


PRODUCT_IMAGE_MAX_BYTES = AVATAR_MAX_BYTES  # Respect the existing bucket's 2 MB policy.


class ProductMediaService:
    """Built per request with the configured storage (None while Supabase Storage is not configured)."""

    def __init__(self, storage: AvatarStorage | None):
        self.storage = storage

    def upload_product_image(self, actor: Actor, data: bytes) -> str:
        # Shared image staging for products, news and banners; no catalog-write permission is granted.
        require_role(actor, *STAFF_OR_ADMIN)
        if not data:
            raise AuthError(422, "Vui lòng chọn ảnh sản phẩm.")
        if len(data) > PRODUCT_IMAGE_MAX_BYTES:
            raise AuthError(413, "Ảnh sản phẩm tối đa 2 MB.")
        content_type = detect_image_type(data)
        if content_type is None:
            raise AuthError(422, "Ảnh sản phẩm phải là JPG, PNG hoặc WEBP.")
        storage = self.storage
        if storage is None:
            raise AuthError(503, "Chưa cấu hình kho ảnh sản phẩm. Kiểm tra cấu hình Supabase Storage trên máy chủ.")
        # Separate namespace: never replaces or deletes a user's avatar. Fresh names avoid CDN caching.
        path = f"products/{actor.user_id}/{uuid.uuid4().hex}.{AVATAR_EXTENSIONS[content_type]}"
        try:
            storage._call("POST", path, data, content_type)
        except OSError:
            raise AuthError(502, "Không tải được ảnh sản phẩm lên kho lưu trữ. Vui lòng thử lại sau.") from None
        return storage.public_url(path)
