"""Managed AI turns: short DB phases, durable leases, replay and bounded retries.

Stage 10.3: bounded local tools and verified catalog facts/product references.
Catalog-based advice: before the first model round the backend reads the question with the saved conversation state
(intent, inherited slots, "máy thứ hai", products already shown) and runs the obvious catalog reads; Gemini gets that
as data. Wishlist, cart and order history take no part in what is recommended.
"""

import logging
import json
import re
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError

from app.core.ai_config import AiSettings
from app.core.auth_state import StateStore
from app.integrations.ai import ChatCompletion, ChatModel
from app.prompts.vietech_ai import VIETECH_SYSTEM_PROMPT
from app.prompts.vietech_ai_protocol import VIETECH_TOOL_PROTOCOL
from app.repositories.chat import ConversationRepository, MessageRepository
from app.repositories.user import UserRepository
from app.schemas.ai_chat import (AiMessageCancel, AiMessageCreate, AiTurnResponse, PresentAnswerArguments,
                                  ProductSelection)
from app.schemas.chat import MessageResponse

from .actor import Actor, require_role
from .base import BaseService
from .ai_intent import ConversationState, PastTurn, new_shopping_request, slots_from_constraints
from .ai_tools import AiTools, GroundingContext, TOOL_SCHEMAS, tool_definitions
from .compatibility_intent import compatibility_question
from .exceptions import AiUnavailableError, BusinessRuleError, ConflictError, NotFoundError, TooManyRequestsError

logger = logging.getLogger(__name__)

REPAIR_NOTE = (
    "Lệnh gọi công cụ vừa rồi bị từ chối (JSON sai hoặc công cụ không có trong danh sách của lượt này). Chỉ gọi công cụ "
    "đang được cung cấp, đúng schema; với present_answer chỉ gửi intent, products [{product_id, product_variant_id?, "
    "specification_keys?}], clarification và message."
)
# Stage 10.7: a comparison (search, search, get, get) uses all four rounds; the model then tried to read more.
FINAL_NOTE = "Đã hết lượt tra cứu. Gọi present_answer ngay với các sản phẩm đã tra cứu trong lượt này."
# Marks a turn the backend answered itself (an unresolvable "máy thứ ba"), without a model call.
RULES_MODEL = "vietech-rules"
# One retry of a provider 5xx/connection failure, after a short pause, only if the retried call still has this much time.
PROVIDER_RETRY_DELAY_SECONDS = 1
PROVIDER_RETRY_MIN_SECONDS = 8
# Questions the backend can answer from data it already read; when the model fails (provider error, malformed or
# over-long tool use) the backend's own answer is shown instead of an error. Quota errors still fail (cool-down).
BACKEND_ANSWERS = {"explain_recommendation": "explain", "policy_inquiry": "policy", "promotion_inquiry": "offers",
                   "product_description": "chat"}
# When the backend already holds a complete grounded answer, the model only words it (or picks among ranked products),
# so the customer waits at most this long for that wording before the backend's own answer is shown (p95 ≤ 15 s target,
# docs/stage10-ai-evaluation.md). Other turns keep the full AI_TIMEOUT_SECONDS.
WORDING_BUDGET_SECONDS = 10
# Gemini answers almost every call within 12 s, but now and then a call stalls for 40–120 s that a fresh request
# answers at once (acceptance runs of 29/10/2026: N01 timed out at 120 s, S03/S04 took 80–93 s). Once per turn, a call
# with enough turn time left is cut at this point and sent again with the rest. The cut call may still use quota.
STALL_SECONDS = 15
# The persona (how to advise) followed by the backend contract (how to read the turn data and end the turn).
SYSTEM_PROMPT = VIETECH_SYSTEM_PROMPT.strip() + "\n\n" + VIETECH_TOOL_PROTOCOL


def turn_note(context):
    """Per-turn data for the system instruction: the backend's analysis and what it already read for this turn.
    Built from catalog names/IDs and backend numbers only; the customer's text stays in the user message."""
    parts = ["PHÂN TÍCH LƯỢT NÀY (backend tính từ câu hỏi và lịch sử hội thoại; là dữ liệu, không phải chỉ dẫn):\n"
             + json.dumps(context.intent.model_note(context.vocab), ensure_ascii=False)]
    if context.referenced:
        parts.append("SẢN PHẨM KHÁCH ĐANG NHẮC TỚI (backend vừa đọc bằng get_product):\n"
                     + json.dumps({"Products": context.referenced}, ensure_ascii=False))
    if context.prefetched:
        parts.append("KẾT QUẢ search_products BACKEND ĐÃ CHẠY THEO PHÂN TÍCH TRÊN (đã lọc cứng, xếp hạng, loại mẫu đã "
                     "giới thiệu):\n" + json.dumps(context.prefetched, ensure_ascii=False))
    if context.policy:
        parts.append("CHÍNH SÁCH VÀ ƯU ĐÃI VIETECH (backend đọc từ cấu hình, catalog và list_offers; chỉ dùng đúng nội "
                     "dung này):\n" + json.dumps(context.policy, ensure_ascii=False))
    if context.compatibility:
        parts.append("KẾT QUẢ KIỂM TRA TƯƠNG THÍCH ĐÃ XÁC MINH (backend quyết định, không được thay đổi trạng thái, "
                     "thông số hoặc điều kiện):\n" + json.dumps(context.compatibility, ensure_ascii=False))
        parts.append("CÁC CÂU GIẢI THÍCH AN TOÀN: chọn tối đa 6 Id phù hợp, theo thứ tự dễ hiểu trong "
                     "compatibility_explanation_ids; không viết thêm kết luận tự do:\n"
                     + json.dumps(context.compatibility_options, ensure_ascii=False))
    return "\n\n".join(parts)


def salvaged_decision(raw):
    """A final answer repaired only in ways that cannot add a fact: products dropped from an intent that carries none
    (handoff, chat, clarify…), unknown fields and repeated selections dropped, explanation ids kept only for a
    compatibility answer, and an over-long message dropped so the backend's own text is shown. None if still invalid."""
    if not isinstance(raw, str) or len(raw) > 4000:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    data = {key: value for key, value in data.items() if key in PresentAnswerArguments.model_fields}
    products = data.get("products")
    if data.get("intent") in ("clarify", "handoff", "no_results", "offers", "chat"):
        data["products"] = []
    elif isinstance(products, list):
        known = ProductSelection.model_fields
        cleaned, seen = [], set()
        for item in products:
            if isinstance(item, dict):
                item = {key: value for key, value in item.items() if key in known}
                identity = (item.get("product_id"), item.get("product_variant_id") if data.get("intent") == "compare" else None)
                if identity not in seen:
                    seen.add(identity)
                    cleaned.append(item)
        data["products"] = cleaned[:5]
    if isinstance(data.get("message"), str) and len(data["message"]) > 1500:
        data["message"] = None
    if data.get("intent") != "compatibility":
        data.pop("compatibility_explanation_ids", None)
    try:
        return PresentAnswerArguments.model_validate(data)
    except ValidationError:
        return None


def model_text(text: str) -> str:
    """Minimize accidental email/phone disclosure in free-form chat; never loads user profiles."""
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email đã ẩn]", text)
    return re.sub(r"(?<!\w)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\w)", "[điện thoại đã ẩn]", text)


class AiChatService(BaseService):
    def __init__(self, session, *, settings: AiSettings, model: ChatModel, state: StateStore,
                 timer=time.monotonic, sleep=time.sleep, **kwargs):
        super().__init__(session, **kwargs)
        self.settings, self.model, self.state = settings, model, state
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.users = UserRepository(session)
        self.timer, self.sleep = timer, sleep

    def ask(self, actor: Actor, conversation_id: uuid.UUID, data: AiMessageCreate) -> AiTurnResponse:
        require_role(actor, "Customer")
        # Revalidate at the service boundary, including callers that bypass a router/schema.
        data = AiMessageCreate.model_validate(data.model_dump())
        if len(data.Content) > self.settings.input_max_chars:
            raise BusinessRuleError("Câu hỏi vượt giới hạn ký tự", code="ai_input_too_long")
        if self.in_transaction():
            raise BusinessRuleError("Gửi câu hỏi AI phải là nghiệp vụ độc lập", code="ai_requires_own_transaction")
        prepared, ticket, history, state = self._prepare(actor, conversation_id, data)
        # The auth dependency can have opened a read transaction on this same Session.
        # _prepare committed it; close/reset also clears identity-map state before network I/O.
        self.session.close()
        if ticket is None:
            return prepared
        started = self.timer()
        try:
            context = GroundingContext(data.Content, state=state)
            self._analyze(actor, conversation_id, data.ClientRequestId, ticket, context, history)
            cooldown = self._cooldown_remaining()
            if context.intent.transaction:
                # "Đặt giúp tôi … và thanh toán luôn": the assistant never orders or pays, so the answer is fixed; a
                # model round once answered it with a product list that placed nothing (S05).
                completion = ChatCompletion("", RULES_MODEL)
                decision = PresentAnswerArguments(intent="handoff")
            elif context.intent.intent == "comparison_guidance":
                completion = ChatCompletion("", RULES_MODEL)
                decision = PresentAnswerArguments(intent="chat")
            elif context.intent.clarification:
                # "Máy thứ ba" after a two-item list: ask which product is meant instead of guessing.
                completion = ChatCompletion("", RULES_MODEL)
                decision = PresentAnswerArguments(intent="clarify", clarification="products")
            elif context.comparison is not None:
                # Smart Compare with its exact SKUs resolved: the table and its analysis come from the catalog and the
                # Recommendation Engine, and model wording is never shown for them (AiTools._comparison). A model round
                # could not change the answer; it would only add latency, quota use and a failure mode.
                completion = ChatCompletion("", RULES_MODEL)
                decision = PresentAnswerArguments(intent="compare", products=[
                    {"product_id": ref["ProductId"], "product_variant_id": ref["ProductVariantId"]}
                    for ref in context.intent.references])
            elif ((context.intent.recommending or context.intent.comparison_search)
                  and context.prefetched is not None and not context.prefetched["Products"]
                  and not context.hidden):
                # Nothing in the catalog passes the hard filters. The model may not loosen the customer's conditions, so
                # more searches cannot change that: the backend answers (nearest product above the budget included).
                # "Everything suitable was already shown" (hidden) still goes to the model, which suggests what to relax.
                completion = ChatCompletion("", RULES_MODEL)
                decision = PresentAnswerArguments(intent="no_results")
            elif cooldown and context.compatibility is not None:
                # Gemini is cooling down after a quota error. The verified rule result and its backend explanation
                # do not need the model, so the customer still gets them instead of a quota error.
                context.compatibility_fallback = True
                completion, decision = ChatCompletion("", RULES_MODEL), PresentAnswerArguments(intent="compatibility")
            elif cooldown:
                raise AiUnavailableError("AI tạm hết hạn mức. Vui lòng thử lại sau.", code="ai_quota_exceeded",
                                         retry_after_seconds=cooldown)
            else:
                ranked = self._ranked_answer(context)
                budget = WORDING_BUDGET_SECONDS if (
                    context.compatibility is not None or ranked is not None
                    or (BACKEND_ANSWERS.get(context.intent.intent) and not self._offers_missing(context))) else None
                try:
                    completion, decision = self._reply_with_tools(actor, conversation_id, data.ClientRequestId,
                                                                  ticket, history, context, budget=budget)
                except AiUnavailableError as error:
                    fallback = BACKEND_ANSWERS.get(context.intent.intent)
                    if context.compatibility is not None:
                        context.compatibility_fallback = True
                        self._provider_cooldown(error)
                        fallback = "compatibility"
                    elif fallback is None and ranked is not None:
                        fallback = "recommend"  # The backend's ranked candidates, in its own order and wording.
                    if fallback is None or (error.code == "ai_quota_exceeded" and fallback != "compatibility") or (
                            fallback == "offers" and self._offers_missing(context)):
                        raise
                    logger.warning("AI model failed, backend answer used request_id=%s intent=%s code=%s",
                                   data.ClientRequestId, context.intent.intent, error.code)
                    completion = ChatCompletion("", RULES_MODEL)
                    decision = ranked if fallback == "recommend" else PresentAnswerArguments(intent=fallback)
            return self._finish(actor, conversation_id, data.ClientRequestId, ticket, completion, decision, context)
        except Exception as error:
            self._fail(conversation_id, data.ClientRequestId, ticket, error)
            source = error.__context__
            provider_status = getattr(source, "status_code", None)
            logger.warning("AI turn failed request_id=%s model=%s code=%s error_type=%s provider_error_type=%s "
                           "provider_status=%s elapsed_ms=%d", data.ClientRequestId, self.settings.model,
                           getattr(error, "code", "ai_unavailable"), type(error).__name__,
                           type(source).__name__ if source else None,
                           provider_status if isinstance(provider_status, int) else None,
                           round((self.timer() - started) * 1000))
            raise

    def get_status(self, actor: Actor, conversation_id: uuid.UUID, request_id: uuid.UUID) -> AiTurnResponse:
        require_role(actor, "Customer")
        with self.transaction():
            self._owned_ai(actor, conversation_id)
            question = self.messages.get_ai_request(conversation_id, request_id)
            if question is None:
                raise NotFoundError("Không tìm thấy yêu cầu AI", code="ai_request_not_found")
            self._expire(question)
            return self._response(question)

    def cancel(self, actor: Actor, conversation_id: uuid.UUID, request_id: uuid.UUID,
               data: AiMessageCancel) -> AiTurnResponse:
        require_role(actor, "Customer")
        data = AiMessageCancel.model_validate(data.model_dump())
        if len(data.Content) > self.settings.input_max_chars:
            raise BusinessRuleError("Câu hỏi vượt giới hạn ký tự", code="ai_input_too_long")
        with self.transaction():
            conversation = self._owned_ai(actor, conversation_id)
            question = self.messages.get_ai_request(conversation_id, request_id)
            if question is None:
                if conversation.Status != "Open":
                    raise BusinessRuleError("Hội thoại đã đóng", code="conversation_closed")
                # Serialize on the conversation lock, like _prepare: a late POST replays this terminal request.
                question = self.messages.create({
                    "MessageId": uuid.uuid4(), "ConversationId": conversation_id,
                    "SenderUserId": actor.user_id, "SenderType": "Customer", "MessageType": "Text",
                    "Content": data.Content, "IsRead": False, "SentAt": self.now(),
                    "Metadata": {"ClientRequestId": str(request_id), "AiProcessingStatus": "Cancelled",
                                 "AiAttemptCount": 0, "AiCancelledAt": self.now().isoformat()},
                })
            else:
                if question.Content != data.Content:
                    raise ConflictError("Mã yêu cầu đã được dùng cho câu hỏi khác", code="ai_request_content_conflict")
                if question.Metadata["AiProcessingStatus"] not in ("Completed", "Cancelled"):
                    question.Metadata = {**question.Metadata, "AiProcessingStatus": "Cancelled",
                                         "AiCancelledAt": self.now().isoformat()}
            self.messages.flush()
            return self._response(question)

    def _prepare(self, actor, conversation_id, data):
        with self.transaction():
            conversation = self._owned_ai(actor, conversation_id)
            question = self.messages.get_ai_request(conversation_id, data.ClientRequestId)
            if question is not None:
                if question.Content != data.Content:
                    raise ConflictError("Mã yêu cầu đã được dùng cho câu hỏi khác", code="ai_request_content_conflict")
                self._expire(question)
                if question.Metadata["AiProcessingStatus"] in ("Completed", "Pending", "Cancelled"):
                    return self._response(question), None, [], ConversationState()
            if conversation.Status != "Open":
                raise BusinessRuleError("Hội thoại đã đóng", code="conversation_closed")
            if question is not None and question.Metadata.get("AiRetryAfterAt"):
                deadline = datetime.fromisoformat(question.Metadata["AiRetryAfterAt"])
                remaining = (deadline - self.now()).total_seconds()
                if remaining > 0:
                    raise AiUnavailableError("AI tạm hết hạn mức. Vui lòng thử lại sau.",
                                             code="ai_quota_exceeded", retry_after_seconds=int(remaining) + 1)
            for pending in self.messages.pending_ai_requests(conversation_id):
                self._expire(pending)
                if pending.Metadata["AiProcessingStatus"] == "Pending":
                    raise ConflictError("AI đang xử lý câu hỏi trước", code="ai_conversation_busy")
            self.messages.flush()  # Release expired Pending unique-index entries before claiming.
            attempts = (question.Metadata or {}).get("AiAttemptCount", 0) if question else 0
            if attempts >= self.settings.max_attempts:
                raise ConflictError("Yêu cầu đã hết số lần thử lại", code="ai_retry_limit")
            history = state = None
            cooldown = self._cooldown_remaining()
            if cooldown:
                # Only a laptop/monitor check can be answered without Gemini; anything else is refused before it is
                # saved, as before. ask() checks the analysed intent again.
                history, state = self._history(conversation_id)
                if not compatibility_question(data.Content, state, new_request=new_shopping_request(data.Content)):
                    raise AiUnavailableError("AI tạm hết hạn mức. Vui lòng thử lại sau.", code="ai_quota_exceeded",
                                             retry_after_seconds=cooldown)
            self._rate_limit(actor)
            ticket = str(uuid.uuid4())
            metadata = {
                "ClientRequestId": str(data.ClientRequestId), "AiProcessingStatus": "Pending",
                "AiModel": self.settings.model,
                "AiLeaseToken": ticket, "AiLeaseExpiresAt": (self.now() + timedelta(
                    seconds=self.settings.lease_seconds)).isoformat(), "AiAttemptCount": attempts + 1,
            }
            if question is None:
                question = self.messages.create({
                    "MessageId": uuid.uuid4(), "ConversationId": conversation_id,
                    "SenderUserId": actor.user_id, "SenderType": "Customer", "MessageType": "Text",
                    "Content": data.Content, "Metadata": metadata, "IsRead": False, "SentAt": self.now(),
                })
            else:
                question.Metadata = metadata
            self.messages.flush()
            if state is None:  # Completed turns only: the request just claimed is not part of its own history.
                history, state = self._history(conversation_id)
            history.append({"role": "user", "content": model_text(data.Content)})
            return self._response(question), ticket, history, state

    def _analyze(self, actor, conversation_id, request_id, ticket, context, history):
        """Short authorized read phase: intent and context, referenced products, the ranked prefetch."""
        try:
            with self.transaction():
                conversation = self._owned_ai(actor, conversation_id)
                question = self.messages.get_ai_request(conversation_id, request_id)
                if conversation.Status != "Open" or not self._owns_ticket(question, ticket) or self._expired(question):
                    raise ConflictError("Lượt xử lý AI đã kết thúc", code="ai_request_superseded")
                AiTools(self.session, clock=self._clock, ranking=self.settings.ranking_enabled, actor=actor).prepare(context)
        finally:
            self.session.close()
        history[0] = {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + turn_note(context)}
        logger.info("AI turn analysis request_id=%s intent=%s follow_up=%s inherited=%s excluded=%d references=%d "
                    "prefetched=%s", request_id, context.intent.intent, context.intent.follow_up,
                    ",".join(context.intent.inherited) or "-", len(context.intent.excluded_product_ids),
                    len(context.intent.references), context.prefetched is not None)

    @staticmethod
    def _decision(raw):
        try:
            if not isinstance(raw, str) or len(raw) > 4000:  # Includes the model's message of up to 1.500 characters.
                raise ValueError
            return PresentAnswerArguments.model_validate_json(raw)
        except ValidationError as error:
            # Field names only (never the content), to see which rule the model keeps breaking.
            fields = ",".join(sorted({".".join(map(str, item["loc"])) or "answer" for item in error.errors()}))
            logger.warning("AI final answer invalid fields=%s", fields)
            raise AiUnavailableError("AI chưa trả được kết quả có cấu trúc hợp lệ.", code="ai_invalid_output") from None
        except ValueError:
            raise AiUnavailableError("AI chưa trả được kết quả có cấu trúc hợp lệ.", code="ai_invalid_output") from None

    def _ranked_answer(self, context):
        """The backend's own recommendation when its ranked, hard-filtered search found products: the top candidates
        (as many as asked, at most max_products). finish() re-reads and re-ranks them like a model's choice."""
        if not context.intent.recommending or not (context.prefetched or {}).get("Products"):
            return None
        count = min(self.settings.max_products, context.intent.requested_count or self.settings.max_products)
        return PresentAnswerArguments(intent="recommend", products=[
            {"product_id": product["ProductId"]} for product in context.prefetched["Products"][:count]])

    @staticmethod
    def _offers_missing(context):
        return context.intent.intent == "promotion_inquiry" and not context.offer_scopes and not context.policy

    def _reply_with_tools(self, actor, conversation_id, request_id, ticket, history, context, *, budget=None):
        """`budget`: seconds the model may take when the backend already has an answer to fall back on."""
        deadline = self.timer() + (min(budget, self.settings.timeout_seconds) if budget else self.settings.timeout_seconds)
        messages = list(history)
        prompt_tokens = completion_tokens = 0
        call_ids = set()
        result_chars = 0
        repaired_final = False
        provider_retried = stall_retried = False
        # One extra final-only call exists only for a repair requested in the last round.
        for round_index in range(self.settings.max_tool_rounds + 2):
            self._check_active(actor, conversation_id, request_id, ticket)
            remaining = deadline - self.timer()
            if remaining <= 0:
                raise AiUnavailableError("AI phản hồi quá thời gian chờ.")
            last = context.compatibility is not None or round_index >= self.settings.max_tool_rounds
            if round_index == self.settings.max_tool_rounds:
                messages.append({"role": "system", "content": FINAL_NOTE})
            try:
                call_started = self.timer()
                response = None
                while response is None:
                    left = deadline - self.timer()
                    cut = not stall_retried and left >= STALL_SECONDS + PROVIDER_RETRY_MIN_SECONDS
                    try:
                        response = self.model.complete(messages, tools=tool_definitions(final_only=last),
                                                       timeout_seconds=STALL_SECONDS if cut else left)
                    except AiUnavailableError as error:
                        # A stalled call cut at STALL_SECONDS, a provider 5xx or a dropped connection is sent once more
                        # per turn, the same request, while enough of the turn's time is left; the turn's own timeout,
                        # a quota error or invalid output is not.
                        if error.timed_out and cut:
                            stall_retried, pause, reason = True, 0, "stalled call"
                        elif (error.transient and not provider_retried
                              and deadline - self.timer() >= PROVIDER_RETRY_MIN_SECONDS + PROVIDER_RETRY_DELAY_SECONDS):
                            provider_retried, pause, reason = True, PROVIDER_RETRY_DELAY_SECONDS, "transient failure"
                        else:
                            raise
                        logger.warning("AI provider %s, retrying once request_id=%s round=%d",
                                       reason, request_id, round_index + 1)
                        if pause:
                            self.sleep(pause)
                        self._check_active(actor, conversation_id, request_id, ticket)
                        call_started = self.timer()
            except AiUnavailableError as error:
                # The provider rejected a malformed tool call before returning it (stage 10.7); ask once to redo it.
                if error.code != "ai_invalid_output" or repaired_final:
                    raise
                repaired_final = True
                messages.append({"role": "system", "content": REPAIR_NOTE})
                continue
            logger.info("AI model round request_id=%s model=%s round=%d elapsed_ms=%d tool_calls=%d "
                        "input_tokens=%d output_tokens=%d", request_id, self.settings.model, round_index + 1,
                        round((self.timer() - call_started) * 1000), len(response.tool_calls),
                        response.prompt_tokens, response.completion_tokens)
            prompt_tokens += response.prompt_tokens
            completion_tokens += response.completion_tokens
            if self.timer() >= deadline:
                raise AiUnavailableError("AI phản hồi quá thời gian chờ.")
            calls = response.tool_calls
            completion = replace(response, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
            if not calls:
                # Scripted/test adapters may return the final JSON without a function envelope.
                return completion, self._decision(response.content)
            if any(call.name == "present_answer" for call in calls):
                if len(calls) != 1:
                    raise AiUnavailableError("AI trộn kết quả cuối với công cụ tra cứu.", code="ai_invalid_output")
                try:
                    return completion, self._decision(calls[0].arguments)
                except AiUnavailableError:
                    if repaired_final or last:
                        # No repair round left: keep what can be kept without adding a fact, else fail as before.
                        salvaged = salvaged_decision(calls[0].arguments)
                        if salvaged is None:
                            raise
                        logger.warning("AI final answer salvaged request_id=%s intent=%s", request_id, salvaged.intent)
                        return completion, salvaged
                    repaired_final = True
                    invalid = calls[0]
                    if not invalid.id or invalid.id in call_ids:
                        raise AiUnavailableError("AI trả mã công cụ không hợp lệ.", code="ai_invalid_output")
                    call_ids.add(invalid.id)
                    messages.append({"role": "assistant", "content": None, "provider_steps": response.provider_steps,
                        "tool_calls": [{"id": invalid.id,
                        "type": "function", "function": {"name": invalid.name, "arguments": invalid.arguments}}]})
                    messages.append({"role": "tool", "tool_call_id": invalid.id,
                        "content": json.dumps({"error": "invalid_final_answer",
                            "message": "Use only intent, products [{product_id, product_variant_id?, specification_keys?}], clarification, message (max 1500 characters). No other fields. Compare needs at least two products."})})
                    continue
            if last or len(calls) > 2 or len(call_ids) + len(calls) > 6:
                raise AiUnavailableError("AI vượt giới hạn tra cứu. Vui lòng hỏi cụ thể hơn.", code="ai_tool_limit")
            messages.append({"role": "assistant", "content": response.content or None,
                "provider_steps": response.provider_steps,
                "tool_calls": [{"id": c.id, "type": "function", "function": {
                    "name": c.name, "arguments": c.arguments}} for c in calls]})
            for call in calls:
                if not call.id or call.id in call_ids:
                    raise AiUnavailableError("AI trả mã công cụ không hợp lệ.", code="ai_invalid_output")
                call_ids.add(call.id)
                schema = TOOL_SCHEMAS.get(call.name)
                if schema is None:
                    result = {"error": "unknown_tool"}
                else:
                    try:
                        if not isinstance(call.arguments, str) or len(call.arguments) > 2500:
                            raise ValueError
                        args = schema[0].model_validate_json(call.arguments)
                    except (ValueError, ValidationError):
                        result = {"error": "invalid_tool_arguments"}
                    else:
                        result = self._read_tool(actor, conversation_id, request_id, ticket,
                                                 call.name, args, context)
                encoded = json.dumps(result, ensure_ascii=False)
                result_chars += len(encoded)
                if len(encoded) > 14000 or result_chars > 24000:
                    raise AiUnavailableError("Kết quả tra cứu quá lớn. Vui lòng thu hẹp câu hỏi.", code="ai_tool_limit")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": encoded})
                if self.timer() >= deadline:
                    raise AiUnavailableError("AI phản hồi quá thời gian chờ.")
        raise AiUnavailableError("AI chưa hoàn tất tra cứu.")

    def _check_active(self, actor, conversation_id, request_id, ticket):
        try:
            with self.transaction():
                conversation = self._owned_ai(actor, conversation_id)
                question = self.messages.get_ai_request(conversation_id, request_id)
                if conversation.Status != "Open" or not self._owns_ticket(question, ticket) or self._expired(question):
                    raise ConflictError("Lượt xử lý AI đã kết thúc", code="ai_request_superseded")
        finally:
            self.session.close()

    def _read_tool(self, actor, conversation_id, request_id, ticket, name, args, context):
        try:
            with self.transaction():
                conversation = self._owned_ai(actor, conversation_id)
                question = self.messages.get_ai_request(conversation_id, request_id)
                if conversation.Status != "Open" or not self._owns_ticket(question, ticket) or self._expired(question):
                    raise ConflictError("Lượt xử lý AI đã kết thúc", code="ai_request_superseded")
                tools = AiTools(self.session, clock=self._clock, ranking=self.settings.ranking_enabled, actor=actor)
                # Dispatch is explicit; model-provided strings never select arbitrary methods.
                if name == "search_products":
                    return tools.search_products(args, context)
                if name == "get_product":
                    return tools.get_product(args, context)
                if name == "list_offers":
                    return tools.list_offers(args, context)
                return {"error": "unknown_tool"}
        except (BusinessRuleError, NotFoundError) as error:
            return {"error": error.code, "message": error.message}
        finally:
            self.session.close()

    def _finish(self, actor, conversation_id, request_id, ticket, completion, decision, context):
        with self.transaction():
            conversation = self._owned_ai(actor, conversation_id)
            question = self.messages.get_ai_request(conversation_id, request_id)
            if not self._owns_ticket(question, ticket):
                raise ConflictError("Lượt xử lý AI đã được thay thế", code="ai_request_superseded")
            if self._expired(question) or conversation.Status != "Open":
                raise ConflictError("Hội thoại hoặc lượt xử lý đã kết thúc", code="ai_request_expired")
            answer, cards, references, notes = AiTools(self.session, clock=self._clock,
                                                       ranking=self.settings.ranking_enabled, actor=actor).finish(
                decision, context, self.settings.max_products)
            if not answer.strip() or len(answer) > 5000:
                raise AiUnavailableError("AI chưa trả được câu trả lời hợp lệ.")
            reply = self.messages.create({
                "MessageId": uuid.uuid4(), "ConversationId": conversation_id,
                "SenderUserId": None, "SenderType": "AI", "MessageType": "Text", "Content": answer,
                # Internal (customers only get ReplyToMessageId): the shown products, in order, for "máy thứ hai"
                # and for not repeating them when the customer asks for more.
                "Metadata": {"ReplyToMessageId": str(question.MessageId), "ProductReferences": references,
                             "AnswerIntent": notes["AnswerIntent"],
                             **({"Comparison": notes["Comparison"]} if notes.get("Comparison") else {}),
                             **({"Compatibility": notes["Compatibility"]} if notes.get("Compatibility") else {})},
                "IsRead": False, "SentAt": self.now(),
            })
            card_ids = []
            for card in cards:
                card_id = uuid.uuid4()
                card_ids.append(str(card_id))
                self.messages.create({"MessageId": card_id, "ConversationId": conversation_id,
                    "SenderUserId": None, "SenderType": "AI", "MessageType": "Product", "Content": "",
                    "Metadata": {**card, "AiAnswerMessageId": str(reply.MessageId)},
                    "IsRead": False, "SentAt": self.now()})
            question.Metadata = {
                **question.Metadata, "AiProcessingStatus": "Completed", "AiReplyMessageId": str(reply.MessageId),
                "AiCardMessageIds": card_ids, "AiConstraints": context.constraints,
                "AiIntent": context.intent.to_metadata(), "AiAnswerSource": notes["AnswerSource"],
                **({"AiGroundingIssues": notes["GroundingIssues"]} if notes.get("GroundingIssues") else {}),
                **({"AiRanking": context.ranking_log} if context.ranking_log else {}),
                "AiModel": completion.model, "AiUsage": {"Input": completion.prompt_tokens,
                                                         "Output": completion.completion_tokens},
            }
            self.messages.flush()
            return self._response(question)

    def _fail(self, conversation_id, request_id, ticket, error):
        try:
            with self.transaction():
                self.conversations.get_by_id_for_update(conversation_id)
                question = self.messages.get_ai_request(conversation_id, request_id)
                if self._owns_ticket(question, ticket):
                    metadata = {**question.Metadata, "AiProcessingStatus": "Failed",
                                "AiErrorCode": getattr(error, "code", "ai_unavailable")}
                    retry_after = getattr(error, "retry_after_seconds", None)
                    if retry_after:
                        metadata["AiRetryAfterAt"] = (self.now() + timedelta(seconds=retry_after)).isoformat()
                    question.Metadata = metadata
                    self.messages.flush()
        except SQLAlchemyError:
            # A later retry can recover the expired lease if the database is temporarily unavailable.
            logger.warning("Could not save failed AI request status")
        self._provider_cooldown(error)

    def _provider_cooldown(self, error):
        if getattr(error, "code", None) == "ai_quota_exceeded" and error.retry_after_seconds:
            key = f"ai-provider-cooldown:{self.settings.model}"
            until = self.now().timestamp() + error.retry_after_seconds
            with self.state.lock(key):
                existing = self.state.get(key) or {}
                self.state.put(key, {"until": max(until, existing.get("until", 0))},
                               max(error.retry_after_seconds, 60))

    def _owned_ai(self, actor, conversation_id):
        conversation = self.conversations.get_by_id_for_update(conversation_id)
        if conversation is None or conversation.CustomerId != actor.user_id:
            raise NotFoundError("Không tìm thấy hội thoại", code="conversation_not_found")
        user = self.users.get_by_id(actor.user_id)
        if user is None or user.IsDeleted or user.AccountStatus != "Active" or user.Role != "Customer":
            raise NotFoundError("Không tìm thấy hội thoại", code="conversation_not_found")
        if conversation.Mode != "AI":
            raise BusinessRuleError("Hội thoại không ở chế độ AI", code="conversation_not_ai_mode")
        return conversation

    @staticmethod
    def _owns_ticket(question, ticket):
        metadata = question.Metadata if question else None
        return bool(metadata and metadata.get("AiProcessingStatus") == "Pending"
                    and metadata.get("AiLeaseToken") == ticket)

    def _expired(self, question):
        try:
            deadline = datetime.fromisoformat(question.Metadata["AiLeaseExpiresAt"])
            return deadline.tzinfo is None or deadline <= self.now()
        except (KeyError, TypeError, ValueError):
            return True

    def _expire(self, question):
        if question.Metadata.get("AiProcessingStatus") == "Pending" and self._expired(question):
            question.Metadata = {**question.Metadata, "AiProcessingStatus": "Failed", "AiErrorCode": "ai_lease_expired"}

    def _history(self, conversation_id):
        """Text pairs for the model, and the saved state (slots, shown products in order) for the backend."""
        questions = self.messages.completed_ai_requests(conversation_id, self.settings.context_max_turns)
        ids = [uuid.UUID(q.Metadata["AiReplyMessageId"]) for q in questions]
        replies = {str(m.MessageId): m for m in self.messages.get_messages_by_ids(ids)}
        history = [{"role": "system", "content": SYSTEM_PROMPT}]
        answered = [(question, replies.get(question.Metadata["AiReplyMessageId"])) for question in questions]
        answered = [(question, reply) for question, reply in answered
                    if reply and reply.ConversationId == conversation_id and reply.SenderType == "AI"]
        past = []
        for question, reply in answered:
            saved = question.Metadata or {}
            slots = (saved.get("AiIntent") or {}).get("Slots") or slots_from_constraints(saved.get("AiConstraints"))
            meta = reply.Metadata or {}
            past.append(PastTurn(slots, meta.get("AnswerIntent"), tuple(meta.get("ProductReferences") or ())))
        turns = []
        budget = 10000
        for question, reply in reversed(answered):
            content = model_text(reply.Content)
            references = (reply.Metadata or {}).get("ProductReferences")
            if references:
                shown = [{key: ref.get(key) for key in ("Rank", "ProductId", "ProductName") if ref.get(key)}
                         for ref in references[:5]]
                content += "\nTham chiếu thẻ (dữ liệu): " + json.dumps(shown, ensure_ascii=False)
            cost = len(question.Content) + len(content)
            if cost > budget:
                break
            budget -= cost
            turns.append([{"role": "user", "content": model_text(question.Content)},
                          {"role": "assistant", "content": content}])
        for turn in reversed(turns):
            history.extend(turn)
        return history, ConversationState(tuple(past))

    def _response(self, question):
        metadata = question.Metadata
        replies = []
        if metadata["AiProcessingStatus"] == "Completed":
            reply = self.messages.get_by_id(uuid.UUID(metadata["AiReplyMessageId"]))
            if reply is None or reply.ConversationId != question.ConversationId or reply.SenderType != "AI":
                raise AiUnavailableError("Chưa đọc được kết quả AI đã lưu.")
            replies.append(MessageResponse.model_validate(reply))
            card_ids = [uuid.UUID(value) for value in metadata.get("AiCardMessageIds", [])]
            cards = {row.MessageId: row for row in self.messages.get_messages_by_ids(card_ids)}
            for id_ in card_ids:
                card = cards.get(id_)
                if (card is None or card.ConversationId != question.ConversationId or card.SenderType != "AI"
                        or card.MessageType != "Product" or (card.Metadata or {}).get("AiAnswerMessageId") != str(reply.MessageId)):
                    raise AiUnavailableError("Chưa đọc được thẻ sản phẩm đã lưu.")
                replies.append(MessageResponse.model_validate(card))
        return AiTurnResponse(ClientRequestId=metadata["ClientRequestId"], Status=metadata["AiProcessingStatus"],
                              CustomerMessage=MessageResponse.model_validate(question), AiMessages=replies)

    def _cooldown_remaining(self):
        """Seconds left of the provider cooldown set after a quota error, or None."""
        cooldown = self.state.get(f"ai-provider-cooldown:{self.settings.model}") or {}
        remaining = cooldown.get("until", 0) - self.now().timestamp()
        return int(remaining) + 1 if remaining > 0 else None

    def _rate_limit(self, actor):
        key = f"ai-send:{actor.user_id}"
        now = self.now().timestamp()
        with self.state.lock(key):
            record = self.state.get(key) or {"times": []}
            times = [t for t in record["times"] if t > now - 60]
            if len(times) >= self.settings.requests_per_minute:
                raise TooManyRequestsError("Bạn gửi câu hỏi quá nhanh. Vui lòng thử lại sau.", code="rate_limited",
                                           retry_after_seconds=max(1, int(times[0] + 60 - now) + 1))
            self.state.put(key, {"times": [*times, now]}, 60)
