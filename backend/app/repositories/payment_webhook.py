"""Repository cho PaymentWebhookEvents (sự kiện giao dịch ngân hàng từ webhook). Không xóa sự kiện."""

import uuid
from datetime import datetime
from typing import NoReturn

from app.models import PaymentWebhookEvent
from app.models.payment_webhook import WEBHOOK_RECEIVED

from .base import BaseRepository


class PaymentWebhookEventRepository(BaseRepository[PaymentWebhookEvent]):
    model = PaymentWebhookEvent

    def get_by_key(self, provider: str, account_number: str, provider_transaction_id: str) -> PaymentWebhookEvent | None:
        """Khóa idempotency (UNIQUE): (Provider, AccountNumber, ProviderTransactionId)."""
        return self.get_one(
            PaymentWebhookEvent.Provider == provider,
            PaymentWebhookEvent.AccountNumber == account_number,
            PaymentWebhookEvent.ProviderTransactionId == provider_transaction_id,
        )

    def list_unprocessed_ids(self, *, received_before: datetime, limit: int) -> list[uuid.UUID]:
        """Sự kiện đã lưu nhưng chưa xử lý xong (ví dụ lỗi giữa chừng và SePay đã hết lượt gửi lại)."""
        return [
            e.PaymentWebhookEventId
            for e in self.get_all(
                PaymentWebhookEvent.Status == WEBHOOK_RECEIVED,
                PaymentWebhookEvent.ReceivedAt <= received_before,
                order_by=(PaymentWebhookEvent.ReceivedAt, PaymentWebhookEvent.PaymentWebhookEventId),
                limit=limit,
            )
        ]

    def delete(self, obj: PaymentWebhookEvent) -> NoReturn:
        raise PermissionError("PaymentWebhookEvents không được xóa")
