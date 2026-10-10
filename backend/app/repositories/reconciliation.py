"""Repository cho PaymentReconciliations (khoản thanh toán bất thường cần đối soát). Không xóa bản ghi."""

import uuid
from typing import NoReturn

from app.models import PaymentReconciliation

from .base import BaseRepository


class PaymentReconciliationRepository(BaseRepository[PaymentReconciliation]):
    model = PaymentReconciliation

    def get_by_key(self, gateway_transaction_code: str, issue_type: str) -> PaymentReconciliation | None:
        """Khóa idempotency: (GatewayTransactionCode, IssueType) — UNIQUE trong database."""
        return self.get_one(
            PaymentReconciliation.GatewayTransactionCode == gateway_transaction_code,
            PaymentReconciliation.IssueType == issue_type,
        )

    def _filters(self, status: str | None, issue_type: str | None, order_id: uuid.UUID | None) -> list:
        conditions = []
        if status is not None:
            conditions.append(PaymentReconciliation.Status == status)
        if issue_type is not None:
            conditions.append(PaymentReconciliation.IssueType == issue_type)
        if order_id is not None:
            conditions.append(PaymentReconciliation.OrderId == order_id)
        return conditions

    def list_reconciliations(
        self,
        *,
        status: str | None = None,
        issue_type: str | None = None,
        order_id: uuid.UUID | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[PaymentReconciliation]:
        return self.get_all(
            *self._filters(status, issue_type, order_id),
            order_by=(PaymentReconciliation.CreatedAt.desc(), PaymentReconciliation.PaymentReconciliationId),
            offset=offset,
            limit=limit,
        )

    def count_reconciliations(
        self, *, status: str | None = None, issue_type: str | None = None, order_id: uuid.UUID | None = None
    ) -> int:
        return self.count(*self._filters(status, issue_type, order_id))

    def delete(self, obj: PaymentReconciliation) -> NoReturn:
        raise PermissionError("PaymentReconciliations không được xóa; đóng bằng trạng thái Resolved")
