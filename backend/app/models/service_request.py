from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
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

# Mỗi record thuộc đúng một trong WarrantyRequest / ReturnRequest.
ONE_SERVICE_REQUEST_CHECK = 'num_nonnulls("WarrantyRequestId", "ReturnRequestId") = 1'


class WarrantyRequest(Base):
    __tablename__ = "WarrantyRequests"
    __table_args__ = (
        check_in("EligibilityStatus", WARRANTY_ELIGIBILITY_STATUSES, "EligibilityStatus_Valid"),
        check_in("Status", WARRANTY_REQUEST_STATUSES, "Status_Valid"),
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


class ReturnRequest(Base):
    __tablename__ = "ReturnRequests"
    __table_args__ = (
        check_in("Status", RETURN_REQUEST_STATUSES, "Status_Valid"),
        CheckConstraint('"CompensationAmount" >= 0', name="CompensationAmount_NonNegative"),
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


class ServiceRequestAttachment(Base):
    __tablename__ = "ServiceRequestAttachments"
    __table_args__ = (CheckConstraint(ONE_SERVICE_REQUEST_CHECK, name="OneServiceRequest"),)

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
    __table_args__ = (CheckConstraint(ONE_SERVICE_REQUEST_CHECK, name="OneServiceRequest"),)

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
    Note: Mapped[str | None] = mapped_column(Text, nullable=True)
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
