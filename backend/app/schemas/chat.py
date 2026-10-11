"""Schemas cho Conversations, Messages.

Giá trị đã chốt (đợt 5.3): Mode AI/Staff; SenderType Customer/Staff/AI (server gán, client không gửi);
MessageType Text/Image/Product. Response giữ kiểu chuỗi để đọc được cả dữ liệu cũ.
Đợt 5.10: định danh nhân viên là nội bộ (như AssignedStaffId ở Orders/WarrantyRequests/ReturnRequests) — schema cho
Customer không có AssignedStaffId và không trả SenderUserId của tin nhân viên; schema Admin* dành cho Staff/Admin.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import model_validator

from app.models.chat import MESSAGE_CONTENT_MAX_LENGTH

from .common import (
    ConversationMode,
    ConversationStatus,
    MessageTypeValue,
    RequestSchema,
    ResponseSchema,
    relation_field,
)


class ConversationCreate(RequestSchema):
    """CustomerId lấy từ người dùng đăng nhập; Status do server gán."""

    Mode: ConversationMode


# Không có schema cập nhật hội thoại tổng quát (đợt 5.3.1): Status/Mode/AssignedStaffId chỉ đổi qua nghiệp vụ
# ChatService.claim_conversation / close_conversation (có kiểm tra quyền); Mode không đổi sau khi mở hội thoại.


class MessageCreate(RequestSchema):
    """SenderUserId, SenderType do server gán theo người gửi (khách hàng / nhân viên); tin AI chỉ do luồng nội bộ tạo.

    Text: Content bắt buộc (không rỗng). Image: Metadata {"ImageUrl": "https://..."} (Content = chú thích, có thể rỗng).
    Product: Metadata {"ProductId": "<uuid>"} — server kiểm tra sản phẩm và tự ghi thông tin sản phẩm vào Metadata.
    """

    NULLABLE_FIELDS = frozenset({"Metadata"})

    MessageType: MessageTypeValue
    Content: str = ""
    Metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _content_length(self):
        """Tối đa MESSAGE_CONTENT_MAX_LENGTH ký tự sau khi bỏ khoảng trắng đầu/cuối (Service kiểm tra lại)."""
        if len(self.Content.strip()) > MESSAGE_CONTENT_MAX_LENGTH:
            raise ValueError(f"Nội dung tin nhắn tối đa {MESSAGE_CONTENT_MAX_LENGTH} ký tự")
        return self


class _MessageFields(ResponseSchema):
    MessageId: uuid.UUID
    ConversationId: uuid.UUID
    SenderUserId: uuid.UUID | None
    SenderType: str
    MessageType: str
    Content: str
    Metadata: dict[str, Any] | None
    IsRead: bool
    SentAt: datetime


class MessageResponse(_MessageFields):
    """Dành cho khách hàng: SenderUserId chỉ có ở tin của chính khách (tin nhân viên/AI: None)."""

    @model_validator(mode="after")
    def _hide_staff_sender(self):
        if self.SenderType != "Customer":
            self.SenderUserId = None
        return self


class AdminMessageResponse(_MessageFields):
    """Staff/Admin: đủ SenderUserId."""


class ConversationResponse(ResponseSchema):
    """Dành cho khách hàng: không có AssignedStaffId."""

    ConversationId: uuid.UUID
    CustomerId: uuid.UUID
    Mode: str
    Status: ConversationStatus
    CreatedAt: datetime
    ClosedAt: datetime | None


class ConversationDetailResponse(ConversationResponse):
    Messages: list[MessageResponse] = relation_field("messages")


class AdminConversationResponse(ConversationResponse):
    AssignedStaffId: uuid.UUID | None


class AdminConversationDetailResponse(AdminConversationResponse):
    Messages: list[AdminMessageResponse] = relation_field("messages")
