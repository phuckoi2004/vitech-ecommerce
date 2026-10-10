"""Lỗi nghiệp vụ của Service layer (không phụ thuộc FastAPI/HTTP).

Router sẽ ánh xạ các lỗi này sang HTTP status ở giai đoạn sau.
"""


class ServiceError(Exception):
    """Lỗi nghiệp vụ chung. ``code`` dùng cho client/Router phân biệt lỗi."""

    code = "service_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class NotFoundError(ServiceError):
    code = "not_found"


class ConflictError(ServiceError):
    """Dữ liệu trùng (ví dụ Email, PhoneNumber đã tồn tại)."""

    code = "conflict"


class BusinessRuleError(ServiceError):
    """Vi phạm quy tắc nghiệp vụ hoặc dữ liệu đầu vào không hợp lệ theo nghiệp vụ."""

    code = "business_rule_violation"


class AuthenticationError(ServiceError):
    """Sai thông tin đăng nhập / mật khẩu."""

    code = "invalid_credentials"


class AccountLockedError(ServiceError):
    code = "account_locked"


class EmailNotVerifiedError(ServiceError):
    code = "email_not_verified"


class InvalidOtpError(ServiceError):
    """OTP sai (code otp_invalid) hoặc hết hạn (otp_expired)."""

    code = "invalid_otp"


class TooManyRequestsError(ServiceError):
    """Vượt giới hạn: gửi OTP quá sớm/quá số lần (otp_send_too_soon, otp_send_limit_exceeded) hoặc đang bị khóa
    xác minh do nhập sai quá số lần (otp_verification_locked). ``retry_after_seconds``: thời gian chờ còn lại."""

    code = "too_many_requests"

    def __init__(self, message: str, *, code: str | None = None, retry_after_seconds: int | None = None) -> None:
        super().__init__(message, code=code)
        self.retry_after_seconds = retry_after_seconds


class PaymentVerificationError(ServiceError):
    """Dữ liệu từ cổng thanh toán không xác minh được (sai chữ ký, sai định dạng)."""

    code = "payment_verification_failed"


class PermissionDeniedError(ServiceError):
    """Actor không có quyền nghiệp vụ thực hiện thao tác (sai role hoặc vi phạm quy tắc kiểm soát)."""

    code = "permission_denied"


class PaymentGatewayError(ServiceError):
    """Gọi cổng thanh toán lỗi/không rõ kết quả; giao dịch liên quan được giữ để đối soát."""

    code = "payment_gateway_error"
