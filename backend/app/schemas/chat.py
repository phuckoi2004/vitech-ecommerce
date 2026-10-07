"""Schemas cho Conversations, Messages.

Giá trị của Mode, SenderType, MessageType chưa được chốt trong schema nên giữ dạng chuỗi.
"""

import uuid
from datetime import datetime
from typing import Any

from .common import ConversationStatus, RequestSchema, ResponseSchema, relation_field, varchar


class ConversationCreate(RequestSchema):
    """CustomerId lấy từ người dùng đăng nhập; Status do server gán."""

    Mode: varchar(20)


class ConversationUpdate(RequestSchema):
    """Staff/admin phân công hoặc đóng hội thoại (ClosedAt do server gán)."""

    NULLABLE_FIELDS = frozenset({"AssignedStaffId"})

    AssignedStaffId: uuid.UUID | None = None
    Mode: varchar(20) | None = None
    Status: ConversationStatus | None = None


class MessageCreate(RequestSchema):
    """SenderUserId, SenderType do server gán theo người gửi (khách hàng / nhân viên / AI)."""

    NULLABLE_FIELDS = frozenset({"Metadata"})

    MessageType: varchar(20)
    Content: str
    Metadata: dict[str, Any] | None = None


class MessageResponse(ResponseSchema):
    MessageId: uuid.UUID
    ConversationId: uuid.UUID
    SenderUserId: uuid.UUID | None
    SenderType: str
    MessageType: str
    Content: str
    Metadata: dict[str, Any] | None
    IsRead: bool
    SentAt: datetime


class ConversationResponse(ResponseSchema):
    ConversationId: uuid.UUID
    CustomerId: uuid.UUID
    AssignedStaffId: uuid.UUID | None
    Mode: str
    Status: ConversationStatus
    CreatedAt: datetime
    ClosedAt: datetime | None


class ConversationDetailResponse(ConversationResponse):
    Messages: list[MessageResponse] = relation_field("messages")
