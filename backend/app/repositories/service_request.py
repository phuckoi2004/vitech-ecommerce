"""Repositories cho WarrantyRequests, ReturnRequests, ServiceRequestAttachments, ServiceRequestHistories.

Không quyết định điều kiện bảo hành, duyệt đổi trả, bàn giao hay chuyển trạng thái (thuộc Service).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import ReturnRequest, ServiceRequestAttachment, ServiceRequestHistory, WarrantyRequest

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
    model = ServiceRequestHistory

    def list_by_warranty_request(self, warranty_request_id: uuid.UUID) -> list[ServiceRequestHistory]:
        return self.get_all(
            ServiceRequestHistory.WarrantyRequestId == warranty_request_id,
            order_by=(ServiceRequestHistory.ChangedAt, ServiceRequestHistory.ServiceRequestHistoryId),
        )

    def list_by_return_request(self, return_request_id: uuid.UUID) -> list[ServiceRequestHistory]:
        return self.get_all(
            ServiceRequestHistory.ReturnRequestId == return_request_id,
            order_by=(ServiceRequestHistory.ChangedAt, ServiceRequestHistory.ServiceRequestHistoryId),
        )
