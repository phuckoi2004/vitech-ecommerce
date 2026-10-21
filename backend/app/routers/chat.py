"""Chat APIs: the customer's conversations with staff or the AI bot, and the staff inbox.

Customer routes return customer schemas (no assigned staff, no staff sender id); ``/admin`` routes return the
internal schemas. The Service checks who may read or write each conversation. AI replies are recorded by the
future AI integration (``ChatService.record_ai_reply``), not through these routes.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.schemas import (
    AdminConversationDetailResponse,
    AdminConversationResponse,
    AdminMessageResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    PageResponse,
)
from app.services.chat import ChatService
from app.schemas.chat import MessageReadRequest
from app.services.exceptions import BusinessRuleError

from .dependencies import CurrentActor, InternalOnly, Page, PageSize, get_chat_service

router = APIRouter(tags=["Chat"])
admin_router = APIRouter(prefix="/admin", tags=["Quản lý chat"], dependencies=[InternalOnly])

Chat = Annotated[ChatService, Depends(get_chat_service)]
StatusFilter = Annotated[str | None, Query(alias="status")]


# ------------------------------------------------------------------ customer


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def start_conversation(data: ConversationCreate, service: Chat, actor: CurrentActor):
    """Returns the open conversation of the same mode if one already exists."""
    return service.start_conversation(actor, data)


@router.get("/conversations", response_model=PageResponse[ConversationResponse])
def list_my_conversations(service: Chat, actor: CurrentActor, status_filter: StatusFilter = None,
                          page: Page = 1, page_size: PageSize = 20):
    return service.list_my_conversations(actor, status=status_filter, page=page, page_size=page_size)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_my_conversation(conversation_id: uuid.UUID, service: Chat, actor: CurrentActor):
    return service.get_conversation(actor, conversation_id)


@router.get("/conversations/{conversation_id}/messages", response_model=PageResponse[MessageResponse])
def list_my_messages(conversation_id: uuid.UUID, service: Chat, actor: CurrentActor, page: Page = 1,
                     page_size: PageSize = 50):
    return service.list_messages(actor, conversation_id, page=page, page_size=page_size)


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse,
             status_code=status.HTTP_201_CREATED)
def send_my_message(conversation_id: uuid.UUID, data: MessageCreate, service: Chat, actor: CurrentActor):
    return service.send_message(actor, conversation_id, data)


@router.post("/conversations/{conversation_id}/close", response_model=ConversationResponse)
def close_my_conversation(conversation_id: uuid.UUID, service: Chat, actor: CurrentActor):
    return service.close_conversation(actor, conversation_id)


# ------------------------------------------------------------------ staff inbox


@admin_router.get("/conversations", response_model=PageResponse[AdminConversationResponse])
def admin_list_conversations(service: Chat, actor: CurrentActor, status_filter: StatusFilter = None,
                             mode: str | None = None, page: Page = 1, page_size: PageSize = 20):
    """All conversations (Admin only)."""
    return service.admin_list_conversations(actor, status=status_filter, mode=mode, page=page, page_size=page_size)


@admin_router.get("/conversations/unassigned", response_model=PageResponse[AdminConversationResponse])
def list_unassigned_conversations(service: Chat, actor: CurrentActor, page: Page = 1, page_size: PageSize = 20):
    return service.list_unassigned_conversations(actor, page=page, page_size=page_size)


@admin_router.get("/conversations/active", response_model=PageResponse[AdminConversationResponse])
def list_active_conversations(service: Chat, actor: CurrentActor, page: Page = 1, page_size: PageSize = 20):
    """Customers currently being helped by any staff member, with who is helping (Admin only)."""
    return service.list_active_conversations(actor, page=page, page_size=page_size)


@admin_router.get("/conversations/assigned", response_model=PageResponse[AdminConversationResponse])
def list_assigned_conversations(service: Chat, actor: CurrentActor, status_filter: StatusFilter = None,
                                page: Page = 1, page_size: PageSize = 20):
    """Conversations claimed by the signed-in staff member."""
    return service.list_assigned_conversations(actor, status=status_filter, page=page, page_size=page_size)


@admin_router.post("/conversations/{conversation_id}/claim", response_model=AdminConversationResponse)
def claim_conversation(conversation_id: uuid.UUID, service: Chat, actor: CurrentActor):
    return service.claim_conversation(actor, conversation_id)


@admin_router.get("/conversations/{conversation_id}", response_model=AdminConversationDetailResponse)
def admin_get_conversation(conversation_id: uuid.UUID, service: Chat, actor: CurrentActor):
    return service.get_conversation(actor, conversation_id)


@admin_router.get('/conversations/{conversation_id}/summary', response_model=AdminConversationResponse)
def conversation_summary(conversation_id: uuid.UUID, service: Chat, actor: CurrentActor):
    return service.get_summary(actor, conversation_id)


@admin_router.get('/conversations/{conversation_id}/message-window', response_model=PageResponse[AdminMessageResponse])
def message_window(conversation_id: uuid.UUID, service: Chat, actor: CurrentActor,
                   limit: Annotated[int, Query(ge=1, le=100)] = 50, latest: bool = False,
                   after_sent_at: datetime | None = None, after_message_id: uuid.UUID | None = None,
                   before_sent_at: datetime | None = None, before_message_id: uuid.UUID | None = None):
    if (after_sent_at is None) != (after_message_id is None) or (before_sent_at is None) != (before_message_id is None):
        raise BusinessRuleError('Cần cả thời gian và mã tin nhắn để phân trang', code='invalid_message_cursor')
    return service.message_window(actor, conversation_id, limit=limit, latest=latest,
                                  after=(after_sent_at, after_message_id) if after_sent_at else None,
                                  before=(before_sent_at, before_message_id) if before_sent_at else None)


@admin_router.post('/conversations/{conversation_id}/read', response_model=dict[str, int])
def mark_messages_read(conversation_id: uuid.UUID, data: MessageReadRequest, service: Chat, actor: CurrentActor):
    return service.mark_messages_read(actor, conversation_id, data.MessageIds)


@admin_router.get("/conversations/{conversation_id}/messages", response_model=PageResponse[AdminMessageResponse])
def admin_list_messages(conversation_id: uuid.UUID, service: Chat, actor: CurrentActor, page: Page = 1,
                        page_size: PageSize = 50):
    return service.list_messages(actor, conversation_id, page=page, page_size=page_size)


@admin_router.post("/conversations/{conversation_id}/messages", response_model=AdminMessageResponse,
                   status_code=status.HTTP_201_CREATED)
def admin_send_message(conversation_id: uuid.UUID, data: MessageCreate, service: Chat, actor: CurrentActor):
    return service.send_message(actor, conversation_id, data)


@admin_router.post("/conversations/{conversation_id}/close", response_model=AdminConversationResponse)
def admin_close_conversation(conversation_id: uuid.UUID, service: Chat, actor: CurrentActor):
    return service.close_conversation(actor, conversation_id)
