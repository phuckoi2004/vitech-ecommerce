"""Repositories cho WarrantyRequests, ReturnRequests, ServiceRequestAttachments, ServiceRequestHistories.

Không quyết định điều kiện bảo hành, duyệt đổi trả, bàn giao hay chuyển trạng thái (thuộc Service).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import OrderItem, ReturnRequest, ServiceRequestAttachment, ServiceRequestHistory, WarrantyRequest
from app.models.service_request import RETURN_OPEN_STATUSES, WARRANTY_OPEN_STATUSES

from .base import BaseRepository


class WarrantyRequestRepository(BaseRepository[WarrantyRequest]):
    model = WarrantyRequest

    def get_by_code(self, request_code: str) -> WarrantyRequest | None:
        return self.get_one(WarrantyRequest.RequestCode == request_code)

    def exists_by_code(self, request_code: str) -> bool:
        return self.exists(WarrantyRequest.RequestCode == request_code)

    def get_by_id_and_customer(self, warranty_request_id: uuid.UUID, customer_id: uuid.UUID) -> WarrantyRequest | None:
        return self.get_one(
            WarrantyRequest.WarrantyRequestId == warranty_request_id, WarrantyRequest.CustomerId == customer_id
        )

    def get_detail(self, warranty_request_id: uuid.UUID) -> WarrantyRequest | None:
        """WarrantyRequest kèm Attachments và Histories."""
        stmt = (
            select(WarrantyRequest)
            .where(WarrantyRequest.WarrantyRequestId == warranty_request_id)
            .options(selectinload(WarrantyRequest.attachments), selectinload(WarrantyRequest.histories))
        )
        return self.session.scalars(stmt).one_or_none()

    def list_by_order_item(self, order_item_id: uuid.UUID) -> list[WarrantyRequest]:
        return self.get_all(
            WarrantyRequest.OrderItemId == order_item_id,
            order_by=(WarrantyRequest.RequestedAt.desc(), WarrantyRequest.WarrantyRequestId),
        )

    def list_by_product_serial(self, product_serial_id: uuid.UUID) -> list[WarrantyRequest]:
        return self.get_all(
            WarrantyRequest.ProductSerialId == product_serial_id,
            order_by=(WarrantyRequest.RequestedAt.desc(), WarrantyRequest.WarrantyRequestId),
        )

    def get_open_by_product_serial(self, product_serial_id: uuid.UUID) -> WarrantyRequest | None:
        """Yêu cầu đang xử lý (New/HandedOver/Processing) của serial; tối đa một (UX_WarrantyRequests_Serial_Open)."""
        return self.get_one(
            WarrantyRequest.ProductSerialId == product_serial_id,
            WarrantyRequest.Status.in_(WARRANTY_OPEN_STATUSES),
        )

    def get_open_by_order_item_without_serial(self, order_item_id: uuid.UUID) -> WarrantyRequest | None:
        """Yêu cầu đang xử lý của dòng đơn không quản lý serial (UX_WarrantyRequests_OrderItem_Open_NoSerial)."""
        return self.get_one(
            WarrantyRequest.OrderItemId == order_item_id,
            WarrantyRequest.ProductSerialId.is_(None),
            WarrantyRequest.Status.in_(WARRANTY_OPEN_STATUSES),
        )

    def get_latest_replacement_handover(self, product_serial_id: uuid.UUID) -> WarrantyRequest | None:
        """Yêu cầu gần nhất đã bàn giao serial này cho khách làm máy thay thế (ReplacementHandedOverAt có giá trị)."""
        stmt = (
            select(WarrantyRequest)
            .where(
                WarrantyRequest.ReplacementProductSerialId == product_serial_id,
                WarrantyRequest.ReplacementHandedOverAt.is_not(None),
            )
            .order_by(WarrantyRequest.ReplacementHandedOverAt.desc(), WarrantyRequest.WarrantyRequestId)
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def _filters(
        self,
        customer_id: uuid.UUID | None,
        assigned_staff_id: uuid.UUID | None,
        supplier_id: uuid.UUID | None,
        status: str | None,
        eligibility_status: str | None,
    ) -> list:
        conditions = []
        if customer_id is not None:
            conditions.append(WarrantyRequest.CustomerId == customer_id)
        if assigned_staff_id is not None:
            conditions.append(WarrantyRequest.AssignedStaffId == assigned_staff_id)
        if supplier_id is not None:
            conditions.append(WarrantyRequest.SupplierId == supplier_id)
        if status is not None:
            conditions.append(WarrantyRequest.Status == status)
        if eligibility_status is not None:
            conditions.append(WarrantyRequest.EligibilityStatus == eligibility_status)
        return conditions

    def list_requests(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
        status: str | None = None,
        eligibility_status: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[WarrantyRequest]:
        return self.get_all(
            *self._filters(customer_id, assigned_staff_id, supplier_id, status, eligibility_status),
            order_by=(WarrantyRequest.RequestedAt.desc(), WarrantyRequest.WarrantyRequestId),
            offset=offset,
            limit=limit,
        )

    def count_requests(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
        status: str | None = None,
        eligibility_status: str | None = None,
    ) -> int:
        return self.count(*self._filters(customer_id, assigned_staff_id, supplier_id, status, eligibility_status))


class ReturnRequestRepository(BaseRepository[ReturnRequest]):
    model = ReturnRequest

    def get_by_code(self, request_code: str) -> ReturnRequest | None:
        return self.get_one(ReturnRequest.RequestCode == request_code)

    def exists_by_code(self, request_code: str) -> bool:
        return self.exists(ReturnRequest.RequestCode == request_code)

    def get_by_id_and_customer(self, return_request_id: uuid.UUID, customer_id: uuid.UUID) -> ReturnRequest | None:
        return self.get_one(ReturnRequest.ReturnRequestId == return_request_id, ReturnRequest.CustomerId == customer_id)

    def get_detail(self, return_request_id: uuid.UUID) -> ReturnRequest | None:
        """ReturnRequest kèm Attachments và Histories."""
        stmt = (
            select(ReturnRequest)
            .where(ReturnRequest.ReturnRequestId == return_request_id)
            .options(selectinload(ReturnRequest.attachments), selectinload(ReturnRequest.histories))
        )
        return self.session.scalars(stmt).one_or_none()

    def list_by_order_item(self, order_item_id: uuid.UUID) -> list[ReturnRequest]:
        return self.get_all(
            ReturnRequest.OrderItemId == order_item_id,
            order_by=(ReturnRequest.RequestedAt.desc(), ReturnRequest.ReturnRequestId),
        )

    def list_refund_transaction_ids_for_order(self, order_id: uuid.UUID) -> set[uuid.UUID]:
        """Giao dịch Refund đang liên kết với yêu cầu trả hàng của các dòng thuộc đơn (RefundPaymentTransactionId)."""
        stmt = (
            select(ReturnRequest.RefundPaymentTransactionId)
            .join(OrderItem, OrderItem.OrderItemId == ReturnRequest.OrderItemId)
            .where(OrderItem.OrderId == order_id, ReturnRequest.RefundPaymentTransactionId.is_not(None))
        )
        return set(self.session.scalars(stmt))

    def list_open_request_codes_for_order(self, order_id: uuid.UUID) -> list[str]:
        """Mã các yêu cầu đổi/trả đang xử lý (RETURN_OPEN_STATUSES) của các dòng thuộc đơn, theo RequestCode."""
        stmt = (
            select(ReturnRequest.RequestCode)
            .join(OrderItem, OrderItem.OrderItemId == ReturnRequest.OrderItemId)
            .where(OrderItem.OrderId == order_id, ReturnRequest.Status.in_(RETURN_OPEN_STATUSES))
            .order_by(ReturnRequest.RequestCode)
        )
        return list(self.session.scalars(stmt))

    def get_open_by_product_serial(self, product_serial_id: uuid.UUID) -> ReturnRequest | None:
        """Yêu cầu đổi/trả đang xử lý (Pending/Approved/Receiving/Processing) của serial (UX_ReturnRequests_Serial_Open)."""
        return self.get_one(
            ReturnRequest.ProductSerialId == product_serial_id,
            ReturnRequest.Status.in_(RETURN_OPEN_STATUSES),
        )

    def _filters(
        self,
        customer_id: uuid.UUID | None,
        assigned_staff_id: uuid.UUID | None,
        status: str | None,
        request_type: str | None,
    ) -> list:
        conditions = []
        if customer_id is not None:
            conditions.append(ReturnRequest.CustomerId == customer_id)
        if assigned_staff_id is not None:
            conditions.append(ReturnRequest.AssignedStaffId == assigned_staff_id)
        if status is not None:
            conditions.append(ReturnRequest.Status == status)
        if request_type is not None:
            conditions.append(ReturnRequest.RequestType == request_type)
        return conditions

    def list_requests(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        status: str | None = None,
        request_type: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[ReturnRequest]:
        return self.get_all(
            *self._filters(customer_id, assigned_staff_id, status, request_type),
            order_by=(ReturnRequest.RequestedAt.desc(), ReturnRequest.ReturnRequestId),
            offset=offset,
            limit=limit,
        )

    def count_requests(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        status: str | None = None,
        request_type: str | None = None,
    ) -> int:
        return self.count(*self._filters(customer_id, assigned_staff_id, status, request_type))


class ServiceRequestAttachmentRepository(BaseRepository[ServiceRequestAttachment]):
    model = ServiceRequestAttachment

    def list_by_warranty_request(self, warranty_request_id: uuid.UUID) -> list[ServiceRequestAttachment]:
        return self.get_all(
            ServiceRequestAttachment.WarrantyRequestId == warranty_request_id,
            order_by=(ServiceRequestAttachment.UploadedAt, ServiceRequestAttachment.ServiceRequestAttachmentId),
        )

    def list_by_return_request(self, return_request_id: uuid.UUID) -> list[ServiceRequestAttachment]:
        return self.get_all(
            ServiceRequestAttachment.ReturnRequestId == return_request_id,
            order_by=(ServiceRequestAttachment.UploadedAt, ServiceRequestAttachment.ServiceRequestAttachmentId),
        )


class ServiceRequestHistoryRepository(BaseRepository[ServiceRequestHistory]):
    """Lịch sử yêu cầu. Mặc định chỉ trả dòng công khai; ``include_internal=True`` chỉ dùng cho Staff/Admin."""

    model = ServiceRequestHistory

    def _list(self, condition, include_internal: bool) -> list[ServiceRequestHistory]:
        conditions = [condition] if include_internal else [condition, ServiceRequestHistory.IsInternal.is_(False)]
        return self.get_all(
            *conditions,
            order_by=(ServiceRequestHistory.ChangedAt, ServiceRequestHistory.ServiceRequestHistoryId),
        )

    def list_by_warranty_request(
        self, warranty_request_id: uuid.UUID, *, include_internal: bool = False
    ) -> list[ServiceRequestHistory]:
        return self._list(ServiceRequestHistory.WarrantyRequestId == warranty_request_id, include_internal)

    def list_by_return_request(
        self, return_request_id: uuid.UUID, *, include_internal: bool = False
    ) -> list[ServiceRequestHistory]:
        return self._list(ServiceRequestHistory.ReturnRequestId == return_request_id, include_internal)
