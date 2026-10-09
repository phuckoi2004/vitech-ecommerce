"""Schemas cho WarrantyRequests, ReturnRequests, ServiceRequestAttachments, ServiceRequestHistories.

WarrantyRequests:
- EligibilityStatus = kết quả kiểm tra điều kiện bảo hành (Pending, Eligible, Ineligible).
- Status = trạng thái xử lý yêu cầu (không có Approved).
"""

import uuid
from datetime import datetime

from pydantic import Field

from .common import (
    Money,
    RequestSchema,
    ResponseSchema,
    ReturnRequestStatus,
    WarrantyEligibilityStatus,
    WarrantyRequestStatus,
    relation_field,
    varchar,
)

# ---------------------------------------------------------------------------
# Attachments / Histories
# ---------------------------------------------------------------------------


class ServiceRequestAttachmentCreate(RequestSchema):
    """WarrantyRequestId / ReturnRequestId do server gán theo yêu cầu cha."""

    FileUrl: varchar(500)
    FileType: varchar(20)


class ServiceRequestAttachmentResponse(ResponseSchema):
    ServiceRequestAttachmentId: uuid.UUID
    FileUrl: str
    FileType: str
    UploadedAt: datetime


class ServiceRequestHistoryResponse(ResponseSchema):
    ServiceRequestHistoryId: uuid.UUID
    OldStatus: str | None
    NewStatus: str
    Note: str | None
    ChangedAt: datetime


class AdminServiceRequestHistoryResponse(ServiceRequestHistoryResponse):
    ChangedByUserId: uuid.UUID | None


# ---------------------------------------------------------------------------
# WarrantyRequests
# ---------------------------------------------------------------------------


class WarrantyRequestCreate(RequestSchema):
    """Khách hàng gửi yêu cầu bảo hành.

    RequestCode, EligibilityStatus, Status do server gán; CustomerId lấy từ người dùng đăng nhập.
    """

    NULLABLE_FIELDS = frozenset({"ProductSerialId"})

    OrderItemId: uuid.UUID
    ProductSerialId: uuid.UUID | None = None
    IssueDescription: str
    Attachments: list[ServiceRequestAttachmentCreate] = Field(default_factory=list)


class WarrantyEligibilityUpdate(RequestSchema):
    """Nhân viên ghi nhận kết quả kiểm tra điều kiện bảo hành."""

    NULLABLE_FIELDS = frozenset({"EligibilityReason"})

    EligibilityStatus: WarrantyEligibilityStatus
    EligibilityReason: str | None = None


class WarrantyRequestUpdate(RequestSchema):
    """Nhân viên cập nhật xử lý (PATCH). Các mốc thời gian do server gán theo trạng thái."""

    NULLABLE_FIELDS = frozenset(
        {"AssignedStaffId", "SupplierId", "HandoverCode", "ServiceCenter", "ResultType", "ResultNote", "Note"}
    )

    AssignedStaffId: uuid.UUID | None = None
    SupplierId: uuid.UUID | None = None
    Status: WarrantyRequestStatus | None = None
    HandoverCode: varchar(50) | None = None
    ServiceCenter: varchar(255) | None = None
    ResultType: varchar(30) | None = None
    ResultNote: str | None = None
    # Ghi chú cho ServiceRequestHistories khi đổi Status.
    Note: str | None = None


class WarrantyRequestResponse(ResponseSchema):
    """Dành cho khách hàng: không có AssignedStaffId, SupplierId."""

    WarrantyRequestId: uuid.UUID
    RequestCode: str
    OrderItemId: uuid.UUID
    ProductSerialId: uuid.UUID | None
    IssueDescription: str
    EligibilityStatus: WarrantyEligibilityStatus
    EligibilityReason: str | None
    Status: WarrantyRequestStatus
    ReceivedAt: datetime | None
    HandoverCode: str | None
    ServiceCenter: str | None
    HandedOverAt: datetime | None
    ResultType: str | None
    ResultNote: str | None
    RequestedAt: datetime
    CompletedAt: datetime | None


class WarrantyRequestDetailResponse(WarrantyRequestResponse):
    Attachments: list[ServiceRequestAttachmentResponse] = relation_field("attachments")
    Histories: list[ServiceRequestHistoryResponse] = relation_field("histories")


class AdminWarrantyRequestResponse(WarrantyRequestResponse):
    CustomerId: uuid.UUID
    AssignedStaffId: uuid.UUID | None
    SupplierId: uuid.UUID | None


class AdminWarrantyRequestDetailResponse(AdminWarrantyRequestResponse):
    Attachments: list[ServiceRequestAttachmentResponse] = relation_field("attachments")
    Histories: list[AdminServiceRequestHistoryResponse] = relation_field("histories")


# ---------------------------------------------------------------------------
# ReturnRequests
# ---------------------------------------------------------------------------


class ReturnRequestCreate(RequestSchema):
    """Khách hàng gửi yêu cầu đổi / trả. RequestCode, Status do server gán."""

    OrderItemId: uuid.UUID
    RequestType: varchar(20)
    Reason: str
    Attachments: list[ServiceRequestAttachmentCreate] = Field(default_factory=list)


class ReturnRequestUpdate(RequestSchema):
    """Nhân viên xử lý yêu cầu đổi / trả (PATCH). Các mốc thời gian do server gán."""

    NULLABLE_FIELDS = frozenset(
        {"AssignedStaffId", "DecisionReason", "DamageAssessment", "ResolutionType", "CompensationAmount", "Note"}
    )

    AssignedStaffId: uuid.UUID | None = None
    Status: ReturnRequestStatus | None = None
    DecisionReason: str | None = None
    DamageAssessment: str | None = None
    ResolutionType: varchar(30) | None = None
    CompensationAmount: Money | None = None
    # Ghi chú cho ServiceRequestHistories khi đổi Status.
    Note: str | None = None


class ReturnRequestResponse(ResponseSchema):
    """Dành cho khách hàng: không có AssignedStaffId."""

    ReturnRequestId: uuid.UUID
    RequestCode: str
    OrderItemId: uuid.UUID
    RequestType: str
    Reason: str
    Status: ReturnRequestStatus
    DecisionReason: str | None
    DamageAssessment: str | None
    ResolutionType: str | None
    CompensationAmount: Money | None
    RequestedAt: datetime
    ReceivedAt: datetime | None
    CompletedAt: datetime | None


class ReturnRequestDetailResponse(ReturnRequestResponse):
    Attachments: list[ServiceRequestAttachmentResponse] = relation_field("attachments")
    Histories: list[ServiceRequestHistoryResponse] = relation_field("histories")


class AdminReturnRequestResponse(ReturnRequestResponse):
    CustomerId: uuid.UUID
    AssignedStaffId: uuid.UUID | None


class AdminReturnRequestDetailResponse(AdminReturnRequestResponse):
    Attachments: list[ServiceRequestAttachmentResponse] = relation_field("attachments")
    Histories: list[AdminServiceRequestHistoryResponse] = relation_field("histories")
