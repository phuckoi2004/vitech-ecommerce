from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from functools import lru_cache

from .config import AuthSettings
from .errors import AuthConfigurationError, AuthError


class SMTPMailer:
    def __init__(self, settings: AuthSettings):
        self.settings = settings

    def send_otp(self, email: str, code: str, purpose: str, ttl: int) -> None:
        settings = self.settings
        if (
            not settings.smtp_host or not settings.smtp_sender
            or not (settings.smtp_ssl or settings.smtp_starttls)
            or "\n" in settings.smtp_sender or "\r" in settings.smtp_sender
            or "\n" in email or "\r" in email
            or bool(settings.smtp_username) != bool(settings.smtp_password)
        ):
            raise AuthConfigurationError()
        message = EmailMessage()
        message["Subject"] = "Mã xác minh VieTech"
        message["From"] = settings.smtp_sender
        message["To"] = email
        purpose_text = {
            "signup": "đăng ký tài khoản", "password_reset": "đặt lại mật khẩu",
            "email_change": "thay đổi email",
        }.get(purpose, "xác minh tài khoản")
        message.set_content(
            f"Mã xác minh {purpose_text} của bạn là: {code}\n"
            f"Mã có hiệu lực trong {ttl} giây. Không chia sẻ mã với người khác.\n"
            "Nếu bạn không yêu cầu thao tác này, hãy bỏ qua email."
        )
        context = ssl.create_default_context()
        try:
            if settings.smtp_ssl:
                connection = smtplib.SMTP_SSL(
                    settings.smtp_host, settings.smtp_port,
                    timeout=settings.smtp_timeout, context=context,
                )
            else:
                connection = smtplib.SMTP(
                    settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout,
                )
            with connection:
                connection.ehlo()
                if not settings.smtp_ssl:
                    connection.starttls(context=context)
                    connection.ehlo()
                if settings.smtp_username:
                    connection.login(settings.smtp_username, settings.smtp_password)
                connection.send_message(message)
        except (smtplib.SMTPException, OSError, ValueError):
            raise AuthError(503, "Không thể gửi email xác minh lúc này. Vui lòng thử lại sau.") from None


@lru_cache(maxsize=8)
def get_mailer(settings: AuthSettings) -> SMTPMailer:
    return SMTPMailer(settings)
