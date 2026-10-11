"""Payment webhook service: ghi nhận và xử lý giao dịch ngân hàng từ webhook SePay.

Không phải thao tác của người dùng (không nhận Actor): nguồn gửi đã được xác thực bằng HMAC trước khi gọi Service.
1. Lưu sự kiện bền vững (transaction riêng), idempotent theo (Provider, AccountNumber, ProviderTransactionId):
   SePay gửi lại cùng `id` → không lưu/xử lý lại. Hai lần gửi đồng thời: UNIQUE của database chặn bản ghi thứ hai.
2. Xử lý (transaction riêng, khóa sự kiện): chỉ tiền vào đúng tài khoản cấu hình; đối chiếu qua
   PaymentService.apply_bank_transfer (mã thanh toán + số tiền; không tự chọn đơn; không tự hoàn tiền).
Bước 2 lỗi: sự kiện giữ Received → caller trả lỗi để SePay gửi lại; ``process_unprocessed`` xử lý lại sau.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.sepay import SePayWebhookPayload
from app.models.payment_webhook import PROVIDER_SEPAY, WEBHOOK_IGNORED, WEBHOOK_PROCESSED, WEBHOOK_RECEIVED
from app.repositories import PaymentWebhookEventRepository

from .base import BaseService, utc_now
from .exceptions import BusinessRuleError, ConflictError, NotFoundError
from .payment import BankTransfer, PaymentService

TRANSFER_IN = "in"


class PaymentWebhookService(BaseService):
    def __init__(
        self,
        session: Session,
        *,
        account_number: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(session, clock=clock)
        if not account_number:
            raise ValueError("Cần tài khoản nhận tiền đã cấu hình (SEPAY_ACCOUNT_NUMBER)")
        self.account_number = account_number.strip()
        self.events = PaymentWebhookEventRepository(session)
        self.payments = PaymentService(session, gateway=None, clock=clock)

    def receive_sepay(self, payload: SePayWebhookPayload, raw: dict[str, Any]) -> str:
        """Ghi nhận rồi xử lý một webhook SePay đã xác thực. Trả kết quả (ví dụ paid, amount_mismatch, duplicate)."""
        if self.in_transaction():
            raise BusinessRuleError("Webhook phải là use case độc lập", code="webhook_requires_own_transaction")
        event_id, already_final = self._store_sepay_event(payload, raw)
        if already_final:
            return "duplicate"
        return self.process_event(event_id)

    def process_event(self, event_id: uuid.UUID) -> str:
        """Xử lý một sự kiện đã lưu (khóa dòng; sự kiện đã xử lý thì bỏ qua — an toàn khi gọi lặp/đồng thời)."""
        with self.transaction():
            event = self.events.get_by_id_for_update(event_id)
            if event is None:
                raise NotFoundError("Không tìm thấy sự kiện webhook", code="webhook_event_not_found")
            if event.Status != WEBHOOK_RECEIVED:
                return "duplicate"
            if event.TransferType != TRANSFER_IN:
                status, outcome, transaction_id = WEBHOOK_IGNORED, "ignored_transfer_out", None
            elif event.AccountNumber != self.account_number:
                status, outcome, transaction_id = WEBHOOK_IGNORED, "ignored_other_account", None
            else:
                outcome, transaction_id = self.payments.apply_bank_transfer(
                    BankTransfer(
                        reconciliation_key=f"sepay:{event.AccountNumber}:{event.ProviderTransactionId}",
                        payment_code=event.PaymentCode,
                        amount=Decimal(event.TransferAmount),
                        response_data=_stored_response_data(event.Payload),
                        webhook_event_id=event.PaymentWebhookEventId,
                    )
                )
                status = WEBHOOK_PROCESSED
            event.Status = status
            event.ProcessingNote = outcome
            event.PaymentTransactionId = transaction_id
            event.ProcessedAt = self.now()
            self.events.flush()
            return outcome

    def process_unprocessed(self, *, older_than: timedelta = timedelta(minutes=5), limit: int = 100) -> int:
        """Xử lý lại các sự kiện còn Received (đã lưu nhưng xử lý lỗi). Dành cho tác vụ nội bộ; trả số đã xử lý."""
        if self.in_transaction():
            raise BusinessRuleError("Tác vụ phải là use case độc lập", code="webhook_requires_own_transaction")
        processed = 0
        for event_id in self.events.list_unprocessed_ids(received_before=self.now() - older_than, limit=limit):
            if self.process_event(event_id) != "duplicate":
                processed += 1
        return processed

    def _store_sepay_event(self, payload: SePayWebhookPayload, raw: dict[str, Any]) -> tuple[uuid.UUID, bool]:
        key = (PROVIDER_SEPAY, payload.accountNumber.strip(), str(payload.id))
        try:
            with self.transaction():
                existing = self.events.get_by_key(*key)
                if existing is not None:
                    return existing.PaymentWebhookEventId, existing.Status != WEBHOOK_RECEIVED
                event = self.events.create(
                    {
                        "Provider": PROVIDER_SEPAY,
                        "ProviderTransactionId": key[2],
                        "AccountNumber": key[1],
                        "TransferType": payload.transferType,
                        "TransferAmount": Decimal(payload.transferAmount),
                        "PaymentCode": payload.payment_code,
                        "ReferenceCode": payload.referenceCode or None,
                        "TransactionDate": payload.transaction_time_utc,
                        "Payload": raw,
                        "Status": WEBHOOK_RECEIVED,
                        "ReceivedAt": self.now(),
                    }
                )
                self.events.flush()
                return event.PaymentWebhookEventId, False
        except ConflictError:
            # Lần gửi đồng thời khác vừa lưu cùng sự kiện (UNIQUE): dùng bản ghi đã có.
            existing = self.events.get_by_key(*key)
            if existing is None:
                raise
            return existing.PaymentWebhookEventId, existing.Status != WEBHOOK_RECEIVED


def _stored_response_data(payload: dict[str, Any]) -> dict[str, Any]:
    """Thông tin giao dịch lưu vào PaymentTransactions/đối soát: không gồm tên/nội dung chuyển khoản."""
    return SePayWebhookPayload.model_validate(payload).stored_response_data()
