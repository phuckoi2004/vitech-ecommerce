from __future__ import annotations


class AuthError(Exception):
    """An authentication error whose message is safe to return to a client."""

    def __init__(self, status_code: int, message: str, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.detail = message
        self.headers = headers


class AuthConfigurationError(AuthError):
    def __init__(self):
        super().__init__(503, "Dịch vụ xác thực chưa được cấu hình đầy đủ.")


class StateUnavailable(AuthError):
    def __init__(self):
        super().__init__(503, "Dịch vụ xác thực tạm thời không khả dụng.")
