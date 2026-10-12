"""Tích hợp SePay: webhook giao dịch ngân hàng (HMAC-SHA256) và QR chuyển khoản VietQR.

Hợp đồng đã đối chiếu với tài liệu chính thức (docs.sepay.vn/tich-hop-webhooks.html,
developer.sepay.vn/vi/sepay-webhooks/{tich-hop-webhook, xac-thuc, xu-ly-loi, tao-qr-va-form-thanh-toan}):
- Webhook: POST, body JSON. Trường: id (số nguyên, không đổi qua mọi lần gửi lại), gateway, transactionDate
  ("YYYY-MM-DD HH:mm:ss", giờ Việt Nam), accountNumber, subAccount (có thể rỗng), code (mã thanh toán trích từ
  nội dung theo tiền tố; null nếu không trích được), content, transferType ("in"/"out"), description (có thể rỗng),
  transferAmount (VND, số nguyên dương), accumulated (có thể 0), referenceCode (có thể rỗng).
- HMAC-SHA256: X-SePay-Timestamp = Unix giây; X-SePay-Signature = "sha256=" + hex(HMAC_SHA256(secret,
  "{timestamp}.{raw_body}")); ký trên bytes gốc của body; từ chối nếu lệch quá 300 giây.
- Thành công: HTTP 200/201, body JSON {"success": true}, trong 30 giây; mọi trường hợp khác SePay gửi lại.
- QR: ảnh VietQR dựng bằng URL với acc, bank, amount (VND), des (nội dung). SePay không có API tạo QR/hoàn tiền.
Chưa xác minh được (cấu hình bắt buộc / cần hỏi SePay): phạm vi duy nhất của `id`; quy tắc "Cấu trúc mã thanh toán"
trong dashboard (tiền tố, độ dài); địa chỉ ảnh QR (tài liệu ghi cả vietqr.app/img và qr.sepay.vn/img).

Không ghi secret, chữ ký hay nội dung payload (tên/nội dung chuyển khoản) vào log.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import string
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from app.services.exceptions import BusinessRuleError, PaymentGatewayError, PaymentVerificationError
from app.services.ports import GatewayPaymentResult, GatewayRefundResult, QrPaymentRequest

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-SePay-Signature"
TIMESTAMP_HEADER = "X-SePay-Timestamp"
SIGNATURE_PREFIX = "sha256="
DEFAULT_TIMESTAMP_TOLERANCE_SECONDS = 300
SUCCESS_BODY: dict[str, Any] = {"success": True}
FAILURE_BODY: dict[str, Any] = {"success": False}
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9]{1,20}$")
_CODE_ALPHABET = string.ascii_uppercase + string.digits
MIN_RANDOM_CODE_LENGTH = 8  # mã thanh toán phải khó đoán (khuyến nghị của SePay)


class SePayConfigError(Exception):
    """Thiếu/sai cấu hình SePay. Chỉ chứa TÊN biến môi trường, không chứa giá trị."""


class WebhookAuthenticationError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ======================================================================
# Cấu hình (biến môi trường; không hardcode, không ghi log giá trị)
# ======================================================================


@dataclass(frozen=True)
class SePaySettings:
    webhook_secret: str = field(repr=False)
    account_number: str
    bank: str | None = None
    qr_image_url: str | None = None
    payment_code_prefix: str | None = None
    payment_code_length: int | None = None
    timestamp_tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SePaySettings":
        """Đọc cấu hình webhook (bắt buộc: SEPAY_WEBHOOK_SECRET, SEPAY_ACCOUNT_NUMBER) và QR (tùy chọn khi tạo QR)."""
        env = os.environ if env is None else env

        def value(name: str) -> str | None:
            raw = env.get(name)
            return raw.strip() if raw and raw.strip() else None

        missing = [name for name in ("SEPAY_WEBHOOK_SECRET", "SEPAY_ACCOUNT_NUMBER") if value(name) is None]
        if missing:
            raise SePayConfigError(f"Thiếu cấu hình: {', '.join(missing)}")
        length_raw = value("SEPAY_PAYMENT_CODE_LENGTH")
        try:
            length = int(length_raw) if length_raw is not None else None
        except ValueError:
            raise SePayConfigError("SEPAY_PAYMENT_CODE_LENGTH phải là số nguyên") from None
        return cls(
            webhook_secret=value("SEPAY_WEBHOOK_SECRET"),
            account_number=value("SEPAY_ACCOUNT_NUMBER"),
            bank=value("SEPAY_BANK"),
            qr_image_url=value("SEPAY_QR_IMAGE_URL"),
            payment_code_prefix=value("SEPAY_PAYMENT_CODE_PREFIX"),
            payment_code_length=length,
        )

    def require_qr(self) -> None:
        """Kiểm tra đủ cấu hình để dựng QR (gọi khi khởi tạo SePayQrGateway)."""
        missing = [
            name
            for name, current in (
                ("SEPAY_BANK", self.bank),
                ("SEPAY_QR_IMAGE_URL", self.qr_image_url),
                ("SEPAY_PAYMENT_CODE_PREFIX", self.payment_code_prefix),
                ("SEPAY_PAYMENT_CODE_LENGTH", self.payment_code_length),
            )
            if current is None
        ]
        if missing:
            raise SePayConfigError(f"Thiếu cấu hình QR: {', '.join(missing)}")
        if urlparse(self.qr_image_url).scheme != "https":
            raise SePayConfigError("SEPAY_QR_IMAGE_URL phải dùng https")
        if not _PREFIX_PATTERN.match(self.payment_code_prefix):
            raise SePayConfigError("SEPAY_PAYMENT_CODE_PREFIX chỉ gồm chữ/số, tối đa 20 ký tự")
        if not MIN_RANDOM_CODE_LENGTH <= self.payment_code_length <= 30:
            raise SePayConfigError(f"SEPAY_PAYMENT_CODE_LENGTH phải từ {MIN_RANDOM_CODE_LENGTH} đến 30")


# ======================================================================
# Xác thực webhook (HMAC-SHA256 theo tài liệu SePay)
# ======================================================================


def _header(headers: Mapping[str, str], name: str) -> str | None:
    found = headers.get(name)
    if found is None:
        lowered = name.lower()
        found = next((v for k, v in headers.items() if k.lower() == lowered), None)
    return found.strip() if isinstance(found, str) else None


def compute_signature(secret: str, timestamp: str, raw_body: bytes) -> str:
    """"sha256=" + hex(HMAC_SHA256(secret, "{timestamp}.{raw_body}")) — đúng thuật toán trong tài liệu SePay."""
    message = timestamp.encode("utf-8") + b"." + raw_body
    return SIGNATURE_PREFIX + hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_sepay_signature(
    raw_body: bytes,
    headers: Mapping[str, str],
    *,
    secret: str,
    now: float,
    tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
) -> None:
    """Raise WebhookAuthenticationError nếu thiếu header, timestamp sai/lệch quá ngưỡng hoặc chữ ký không khớp.

    ``raw_body`` phải là bytes gốc của request (không dựng lại từ JSON đã parse).
    """
    if not secret:
        raise SePayConfigError("Thiếu cấu hình: SEPAY_WEBHOOK_SECRET")
    if not isinstance(raw_body, (bytes, bytearray)):
        raise TypeError("raw_body phải là bytes gốc của request")
    signature = _header(headers, SIGNATURE_HEADER)
    timestamp = _header(headers, TIMESTAMP_HEADER)
    if not signature or not timestamp:
        raise WebhookAuthenticationError("missing_signature_headers")
    if not timestamp.isdigit():
        raise WebhookAuthenticationError("invalid_timestamp")
    if abs(now - int(timestamp)) > tolerance_seconds:
        raise WebhookAuthenticationError("timestamp_out_of_tolerance")
    expected = compute_signature(secret, timestamp, bytes(raw_body))
    if not hmac.compare_digest(expected.encode("utf-8"), signature.encode("utf-8")):
        raise WebhookAuthenticationError("invalid_signature")


# ======================================================================
# Payload
# ======================================================================


class SePayWebhookPayload(BaseModel):
    """Payload webhook SePay; trường lạ bị bỏ qua (SePay có thể bổ sung), trường cốt lõi bắt buộc đúng kiểu."""

    model_config = ConfigDict(extra="ignore")

    id: StrictInt = Field(ge=0)
    gateway: str | None = None
    transactionDate: str | None = None
    accountNumber: str = Field(min_length=1, max_length=50)
    subAccount: str | None = None
    code: str | None = Field(default=None, max_length=100)
    content: str | None = None
    transferType: Literal["in", "out"]
    description: str | None = None
    transferAmount: StrictInt = Field(ge=0)
    accumulated: StrictInt | None = None
    referenceCode: str | None = Field(default=None, max_length=100)

    @property
    def payment_code(self) -> str | None:
        """`code` đã trim; chuỗi rỗng coi như không có mã."""
        return self.code.strip() if self.code and self.code.strip() else None

    @property
    def transaction_time_utc(self) -> datetime | None:
        """transactionDate (giờ Việt Nam) → UTC; không đọc được thì None (không chặn ghi nhận giao dịch)."""
        if not self.transactionDate:
            return None
        try:
            local = datetime.strptime(self.transactionDate.strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        return local.replace(tzinfo=VIETNAM_TZ).astimezone(timezone.utc)

    def reconciliation_key(self) -> str:
        """Định danh giao dịch SePay cho đối soát (gồm tài khoản vì phạm vi duy nhất của `id` chưa được xác nhận)."""
        return f"sepay:{self.accountNumber.strip()}:{self.id}"

    def stored_response_data(self) -> dict[str, Any]:
        """Thông tin giao dịch lưu vào PaymentTransactions/đối soát (không gồm tên/nội dung chuyển khoản)."""
        return {
            "provider": "SePay",
            "sepay_id": self.id,
            "gateway": self.gateway,
            "transaction_date": self.transactionDate,
            "account_number": self.accountNumber,
            "code": self.code,
            "transfer_type": self.transferType,
            "transfer_amount": self.transferAmount,
            "reference_code": self.referenceCode,
        }


def parse_sepay_payload(raw_body: bytes) -> tuple[SePayWebhookPayload, dict[str, Any]]:
    """Parse JSON (chỉ hỗ trợ Content-Type application/json — cấu hình webhook phải chọn JSON)."""
    data = json.loads(raw_body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Payload phải là JSON object")
    return SePayWebhookPayload.model_validate(data), data


# ======================================================================
# Xử lý request webhook (không phụ thuộc FastAPI; Router chỉ chuyển raw body + headers vào đây)
# ======================================================================

WebhookProcessor = Callable[[SePayWebhookPayload, dict[str, Any], SePaySettings], str]


def handle_sepay_webhook(
    raw_body: bytes,
    headers: Mapping[str, str],
    *,
    settings_loader: Callable[[], SePaySettings],
    process: WebhookProcessor,
    now: Callable[[], float],
) -> tuple[int, dict[str, Any]]:
    """Trả (HTTP status, body). Chỉ trả 200 + {"success": true} khi sự kiện đã được ghi nhận bền vững và xử lý xong.

    - Thiếu cấu hình → 503 (không bao giờ xử lý khi chưa xác thực được).
    - Sai/thiếu chữ ký, timestamp → 401. Payload không hợp lệ → 400.
    - Lỗi lưu/xử lý (ví dụ database) → 500 để SePay gửi lại; sự kiện đã lưu sẽ được xử lý lại theo idempotency.
    """
    try:
        settings = settings_loader()
    except SePayConfigError as exc:
        logger.error("Webhook SePay bị từ chối do cấu hình: %s", exc)
        return 503, dict(FAILURE_BODY)
    try:
        verify_sepay_signature(
            raw_body, headers, secret=settings.webhook_secret, now=now(),
            tolerance_seconds=settings.timestamp_tolerance_seconds,
        )
    except WebhookAuthenticationError as exc:
        logger.warning("Từ chối webhook SePay: %s", exc.reason)
        return 401, dict(FAILURE_BODY)
    try:
        payload, data = parse_sepay_payload(raw_body)
    except (ValueError, UnicodeDecodeError, ValidationError):
        logger.warning("Payload webhook SePay không hợp lệ")
        return 400, dict(FAILURE_BODY)
    try:
        outcome = process(payload, data, settings)
    except Exception as exc:
        # Không ghi chi tiết lỗi (có thể chứa dữ liệu payload/SQL); SePay sẽ gửi lại.
        logger.error("Không ghi nhận được webhook SePay id=%s (%s)", payload.id, type(exc).__name__)
        return 500, dict(FAILURE_BODY)
    logger.info("Webhook SePay id=%s: %s", payload.id, outcome)
    return 200, dict(SUCCESS_BODY)


# ======================================================================
# Tạo QR (PaymentGateway adapter cho PaymentService)
# ======================================================================


class SePayQrGateway:
    """Dựng QR VietQR cho SePay (không gọi mạng). Mã thanh toán ngẫu nhiên, khó đoán, đặt trong nội dung chuyển khoản.

    SePay không có API hoàn tiền: ``supports_refund = False`` → PaymentService ghi Refund Pending để Staff/Admin
    chuyển khoản thủ công rồi xác nhận (``resolve_pending_refund``).
    """

    supports_refund = False

    def __init__(self, settings: SePaySettings, *, choice: Callable[[str], str] = secrets.choice) -> None:
        settings.require_qr()
        self.settings = settings
        self._choice = choice

    def validate_payment_amount(self, amount: Decimal) -> None:
        """QR VietQR nhận số tiền nguyên VND; không tự làm tròn số tiền đơn hàng."""
        if amount <= 0 or amount != amount.to_integral_value():
            raise BusinessRuleError(
                "Số tiền thanh toán QR phải là số nguyên VND lớn hơn 0", code="qr_amount_not_supported"
            )

    def new_payment_code(self) -> str:
        suffix = "".join(self._choice(_CODE_ALPHABET) for _ in range(self.settings.payment_code_length))
        return f"{self.settings.payment_code_prefix}{suffix}"

    def create_qr_payment(self, *, order_code: str, amount: Decimal) -> QrPaymentRequest:
        self.validate_payment_amount(amount)
        code = self.new_payment_code()
        query = urlencode(
            {"acc": self.settings.account_number, "bank": self.settings.bank, "amount": str(int(amount)), "des": code}
        )
        return QrPaymentRequest(
            gateway_transaction_code=code,
            qr_data=f"{self.settings.qr_image_url}?{query}",
            response_data={"provider": "SePay", "payment_code": code},
        )

    def verify_callback(self, payload: Mapping[str, Any]) -> GatewayPaymentResult:
        raise PaymentVerificationError(
            "SePay dùng webhook riêng (handle_sepay_webhook/PaymentWebhookService)", code="unsupported_callback"
        )

    def refund(self, *, gateway_transaction_code: str, amount: Decimal) -> GatewayRefundResult:
        raise PaymentGatewayError("SePay không hỗ trợ hoàn tiền qua API", code="refund_not_supported")
