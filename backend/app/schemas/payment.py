"""Schemas cho PaymentMethods, PaymentTransactions.

PaymentTransactions do server/cổng thanh toán tạo; client chỉ đọc.
ResponseData (phản hồi thô từ cổng thanh toán) chỉ có trong schema admin.
"""

import uuid
from datetime import datetime
from typing import Any

from .common import Money, PaymentTransactionStatus, RequestSchema, ResponseSchema, varchar

# ---------------------------------------------------------------------------
# PaymentMethods
# ---------------------------------------------------------------------------


class PaymentMethodCreate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Description"})

    Code: varchar(50)
    Name: varchar(255)
    Description: str | None = None
    IsActive: bool | None = None
    DisplayOrder: int | None = None


class PaymentMethodUpdate(RequestSchema):
    NULLABLE_FIELDS = frozenset({"Description"})

    Code: varchar(50) | None = None
    Name: varchar(255) | None = None
    Description: str | None = None
    IsActive: bool | None = None
    DisplayOrder: int | None = None


class PaymentMethodResponse(ResponseSchema):
    PaymentMethodId: uuid.UUID
    Code: str
    Name: str
    Description: str | None
    IsActive: bool
    DisplayOrder: int


# ---------------------------------------------------------------------------
# PaymentTransactions
# ---------------------------------------------------------------------------


class PaymentTransactionResponse(ResponseSchema):
    """Dành cho khách hàng (ví dụ hiển thị QR thanh toán)."""

    PaymentTransactionId: uuid.UUID
    OrderId: uuid.UUID
    PaymentMethodId: uuid.UUID
    TransactionType: str
    Amount: Money
    Status: PaymentTransactionStatus
    QrData: str | None
    PaidAt: datetime | None
    CreatedAt: datetime


class AdminPaymentTransactionResponse(PaymentTransactionResponse):
    GatewayTransactionCode: str | None
    ResponseData: dict[str, Any] | None
