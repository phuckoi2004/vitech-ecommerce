"""Explicitly check or create the avatar bucket; never called on API startup."""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from app.core.errors import AuthError
from app.core.storage import AVATAR_EXTENSIONS, AVATAR_MAX_BYTES, get_avatar_storage


def _bucket_request(storage, method, payload=None):
    target = f"{storage.url}/storage/v1/bucket"
    if method == "GET":
        target += "/" + urllib.parse.quote(storage.bucket, safe="")
    headers = storage.authentication_headers()
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(target, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=storage.timeout) as response:
        result = json.loads(response.read())
    if not isinstance(result, dict):
        raise AuthError(503, "Kho avatar trả về dữ liệu không hợp lệ.")
    return result


def _missing_bucket(error):
    # Storage uses 400/NoSuchBucket on current hosted projects; older responses use 404.
    # Never treat other HTTP 400 failures (bad keys/configuration) as permission to create.
    if error.code not in {400, 404}:
        return False
    try:
        body = json.loads(error.read())
        return isinstance(body, dict) and (body.get("code") or body.get("error")) in {"NoSuchBucket", "not_found"}
    except (ValueError, OSError):
        return False


def _require_compatible_bucket(storage, bucket):
    if bucket.get("id") != storage.bucket:
        raise AuthError(503, "Kho avatar trả về bucket không đúng cấu hình.")
    if bucket.get("public") is not True:
        raise AuthError(503, "Bucket avatar hiện là private. Chọn một bucket public dành riêng cho avatar; lệnh không sửa bucket hiện có.")
    limit = bucket.get("file_size_limit")
    types = bucket.get("allowed_mime_types")
    if (str(limit) != str(AVATAR_MAX_BYTES) or not isinstance(types, list)
            or any(not isinstance(item, str) for item in types)
            or set(types) != set(AVATAR_EXTENSIONS)):
        raise AuthError(503, "Bucket avatar cần giới hạn 2 MB và chỉ nhận JPG, PNG, WEBP. Điều chỉnh trong Supabase hoặc chọn bucket khác; lệnh không sửa bucket hiện có.")


def setup_avatar_storage(*, check_only=False):
    storage = get_avatar_storage()
    if storage is None:
        raise AuthError(503, "Chưa cấu hình kho avatar: cần SUPABASE_URL và SUPABASE_SECRET_KEY (hoặc SUPABASE_SERVICE_ROLE_KEY) trong backend/.env.")
    try:
        bucket = _bucket_request(storage, "GET")
    except urllib.error.HTTPError as error:
        if not _missing_bucket(error):
            raise
        if check_only:
            raise AuthError(503, "Chưa có bucket avatar. Chạy python -m app.cli.setup_avatar_storage để tạo bucket đã cấu hình.") from None
        payload = {"id": storage.bucket, "name": storage.bucket, "public": True,
                   "file_size_limit": AVATAR_MAX_BYTES, "allowed_mime_types": list(AVATAR_EXTENSIONS)}
        try:
            _bucket_request(storage, "POST", payload)
        except urllib.error.HTTPError as create_error:
            if create_error.code != 409:
                raise
            # Another setup process may have created it. Re-read and validate;
            # never change an existing bucket, its access or its contents.
        bucket = _bucket_request(storage, "GET")
    _require_compatible_bucket(storage, bucket)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kiểm tra hoặc tạo bucket Supabase dành cho avatar.")
    parser.add_argument("--check", action="store_true", help="Chỉ kiểm tra, không tạo hoặc sửa bucket.")
    args = parser.parse_args(argv)
    try:
        setup_avatar_storage(check_only=args.check)
    except AuthError as error:
        print(error.message, file=sys.stderr)
        return 1
    except urllib.error.HTTPError as error:
        # Remote messages and exception URLs may contain secrets; print only
        # the numeric status and a fixed, actionable message.
        print(f"Supabase Storage trả HTTP {error.code}. Kiểm tra API key server, quyền truy cập và cấu hình kho avatar.", file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("Không kết nối hoặc đọc được cấu hình kho avatar. Kiểm tra SUPABASE_URL và kết nối mạng.", file=sys.stderr)
        return 1
    print("Kho avatar đã sẵn sàng: public, JPG/PNG/WEBP, tối đa 2 MB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
