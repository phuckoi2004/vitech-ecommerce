"""ChatService đợt 5.3.1: Customer tự đóng hội thoại, quyền Admin kế thừa Staff, giới hạn 5.000 ký tự,
không còn schema cập nhật hội thoại tổng quát.

Fake trong bộ nhớ: khóa dòng/partial UNIQUE chỉ được giả lập; không chứng minh concurrency thật của PostgreSQL.
"""

import unittest
from datetime import timedelta

from pydantic import ValidationError

import app.schemas
import app.schemas.chat
from app.models import Conversation, Message
from app.schemas import ConversationCreate, MessageCreate
from app.services import BusinessRuleError, ConflictError, NotFoundError

from tests.fakes import NOW
from tests.test_chat import ChatTestBase, bypass


class CustomerCloseTest(ChatTestBase):
    def close(self, conversation_id, by=None):
        return self.svc.close_conversation(self.a(by or self.customer), conversation_id)

    def test_customer_closes_own_ai_conversation_then_opens_staff_conversation(self):
        ai = self.start(mode="AI")
        self.clock.now = NOW + timedelta(minutes=5)
        closed = self.close(ai.ConversationId)
        self.assertEqual((closed.Status, closed.ClosedAt, closed.Mode), ("Closed", NOW + timedelta(minutes=5), "AI"))
        staff_chat = self.start(mode="Staff")
        self.assertNotEqual(staff_chat.ConversationId, ai.ConversationId)
        self.assertEqual(self.db.get(Conversation, ai.ConversationId).Mode, "AI")  # không tự chuyển AI → Staff
        open_ones = [c for c in self.conversations() if c.CustomerId == self.customer.UserId and c.Status == "Open"]
        self.assertEqual([c.ConversationId for c in open_ones], [staff_chat.ConversationId])

    def test_customer_closes_own_staff_conversation_even_when_assigned(self):
        conversation = self.start()
        self.claim(conversation.ConversationId)
        self.assertEqual(self.close(conversation.ConversationId).Status, "Closed")
        record = self.db.get(Conversation, conversation.ConversationId)
        self.assertEqual(record.AssignedStaffId, self.staff.UserId)  # không đổi người phụ trách

    def test_customer_cannot_close_someone_elses_conversation(self):
        theirs = self.start(by=self.other)
        self.assert_error(NotFoundError, "conversation_not_found", lambda: self.close(theirs.ConversationId))
        self.assertEqual(self.db.get(Conversation, theirs.ConversationId).Status, "Open")

    def test_closing_twice_does_not_change_history(self):
        conversation = self.start(mode="AI")
        self.close(conversation.ConversationId)
        self.clock.now = NOW + timedelta(hours=1)
        self.assert_error(BusinessRuleError, "conversation_closed", lambda: self.close(conversation.ConversationId))
        record = self.db.get(Conversation, conversation.ConversationId)
        self.assertEqual((record.Status, record.ClosedAt), ("Closed", NOW))

    def test_customer_and_staff_closing_at_the_same_time(self):
        """Hai yêu cầu đổi trạng thái cùng hội thoại: khóa dòng tuần tự hóa; yêu cầu sau thấy đã đóng."""
        conversation = self.start()
        self.claim(conversation.ConversationId)
        self.db.locks.clear()
        self.close(conversation.ConversationId)
        self.clock.now = NOW + timedelta(seconds=1)
        self.assert_error(BusinessRuleError, "conversation_closed",
                          lambda: self.close(conversation.ConversationId, by=self.staff))
        self.assertEqual([k for n, k in self.db.locks if n == "Conversation"], [conversation.ConversationId] * 2)
        self.assertEqual(self.db.get(Conversation, conversation.ConversationId).ClosedAt, NOW)
        self.assert_error(BusinessRuleError, "conversation_closed", lambda: self.send(conversation.ConversationId))

    def test_close_then_claim_or_send_is_rejected(self):
        conversation = self.start()
        self.close(conversation.ConversationId)
        self.assert_error(BusinessRuleError, "conversation_closed", lambda: self.claim(conversation.ConversationId))
        self.assertIsNone(self.db.get(Conversation, conversation.ConversationId).AssignedStaffId)

    def test_one_open_conversation_rule_still_holds(self):
        first = self.start(mode="AI")
        self.assert_error(BusinessRuleError, "open_conversation_exists", lambda: self.start(mode="Staff"))
        self.close(first.ConversationId)
        second = self.start(mode="Staff")
        self.assertEqual(self.start(mode="Staff").ConversationId, second.ConversationId)
        self.assertEqual(sum(1 for c in self.conversations() if c.Status == "Open"), 1)


class AdminInheritsStaffTest(ChatTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.conversation = self.start()
        self.cid = self.conversation.ConversationId

    def test_admin_sees_queue_claims_replies_and_closes(self):
        queue = self.svc.list_unassigned_conversations(self.a(self.admin))
        self.assertEqual([c.ConversationId for c in queue.Items], [self.cid])
        self.assertEqual(self.claim(self.cid, by=self.admin).AssignedStaffId, self.admin.UserId)
        reply = self.send(self.cid, by=self.admin, content="Quản trị viên hỗ trợ")
        self.assertEqual((reply.SenderType, reply.SenderUserId), ("Staff", self.admin.UserId))
        self.assertEqual(self.svc.list_assigned_conversations(self.a(self.admin)).Total, 1)
        self.assertEqual(self.svc.close_conversation(self.a(self.admin), self.cid).Status, "Closed")

    def test_admin_cannot_take_over_or_reply_for_another_staff(self):
        self.claim(self.cid, by=self.staff)
        self.assert_error(ConflictError, "conversation_already_claimed", lambda: self.claim(self.cid, by=self.admin))
        self.assertEqual(self.db.get(Conversation, self.cid).AssignedStaffId, self.staff.UserId)
        self.assert_error(BusinessRuleError, "conversation_not_assigned_to_you",
                          lambda: self.send(self.cid, by=self.admin))
        self.assert_error(BusinessRuleError, "conversation_not_assigned_to_you",
                          lambda: self.svc.close_conversation(self.a(self.admin), self.cid))
        self.assertEqual(self.svc.get_conversation(self.a(self.admin), self.cid).AssignedStaffId,
                         self.staff.UserId)  # vẫn xem được qua quyền quản trị
        self.assertEqual((self.db.get(Conversation, self.cid).Status, self.messages()), ("Open", []))


class MessageLengthTest(ChatTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.cid = self.start().ConversationId

    def test_text_of_exactly_5000_characters_is_accepted(self):
        content = "a" * 5000
        self.assertEqual(len(MessageCreate(MessageType="Text", Content=content).Content), 5000)
        self.assertEqual(len(self.send(self.cid, content=content).Content), 5000)
        padded = self.send(self.cid, content="  " + "b" * 5000 + "\n")  # khoảng trắng đầu/cuối không tính
        self.assertEqual(padded.Content, "b" * 5000)

    def test_text_of_5001_characters_is_rejected_without_truncation(self):
        with self.assertRaises(ValidationError):
            MessageCreate(MessageType="Text", Content="a" * 5001)
        self.assert_error(BusinessRuleError, "message_content_too_long", lambda: self.svc.send_message(
            self.a(self.customer), self.cid, bypass({"MessageType": "Text", "Content": "a" * 5001})))
        self.assertEqual(self.messages(), [])  # không lưu bản bị cắt ngắn

    def test_empty_text_is_still_rejected(self):
        for content in ("", "   ", "\n"):
            with self.subTest(content=content):
                self.assert_error(BusinessRuleError, "message_content_required", lambda c=content: self.send(self.cid, content=c))

    def test_image_and_product_keep_their_own_rules(self):
        product = self.f.variant().product
        long_url = "https://cdn.vietech.vn/" + "a" * 470  # 493 ký tự: hợp lệ với giới hạn URL 500
        self.assertEqual(self.send(self.cid, message_type="Image", content="", metadata={"ImageUrl": long_url}).Metadata,
                         {"ImageUrl": long_url})
        self.assert_error(BusinessRuleError, "invalid_image_url", lambda: self.send(
            self.cid, message_type="Image", content="", metadata={"ImageUrl": "https://cdn.vietech.vn/" + "a" * 480}))
        self.assertEqual(self.send(self.cid, message_type="Product", content="x" * 5000,
                                   metadata={"ProductId": str(product.ProductId)}).Metadata["ProductId"],
                         str(product.ProductId))
        self.assert_error(BusinessRuleError, "message_content_too_long", lambda: self.svc.send_message(
            self.a(self.customer), self.cid,
            bypass({"MessageType": "Image", "Content": "c" * 5001, "Metadata": {"ImageUrl": long_url}})))

    def test_sender_still_cannot_be_forged(self):
        for extra in ({"SenderType": "AI"}, {"SenderUserId": str(self.staff.UserId)}):
            with self.subTest(extra=extra):
                self.assert_error(BusinessRuleError, "message_field_not_allowed", lambda e=extra: self.svc.send_message(
                    self.a(self.customer), self.cid, bypass({"MessageType": "Text", "Content": "x", **e})))
        self.assertEqual(self.messages(), [])

    def test_ai_reply_obeys_the_same_limit(self):
        ai = self.start(mode="AI", by=self.other)
        self.assert_error(BusinessRuleError, "message_content_too_long",
                          lambda: self.svc.record_ai_reply(ai.ConversationId, "a" * 5001))
        self.assertEqual(len(self.svc.record_ai_reply(ai.ConversationId, "a" * 5000).Content), 5000)


class NoGenericConversationUpdateTest(ChatTestBase):
    def test_generic_update_schema_no_longer_exists(self):
        self.assertFalse(hasattr(app.schemas, "ConversationUpdate"))
        self.assertFalse(hasattr(app.schemas.chat, "ConversationUpdate"))
        self.assertNotIn("ConversationUpdate", app.schemas.__all__)
        self.assertFalse([name for name in dir(self.svc) if "update" in name.lower() and not name.startswith("_")])

    def test_status_mode_and_assignee_change_only_through_business_methods(self):
        for extra in ({"Status": "Closed"}, {"AssignedStaffId": str(self.staff.UserId)}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                ConversationCreate(Mode="Staff", **extra)
        for extra in ({"Status": "Closed"}, {"AssignedStaffId": self.staff.UserId}):
            with self.subTest(extra=extra, bypass=True):
                self.assert_error(BusinessRuleError, "conversation_field_not_allowed", lambda e=extra: self.svc.start_conversation(
                    self.a(self.customer), bypass({"Mode": "Staff", **e})))
        conversation = self.start(mode="AI")
        self.assert_error(BusinessRuleError, "open_conversation_exists", lambda: self.start(mode="Staff"))
        self.assertEqual(self.db.get(Conversation, conversation.ConversationId).Mode, "AI")  # Mode không đổi
        staff_chat = self.start(by=self.other)
        self.assertEqual(self.claim(staff_chat.ConversationId).AssignedStaffId, self.staff.UserId)
        self.assertEqual(self.svc.close_conversation(self.a(self.staff), staff_chat.ConversationId).Status, "Closed")
        self.assertEqual(len(self.db.rows(Message)), 0)


if __name__ == "__main__":
    unittest.main()
