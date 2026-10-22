"""Repositories cho Conversations, Messages. Không gọi AI service."""

import uuid
from datetime import datetime

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.sql import ColumnElement

from app.models import Conversation, Message, User

from .base import BaseRepository


def has_messages() -> ColumnElement[bool]:
    """Hội thoại đã có ít nhất một tin nhắn (khách không chỉ mở khung chat rồi rời đi)."""
    return exists().where(Message.ConversationId == Conversation.ConversationId)


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    def get_titles(self, conversation_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        """First customer text for an already authorized page, in one bounded query."""
        if not conversation_ids:
            return {}
        ranked = select(
            Message.ConversationId,
            func.substr(Message.Content, 1, 120).label("title"),
            func.row_number().over(partition_by=Message.ConversationId,
                                   order_by=(Message.SentAt, Message.MessageId)).label("message_rank"),
        ).where(Message.ConversationId.in_(conversation_ids), Message.SenderType == "Customer",
                Message.MessageType == "Text", func.length(func.trim(Message.Content)) > 0).subquery()
        rows = self.session.execute(select(ranked.c.ConversationId, ranked.c.title)
                                    .where(ranked.c.message_rank == 1)).all()
        return {id_: " ".join(content.split())[:90] for id_, content in rows}

    def get_support_context(self, conversation_ids: list[uuid.UUID]) -> dict:
        """Only enrich IDs already authorized by the service; two queries per page, no N+1/history load."""
        if not conversation_ids:
            return {}
        unread = (select(Message.ConversationId, func.count().label('Count'))
                  .where(Message.ConversationId.in_(conversation_ids), Message.SenderType == 'Customer', Message.IsRead.is_(False))
                  .group_by(Message.ConversationId).subquery())
        staff = aliased(User)
        customers = self.session.execute(
            select(Conversation.ConversationId, User.FullName, User.Email, func.coalesce(unread.c.Count, 0), staff.FullName)
            .join(User, User.UserId == Conversation.CustomerId)
            .outerjoin(staff, staff.UserId == Conversation.AssignedStaffId)
            .outerjoin(unread, unread.c.ConversationId == Conversation.ConversationId)
            .where(Conversation.ConversationId.in_(conversation_ids))
        ).all()
        ranked = select(
            Message,
            func.row_number().over(
                partition_by=Message.ConversationId,
                order_by=(Message.SentAt.desc(), Message.MessageId.desc()),
            ).label("message_rank"),
        ).where(Message.ConversationId.in_(conversation_ids)).subquery()
        latest = aliased(Message, ranked)
        messages = self.session.scalars(select(latest).where(ranked.c.message_rank == 1)).all()
        by_id = {message.ConversationId: message for message in messages}
        return {id_: (name, email, by_id.get(id_), int(count), staff_name)
                for id_, name, email, count, staff_name in customers}

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

    def get_open_by_customer(self, customer_id: uuid.UUID) -> Conversation | None:
        """Hội thoại đang Open của Customer (tối đa một: UX_Conversations_CustomerId_Open)."""
        return self.get_one(Conversation.CustomerId == customer_id, Conversation.Status == "Open")

    def _filters(
        self,
        customer_id: uuid.UUID | None,
        assigned_staff_id: uuid.UUID | None,
        status: str | None,
        mode: str | None,
        unassigned: bool = False,
        assigned: bool = False,
        started: bool = False,
        hide_unused_closed: bool = False,
    ) -> list:
        conditions = []
        if started:
            conditions.append(has_messages())
        if hide_unused_closed:
            conditions.append(or_(Conversation.Status == "Open", has_messages()))
        if unassigned:
            conditions.append(Conversation.AssignedStaffId.is_(None))
        if assigned:
            conditions.append(Conversation.AssignedStaffId.is_not(None))
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
        unassigned: bool = False,
        assigned: bool = False,
        started: bool = False,
        hide_unused_closed: bool = False,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[Conversation]:
        return self.get_all(
            *self._filters(customer_id, assigned_staff_id, status, mode, unassigned, assigned, started,
                           hide_unused_closed),
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
        unassigned: bool = False,
        assigned: bool = False,
        started: bool = False,
        hide_unused_closed: bool = False,
    ) -> int:
        return self.count(*self._filters(customer_id, assigned_staff_id, status, mode, unassigned, assigned, started,
                                         hide_unused_closed))


class MessageRepository(BaseRepository[Message]):
    model = Message

    def get_ai_request(self, conversation_id: uuid.UUID, request_id: uuid.UUID) -> Message | None:
        return self.get_one(Message.ConversationId == conversation_id, Message.SenderType == "Customer",
                            Message.Metadata.op("->>")("ClientRequestId") == str(request_id))

    def pending_ai_requests(self, conversation_id: uuid.UUID) -> list[Message]:
        return self.get_all(Message.ConversationId == conversation_id, Message.SenderType == "Customer",
                            Message.Metadata.op("->>")("AiProcessingStatus") == "Pending")

    def completed_ai_requests(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        rows = self.get_all(Message.ConversationId == conversation_id, Message.SenderType == "Customer",
                            Message.Metadata.op("->>")("AiProcessingStatus") == "Completed",
                            order_by=(Message.SentAt.desc(), Message.MessageId.desc()), limit=limit)
        return list(reversed(rows))

    def get_messages_by_ids(self, ids: list[uuid.UUID]) -> list[Message]:
        return self.get_all(Message.MessageId.in_(ids)) if ids else []

    def list_window(self, conversation_id: uuid.UUID, *, limit: int, latest: bool = False,
                    after: tuple[datetime, uuid.UUID] | None = None,
                    before: tuple[datetime, uuid.UUID] | None = None) -> list[Message]:
        conditions = [Message.ConversationId == conversation_id]
        if after:
            at, id_ = after
            conditions.append(or_(Message.SentAt > at, and_(Message.SentAt == at, Message.MessageId > id_)))
        if before:
            at, id_ = before
            conditions.append(or_(Message.SentAt < at, and_(Message.SentAt == at, Message.MessageId < id_)))
        reverse = latest or before is not None
        order = (Message.SentAt.desc(), Message.MessageId.desc()) if reverse else (Message.SentAt, Message.MessageId)
        rows = self.get_all(*conditions, order_by=order, limit=limit)
        return list(reversed(rows)) if reverse else rows

    def mark_read(self, conversation_id: uuid.UUID, ids: list[uuid.UUID], sender_types: tuple[str, ...]) -> int:
        result = self.session.execute(update(Message).where(
            Message.ConversationId == conversation_id, Message.MessageId.in_(ids),
            Message.SenderType.in_(sender_types), Message.IsRead.is_(False),
        ).values(IsRead=True))
        return result.rowcount

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
