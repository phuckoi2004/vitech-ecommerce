"""Payment APIs: payment methods, QR payments, COD records, refunds and reconciliations.

QR payments become Paid only through the verified SePay webhook (``webhooks.py``); no endpoint here marks
a payment as paid. Amounts always come from the database, never from the client (except a partial refund
amount, which the Service validates against what was actually collected).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.schemas import (
    AdminOrderResponse,
    AdminPaymentTransactionResponse,
    OrderRefundCreate,
    PageResponse,
    PaymentMethodCreate,
    PaymentMethodResponse,
    PaymentMethodUpdate,
    PaymentReconciliationResolve,
    PaymentReconciliationResponse,
    PaymentTransactionResponse,
    QrPaymentResponse,
    RefundResolution,
    RefundSourceResponse,
)
from app.services.payment import PaymentService

from .dependencies import CurrentActor, InternalOnly, OptionalActor, Page, PageSize, get_payment_service

router = APIRouter(tags=["Thanh toán"])
admin_router = APIRouter(prefix="/admin", tags=["Quản lý thanh toán"], dependencies=[InternalOnly])

Payments = Annotated[PaymentService, Depends(get_payment_service)]


# ------------------------------------------------------------------ payment methods


@router.get("/payment-methods", response_model=list[PaymentMethodResponse])
def list_payment_methods(service: Payments, actor: OptionalActor, active_only: bool = True):
    return service.list_payment_methods(actor=actor, active_only=active_only)


@router.get("/payment-methods/{payment_method_id}", response_model=PaymentMethodResponse)
def get_payment_method(payment_method_id: uuid.UUID, service: Payments, actor: OptionalActor):
    return service.get_payment_method(payment_method_id, actor=actor)


@admin_router.post("/payment-methods", response_model=PaymentMethodResponse, status_code=status.HTTP_201_CREATED)
def create_payment_method(data: PaymentMethodCreate, service: Payments, actor: CurrentActor):
    return service.create_payment_method(actor, data)


@admin_router.patch("/payment-methods/{payment_method_id}", response_model=PaymentMethodResponse)
def update_payment_method(payment_method_id: uuid.UUID, data: PaymentMethodUpdate, service: Payments,
                          actor: CurrentActor):
    return service.update_payment_method(actor, payment_method_id, data)


@admin_router.delete("/payment-methods/{payment_method_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment_method(payment_method_id: uuid.UUID, service: Payments, actor: CurrentActor):
    service.delete_payment_method(actor, payment_method_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ customer payments


@router.post("/orders/{order_id}/payments/qr", response_model=QrPaymentResponse,
             status_code=status.HTTP_201_CREATED)
def create_qr_payment(order_id: uuid.UUID, service: Payments, actor: CurrentActor):
    """Pending QR payment with its transfer details (QR image, transfer content, bank account, amount, deadline)."""
    return service.create_qr_payment(actor, order_id)


@router.get("/orders/{order_id}/payments", response_model=list[PaymentTransactionResponse])
def list_my_order_payments(order_id: uuid.UUID, service: Payments, actor: CurrentActor):
    return service.list_order_transactions(actor, order_id)


@router.post("/payments/{payment_transaction_id}/cancel", response_model=PaymentTransactionResponse)
def cancel_qr_payment(payment_transaction_id: uuid.UUID, service: Payments, actor: CurrentActor):
    return service.cancel_qr_payment(actor, payment_transaction_id)


# ------------------------------------------------------------------ transactions (Staff/Admin)


@admin_router.get("/payment-transactions", response_model=PageResponse[AdminPaymentTransactionResponse])
def admin_list_transactions(service: Payments, actor: CurrentActor,
                            status_filter: Annotated[str | None, Query(alias="status")] = None,
                            payment_method_id: uuid.UUID | None = None, transaction_type: str | None = None,
                            page: Page = 1, page_size: PageSize = 20):
    return service.admin_list_transactions(actor, status=status_filter, payment_method_id=payment_method_id,
                                           transaction_type=transaction_type, page=page, page_size=page_size)


@admin_router.get("/orders/{order_id}/payments", response_model=list[AdminPaymentTransactionResponse])
def admin_list_order_payments(order_id: uuid.UUID, service: Payments, actor: CurrentActor):
    return service.admin_list_order_transactions(actor, order_id)


@admin_router.post("/orders/{order_id}/payments/cod", response_model=AdminPaymentTransactionResponse,
                   status_code=status.HTTP_201_CREATED)
def record_cod_payment(order_id: uuid.UUID, service: Payments, actor: CurrentActor):
    """Backfills the transaction of a legacy COD order already marked Paid (see OrderService.confirm_cod_delivery)."""
    return service.record_cod_payment(actor, order_id)


# ------------------------------------------------------------------ refunds (Staff/Admin)


@admin_router.get("/refunds/awaiting-orders", response_model=PageResponse[AdminOrderResponse])
def list_orders_awaiting_refund(service: Payments, actor: CurrentActor, page: Page = 1, page_size: PageSize = 20):
    return service.list_orders_awaiting_refund(actor, page=page, page_size=page_size)


@admin_router.get("/orders/{order_id}/refund-sources", response_model=list[RefundSourceResponse])
def list_refund_sources(order_id: uuid.UUID, service: Payments, actor: CurrentActor):
    return service.list_refund_sources(actor, order_id)


@admin_router.post("/orders/{order_id}/refunds", response_model=AdminPaymentTransactionResponse,
                   status_code=status.HTTP_201_CREATED)
def refund_order(order_id: uuid.UUID, data: OrderRefundCreate, service: Payments, actor: CurrentActor):
    return service.refund_order(actor, order_id, amount=data.Amount,
                                payment_transaction_id=data.PaymentTransactionId)


@admin_router.post("/refunds/{refund_transaction_id}/resolve", response_model=AdminPaymentTransactionResponse)
def resolve_pending_refund(refund_transaction_id: uuid.UUID, data: RefundResolution, service: Payments,
                           actor: CurrentActor):
    return service.resolve_pending_refund(actor, refund_transaction_id, data)


# ------------------------------------------------------------------ reconciliations (Staff/Admin)


@admin_router.get("/payment-reconciliations", response_model=PageResponse[PaymentReconciliationResponse])
def list_reconciliations(service: Payments, actor: CurrentActor,
                         status_filter: Annotated[str | None, Query(alias="status")] = None,
                         issue_type: str | None = None, order_id: uuid.UUID | None = None,
                         page: Page = 1, page_size: PageSize = 20):
    return service.list_reconciliations(actor, status=status_filter, issue_type=issue_type, order_id=order_id,
                                        page=page, page_size=page_size)


@admin_router.post("/payment-reconciliations/{reconciliation_id}/resolve",
                   response_model=PaymentReconciliationResponse)
def resolve_reconciliation(reconciliation_id: uuid.UUID, data: PaymentReconciliationResolve, service: Payments,
                           actor: CurrentActor):
    return service.resolve_reconciliation(actor, reconciliation_id, data)
