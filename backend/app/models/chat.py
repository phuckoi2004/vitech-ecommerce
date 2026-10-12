from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, check_in

if TYPE_CHECKING:
    from .user import User


CONVERSATION_STATUSES = ("Open", "Closed")
# Giá trị đã chốt (đợt 5.3); CHECK + partial unique index thêm bởi migration c8d2f4a6b1e3 (chưa áp dụng).
CONVERSATION_MODES = ("AI", "Staff")
MESSAGE_SENDER_TYPES = ("Customer", "Staff", "AI")
MESSAGE_TYPES = ("Text", "Image", "Product")
# Độ dài tối đa của Content (văn bản tin nhắn / chú thích ảnh, sản phẩm) sau khi bỏ khoảng trắng đầu/cuối (đợt 5.3.1).
# Không áp dụng cho URL ảnh hay Metadata (có quy tắc riêng). Không tự cắt ngắn: vượt thì từ chối.
MESSAGE_CONTENT_MAX_LENGTH = 5000


class Conversation(Base):
    __tablename__ = "Conversations"
    __table_args__ = (
        check_in("Status", CONVERSATION_STATUSES, "Status_Valid"),
        check_in("Mode", CONVERSATION_MODES, "Mode_Valid"),
    )

    ConversationId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    CustomerId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="RESTRICT"), nullable=False
    )
    AssignedStaffId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    Mode: Mapped[str] = mapped_column(String(20), nullable=False)
    Status: Mapped[str] = mapped_column(String(30), nullable=False)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ClosedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[User] = relationship(
        back_populates="customer_conversations", foreign_keys=[CustomerId]
    )
    assigned_staff: Mapped[User | None] = relationship(
        back_populates="assigned_conversations", foreign_keys=[AssignedStaffId]
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        foreign_keys="Message.ConversationId",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Message(Base):
    __tablename__ = "Messages"
    __table_args__ = (
        check_in("SenderType", MESSAGE_SENDER_TYPES, "SenderType_Valid"),
        check_in("MessageType", MESSAGE_TYPES, "MessageType_Valid"),
        # Tin nhắn AI không gắn với tài khoản người dùng (không ai gửi tin dưới danh nghĩa AI bằng tài khoản của mình).
        CheckConstraint("\"SenderType\" <> 'AI' OR \"SenderUserId\" IS NULL", name="AiSender_NoUser"),
    )

    MessageId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ConversationId: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("Conversations.ConversationId", ondelete="CASCADE"),
        nullable=False,
    )
    SenderUserId: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("Users.UserId", ondelete="SET NULL"), nullable=True
    )
    SenderType: Mapped[str] = mapped_column(String(20), nullable=False)
    MessageType: Mapped[str] = mapped_column(String(20), nullable=False)
    Content: Mapped[str] = mapped_column(Text, nullable=False)
    Metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    IsRead: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    SentAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    conversation: Mapped[Conversation] = relationship(
        back_populates="messages", foreign_keys=[ConversationId]
    )
    sender: Mapped[User | None] = relationship(back_populates="sent_messages", foreign_keys=[SenderUserId])


# Mỗi Customer tối đa một hội thoại đang Open (chặn hai yêu cầu mở hội thoại đồng thời).
Index(
    "UX_Conversations_CustomerId_Open",
    Conversation.CustomerId,
    unique=True,
    postgresql_where=text("\"Status\" = 'Open'"),
)
