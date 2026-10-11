"""Internal endpoints called by an external cron job, never by browsers or users (docs/internal-endpoints.md).

Every route requires the shared secret ``INTERNAL_CRON_SECRET`` in the ``X-Internal-Secret`` header, compared in
constant time and checked before anything else. A missing or too-short secret disables the endpoints (503).
The secret is never logged or echoed. Routes are hidden from the public OpenAPI schema.
"""

import hmac
import os
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.integrations.sepay import SePayConfigError, SePaySettings
from app.schemas import InternalJobResponse
from app.services.order import OrderService
from app.services.payment_webhook import PaymentWebhookService

from .dependencies import Database, get_order_service

INTERNAL_SECRET_ENV = "INTERNAL_CRON_SECRET"
MIN_SECRET_BYTES = 32


def require_cron_secret(secret: Annotated[str | None, Header(alias="X-Internal-Secret")] = None) -> None:
    expected = (os.getenv(INTERNAL_SECRET_ENV) or "").strip()
    if len(expected.encode("utf-8")) < MIN_SECRET_BYTES:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Endpoint nội bộ chưa được cấu hình")
    if not secret or not hmac.compare_digest(secret.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Không có quyền gọi endpoint nội bộ")


def get_payment_webhook_service(db: Database) -> PaymentWebhookService:
    try:
        settings = SePaySettings.from_env()
    except SePayConfigError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhook thanh toán chưa được cấu hình") from None
    return PaymentWebhookService(db, account_number=settings.account_number)


router = APIRouter(prefix="/internal", tags=["Nội bộ"], include_in_schema=False,
                   dependencies=[Depends(require_cron_secret)])

Orders = Annotated[OrderService, Depends(get_order_service)]
Webhooks = Annotated[PaymentWebhookService, Depends(get_payment_webhook_service)]
JobLimit = Annotated[int, Query(ge=1, le=1000)]


@router.post("/orders/expire-unpaid-qr", response_model=InternalJobResponse)
def expire_unpaid_qr_orders(service: Orders, limit: JobLimit = 100):
    """Cancels QR orders left unpaid for 15 minutes (one transaction per order; safe to run repeatedly)."""
    return InternalJobResponse(Processed=service.expire_unpaid_qr_orders(limit=limit))


@router.post("/payment-webhooks/process", response_model=InternalJobResponse)
def process_unprocessed_webhooks(service: Webhooks, limit: JobLimit = 100,
                                 older_than_minutes: Annotated[int, Query(ge=1, le=1440)] = 5):
    """Retries stored webhook events still marked Received (their first processing failed)."""
    return InternalJobResponse(Processed=service.process_unprocessed(
        older_than=timedelta(minutes=older_than_minutes), limit=limit))
