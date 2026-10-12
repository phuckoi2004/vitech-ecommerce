from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, check_in

if TYPE_CHECKING:
    from .catalog import ProductSerial
    from .order import OrderItem
    from .purchasing import Supplier
    from .user import User


# Kết quả kiểm tra điều kiện bảo hành.
WARRANTY_ELIGIBILITY_STATUSES = ("Pending", "Eligible", "Ineligible")
# Trạng thái xử lý yêu cầu bảo hành (không có Approved).
WARRANTY_REQUEST_STATUSES = ("New", "Rejected", "HandedOver", "Processing", "Completed", "Cancelled")
RETURN_REQUEST_STATUSES = (
    "Pending",
    "Approved",
    "Rejected",
    "Receiving",
    "Processing",
    "Completed",
    "Cancelled",
)

# Giá trị đã chốt (đợt 5.4); CHECK thêm bởi migration d4f7b2e9a6c1 (chưa áp dụng).
WARRANTY_RESULT_TYPES = ("Repaired", "ProductReplaced", "PartReplaced", "NotRepairable")
ATTACHMENT_FILE_TYPES = ("Image", "Video")
# Yêu cầu bảo hành đang xử lý (chặn yêu cầu trùng cho cùng serial / dòng đơn không quản lý serial).
WARRANTY_OPEN_STATUSES = ("New", "HandedOver", "Processing")
_WARRANTY_OPEN_SQL = "\"Status\" IN ('New', 'HandedOver', 'Processing')"
# Đổi/trả (đợt 5.4; CHECK, cột mới và index bởi migration f3b8d1a5c7e2, chưa áp dụng).
RETURN_REQUEST_TYPES = ("Exchange", "Return")
RETURN_OPEN_STATUSES = ("Pending", "Approved", "Receiving", "Processing")
_RETURN_OPEN_SQL = "\"Status\" IN ('Pending', 'Approved', 'Receiving', 'Processing')"

# Mỗi record thuộc đúng một trong WarrantyRequest / ReturnRequest.
ONE_SERVICE_REQUEST_CHECK = 'num_nonnulls("WarrantyRequestId", "ReturnRequestId") = 1'


class WarrantyRequest(Base):
    __tablename__ = "WarrantyRequests"
    __table_args__ = (
        check_in("EligibilityStatus", WARRANTY_ELIGIBILITY_STATUSES, "EligibilityStatus_Valid"),
        check_in("Status", WARRANTY_REQUEST_STATUSES, "Status_Valid"),
        check_in("ResultType", WARRANTY_RESULT_TYPES, "ResultType_Valid"),
        # Thông tin máy thay thế chỉ có khi kết quả là đổi máy.
        CheckConstraint(
            '("ReplacementProductSerialId" IS NULL AND "ReplacementHandedOverAt" IS NULL) '
            "OR \"ResultType\" = 'ProductReplaced'",
            name="Replacement_OnlyProductReplaced",
        ),
        CheckConstraint('"ResultApprovedAt" IS NULL OR "ResultType" IS NOT NULL', name="Approval_RequiresResult"),
        # Đợt 5.4.1 (migration e6a2d9c4b8f1): kết quả phải có người/thời điểm đề xuất; người duyệt khác người đề xuất.
        CheckConstraint('"ResultType" IS NULL OR "ResultProposedAt" IS NOT NULL', name="Proposal_Recorded"),
        CheckConstraint(
            '"ResultApprovedByUserId" IS NULL OR "ResultProposedByUserId" IS NULL '
            'OR "ResultApprovedByUserId" <> "ResultProposedByUserId"',
            name="Approval_NotByProposer",
        ),
        # Hoàn tất cần kết quả đã được Admin duyệt; đổi máy cần đã bàn giao máy thay thế.
        CheckConstraint(
            "\"Status\" <> 'Completed' OR (\"CompletedAt\" IS NOT NULL AND \"ResultType\" IS NOT NULL "
            "AND \"ResultApprovedAt\" IS NOT NULL "
            "AND (\"ResultType\" <> 'ProductReplaced' OR \"ReplacementHandedOverAt\" IS NOT NULL))",
            name="Completed_RequiresApprovedResult",
        ),
    )

    WarrantyRequestId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    RequestCode: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    CustomerId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    AssignedStaffId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    OrderItemId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("OrderItems.OrderItemId", ondelete="RESTRICT"), nullable=False
    )
    ProductSerialId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ProductSerials.ProductSerialId", ondelete="RESTRICT"),
        nullable=True,
    )
    SupplierId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Suppliers.SupplierId", ondelete="RESTRICT"), nullable=True
    )
    IssueDescription: Mapped[str] = mapped_column(Text, nullable=False)
    EligibilityStatus: Mapped[str] = mapped_column(String(30), nullable=False)
    EligibilityReason: Mapped[str | None] = mapped_column(Text, nullable=True)
    Status: Mapped[str] = mapped_column(String(30), nullable=False)
    ReceivedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    HandoverCode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ServiceCenter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    HandedOverAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ResultType: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ResultNote: Mapped[str | None] = mapped_column(Text, nullable=True)
    RequestedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    CompletedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Người/thời điểm đề xuất kết quả đang chờ duyệt (migration e6a2d9c4b8f1).
    ResultProposedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    ResultProposedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Admin duyệt kết quả do nhân viên đề xuất (migration d4f7b2e9a6c1).
    ResultApprovedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    ResultApprovedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Máy thay thế giao cho khách (ResultType = ProductReplaced); serial cũ giữ nguyên lịch sử.
    ReplacementProductSerialId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ProductSerials.ProductSerialId", ondelete="RESTRICT"), nullable=True
    )
    ReplacementHandedOverAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ReplacementHandedOverByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )

    customer: Mapped[User] = relationship(back_populates="warranty_requests", foreign_keys=[CustomerId])
    assigned_staff: Mapped[User | None] = relationship(
        back_populates="assigned_warranty_requests", foreign_keys=[AssignedStaffId]
    )
    order_item: Mapped[OrderItem] = relationship(
        back_populates="warranty_requests", foreign_keys=[OrderItemId]
    )
    product_serial: Mapped[ProductSerial | None] = relationship(
        back_populates="warranty_requests", foreign_keys=[ProductSerialId]
    )
    supplier: Mapped[Supplier | None] = relationship(
        back_populates="warranty_requests", foreign_keys=[SupplierId]
    )
    attachments: Mapped[list[ServiceRequestAttachment]] = relationship(
        back_populates="warranty_request",
        foreign_keys="ServiceRequestAttachment.WarrantyRequestId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    histories: Mapped[list[ServiceRequestHistory]] = relationship(
        back_populates="warranty_request",
        foreign_keys="ServiceRequestHistory.WarrantyRequestId",
        passive_deletes="all",
    )

    @property
    def public_histories(self) -> list[ServiceRequestHistory]:
        """Lịch sử khách hàng được xem: bỏ các dòng nội bộ (IsInternal)."""
        return [h for h in self.histories if not h.IsInternal]


class ReturnRequest(Base):
    __tablename__ = "ReturnRequests"
    __table_args__ = (
        check_in("Status", RETURN_REQUEST_STATUSES, "Status_Valid"),
        CheckConstraint('"CompensationAmount" >= 0', name="CompensationAmount_NonNegative"),
        check_in("RequestType", RETURN_REQUEST_TYPES, "RequestType_Valid"),
        CheckConstraint('"Quantity" > 0', name="Quantity_Positive"),
        # Một serial = một đơn vị hàng.
        CheckConstraint('"ProductSerialId" IS NULL OR "Quantity" = 1', name="Serial_SingleUnit"),
        # Kết quả kiểm tra: số nhập lại + số hỏng = số lượng yêu cầu; chỉ có sau khi đã nhận hàng.
        CheckConstraint(
            '("RestockedQuantity" IS NULL AND "DamagedQuantity" IS NULL) OR ("RestockedQuantity" >= 0 '
            'AND "DamagedQuantity" >= 0 AND "RestockedQuantity" + "DamagedQuantity" = "Quantity")',
            name="Inspection_Consistent",
        ),
        CheckConstraint('"RestockedQuantity" IS NULL OR "ReceivedAt" IS NOT NULL', name="Inspection_RequiresReceipt"),
        # Admin duyệt số tiền đã được tính từ kết quả kiểm tra.
        CheckConstraint(
            '"CompensationApprovedAt" IS NULL OR ("CompensationAmount" IS NOT NULL AND "RestockedQuantity" IS NOT NULL)',
            name="Approval_RequiresAssessment",
        ),
        CheckConstraint(
            "\"RefundPaymentTransactionId\" IS NULL OR (\"RequestType\" = 'Return' "
            'AND "CompensationApprovedAt" IS NOT NULL)',
            name="Refund_RequiresApprovedReturn",
        ),
        CheckConstraint(
            "\"Status\" <> 'Completed' OR (\"CompletedAt\" IS NOT NULL AND \"CompensationApprovedAt\" IS NOT NULL)",
            name="Completed_RequiresApproval",
        ),
    )

    ReturnRequestId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    RequestCode: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    CustomerId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    AssignedStaffId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    OrderItemId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("OrderItems.OrderItemId", ondelete="RESTRICT"), nullable=False
    )
    RequestType: Mapped[str] = mapped_column(String(20), nullable=False)
    Reason: Mapped[str] = mapped_column(Text, nullable=False)
    Status: Mapped[str] = mapped_column(String(30), nullable=False)
    DecisionReason: Mapped[str | None] = mapped_column(Text, nullable=True)
    DamageAssessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    ResolutionType: Mapped[str | None] = mapped_column(String(30), nullable=True)
    CompensationAmount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    RequestedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ReceivedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CompletedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Đợt 5.4 (migration f3b8d1a5c7e2): serial thực tế được trả (NULL với hàng không quản lý serial) và số lượng.
    ProductSerialId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ProductSerials.ProductSerialId", ondelete="RESTRICT"), nullable=True
    )
    Quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Kết quả kiểm tra thực tế: đạt (nhập lại tồn khi Admin duyệt) / hỏng (không nhập tồn).
    RestockedQuantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    DamagedQuantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Căn cứ tính CompensationAmount (giá trị lịch sử của dòng đơn, khấu trừ, công thức) để Admin kiểm tra.
    CompensationBasis: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    CompensationApprovedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    CompensationApprovedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    # Giao dịch Refund (PaymentTransactions, có RefundOfPaymentTransactionId) tạo cho yêu cầu trả hàng.
    RefundPaymentTransactionId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("PaymentTransactions.PaymentTransactionId", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )

    customer: Mapped[User] = relationship(back_populates="return_requests", foreign_keys=[CustomerId])
    assigned_staff: Mapped[User | None] = relationship(
        back_populates="assigned_return_requests", foreign_keys=[AssignedStaffId]
    )
    order_item: Mapped[OrderItem] = relationship(
        back_populates="return_requests", foreign_keys=[OrderItemId]
    )
    attachments: Mapped[list[ServiceRequestAttachment]] = relationship(
        back_populates="return_request",
        foreign_keys="ServiceRequestAttachment.ReturnRequestId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    histories: Mapped[list[ServiceRequestHistory]] = relationship(
        back_populates="return_request",
        foreign_keys="ServiceRequestHistory.ReturnRequestId",
        passive_deletes="all",
    )

    @property
    def public_histories(self) -> list[ServiceRequestHistory]:
        """Lịch sử khách hàng được xem: bỏ các dòng nội bộ (IsInternal)."""
        return [h for h in self.histories if not h.IsInternal]


class ServiceRequestAttachment(Base):
    __tablename__ = "ServiceRequestAttachments"
    __table_args__ = (
        CheckConstraint(ONE_SERVICE_REQUEST_CHECK, name="OneServiceRequest"),
        check_in("FileType", ATTACHMENT_FILE_TYPES, "FileType_Valid"),
    )

    ServiceRequestAttachmentId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    WarrantyRequestId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("WarrantyRequests.WarrantyRequestId", ondelete="CASCADE"),
        nullable=True,
    )
    ReturnRequestId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ReturnRequests.ReturnRequestId", ondelete="CASCADE"),
        nullable=True,
    )
    FileUrl: Mapped[str] = mapped_column(String(500), nullable=False)
    FileType: Mapped[str] = mapped_column(String(20), nullable=False)
    UploadedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    warranty_request: Mapped[WarrantyRequest | None] = relationship(
        back_populates="attachments", foreign_keys=[WarrantyRequestId]
    )
    return_request: Mapped[ReturnRequest | None] = relationship(
        back_populates="attachments", foreign_keys=[ReturnRequestId]
    )


class ServiceRequestHistory(Base):
    __tablename__ = "ServiceRequestHistories"
    __table_args__ = (
        CheckConstraint(ONE_SERVICE_REQUEST_CHECK, name="OneServiceRequest"),
        # Dòng nội bộ không mang nội dung dành cho khách (migration e6a2d9c4b8f1).
        CheckConstraint('NOT "IsInternal" OR "Note" IS NULL', name="Internal_NoPublicNote"),
    )

    ServiceRequestHistoryId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    WarrantyRequestId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("WarrantyRequests.WarrantyRequestId", ondelete="RESTRICT"),
        nullable=True,
    )
    ReturnRequestId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ReturnRequests.ReturnRequestId", ondelete="RESTRICT"),
        nullable=True,
    )
    ChangedByUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    OldStatus: Mapped[str | None] = mapped_column(String(30), nullable=True)
    NewStatus: Mapped[str] = mapped_column(String(30), nullable=False)
    # Note: nội dung khách hàng được xem. InternalNote: chỉ Staff/Admin. IsInternal: cả dòng chỉ Staff/Admin xem
    # (ví dụ đề xuất/từ chối đề xuất kết quả). Migration e6a2d9c4b8f1; dòng cũ mặc định công khai.
    Note: Mapped[str | None] = mapped_column(Text, nullable=True)
    InternalNote: Mapped[str | None] = mapped_column(Text, nullable=True)
    IsInternal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    ChangedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    warranty_request: Mapped[WarrantyRequest | None] = relationship(
        back_populates="histories", foreign_keys=[WarrantyRequestId]
    )
    return_request: Mapped[ReturnRequest | None] = relationship(
        back_populates="histories", foreign_keys=[ReturnRequestId]
    )
    changed_by: Mapped[User | None] = relationship(
        back_populates="service_request_changes", foreign_keys=[ChangedByUserId]
    )


# Mỗi serial / mỗi dòng đơn không quản lý serial tối đa một yêu cầu bảo hành đang xử lý (migration d4f7b2e9a6c1).
Index(
    "UX_WarrantyRequests_Serial_Open",
    WarrantyRequest.ProductSerialId,
    unique=True,
    postgresql_where=text('"ProductSerialId" IS NOT NULL AND ' + _WARRANTY_OPEN_SQL),
)
Index(
    "UX_WarrantyRequests_OrderItem_Open_NoSerial",
    WarrantyRequest.OrderItemId,
    unique=True,
    postgresql_where=text('"ProductSerialId" IS NULL AND ' + _WARRANTY_OPEN_SQL),
)
# Mỗi serial tối đa một yêu cầu đổi/trả đang xử lý (migration f3b8d1a5c7e2).
Index(
    "UX_ReturnRequests_Serial_Open",
    ReturnRequest.ProductSerialId,
    unique=True,
    postgresql_where=text('"ProductSerialId" IS NOT NULL AND ' + _RETURN_OPEN_SQL),
)
