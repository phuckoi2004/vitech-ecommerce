"""Chat service: hội thoại Customer với nhân viên (Staff) hoặc chatbot (AI) — chỉ nghiệp vụ, KHÔNG gọi AI provider.

Nguồn nghiệp vụ: docs/business-requirements.md mục 14 và quyết định đợt 5.3:
- Mode AI/Staff; SenderType Customer/Staff/AI; MessageType Text/Image/Product (CHECK ở migration c8d2f4a6b1e3).
- Mỗi Customer tối đa một hội thoại Open: khóa dòng Users của Customer (FOR UPDATE) rồi kiểm tra; UNIQUE INDEX
  "UX_Conversations_CustomerId_Open" là lớp chặn cuối khi hai yêu cầu đồng thời. Đã có hội thoại Open cùng chế độ →
  trả lại hội thoại đó; khác chế độ → lỗi ``open_conversation_exists`` (không tự đóng hội thoại cũ).
- Staff (Admin kế thừa chức năng Staff — business-requirements mục 2) tự nhận hội thoại Staff đang Open chưa gán:
  khóa dòng Conversation rồi kiểm tra; đã có người nhận → lỗi, không ghi đè. Không có chức năng chuyển giao.
- Quyền xem: Customer — hội thoại của mình; Staff — hội thoại được gán cho mình + hàng đợi (Open, Mode Staff, chưa
  gán); Admin — mọi hội thoại. Không có quyền → "không tìm thấy" (không tiết lộ hội thoại tồn tại).
- Gửi tin: Customer trong hội thoại của mình; Staff/Admin chỉ khi đã được gán. SenderUserId/SenderType do server
  gán theo Actor (client không gửi được). Tin AI chỉ qua ``record_ai_reply`` (nội bộ, cho dịch vụ AI tích hợp sau
  này; không gọi từ Router). Hội thoại đã đóng không nhận tin mới.
- Đóng hội thoại (đợt 5.3.1): Customer đóng hội thoại của chính mình (AI hoặc Staff — ví dụ kết thúc chat AI để mở
  hội thoại với nhân viên); Staff/Admin đóng hội thoại đang được gán cho chính mình (xử lý xong). Khóa dòng
  Conversation nên đóng đồng thời → yêu cầu sau thấy đã đóng. Không mở lại, không tự đóng theo thời gian, không đổi
  Mode của hội thoại (không có thao tác cập nhật hội thoại tổng quát).
- Content tối đa 5.000 ký tự sau khi bỏ khoảng trắng đầu/cuối (Schema + Service); không tự cắt ngắn.
- Dữ liệu trả về (đợt 5.10): Customer nhận ConversationResponse/MessageResponse (không có AssignedStaffId; tin của nhân
  viên không kèm SenderUserId); Staff/Admin nhận AdminConversationResponse/AdminMessageResponse.
"""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models import Conversation
from app.models.chat import CONVERSATION_MODES, MESSAGE_CONTENT_MAX_LENGTH, MESSAGE_TYPES
from app.repositories import ConversationRepository, MessageRepository, ProductRepository, UserRepository
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

from .actor import ANY_ROLE, CUSTOMER_ONLY, STAFF_OR_ADMIN, Actor, has_role, require_role
from .base import BaseService, utc_now
from .catalog import is_product_sellable
from .exceptions import BusinessRuleError, ConflictError, NotFoundError

STATUS_OPEN = "Open"
STATUS_CLOSED = "Closed"
MODE_AI = "AI"
MODE_STAFF = "Staff"
SENDER_CUSTOMER = "Customer"
SENDER_STAFF = "Staff"
SENDER_AI = "AI"
TYPE_TEXT = "Text"
TYPE_IMAGE = "Image"
TYPE_PRODUCT = "Product"
IMAGE_URL_MAX_LENGTH = 500  # cùng giới hạn với các cột ImageUrl khác (varchar(500))
MESSAGE_FIELDS = frozenset({"MessageType", "Content", "Metadata"})


class ChatService(BaseService):
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        super().__init__(session, clock=clock)
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.users = UserRepository(session)
        self.products = ProductRepository(session)

    # ------------------------------------------------------------------ Customer

    def start_conversation(self, actor: Actor, data: ConversationCreate) -> ConversationResponse:
        """Customer mở hội thoại (AI hoặc Staff); đã có hội thoại Open cùng chế độ thì trả lại hội thoại đó."""
        require_role(actor, *CUSTOMER_ONLY)
        values = dict(data.model_dump(exclude_unset=True))
        not_allowed = sorted(set(values) - {"Mode"})
        if not_allowed:  # CustomerId/Status/AssignedStaffId do server quyết định
            raise BusinessRuleError(f"Không được gửi các trường: {not_allowed}", code="conversation_field_not_allowed")
        mode = values.get("Mode")
        if mode not in CONVERSATION_MODES:
            raise BusinessRuleError("Chế độ hội thoại không hợp lệ", code="invalid_conversation_mode")
        if self.in_transaction():
            raise BusinessRuleError("Mở hội thoại phải là use case độc lập", code="conversation_requires_own_transaction")
        try:
            with self.transaction():
                customer = self.users.get_by_id_for_update(actor.user_id)  # tuần tự hóa theo Customer
                if customer is None or customer.IsDeleted:
                    raise NotFoundError("Không tìm thấy tài khoản", code="user_not_found")
                existing = self.conversations.get_open_by_customer(actor.user_id)
                if existing is not None:
                    return self._reuse_open(existing, mode)
                conversation = self.conversations.create(
                    {"CustomerId": actor.user_id, "Mode": mode, "Status": STATUS_OPEN, "CreatedAt": self.now()}
                )
                self.conversations.flush()
                return ConversationResponse.model_validate(conversation)
        except ConflictError as exc:
            if exc.code != "open_conversation_exists":
                raise
            # Yêu cầu đồng thời khác vừa tạo hội thoại Open (UNIQUE INDEX): dùng hội thoại đó, không tạo trùng.
            existing = self.conversations.get_open_by_customer(actor.user_id)
            if existing is None:
                raise
            return self._reuse_open(existing, mode)

    def list_my_conversations(
        self, actor: Actor, *, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> PageResponse[ConversationResponse]:
        require_role(actor, *CUSTOMER_ONLY)
        return self._page(customer_id=actor.user_id, status=status, page=page, page_size=page_size)

    # ------------------------------------------------------------------ Staff / Admin

    def list_unassigned_conversations(
        self, actor: Actor, *, page: int = 1, page_size: int = 20
    ) -> PageResponse[AdminConversationResponse]:
        """Hàng đợi để nhân viên nhận: hội thoại Staff đang Open, chưa có người nhận."""
        require_role(actor, *STAFF_OR_ADMIN)
        return self._page(status=STATUS_OPEN, mode=MODE_STAFF, unassigned=True, page=page, page_size=page_size,
                          schema=AdminConversationResponse)

    def list_assigned_conversations(
        self, actor: Actor, *, status: str | None = None, page: int = 1, page_size: int = 20
    ) -> PageResponse[AdminConversationResponse]:
        require_role(actor, *STAFF_OR_ADMIN)
        return self._page(assigned_staff_id=actor.user_id, status=status, page=page, page_size=page_size,
                          schema=AdminConversationResponse)

    def admin_list_conversations(
        self,
        actor: Actor,
        *,
        status: str | None = None,
        mode: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PageResponse[AdminConversationResponse]:
        require_role(actor, "Admin")
        if mode is not None and mode not in CONVERSATION_MODES:
            raise BusinessRuleError("Chế độ hội thoại không hợp lệ", code="invalid_conversation_mode")
        return self._page(status=status, mode=mode, page=page, page_size=page_size, schema=AdminConversationResponse)

    def claim_conversation(self, actor: Actor, conversation_id: uuid.UUID) -> AdminConversationResponse:
        """Nhân viên tự nhận hội thoại Staff đang Open, chưa gán (khóa dòng: hai người nhận đồng thời → người sau lỗi)."""
        require_role(actor, *STAFF_OR_ADMIN)
        with self.transaction():
            conversation = self._lock(conversation_id)
            if conversation.AssignedStaffId == actor.user_id:
                return AdminConversationResponse.model_validate(conversation)  # gọi lặp: không đổi gì
            if conversation.Status != STATUS_OPEN:
                raise BusinessRuleError("Hội thoại đã đóng", code="conversation_closed")
            if conversation.AssignedStaffId is not None:
                raise ConflictError("Hội thoại đã được nhân viên khác nhận", code="conversation_already_claimed")
            if conversation.Mode != MODE_STAFF:
                raise BusinessRuleError("Chỉ nhận hội thoại ở chế độ nhân viên", code="conversation_not_claimable")
            conversation.AssignedStaffId = actor.user_id
            self.conversations.flush()
            return AdminConversationResponse.model_validate(conversation)

    def close_conversation(
        self, actor: Actor, conversation_id: uuid.UUID
    ) -> ConversationResponse | AdminConversationResponse:
        """Đóng hội thoại (không mở lại).

        Customer: hội thoại của chính mình. Staff/Admin: hội thoại đang được gán cho chính mình. Đã đóng → lỗi, không
        đổi ClosedAt. Khóa dòng Conversation: Customer và nhân viên cùng đóng → người sau thấy đã đóng.
        """
        require_role(actor, *ANY_ROLE)
        with self.transaction():
            conversation = self._lock(conversation_id)
            if not self._can_view(actor, conversation):
                raise NotFoundError("Không tìm thấy hội thoại", code="conversation_not_found")
            if not has_role(actor, "Customer") and conversation.AssignedStaffId != actor.user_id:
                raise BusinessRuleError(
                    "Chỉ nhân viên đang phụ trách được đóng hội thoại", code="conversation_not_assigned_to_you"
                )
            if conversation.Status != STATUS_OPEN:
                raise BusinessRuleError("Hội thoại đã đóng", code="conversation_closed")
            conversation.Status = STATUS_CLOSED
            conversation.ClosedAt = self.now()
            self.conversations.flush()
            return _conversation_schema(actor).model_validate(conversation)

    # ------------------------------------------------------------------ Xem

    def get_conversation(
        self, actor: Actor, conversation_id: uuid.UUID
    ) -> ConversationDetailResponse | AdminConversationDetailResponse:
        require_role(actor, *ANY_ROLE)
        conversation = self.conversations.get_detail(conversation_id)
        if conversation is None or not self._can_view(actor, conversation):
            raise NotFoundError("Không tìm thấy hội thoại", code="conversation_not_found")
        schema = ConversationDetailResponse if has_role(actor, "Customer") else AdminConversationDetailResponse
        return schema.model_validate(conversation)

    def list_messages(
        self, actor: Actor, conversation_id: uuid.UUID, *, page: int = 1, page_size: int = 50
    ) -> PageResponse[MessageResponse] | PageResponse[AdminMessageResponse]:
        require_role(actor, *ANY_ROLE)
        conversation = self.conversations.get_by_id(conversation_id)
        if conversation is None or not self._can_view(actor, conversation):
            raise NotFoundError("Không tìm thấy hội thoại", code="conversation_not_found")
        offset, limit = self._page_args(page, page_size)
        items = self.messages.list_by_conversation(conversation_id, offset=offset, limit=limit)
        schema = _message_schema(actor)
        return PageResponse[schema](
            Items=[schema.model_validate(m) for m in items],
            Total=self.messages.count_by_conversation(conversation_id),
            Page=page,
            PageSize=page_size,
        )

    # ------------------------------------------------------------------ Gửi tin

    def send_message(
        self, actor: Actor, conversation_id: uuid.UUID, data: MessageCreate
    ) -> MessageResponse | AdminMessageResponse:
        """Customer/Staff gửi tin; người gửi và SenderType lấy từ Actor, không từ dữ liệu client."""
        require_role(actor, *ANY_ROLE)
        values = dict(data.model_dump(exclude_unset=True))
        not_allowed = sorted(set(values) - MESSAGE_FIELDS)
        if not_allowed:  # SenderType/SenderUserId/ConversationId... do server gán (chặn cả khi schema bị bỏ qua)
            raise BusinessRuleError(f"Không được gửi các trường: {not_allowed}", code="message_field_not_allowed")
        message_type, content, metadata = _validate_message(values)
        with self.transaction():
            conversation = self._lock(conversation_id)
            sender_type = self._sender_type(actor, conversation)
            if conversation.Status != STATUS_OPEN:
                raise BusinessRuleError("Hội thoại đã đóng, không gửi thêm tin nhắn", code="conversation_closed")
            if message_type == TYPE_PRODUCT:
                metadata = self._product_metadata(metadata["ProductId"])
            message = self.messages.create(
                {
                    "ConversationId": conversation.ConversationId,
                    "SenderUserId": actor.user_id,
                    "SenderType": sender_type,
                    "MessageType": message_type,
                    "Content": content,
                    "Metadata": metadata,
                    "IsRead": False,
                    "SentAt": self.now(),
                }
            )
            self.messages.flush()
            return _message_schema(actor).model_validate(message)

    def record_ai_reply(self, conversation_id: uuid.UUID, content: str) -> AdminMessageResponse:
        """NỘI BỘ: lưu câu trả lời do dịch vụ AI tích hợp tạo cho hội thoại Mode AI (SenderType AI, không gắn
        SenderUserId). Chưa có AI provider; KHÔNG gọi từ Router và không dùng để tạo nội dung AI giả."""
        text = content.strip() if isinstance(content, str) else ""
        if not text:
            raise BusinessRuleError("Nội dung tin nhắn không được để trống", code="message_content_required")
        _check_content_length(text)
        with self.transaction():
            conversation = self._lock(conversation_id)
            if conversation.Mode != MODE_AI:
                raise BusinessRuleError("Hội thoại không ở chế độ AI", code="conversation_not_ai_mode")
            if conversation.Status != STATUS_OPEN:
                raise BusinessRuleError("Hội thoại đã đóng, không gửi thêm tin nhắn", code="conversation_closed")
            message = self.messages.create(
                {
                    "ConversationId": conversation.ConversationId,
                    "SenderUserId": None,
                    "SenderType": SENDER_AI,
                    "MessageType": TYPE_TEXT,
                    "Content": text,
                    "Metadata": None,
                    "IsRead": False,
                    "SentAt": self.now(),
                }
            )
            self.messages.flush()
            return AdminMessageResponse.model_validate(message)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _reuse_open(existing: Conversation, mode: str) -> ConversationResponse:
        if existing.Mode != mode:
            raise BusinessRuleError(
                "Đang có hội thoại mở ở chế độ khác; không mở thêm hội thoại", code="open_conversation_exists"
            )
        return ConversationResponse.model_validate(existing)

    def _lock(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = self.conversations.get_by_id_for_update(conversation_id)
        if conversation is None:
            raise NotFoundError("Không tìm thấy hội thoại", code="conversation_not_found")
        return conversation

    @staticmethod
    def _can_view(actor: Actor, conversation: Conversation) -> bool:
        if has_role(actor, "Admin"):
            return True
        if has_role(actor, "Staff"):
            in_queue = (
                conversation.AssignedStaffId is None
                and conversation.Status == STATUS_OPEN
                and conversation.Mode == MODE_STAFF
            )
            return conversation.AssignedStaffId == actor.user_id or in_queue
        return has_role(actor, "Customer") and conversation.CustomerId == actor.user_id

    def _sender_type(self, actor: Actor, conversation: Conversation) -> str:
        """Kiểm tra quyền gửi và trả SenderType theo vai trò thật của người gửi."""
        if not self._can_view(actor, conversation):
            raise NotFoundError("Không tìm thấy hội thoại", code="conversation_not_found")
        if has_role(actor, "Customer"):
            return SENDER_CUSTOMER
        if conversation.AssignedStaffId != actor.user_id:
            raise BusinessRuleError("Phải nhận hội thoại trước khi trả lời", code="conversation_not_assigned_to_you")
        return SENDER_STAFF

    def _product_metadata(self, product_id: uuid.UUID) -> dict[str, Any]:
        """Sản phẩm phải đang hiển thị công khai; thông tin trong Metadata do server ghi (không đổi dữ liệu sản phẩm)."""
        product = self.products.get_by_id(product_id)
        if not is_product_sellable(product):
            raise NotFoundError("Không tìm thấy sản phẩm", code="product_not_found")
        return {"ProductId": str(product.ProductId), "ProductName": product.Name, "Slug": product.Slug}

    def _page(
        self, *, page: int, page_size: int, schema: type[ConversationResponse] = ConversationResponse, **filters: Any
    ) -> PageResponse[ConversationResponse]:
        status = filters.get("status")
        if status is not None and status not in (STATUS_OPEN, STATUS_CLOSED):
            raise BusinessRuleError("Trạng thái hội thoại không hợp lệ", code="invalid_conversation_status")
        offset, limit = self._page_args(page, page_size)
        items = self.conversations.list_conversations(**filters, offset=offset, limit=limit)
        return PageResponse[schema](
            Items=[schema.model_validate(c) for c in items],
            Total=self.conversations.count_conversations(**filters),
            Page=page,
            PageSize=page_size,
        )


def _conversation_schema(actor: Actor) -> type[ConversationResponse]:
    """Customer: không có AssignedStaffId; Staff/Admin: đủ thông tin phân công."""
    return ConversationResponse if has_role(actor, "Customer") else AdminConversationResponse


def _message_schema(actor: Actor) -> type[MessageResponse] | type[AdminMessageResponse]:
    """Customer: tin của nhân viên không kèm SenderUserId; Staff/Admin: đủ người gửi."""
    return MessageResponse if has_role(actor, "Customer") else AdminMessageResponse


def _validate_message(values: dict[str, Any]) -> tuple[str, str, Any]:
    """Kiểm tra loại tin và dữ liệu đi kèm; trả (MessageType, Content, Metadata). Product: Metadata = {ProductId: UUID}."""
    message_type = values.get("MessageType")
    if message_type not in MESSAGE_TYPES:
        raise BusinessRuleError("Loại tin nhắn không hợp lệ", code="invalid_message_type")
    raw_content = values.get("Content", "")
    if not isinstance(raw_content, str):
        raise BusinessRuleError("Nội dung tin nhắn không hợp lệ", code="invalid_message_content")
    content = raw_content.strip()
    _check_content_length(content)
    metadata = values.get("Metadata")
    if message_type == TYPE_TEXT:
        if not content:
            raise BusinessRuleError("Nội dung tin nhắn không được để trống", code="message_content_required")
        if metadata:
            raise BusinessRuleError("Tin nhắn văn bản không kèm Metadata", code="message_metadata_not_allowed")
        return message_type, content, None
    if not isinstance(metadata, dict) or not metadata:
        raise BusinessRuleError("Thiếu dữ liệu đính kèm của tin nhắn", code="message_metadata_required")
    if message_type == TYPE_IMAGE:
        if set(metadata) != {"ImageUrl"}:
            raise BusinessRuleError("Tin nhắn ảnh chỉ gồm ImageUrl", code="invalid_image_message")
        url = metadata["ImageUrl"].strip() if isinstance(metadata["ImageUrl"], str) else ""
        parsed = urlparse(url)
        if (not url or len(url) > IMAGE_URL_MAX_LENGTH or any(ch.isspace() for ch in url)
                or parsed.scheme != "https" or not parsed.netloc):
            raise BusinessRuleError("Địa chỉ ảnh phải là URL https hợp lệ", code="invalid_image_url")
        return message_type, content, {"ImageUrl": url}
    if set(metadata) != {"ProductId"}:
        raise BusinessRuleError("Tin nhắn sản phẩm chỉ gồm ProductId", code="invalid_product_message")
    try:
        product_id = uuid.UUID(str(metadata["ProductId"]))
    except (ValueError, TypeError, AttributeError):
        raise BusinessRuleError("ProductId không hợp lệ", code="invalid_product_message") from None
    return message_type, content, {"ProductId": product_id}


def _check_content_length(content: str) -> None:
    """Content (đã bỏ khoảng trắng đầu/cuối) tối đa MESSAGE_CONTENT_MAX_LENGTH ký tự; không áp cho URL/Metadata."""
    if len(content) > MESSAGE_CONTENT_MAX_LENGTH:
        raise BusinessRuleError(
            f"Nội dung tin nhắn tối đa {MESSAGE_CONTENT_MAX_LENGTH} ký tự", code="message_content_too_long"
        )
