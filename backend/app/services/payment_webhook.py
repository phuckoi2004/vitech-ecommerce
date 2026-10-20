"""Payment webhook service: ghi nhận và xử lý giao dịch ngân hàng từ webhook SePay.

Không phải thao tác của người dùng (không nhận Actor): nguồn gửi đã được xác thực bằng HMAC trước khi gọi Service.
1. Lưu sự kiện bền vững (transaction riêng), idempotent theo (Provider, AccountNumber, ProviderTransactionId):
   SePay gửi lại cùng `id` → không lưu/xử lý lại. Hai lần gửi đồng thời: UNIQUE của database chặn bản ghi thứ hai.
2. Xử lý (transaction riêng, khóa sự kiện): chỉ tiền vào đúng tài khoản cấu hình (tài khoản thường: `accountNumber`;
   tài khoản ảo VA chính thức: `subAccount`); đối chiếu qua PaymentService.apply_bank_transfer (mã thanh toán + số
   tiền; không tự chọn đơn; không tự hoàn tiền). Mã lấy từ `code` của SePay; khi SePay gửi null, chỉ lấy mã đứng riêng
   đúng mẫu tiền tố + độ dài trong nội dung (find_payment_code).
Bước 2 lỗi: sự kiện giữ Received → caller trả lỗi để SePay gửi lại; ``process_unprocessed`` xử lý lại sau.
"""

import logging
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.sepay import SePaySettings, SePayWebhookPayload, find_payment_code
from app.models.payment_webhook import PROVIDER_SEPAY, WEBHOOK_IGNORED, WEBHOOK_PROCESSED, WEBHOOK_RECEIVED
from app.repositories import PaymentWebhookEventRepository

from .base import BaseService, utc_now
from .exceptions import BusinessRuleError, ConflictError, NotFoundError
from .internal_jobs import JobRun, run_job
from .payment import BankTransfer, PaymentService

TRANSFER_IN = "in"
logger = logging.getLogger(__name__)


class PaymentWebhookService(BaseService):
    def __init__(
        self,
        session: Session,
        *,
        account_number: str,
        main_account_number: str | None = None,
        payment_code_pattern: re.Pattern[str] | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(session, clock=clock)
        if not account_number:
            raise ValueError("Cần tài khoản nhận tiền đã cấu hình (SEPAY_ACCOUNT_NUMBER)")
        self.account_number = account_number.strip()
        self.main_account_number = (main_account_number or "").strip() or None
        self.payment_code_pattern = payment_code_pattern
        self.events = PaymentWebhookEventRepository(session)
        self.payments = PaymentService(session, gateway=None, clock=clock)

    @classmethod
    def from_settings(cls, session: Session, settings: SePaySettings) -> "PaymentWebhookService":
        return cls(session, account_number=settings.account_number, main_account_number=settings.main_account_number,
                   payment_code_pattern=settings.payment_code_pattern)

    def receive_sepay(self, payload: SePayWebhookPayload, raw: dict[str, Any]) -> str:
        """Ghi nhận rồi xử lý một webhook SePay đã xác thực. Trả kết quả (ví dụ paid, amount_mismatch, duplicate)."""
        if self.in_transaction():
            raise BusinessRuleError("Webhook phải là use case độc lập", code="webhook_requires_own_transaction")
        started = perf_counter()
        event_id, already_final = self._store_sepay_event(payload, raw)
        if already_final:
            logger.info("Sự kiện SePay id=%s đã được xử lý ở lần gửi trước; không xử lý lại", payload.id)
            return "duplicate"
        logger.info("Sự kiện SePay id=%s đã lưu bền vững, chờ xử lý (%s)", payload.id, _ms(started))
        return self.process_event(event_id)

    def process_event(self, event_id: uuid.UUID) -> str:
        """Xử lý một sự kiện đã lưu (khóa dòng; sự kiện đã xử lý thì bỏ qua — an toàn khi gọi lặp/đồng thời)."""
        started = perf_counter()
        with self.transaction():
            event = self.events.get_by_id_for_update(event_id)
            if event is None:
                raise NotFoundError("Không tìm thấy sự kiện webhook", code="webhook_event_not_found")
            sepay_id = event.ProviderTransactionId
            if event.Status != WEBHOOK_RECEIVED:
                logger.info("Sự kiện SePay id=%s đã %s ở nơi khác; bỏ qua", sepay_id, event.Status)
                return "duplicate"
            if event.TransferType != TRANSFER_IN:
                status, outcome, transaction_id = WEBHOOK_IGNORED, "ignored_transfer_out", None
            elif not self._received_by_configured_account(event):
                logger.info("Sự kiện SePay id=%s: tài khoản nhận không khớp cấu hình (accountNumber %s, subAccount %s)",
                            sepay_id, _masked(event.AccountNumber), _masked(_text(event.Payload, "subAccount")))
                status, outcome, transaction_id = WEBHOOK_IGNORED, "ignored_other_account", None
            else:
                code = event.PaymentCode
                source = "code của SePay" if code else "nội dung chuyển khoản"
                code = code or find_payment_code(_text(event.Payload, "content"), self.payment_code_pattern)
                logger.info("Sự kiện SePay id=%s: tài khoản nhận khớp; mã thanh toán %s (%s); đối chiếu mã và số tiền %s",
                            sepay_id, _masked(code), source if code else "không tìm thấy", event.TransferAmount)
                outcome, transaction_id = self.payments.apply_bank_transfer(
                    BankTransfer(
                        reconciliation_key=f"sepay:{event.AccountNumber}:{event.ProviderTransactionId}",
                        payment_code=code,
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
        # Here the use case's transaction is committed (or, inside an internal job, handed back to the job).
        logger.info("Sự kiện SePay id=%s: %s; %s (giao dịch thanh toán %s, %s)", sepay_id, outcome,
                    "đã commit vào database" if not self.in_transaction() else "chờ tác vụ commit",
                    str(transaction_id)[:8] if transaction_id else "không có", _ms(started))
        return outcome

    def process_unprocessed(self, *, older_than: timedelta = timedelta(minutes=5), limit: int = 100) -> JobRun:
        """Xử lý lại các sự kiện còn Received (đã lưu nhưng xử lý lỗi). Dành cho tác vụ nội bộ.

        Tối đa ``limit`` sự kiện nhận trước ``older_than``, cũ nhất trước; mỗi sự kiện một transaction (``run_job``).
        Sự kiện đã được xử lý ở nơi khác (SePay gửi lại) được bỏ qua. Sự kiện lỗi được rollback, ghi log, đếm vào
        ``failed`` và giữ nguyên Received để lần chạy sau thử lại; các sự kiện sau vẫn được xử lý.
        """
        if self.in_transaction():
            raise BusinessRuleError("Tác vụ phải là use case độc lập", code="webhook_requires_own_transaction")
        return run_job(
            self,
            "process_unprocessed_webhooks",
            select=lambda: self.events.list_unprocessed_ids(received_before=self.now() - older_than, limit=limit),
            handle=lambda event_id: self.process_event(event_id) != "duplicate",
        )

    def _received_by_configured_account(self, event) -> bool:
        """Tiền vào đúng tài khoản nhận đã cấu hình (SEPAY_ACCOUNT_NUMBER, là `acc` của QR).

        Tài khoản thường: `accountNumber` là tài khoản đó. Tài khoản ảo (VA) chính thức, bắt buộc với MSB: khách chuyển
        vào số VA và SePay gửi số VA trong `subAccount` ("the VA number the customer transferred to"), còn
        `accountNumber` là tài khoản ngân hàng; khi có SEPAY_MAIN_ACCOUNT_NUMBER thì `accountNumber` phải là tài khoản đó.
        """
        if event.AccountNumber == self.account_number:
            return True
        return _text(event.Payload, "subAccount") == self.account_number and (
            self.main_account_number is None or event.AccountNumber == self.main_account_number
        )

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


def _ms(started: float) -> str:
    return f"{(perf_counter() - started) * 1000:.0f} ms"


def _masked(value: str | None) -> str:
    """Số tài khoản / mã thanh toán trong log: chỉ 4 ký tự cuối."""
    return f"…{value[-4:]}" if value else "(không có)"


def _text(payload: dict[str, Any] | None, key: str) -> str | None:
    """Giá trị chuỗi đã trim của payload SePay đã lưu; rỗng hoặc không phải chuỗi thì None."""
    value = (payload or {}).get(key)
    return (value.strip() or None) if isinstance(value, str) else None
