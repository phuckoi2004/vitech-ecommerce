from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, check_in

if TYPE_CHECKING:
    from .user import User


CONVERSATION_STATUSES = ("Open", "Closed")


class Conversation(Base):
    __tablename__ = "Conversations"
    __table_args__ = (check_in("Status", CONVERSATION_STATUSES, "Status_Valid"),)

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
