"""Thành phần dùng chung của WarrantyService và ReturnService (đợt 5.4): mã yêu cầu, đính kèm, ghi chú, lịch sử.

- Đính kèm: chỉ lưu URL do client đã tải lên (không có dịch vụ upload); FileType Image/Video; URL https, tối đa
  500 ký tự (ServiceRequestAttachments.FileUrl varchar(500)), không chứa khoảng trắng.
- Lịch sử: mỗi bước xử lý ghi một dòng ServiceRequestHistories (trạng thái trước/sau, người thực hiện, thời điểm,
  ghi chú). Bước không đổi Status (tiếp nhận, kết quả kiểm tra, đề xuất/duyệt kết quả) ghi OldStatus = NewStatus.
  ChangedByUserId = None nghĩa là hệ thống tự thực hiện.
- Ghi chú (đợt 5.4.1): Note = nội dung khách hàng được xem; InternalNote = chỉ Staff/Admin; IsInternal = cả dòng chỉ
  Staff/Admin xem (Note để trống). Khách hàng không được gửi InternalNote.
"""

import secrets
import string
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from app.models.service_request import ATTACHMENT_FILE_TYPES

from .exceptions import BusinessRuleError

ATTACHMENT_URL_MAX_LENGTH = 500
_CODE_ALPHABET = string.ascii_uppercase + string.digits


def allowed_values(data: Any, allowed: frozenset[str], *, code: str) -> dict[str, Any]:
    """Chỉ nhận các trường cho phép (schema đã chặn; chặn lại nếu schema bị bỏ qua)."""
    values = dict(data.model_dump(exclude_unset=True))
    if "Attachments" in values and hasattr(data, "Attachments"):
        values["Attachments"] = list(data.Attachments)  # giữ đối tượng schema của đính kèm
    not_allowed = sorted(set(values) - allowed)
    if not_allowed:
        raise BusinessRuleError(f"Không được gửi các trường: {not_allowed}", code=code)
    return values


def required_text(value: Any, *, code: str, message: str) -> str:
    """Văn bản bắt buộc: bỏ khoảng trắng đầu/cuối, không được rỗng."""
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise BusinessRuleError(message, code=code)
    return text


def optional_text(value: Any) -> str | None:
    """Ghi chú tùy chọn: bỏ khoảng trắng đầu/cuối; rỗng → None."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise BusinessRuleError("Ghi chú phải là chuỗi ký tự", code="invalid_note")
    return value.strip() or None


def step_notes(data: Any, *, allowed: frozenset[str] = frozenset({"Note", "InternalNote"}),
               code: str) -> tuple[str | None, str | None]:
    """(ghi chú khách xem được, ghi chú nội bộ) của một bước; chỉ nhận các trường cho phép."""
    if data is None:
        return None, None
    values = allowed_values(data, allowed, code=code)
    return optional_text(values.get("Note")), optional_text(values.get("InternalNote"))


def compose_note(event: str, note: str | None = None) -> str:
    """Nội dung dòng lịch sử: mô tả sự kiện + ghi chú của người thực hiện (nếu có)."""
    return f"{event} Ghi chú: {note}" if note else event


def validate_attachments(attachments: Any) -> list[tuple[str, str]]:
    """Danh sách (FileUrl, FileType) hợp lệ; lỗi rõ ràng nếu loại tệp hoặc URL không hợp lệ."""
    result = []
    for attachment in attachments or []:
        url = getattr(attachment, "FileUrl", None)
        file_type = getattr(attachment, "FileType", None)
        if file_type not in ATTACHMENT_FILE_TYPES:
            raise BusinessRuleError("Tệp đính kèm chỉ nhận hình ảnh (Image) hoặc video (Video)",
                                    code="invalid_attachment_type")
        url = url.strip() if isinstance(url, str) else ""
        parsed = urlparse(url)
        if (not url or len(url) > ATTACHMENT_URL_MAX_LENGTH or any(ch.isspace() for ch in url)
                or parsed.scheme != "https" or not parsed.netloc):
            raise BusinessRuleError("Địa chỉ tệp đính kèm phải là URL https hợp lệ", code="invalid_attachment_url")
        result.append((url, file_type))
    return result


def generate_request_code(prefix: str, now: datetime, exists: Callable[[str], bool], *, failure_code: str) -> str:
    """Mã yêu cầu ``<prefix><yymmdd><6 ký tự>``; trùng với mã đã có thì sinh lại (UNIQUE RequestCode vẫn chặn đua)."""
    for _ in range(10):
        code = f"{prefix}{now:%y%m%d}{''.join(secrets.choice(_CODE_ALPHABET) for _ in range(6))}"
        if not exists(code):
            return code
    raise BusinessRuleError("Không tạo được mã yêu cầu", code=failure_code)
