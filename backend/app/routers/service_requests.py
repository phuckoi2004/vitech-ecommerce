"""Service request APIs: warranty and return/exchange requests.

Customers create, follow and cancel their own requests; Staff/Admin process them under ``/admin``.
Active Staff/Admin workflow: forward-only status updates and direct warranty result publication.
Legacy repair-centre, independent review and return finance endpoints are paused for consultation.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.schemas import (
    AdminReturnRequestDetailResponse,
    AdminReturnRequestResponse,
    AdminWarrantyRequestDetailResponse,
    AdminWarrantyRequestResponse,
    PageResponse,
    ReturnApproval,
    ReturnGoodsReceive,
    ReturnInspection,
    ReturnRefundCreate,
    ReturnRequestCreate,
    ReturnRequestDetailResponse,
    ReturnRequestResponse,
    ServiceRequestNote,
    ServiceRequestRejection,
    WarrantyCompletion,
    WarrantyEligibilityUpdate,
    WarrantyHandoverCreate,
    WarrantyRequestCreate,
    WarrantyRequestDetailResponse,
    WarrantyRequestResponse,
    WarrantyResultProposal,
    WarrantyResultRejection,
)
from app.services.returns import ReturnService
from app.services.warranty import WarrantyService
from app.schemas.service_request import ReturnProgressRequest, WarrantyProgressRequest
from app.services import BusinessRuleError

from .dependencies import (
    CurrentActor,
    InternalOnly,
    Page,
    PageSize,
    get_return_service,
    get_warranty_service,
)

router = APIRouter(tags=["Bảo hành và đổi trả"])
admin_router = APIRouter(prefix="/admin", tags=["Xử lý bảo hành và đổi trả"], dependencies=[InternalOnly])

Warranty = Annotated[WarrantyService, Depends(get_warranty_service)]
Returns = Annotated[ReturnService, Depends(get_return_service)]
StatusFilter = Annotated[str | None, Query(alias="status")]


# ------------------------------------------------------------------ warranty (customer)


@router.post("/warranty-requests", response_model=WarrantyRequestDetailResponse, status_code=status.HTTP_201_CREATED)
def create_warranty_request(data: WarrantyRequestCreate, service: Warranty, actor: CurrentActor):
    return service.create_warranty_request(actor, data)


@router.get("/warranty-requests", response_model=PageResponse[WarrantyRequestResponse])
def list_my_warranty_requests(service: Warranty, actor: CurrentActor, status_filter: StatusFilter = None,
                              page: Page = 1, page_size: PageSize = 20):
    return service.list_my_warranty_requests(actor, status=status_filter, page=page, page_size=page_size)


@router.get("/warranty-requests/{request_id}", response_model=WarrantyRequestDetailResponse)
def get_my_warranty_request(request_id: uuid.UUID, service: Warranty, actor: CurrentActor):
    return service.get_my_warranty_request(actor, request_id)


@router.post("/warranty-requests/{request_id}/cancel", response_model=WarrantyRequestDetailResponse)
def cancel_warranty_request(request_id: uuid.UUID, service: Warranty, actor: CurrentActor,
                            data: ServiceRequestNote | None = None):
    return service.cancel_warranty_request(actor, request_id, data)


# ------------------------------------------------------------------ warranty (Staff/Admin)


def paused_service_workflow():
    # TODO: restore the former repair-centre/independent-approval/return-finance
    # workflows only after business consultation. Retain the service implementations
    # and stored financial evidence; no active HTTP endpoint may trigger them.
    raise BusinessRuleError("Luồng xử lý cũ đang tạm dừng; dùng chuyển giai đoạn của phiếu", code="service_workflow_paused")


@admin_router.post("/warranty-requests/{request_id}/advance", response_model=AdminWarrantyRequestDetailResponse)
def advance_warranty(request_id: uuid.UUID, data: WarrantyProgressRequest, service: Warranty, actor: CurrentActor):
    return service.advance_status(actor, request_id, data)


@admin_router.post("/return-requests/{request_id}/advance", response_model=AdminReturnRequestDetailResponse)
def advance_return(request_id: uuid.UUID, data: ReturnProgressRequest, service: Returns, actor: CurrentActor):
    return service.advance_status(actor, request_id, data.ExpectedStatus)


@admin_router.get("/warranty-requests", response_model=PageResponse[AdminWarrantyRequestResponse])
def list_warranty_requests(service: Warranty, actor: CurrentActor, status_filter: StatusFilter = None,
                           eligibility_status: str | None = None, customer_id: uuid.UUID | None = None,
                           assigned_staff_id: uuid.UUID | None = None, supplier_id: uuid.UUID | None = None,
                           page: Page = 1, page_size: PageSize = 20):
    return service.list_warranty_requests(actor, status=status_filter, eligibility_status=eligibility_status,
                                          customer_id=customer_id, assigned_staff_id=assigned_staff_id,
                                          supplier_id=supplier_id, page=page, page_size=page_size)


@admin_router.get("/warranty-requests/{request_id}", response_model=AdminWarrantyRequestDetailResponse)
def get_warranty_request(request_id: uuid.UUID, service: Warranty, actor: CurrentActor):
    return service.get_warranty_request(actor, request_id)


@admin_router.post("/warranty-requests/{request_id}/receive", response_model=AdminWarrantyRequestDetailResponse)
def receive_warranty_request(request_id: uuid.UUID, service: Warranty, actor: CurrentActor,
                             data: ServiceRequestNote | None = None):
    return service.advance_status(actor, request_id, WarrantyProgressRequest(ExpectedStage="New"))


@admin_router.post("/warranty-requests/{request_id}/inspect", response_model=AdminWarrantyRequestDetailResponse)
def inspect_warranty_request(request_id: uuid.UUID, data: WarrantyEligibilityUpdate, service: Warranty,
                             actor: CurrentActor):
    return paused_service_workflow()


@admin_router.post("/warranty-requests/{request_id}/hand-over", response_model=AdminWarrantyRequestDetailResponse)
def hand_over_warranty_request(request_id: uuid.UUID, data: WarrantyHandoverCreate, service: Warranty,
                               actor: CurrentActor):
    return paused_service_workflow()


@admin_router.post("/warranty-requests/{request_id}/start-processing",
                   response_model=AdminWarrantyRequestDetailResponse)
def start_warranty_processing(request_id: uuid.UUID, service: Warranty, actor: CurrentActor,
                              data: ServiceRequestNote | None = None):
    return paused_service_workflow()


@admin_router.post("/warranty-requests/{request_id}/propose-result",
                   response_model=AdminWarrantyRequestDetailResponse)
def propose_warranty_result(request_id: uuid.UUID, data: WarrantyResultProposal, service: Warranty,
                            actor: CurrentActor):
    return paused_service_workflow()


@admin_router.post("/warranty-requests/{request_id}/approve-result",
                   response_model=AdminWarrantyRequestDetailResponse)
def approve_warranty_result(request_id: uuid.UUID, service: Warranty, actor: CurrentActor,
                            data: ServiceRequestNote | None = None):
    return paused_service_workflow()


@admin_router.post("/warranty-requests/{request_id}/reject-result",
                   response_model=AdminWarrantyRequestDetailResponse)
def reject_warranty_result(request_id: uuid.UUID, data: WarrantyResultRejection, service: Warranty,
                           actor: CurrentActor):
    return paused_service_workflow()


@admin_router.post("/warranty-requests/{request_id}/reject", response_model=AdminWarrantyRequestDetailResponse)
def reject_warranty_request(request_id: uuid.UUID, data: ServiceRequestRejection, service: Warranty,
                            actor: CurrentActor):
    return service.reject_status(actor, request_id, data)


@admin_router.post("/warranty-requests/{request_id}/complete", response_model=AdminWarrantyRequestDetailResponse)
def complete_warranty_request(request_id: uuid.UUID, service: Warranty, actor: CurrentActor,
                              data: WarrantyCompletion | None = None):
    return paused_service_workflow()


# ------------------------------------------------------------------ returns (customer)


@router.post("/return-requests", response_model=ReturnRequestDetailResponse, status_code=status.HTTP_201_CREATED)
def create_return_request(data: ReturnRequestCreate, service: Returns, actor: CurrentActor):
    return service.create_return_request(actor, data)


@router.get("/return-requests", response_model=PageResponse[ReturnRequestResponse])
def list_my_return_requests(service: Returns, actor: CurrentActor, status_filter: StatusFilter = None,
                            page: Page = 1, page_size: PageSize = 20):
    return service.list_my_return_requests(actor, status=status_filter, page=page, page_size=page_size)


@router.get("/return-requests/{request_id}", response_model=ReturnRequestDetailResponse)
def get_my_return_request(request_id: uuid.UUID, service: Returns, actor: CurrentActor):
    return service.get_my_return_request(actor, request_id)


@router.post("/return-requests/{request_id}/cancel", response_model=ReturnRequestDetailResponse)
def cancel_return_request(request_id: uuid.UUID, service: Returns, actor: CurrentActor,
                          data: ServiceRequestNote | None = None):
    return service.cancel_return_request(actor, request_id, data)


# ------------------------------------------------------------------ returns (Staff/Admin)


@admin_router.get("/return-requests", response_model=PageResponse[AdminReturnRequestResponse])
def list_return_requests(service: Returns, actor: CurrentActor, status_filter: StatusFilter = None,
                         request_type: str | None = None, customer_id: uuid.UUID | None = None,
                         assigned_staff_id: uuid.UUID | None = None, pending_first: bool = False,
                         page: Page = 1, page_size: PageSize = 20):
    return service.list_return_requests(actor, status=status_filter, request_type=request_type,
                                        customer_id=customer_id, assigned_staff_id=assigned_staff_id,
                                        pending_first=pending_first, page=page, page_size=page_size)


@admin_router.get("/return-requests/{request_id}", response_model=AdminReturnRequestDetailResponse)
def get_return_request(request_id: uuid.UUID, service: Returns, actor: CurrentActor):
    return service.get_return_request(actor, request_id)


@admin_router.post("/return-requests/{request_id}/accept", response_model=AdminReturnRequestDetailResponse)
def accept_return_request(request_id: uuid.UUID, service: Returns, actor: CurrentActor,
                          data: ServiceRequestNote | None = None):
    return service.advance_status(actor, request_id, "Pending")


@admin_router.post("/return-requests/{request_id}/reject", response_model=AdminReturnRequestDetailResponse)
def reject_return_request(request_id: uuid.UUID, data: ServiceRequestRejection, service: Returns,
                          actor: CurrentActor):
    return service.reject_status(actor, request_id, data)


@admin_router.post("/return-requests/{request_id}/start-receiving", response_model=AdminReturnRequestDetailResponse)
def start_return_receiving(request_id: uuid.UUID, service: Returns, actor: CurrentActor,
                           data: ServiceRequestNote | None = None):
    return service.advance_status(actor, request_id, "Approved")


@admin_router.post("/return-requests/{request_id}/receive", response_model=AdminReturnRequestDetailResponse)
def receive_return_goods(request_id: uuid.UUID, data: ReturnGoodsReceive, service: Returns, actor: CurrentActor):
    return service.advance_status(actor, request_id, "Receiving")


@admin_router.post("/return-requests/{request_id}/inspect", response_model=AdminReturnRequestDetailResponse)
def inspect_return_goods(request_id: uuid.UUID, data: ReturnInspection, service: Returns, actor: CurrentActor):
    return paused_service_workflow()


@admin_router.post("/return-requests/{request_id}/approve", response_model=AdminReturnRequestDetailResponse)
def approve_return_request(request_id: uuid.UUID, data: ReturnApproval, service: Returns, actor: CurrentActor):
    return paused_service_workflow()


@admin_router.post("/return-requests/{request_id}/refund", response_model=AdminReturnRequestDetailResponse)
def refund_return_request(request_id: uuid.UUID, service: Returns, actor: CurrentActor,
                          data: ReturnRefundCreate | None = None):
    return paused_service_workflow()


@admin_router.post("/return-requests/{request_id}/confirm-refund", response_model=AdminReturnRequestDetailResponse)
def confirm_return_refund(request_id: uuid.UUID, service: Returns, actor: CurrentActor):
    return paused_service_workflow()
