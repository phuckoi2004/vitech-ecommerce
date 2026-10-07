"""Repositories cho Conversations, Messages. Không gọi AI service."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Conversation, Message

from .base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    def get_detail(self, conversation_id: uuid.UUID) -> Conversation | None:
        """Conversation kèm toàn bộ Messages; với hội thoại dài nên dùng MessageRepository có phân trang."""
        stmt = (
            select(Conversation)
            .where(Conversation.ConversationId == conversation_id)
            .options(selectinload(Conversation.messages))
        )
        return self.session.scalars(stmt).one_or_none()

    def get_by_id_and_customer(self, conversation_id: uuid.UUID, customer_id: uuid.UUID) -> Conversation | None:
        return self.get_one(Conversation.ConversationId == conversation_id, Conversation.CustomerId == customer_id)

    def _filters(
        self, customer_id: uuid.UUID | None, assigned_staff_id: uuid.UUID | None, status: str | None, mode: str | None
    ) -> list:
        conditions = []
        if customer_id is not None:
            conditions.append(Conversation.CustomerId == customer_id)
        if assigned_staff_id is not None:
            conditions.append(Conversation.AssignedStaffId == assigned_staff_id)
        if status is not None:
            conditions.append(Conversation.Status == status)
        if mode is not None:
            conditions.append(Conversation.Mode == mode)
        return conditions

    def list_conversations(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        status: str | None = None,
        mode: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Conversation]:
        return self.get_all(
            *self._filters(customer_id, assigned_staff_id, status, mode),
            order_by=(Conversation.CreatedAt.desc(), Conversation.ConversationId),
            offset=offset,
            limit=limit,
        )

    def count_conversations(
        self,
        *,
        customer_id: uuid.UUID | None = None,
        assigned_staff_id: uuid.UUID | None = None,
        status: str | None = None,
        mode: str | None = None,
    ) -> int:
        return self.count(*self._filters(customer_id, assigned_staff_id, status, mode))


class MessageRepository(BaseRepository[Message]):
    model = Message

    def list_by_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Message]:
        """Lịch sử tin nhắn theo thời gian gửi tăng dần."""
        return self.get_all(
            Message.ConversationId == conversation_id,
            order_by=(Message.SentAt, Message.MessageId),
            offset=offset,
            limit=limit,
        )

    def list_latest_by_conversation(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        """``limit`` tin nhắn mới nhất, trả theo thời gian tăng dần (ví dụ làm ngữ cảnh hội thoại)."""
        latest = self.get_all(
            Message.ConversationId == conversation_id,
            order_by=(Message.SentAt.desc(), Message.MessageId.desc()),
            limit=limit,
        )
        return list(reversed(latest))

    def count_by_conversation(self, conversation_id: uuid.UUID, *, is_read: bool | None = None) -> int:
        conditions = [Message.ConversationId == conversation_id]
        if is_read is not None:
            conditions.append(Message.IsRead.is_(is_read))
        return self.count(*conditions)
