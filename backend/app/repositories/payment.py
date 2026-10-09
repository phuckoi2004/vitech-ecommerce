"""Repositories cho PaymentMethods, PaymentTransactions. Không gọi cổng thanh toán."""

import uuid

from app.models import PaymentMethod, PaymentTransaction

from .base import BaseRepository


class PaymentMethodRepository(BaseRepository[PaymentMethod]):
    model = PaymentMethod

    def get_by_code(self, code: str) -> PaymentMethod | None:
        return self.get_one(PaymentMethod.Code == code)

    def exists_by_code(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [PaymentMethod.Code == code]
        if exclude_id is not None:
            conditions.append(PaymentMethod.PaymentMethodId != exclude_id)
        return self.exists(*conditions)

    def list_methods(self, *, is_active: bool | None = None) -> list[PaymentMethod]:
        conditions = [] if is_active is None else [PaymentMethod.IsActive.is_(is_active)]
        return self.get_all(*conditions, order_by=(PaymentMethod.DisplayOrder, PaymentMethod.Name))


class PaymentTransactionRepository(BaseRepository[PaymentTransaction]):
    model = PaymentTransaction

    def list_by_order(self, order_id: uuid.UUID, *, status: str | None = None) -> list[PaymentTransaction]:
        conditions = [PaymentTransaction.OrderId == order_id]
        if status is not None:
            conditions.append(PaymentTransaction.Status == status)
        return self.get_all(
            *conditions, order_by=(PaymentTransaction.CreatedAt, PaymentTransaction.PaymentTransactionId)
        )

    def list_by_gateway_code(self, gateway_transaction_code: str) -> list[PaymentTransaction]:
        """GatewayTransactionCode không có UNIQUE trong schema nên trả về danh sách."""
        return self.get_all(PaymentTransaction.GatewayTransactionCode == gateway_transaction_code)

    def _filters(self, status: str | None, payment_method_id: uuid.UUID | None, transaction_type: str | None) -> list:
        conditions = []
        if status is not None:
            conditions.append(PaymentTransaction.Status == status)
        if payment_method_id is not None:
            conditions.append(PaymentTransaction.PaymentMethodId == payment_method_id)
        if transaction_type is not None:
            conditions.append(PaymentTransaction.TransactionType == transaction_type)
        return conditions

    def list_transactions(
        self,
        *,
        status: str | None = None,
        payment_method_id: uuid.UUID | None = None,
        transaction_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[PaymentTransaction]:
        return self.get_all(
            *self._filters(status, payment_method_id, transaction_type),
            order_by=(PaymentTransaction.CreatedAt.desc(), PaymentTransaction.PaymentTransactionId),
            offset=offset,
            limit=limit,
        )

    def count_transactions(
        self,
        *,
        status: str | None = None,
        payment_method_id: uuid.UUID | None = None,
        transaction_type: str | None = None,
    ) -> int:
        return self.count(*self._filters(status, payment_method_id, transaction_type))
