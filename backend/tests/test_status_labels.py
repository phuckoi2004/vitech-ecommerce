"""Presentation translations keep workflow codes and stored legacy notices intact."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import get_args

import pytest

from app.core.status_labels import (
    ORDER_STATUS_LABELS, PAYMENT_STATUS_LABELS, PURCHASE_STATUS_LABELS,
    RETURN_STATUS_LABELS, TRANSACTION_STATUS_LABELS, WARRANTY_STATUS_LABELS,
    notification_content,
)
from app.schemas.common import (
    OrderStatusValue, PaymentStatusValue, PaymentTransactionStatus,
    PurchaseOrderStatus, ReturnRequestStatus, WarrantyRequestStatus,
)
from app.schemas.order import OrderStatusUpdate
from app.schemas.user import NotificationResponse


@pytest.mark.parametrize("schema,labels", [
    (OrderStatusValue, ORDER_STATUS_LABELS), (PaymentStatusValue, PAYMENT_STATUS_LABELS),
    (PaymentTransactionStatus, TRANSACTION_STATUS_LABELS), (PurchaseOrderStatus, PURCHASE_STATUS_LABELS),
    (ReturnRequestStatus, RETURN_STATUS_LABELS), (WarrantyRequestStatus, WARRANTY_STATUS_LABELS),
])
def test_every_supported_workflow_status_has_a_vietnamese_label(schema, labels):
    assert set(get_args(schema)) == set(labels)
    assert all(label and label != code for code, label in labels.items())


@pytest.mark.parametrize("status,label", [("Shipping", "Đang giao"), ("Delivered", "Đã giao"), ("Completed", "Hoàn tất")])
def test_legacy_notification_json_is_localized_without_rewriting_source(status, label):
    source = SimpleNamespace(
        NotificationId=uuid.uuid4(), Title="Cập nhật đơn hàng",
        Content=f"Đơn hàng DH001 chuyển sang trạng thái {status}.",
        NotificationType="Order", ReferenceType="Order", ReferenceId=uuid.uuid4(),
        ActionUrl=None, IsRead=False, ReadAt=None, CreatedAt=datetime.now(timezone.utc),
    )
    response = NotificationResponse.model_validate(source)
    dumped = response.model_dump(mode="json")
    assert dumped["Content"] == f"Đơn hàng DH001 chuyển sang trạng thái {label}."
    assert source.Content == f"Đơn hàng DH001 chuyển sang trạng thái {status}."
    assert source.IsRead is False
    assert dumped["ReferenceId"] == str(source.ReferenceId)
    assert OrderStatusUpdate(OrderStatus=status).model_dump()["OrderStatus"] == status


@pytest.mark.parametrize("text,kind,reference", [
    ("Ghi chú của khách: Pending", "Order", "Order"),
    ("Đơn hàng DH001 chuyển sang trạng thái Pending.", "Chat", "Conversation"),
    ("Đơn hàng DH001 chuyển sang trạng thái Pending.", "Order", "ReturnRequest"),
    ("Đơn hàng DH001 chuyển sang trạng thái Đã giao.", "Order", "Order"),
])
def test_only_the_known_order_system_template_is_translated(text, kind, reference):
    assert notification_content(text, kind, reference) == text
