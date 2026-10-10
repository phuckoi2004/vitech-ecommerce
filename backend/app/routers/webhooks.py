"""Router nhận webhook từ cổng thanh toán (không dùng JWT người dùng; nguồn gửi xác thực bằng HMAC).

CHƯA được đăng ký trong app/main.py. Khi bật: ``app.include_router(webhooks.router)`` và cấu hình SePay gửi
webhook (Content-Type JSON, xác thực HMAC-SHA256) tới POST {base_url}/webhooks/sepay.
Router chỉ chuyển raw body + headers sang ``handle_sepay_webhook``; nghiệp vụ nằm ở PaymentWebhookService.
"""

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.integrations.sepay import SePaySettings, SePayWebhookPayload, handle_sepay_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _process_with_database_session(payload: SePayWebhookPayload, raw: dict[str, Any], settings: SePaySettings) -> str:
    """Mở Session riêng cho mỗi webhook (import tại chỗ để module không kết nối/đọc cấu hình DB khi được import)."""
    from app.database import SessionLocal
    from app.services.payment_webhook import PaymentWebhookService

    session = SessionLocal()
    try:
        return PaymentWebhookService(session, account_number=settings.account_number).receive_sepay(payload, raw)
    finally:
        session.close()


@router.post("/sepay")
async def sepay_webhook(request: Request) -> JSONResponse:
    raw_body = await request.body()  # bytes gốc: bắt buộc cho HMAC, không dựng lại từ JSON đã parse
    status_code, body = await run_in_threadpool(
        handle_sepay_webhook,
        raw_body,
        request.headers,
        settings_loader=SePaySettings.from_env,
        process=_process_with_database_session,
        now=time.time,
    )
    return JSONResponse(status_code=status_code, content=body)
