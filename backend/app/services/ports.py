"""Interface cho các dịch vụ bên ngoài mà Service cần.

Implementation cụ thể (bcrypt, email adapter) thuộc giai đoạn Auth/Integration và được
truyền vào Service qua constructor.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


class PasswordHasher(Protocol):
    """Băm và kiểm tra mật khẩu (yêu cầu: bcrypt - NFR-BM-01)."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class OtpSender(Protocol):
    """Gửi OTP qua email (Email Adapter)."""

    def send_registration_otp(self, email: str, otp_code: str) -> None: ...

    def send_password_reset_otp(self, email: str, otp_code: str) -> None: ...


@dataclass(frozen=True)
class QrPaymentRequest:
    """Kết quả tạo yêu cầu thanh toán QR tại cổng thanh toán."""

    gateway_transaction_code: str
    qr_data: str
    response_data: dict[str, Any] | None = None


@dataclass(frozen=True)
class GatewayPaymentResult:
    """Kết quả thanh toán đã được cổng thanh toán xác minh (callback/IPN)."""

    gateway_transaction_code: str
    amount: Decimal
    success: bool
    response_data: dict[str, Any]


@dataclass(frozen=True)
class GatewayRefundResult:
    success: bool
    response_data: dict[str, Any]
    gateway_transaction_code: str | None = None


class PaymentGateway(Protocol):
    """Payment Adapter cho cổng thanh toán QR (Integration Layer)."""

    def create_qr_payment(self, *, order_code: str, amount: Decimal) -> QrPaymentRequest: ...

    def verify_callback(self, payload: Mapping[str, Any]) -> GatewayPaymentResult:
        """Xác minh chữ ký/định dạng callback; không hợp lệ thì raise PaymentVerificationError."""
        ...

    def refund(self, *, gateway_transaction_code: str, amount: Decimal) -> GatewayRefundResult: ...
