"""Schemas cho WarrantyRequests, ReturnRequests, ServiceRequestAttachments, ServiceRequestHistories.

WarrantyRequests:
- EligibilityStatus = kết quả kiểm tra điều kiện bảo hành (Pending, Eligible, Ineligible).
- Status = trạng thái xử lý yêu cầu (không có Approved).
- Không có schema cập nhật tổng quát: mỗi bước (tiếp nhận, kiểm tra, bàn giao, đề xuất/duyệt kết quả, hoàn tất)
  có schema riêng, Status/mốc thời gian/người thực hiện do WarrantyService gán (đợt 5.4).

ReturnRequests (đợt 5.4): tương tự, mỗi bước của ReturnService có schema riêng; số tiền do server tính từ giá trị
lịch sử của dòng đơn (Admin chỉ xác nhận đúng số tiền đã tính, không nhập số tùy ý).

Ghi chú (đợt 5.4.1): ``Note`` là nội dung khách hàng được xem; ``InternalNote`` chỉ Staff/Admin xem. Schema dành cho
khách hàng chỉ trả lịch sử công khai (bỏ dòng IsInternal, không có InternalNote) và chỉ hiện kết quả bảo hành
(ResultType/ResultNote) khi đã được Admin duyệt. Tương tự (đợt 5.10): số tiền trả hàng hệ thống tính ở bước kiểm tra
(CompensationAmount) chỉ hiện cho khách khi Admin đã duyệt (CompensationApprovedAt).
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from .common import (
    AttachmentFileType,
    Money,
    NonBlankText,
    NonNegativeInt,
    PositiveInt,
    RequestSchema,
    ResponseSchema,
    ReturnRequestStatus,
    ReturnRequestType,
    SerialNumberValue,
    WarrantyEligibilityStatus,
    WarrantyRequestStatus,
    WarrantyResultType,
    relation_field,
    varchar,
)

# ---------------------------------------------------------------------------
# Attachments / Histories
# ---------------------------------------------------------------------------


class ServiceRequestAttachmentCreate(RequestSchema):
    """WarrantyRequestId / ReturnRequestId do server gán theo yêu cầu cha."""

    FileUrl: varchar(500)
    FileType: AttachmentFileType


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
    IsInternal: bool
    InternalNote: str | None


class ServiceRequestNote(RequestSchema):
    """Ghi chú tùy chọn cho một bước xử lý (lưu vào ServiceRequestHistories).

    Note: khách hàng xem được. InternalNote: chỉ Staff/Admin (khách hàng không được gửi trường này).
    """

    NULLABLE_FIELDS = frozenset({"Note", "InternalNote"})

    Note: str | None = None
    InternalNote: str | None = None


class ServiceRequestRejection(RequestSchema):
    """Từ chối yêu cầu: Reason bắt buộc, khách hàng xem được; InternalNote (kết luận chi tiết) chỉ Staff/Admin."""

    NULLABLE_FIELDS = frozenset({"InternalNote"})

    Reason: NonBlankText
    InternalNote: str | None = None


class WarrantyResultRejection(RequestSchema):
    """Admin từ chối đề xuất kết quả bảo hành (nội bộ, khách hàng không xem): lý do bắt buộc."""

    Reason: NonBlankText


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
    """Nhân viên ghi nhận kết quả kiểm tra thực tế sau khi tiếp nhận (Ineligible bắt buộc có lý do)."""

    NULLABLE_FIELDS = frozenset({"EligibilityReason", "InternalNote"})

    EligibilityStatus: Literal["Eligible", "Ineligible"]
    EligibilityReason: str | None = None
    InternalNote: str | None = None


class WarrantyHandoverCreate(RequestSchema):
    """Nhân viên bàn giao sản phẩm cho trung tâm bảo hành / nhà cung cấp."""

    NULLABLE_FIELDS = frozenset({"HandoverCode", "SupplierId", "Note", "InternalNote"})

    ServiceCenter: varchar(255)
    HandoverCode: varchar(50) | None = None
    SupplierId: uuid.UUID | None = None
    Note: str | None = None
    InternalNote: str | None = None


class WarrantyResultProposal(RequestSchema):
    """Nhân viên ghi nhận kết quả kiểm tra/xử lý và đề xuất kết quả (Admin khác người đề xuất duyệt).

    Đề xuất là nội bộ: khách hàng chỉ thấy ResultType/ResultNote sau khi được duyệt.
    """

    ResultType: WarrantyResultType
    ResultNote: NonBlankText


class WarrantyCompletion(RequestSchema):
    """Hoàn tất (trả máy cho khách). Đổi máy: serial máy thay thế bàn giao cho khách."""

    NULLABLE_FIELDS = frozenset({"ReplacementProductSerialId", "Note", "InternalNote"})

    ReplacementProductSerialId: uuid.UUID | None = None
    Note: str | None = None
    InternalNote: str | None = None


class _WarrantyRequestFields(ResponseSchema):
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
    ResultType: WarrantyResultType | None
    ResultNote: str | None
    RequestedAt: datetime
    CompletedAt: datetime | None
    ResultApprovedAt: datetime | None
    ReplacementProductSerialId: uuid.UUID | None
    ReplacementHandedOverAt: datetime | None


class WarrantyRequestResponse(_WarrantyRequestFields):
    """Dành cho khách hàng: không có AssignedStaffId, SupplierId, người đề xuất/duyệt.

    Kết quả đang chờ duyệt là nội bộ: ResultType/ResultNote chỉ hiển thị khi đã có ResultApprovedAt.
    """

    @model_validator(mode="after")
    def _hide_unapproved_result(self):
        if self.ResultApprovedAt is None:
            self.ResultType = None
            self.ResultNote = None
        return self


class WarrantyRequestDetailResponse(WarrantyRequestResponse):
    Attachments: list[ServiceRequestAttachmentResponse] = relation_field("attachments")
    # Chỉ lịch sử công khai (bỏ dòng nội bộ); schema không có InternalNote.
    Histories: list[ServiceRequestHistoryResponse] = relation_field("public_histories")


class AdminWarrantyRequestResponse(_WarrantyRequestFields):
    CustomerId: uuid.UUID
    AssignedStaffId: uuid.UUID | None
    SupplierId: uuid.UUID | None
    ResultProposedByUserId: uuid.UUID | None
    ResultProposedAt: datetime | None
    ResultApprovedByUserId: uuid.UUID | None
    ReplacementHandedOverByUserId: uuid.UUID | None


class AdminWarrantyRequestDetailResponse(AdminWarrantyRequestResponse):
    Attachments: list[ServiceRequestAttachmentResponse] = relation_field("attachments")
    Histories: list[AdminServiceRequestHistoryResponse] = relation_field("histories")


# ---------------------------------------------------------------------------
# ReturnRequests
# ---------------------------------------------------------------------------


class ReturnRequestCreate(RequestSchema):
    """Khách hàng gửi yêu cầu đổi / trả. RequestCode, Status, số tiền do server gán.

    Sản phẩm quản lý serial: ProductSerialId bắt buộc (serial thực tế đã mua), Quantity = 1.
    Sản phẩm không quản lý serial: ProductSerialId để trống, Quantity <= số còn có thể trả của dòng đơn.
    """

    NULLABLE_FIELDS = frozenset({"ProductSerialId"})

    OrderItemId: uuid.UUID
    RequestType: ReturnRequestType
    ProductSerialId: uuid.UUID | None = None
    Quantity: PositiveInt = 1
    Reason: str
    Attachments: list[ServiceRequestAttachmentCreate] = Field(default_factory=list)


class ReturnGoodsReceive(RequestSchema):
    """Staff xác nhận hàng thực tế đã về (sản phẩm quản lý serial: quét đúng serial của yêu cầu)."""

    NULLABLE_FIELDS = frozenset({"SerialNumber", "Note", "InternalNote"})

    SerialNumber: SerialNumberValue | None = None
    Note: str | None = None
    InternalNote: str | None = None


class ReturnInspection(RequestSchema):
    """Staff ghi nhận kết quả kiểm tra thực tế: số đạt (nhập lại tồn khi Admin duyệt) và số hỏng (không nhập tồn)."""

    NULLABLE_FIELDS = frozenset({"DamageAssessment", "InternalNote"})

    RestockedQuantity: NonNegativeInt
    DamagedQuantity: NonNegativeInt
    DamageAssessment: str | None = None
    InternalNote: str | None = None


class ReturnApproval(RequestSchema):
    """Admin xác nhận đúng số tiền hệ thống đã tính (CompensationAmount) trước khi hoàn tiền / thu thêm."""

    NULLABLE_FIELDS = frozenset({"Note", "InternalNote"})

    CompensationAmount: Money
    Note: str | None = None
    InternalNote: str | None = None


class ReturnRefundCreate(RequestSchema):
    """Tạo giao dịch hoàn tiền cho yêu cầu trả hàng đã duyệt; mặc định PaymentService chọn khoản thanh toán nguồn."""

    NULLABLE_FIELDS = frozenset({"PaymentTransactionId"})

    PaymentTransactionId: uuid.UUID | None = None


class _ReturnRequestFields(ResponseSchema):
    ReturnRequestId: uuid.UUID
    RequestCode: str
    OrderItemId: uuid.UUID
    ProductSerialId: uuid.UUID | None
    Quantity: int
    RequestType: ReturnRequestType
    Reason: str
    Status: ReturnRequestStatus
    DecisionReason: str | None
    DamageAssessment: str | None
    ResolutionType: str | None
    RestockedQuantity: int | None
    DamagedQuantity: int | None
    CompensationAmount: Money | None
    CompensationApprovedAt: datetime | None
    RefundPaymentTransactionId: uuid.UUID | None
    RequestedAt: datetime
    ReceivedAt: datetime | None
    CompletedAt: datetime | None


class ReturnRequestResponse(_ReturnRequestFields):
    """Dành cho khách hàng: không có AssignedStaffId, căn cứ tính tiền, người duyệt.

    Số tiền đang chờ Admin duyệt là nội bộ: CompensationAmount chỉ hiển thị khi đã có CompensationApprovedAt.
    """

    @model_validator(mode="after")
    def _hide_unapproved_amount(self):
        if self.CompensationApprovedAt is None:
            self.CompensationAmount = None
        return self


class ReturnRequestDetailResponse(ReturnRequestResponse):
    Attachments: list[ServiceRequestAttachmentResponse] = relation_field("attachments")
    # Chỉ lịch sử công khai (bỏ dòng nội bộ); schema không có InternalNote.
    Histories: list[ServiceRequestHistoryResponse] = relation_field("public_histories")


class AdminReturnRequestResponse(_ReturnRequestFields):
    CustomerId: uuid.UUID
    AssignedStaffId: uuid.UUID | None
    CompensationBasis: dict[str, Any] | None
    CompensationApprovedByUserId: uuid.UUID | None


class AdminReturnRequestDetailResponse(AdminReturnRequestResponse):
    Attachments: list[ServiceRequestAttachmentResponse] = relation_field("attachments")
    Histories: list[AdminServiceRequestHistoryResponse] = relation_field("histories")
