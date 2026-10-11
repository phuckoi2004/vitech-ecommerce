"""ChatService (đợt 5.3): mỗi Customer một hội thoại Open, Staff tự nhận, quyền xem/gửi, loại tin nhắn, đóng hội thoại.

Fake trong bộ nhớ: khóa dòng/partial UNIQUE chỉ được giả lập (db.locks, IntegrityError); không chứng minh concurrency
thật của PostgreSQL. Không gọi AI provider.
"""

import unittest
import uuid
from datetime import timedelta
from types import SimpleNamespace

from pydantic import ValidationError

from app.models import Conversation, Message, Product
from app.schemas import ConversationCreate, MessageCreate
from app.services import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError

from tests.fakes import NOW, FakeSession, Factory, InMemoryDB, chat_service


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):
        return self.now


def bypass(values):
    """Dữ liệu đi vòng qua Schema (ví dụ Router lỗi) để kiểm tra Service tự chặn."""
    return SimpleNamespace(model_dump=lambda exclude_unset=True: dict(values))


class ChatTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.clock = Clock()
        self.svc = chat_service(self.db, self.session, clock=self.clock)
        self.customer = self.f.user()
        self.other = self.f.user()
        self.staff = self.f.user("Staff")
        self.staff2 = self.f.user("Staff")
        self.admin = self.f.user("Admin")

    def a(self, user):
        return self.f.actor(user)

    def start(self, mode="Staff", by=None):
        return self.svc.start_conversation(self.a(by or self.customer), ConversationCreate(Mode=mode))

    def claim(self, conversation_id, by=None):
        return self.svc.claim_conversation(self.a(by or self.staff), conversation_id)

    def send(self, conversation_id, by=None, message_type="Text", content="Xin chào", metadata=None):
        data = MessageCreate(MessageType=message_type, Content=content, Metadata=metadata)
        return self.svc.send_message(self.a(by or self.customer), conversation_id, data)

    def conversations(self):
        return self.db.rows(Conversation)

    def messages(self):
        return self.db.rows(Message)

    def assert_error(self, error, code, call):
        with self.assertRaises(error) as ctx:
            call()
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception


class StartConversationTest(ChatTestBase):
    def test_customer_starts_conversation(self):
        result = self.start()
        self.assertEqual((result.CustomerId, result.Mode, result.Status, result.CreatedAt),
                         (self.customer.UserId, "Staff", "Open", NOW))
        self.assertIsNone(self.db.get(Conversation, result.ConversationId).AssignedStaffId)
        self.assertNotIn("AssignedStaffId", result.model_dump())  # đợt 5.10: định danh nhân viên là nội bộ
        self.assertIn(("User", self.customer.UserId), self.db.locks)  # tuần tự hóa theo Customer
        self.assertEqual(self.start(mode="AI", by=self.other).Mode, "AI")

    def test_existing_open_conversation_is_returned_not_duplicated(self):
        first = self.start()
        rollbacks = self.session.rollbacks
        self.assertEqual(self.start().ConversationId, first.ConversationId)
        self.assertEqual(self.session.rollbacks, rollbacks)  # Service tự thấy hội thoại Open, không cần tới UNIQUE
        self.assert_error(BusinessRuleError, "open_conversation_exists", lambda: self.start(mode="AI"))
        self.assertEqual(len(self.conversations()), 1)
        self.assertEqual(self.db.get(Conversation, first.ConversationId).Status, "Open")  # không tự đóng hội thoại cũ

    def test_new_conversation_allowed_after_previous_closed(self):
        first = self.start()
        self.claim(first.ConversationId)
        self.svc.close_conversation(self.a(self.staff), first.ConversationId)
        second = self.start(mode="AI")
        self.assertNotEqual(second.ConversationId, first.ConversationId)
        self.assertEqual(self.db.get(Conversation, first.ConversationId).Status, "Closed")  # không mở lại

    def test_concurrent_start_reuses_conversation_created_by_the_other_request(self):
        """Yêu cầu khác vừa commit hội thoại Open sau lần kiểm tra của yêu cầu này: partial UNIQUE chặn, dùng lại."""
        repo = self.svc.conversations
        original = repo.get_open_by_customer
        calls = {"n": 0}

        def race(customer_id):
            calls["n"] += 1
            if calls["n"] == 1:  # lần kiểm tra đầu chưa thấy; yêu cầu kia commit ngay sau đó
                self.db.add(Conversation(CustomerId=customer_id, Mode="Staff", Status="Open", CreatedAt=NOW))
                self.session._snapshot = self.db.snapshot()  # bản ghi do session khác đã commit
                return None
            return original(customer_id)

        repo.get_open_by_customer = race
        rollbacks = self.session.rollbacks
        result = self.start()
        self.assertEqual(len(self.conversations()), 1)
        self.assertEqual(result.ConversationId, self.conversations()[0].ConversationId)
        self.assertEqual(self.session.rollbacks, rollbacks + 1)  # INSERT vi phạm UNIQUE → rollback → đọc lại

    def test_concurrent_start_with_other_mode_is_rejected(self):
        repo = self.svc.conversations
        original = repo.get_open_by_customer
        calls = {"n": 0}

        def race(customer_id):
            calls["n"] += 1
            if calls["n"] == 1:
                self.db.add(Conversation(CustomerId=customer_id, Mode="AI", Status="Open", CreatedAt=NOW))
                self.session._snapshot = self.db.snapshot()
                return None
            return original(customer_id)

        repo.get_open_by_customer = race
        self.assert_error(BusinessRuleError, "open_conversation_exists", lambda: self.start(mode="Staff"))
        self.assertEqual(len(self.conversations()), 1)

    def test_cannot_start_for_someone_else(self):
        with self.assertRaises(ValidationError):
            ConversationCreate(Mode="Staff", CustomerId=str(self.other.UserId))
        self.assert_error(BusinessRuleError, "conversation_field_not_allowed", lambda: self.svc.start_conversation(
            self.a(self.customer), bypass({"Mode": "Staff", "CustomerId": self.other.UserId})))
        for who in (self.staff, self.admin):
            with self.subTest(role=who.Role), self.assertRaises(PermissionDeniedError):
                self.start(by=who)
        self.assertEqual(self.conversations(), [])

    def test_invalid_mode(self):
        with self.assertRaises(ValidationError):
            ConversationCreate(Mode="Bot")
        for mode in ("Bot", None, "staff"):
            with self.subTest(mode=mode):
                self.assert_error(BusinessRuleError, "invalid_conversation_mode",
                                  lambda m=mode: self.svc.start_conversation(self.a(self.customer), bypass({"Mode": m})))
        self.assertEqual(self.conversations(), [])

    def test_failure_while_saving_rolls_back_and_nested_call_is_rejected(self):
        def broken(values):
            raise RuntimeError("lưu lỗi")

        self.svc.conversations.create = broken
        with self.assertRaises(RuntimeError):
            self.start()
        self.assertEqual(self.conversations(), [])
        with self.assertRaises(BusinessRuleError) as ctx:
            with self.svc.transaction():
                self.start()
        self.assertEqual(ctx.exception.code, "conversation_requires_own_transaction")


class ClaimConversationTest(ChatTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.conversation = self.start()

    def test_staff_claims_unassigned_conversation(self):
        self.db.locks.clear()
        result = self.claim(self.conversation.ConversationId)
        self.assertEqual(result.AssignedStaffId, self.staff.UserId)
        self.assertEqual(self.db.locks[0], ("Conversation", self.conversation.ConversationId))
        self.assertEqual(self.svc.list_unassigned_conversations(self.a(self.staff2)).Total, 0)  # rời hàng đợi
        self.assertEqual(self.svc.list_assigned_conversations(self.a(self.staff)).Total, 1)

    def test_second_staff_cannot_take_over(self):
        self.claim(self.conversation.ConversationId)
        self.assert_error(ConflictError, "conversation_already_claimed",
                          lambda: self.claim(self.conversation.ConversationId, by=self.staff2))
        self.assertEqual(self.db.get(Conversation, self.conversation.ConversationId).AssignedStaffId, self.staff.UserId)
        self.assertEqual(self.claim(self.conversation.ConversationId).AssignedStaffId, self.staff.UserId)  # gọi lặp

    def test_concurrent_claims_second_waits_then_fails(self):
        """Hai nhân viên nhận cùng lúc: khóa dòng tuần tự hóa; người sau đọc lại dòng đã khóa và thấy đã có người nhận."""
        self.db.locks.clear()
        self.claim(self.conversation.ConversationId)
        self.assert_error(ConflictError, "conversation_already_claimed",
                          lambda: self.claim(self.conversation.ConversationId, by=self.staff2))
        self.assertEqual([k for n, k in self.db.locks if n == "Conversation"], [self.conversation.ConversationId] * 2)

    def test_closed_or_ai_conversations_cannot_be_claimed(self):
        self.db.get(Conversation, self.conversation.ConversationId).Status = "Closed"
        self.assert_error(BusinessRuleError, "conversation_closed", lambda: self.claim(self.conversation.ConversationId))
        ai = self.start(mode="AI", by=self.other)
        self.assert_error(BusinessRuleError, "conversation_not_claimable", lambda: self.claim(ai.ConversationId))
        self.assertIsNone(self.db.get(Conversation, ai.ConversationId).AssignedStaffId)

    def test_customers_cannot_claim_and_admin_can(self):
        with self.assertRaises(PermissionDeniedError):
            self.claim(self.conversation.ConversationId, by=self.customer)
        with self.assertRaises(NotFoundError):
            self.claim(uuid.uuid4())
        self.assertEqual(self.claim(self.conversation.ConversationId, by=self.admin).AssignedStaffId, self.admin.UserId)


class ViewConversationTest(ChatTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.mine = self.start()
        self.send(self.mine.ConversationId)
        self.theirs = self.start(by=self.other)
        self.ai = self.start(mode="AI", by=self.f.user())

    def view(self, user, conversation):
        return self.svc.get_conversation(self.a(user), conversation.ConversationId)

    def assert_hidden(self, user, conversation):
        error = self.assert_error(NotFoundError, "conversation_not_found", lambda: self.view(user, conversation))
        return str(error)

    def test_customer_sees_only_own_conversations(self):
        detail = self.view(self.customer, self.mine)
        self.assertEqual((detail.ConversationId, len(detail.Messages)), (self.mine.ConversationId, 1))
        hidden = self.assert_hidden(self.customer, self.theirs)
        missing = self.assert_error(NotFoundError, "conversation_not_found",
                                    lambda: self.svc.get_conversation(self.a(self.customer), uuid.uuid4()))
        self.assertEqual(hidden, str(missing))  # cùng thông báo: không lộ hội thoại tồn tại
        self.assertEqual([c.ConversationId for c in self.svc.list_my_conversations(self.a(self.customer)).Items],
                         [self.mine.ConversationId])

    def test_staff_sees_assigned_and_claimable_queue_only(self):
        self.assertEqual(self.view(self.staff, self.mine).ConversationId, self.mine.ConversationId)  # hàng đợi
        self.claim(self.mine.ConversationId, by=self.staff)
        self.assertEqual(self.view(self.staff, self.mine).AssignedStaffId, self.staff.UserId)
        self.assert_hidden(self.staff2, self.mine)  # đã gán cho người khác
        self.assert_hidden(self.staff, self.ai)  # hội thoại AI không thuộc hàng đợi nhân viên
        queue = self.svc.list_unassigned_conversations(self.a(self.staff2))
        self.assertEqual([c.ConversationId for c in queue.Items], [self.theirs.ConversationId])

    def test_admin_sees_everything(self):
        self.claim(self.mine.ConversationId)
        for conversation in (self.mine, self.theirs, self.ai):
            with self.subTest(conversation=conversation.ConversationId):
                self.assertEqual(self.view(self.admin, conversation).ConversationId, conversation.ConversationId)
        self.assertEqual(self.svc.admin_list_conversations(self.a(self.admin)).Total, 3)
        self.assertEqual(self.svc.admin_list_conversations(self.a(self.admin), mode="AI").Total, 1)
        with self.assertRaises(PermissionDeniedError):
            self.svc.admin_list_conversations(self.a(self.staff))

    def test_listing_permissions_and_validation(self):
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_unassigned_conversations(self.a(self.customer))
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_my_conversations(self.a(self.staff))
        self.assert_error(BusinessRuleError, "invalid_conversation_status",
                          lambda: self.svc.list_my_conversations(self.a(self.customer), status="Pending"))
        with self.assertRaises(PermissionDeniedError):
            self.svc.get_conversation(None, self.mine.ConversationId)

    def test_message_history_is_paginated_with_same_access_rules(self):
        self.clock.now = NOW + timedelta(seconds=1)  # tin sau gửi muộn hơn (thứ tự theo SentAt)
        self.send(self.mine.ConversationId, content="Tin 2")
        page = self.svc.list_messages(self.a(self.customer), self.mine.ConversationId)
        self.assertEqual(([m.Content for m in page.Items], page.Total), (["Xin chào", "Tin 2"], 2))
        self.assert_error(NotFoundError, "conversation_not_found",
                          lambda: self.svc.list_messages(self.a(self.other), self.mine.ConversationId))


class SendMessageTest(ChatTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.conversation = self.start()
        self.cid = self.conversation.ConversationId
        self.product = self.f.variant(price="15990000.00").product

    def test_customer_and_assigned_staff_send_text(self):
        mine = self.send(self.cid, content="  Cần tư vấn  ")
        self.assertEqual((mine.SenderUserId, mine.SenderType, mine.MessageType, mine.Content, mine.Metadata, mine.IsRead),
                         (self.customer.UserId, "Customer", "Text", "Cần tư vấn", None, False))
        self.claim(self.cid)
        reply = self.send(self.cid, by=self.staff, content="Dạ em hỗ trợ ạ")
        self.assertEqual((reply.SenderUserId, reply.SenderType), (self.staff.UserId, "Staff"))
        self.assertIn(("Conversation", self.cid), self.db.locks)

    def test_empty_or_invalid_text(self):
        for content in ("", "   ", "\n\t"):
            with self.subTest(content=content):
                self.assert_error(BusinessRuleError, "message_content_required", lambda c=content: self.send(self.cid, content=c))
        with self.assertRaises(ValidationError):
            MessageCreate(MessageType="Video", Content="x")
        self.assert_error(BusinessRuleError, "invalid_message_type", lambda: self.svc.send_message(
            self.a(self.customer), self.cid, bypass({"MessageType": "Video", "Content": "x"})))
        self.assert_error(BusinessRuleError, "invalid_message_content", lambda: self.svc.send_message(
            self.a(self.customer), self.cid, bypass({"MessageType": "Text", "Content": 123})))
        self.assert_error(BusinessRuleError, "message_metadata_not_allowed",
                          lambda: self.send(self.cid, metadata={"ProductId": str(self.product.ProductId)}))
        self.assertEqual(self.messages(), [])

    def test_sender_cannot_be_forged(self):
        for extra in ({"SenderType": "Staff"}, {"SenderType": "AI"}, {"SenderUserId": str(self.staff.UserId)},
                      {"ConversationId": str(uuid.uuid4())}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                MessageCreate(MessageType="Text", Content="x", **extra)
            with self.subTest(extra=extra, bypass=True):
                self.assert_error(BusinessRuleError, "message_field_not_allowed", lambda e=extra: self.svc.send_message(
                    self.a(self.customer), self.cid, bypass({"MessageType": "Text", "Content": "x", **e})))
        self.claim(self.cid)
        staff_message = self.send(self.cid, by=self.staff)
        self.assertEqual(staff_message.SenderType, "Staff")  # vai trò thật, không phải dữ liệu client
        self.assertFalse(any(m.SenderType == "AI" for m in self.messages()))

    def test_closed_conversation_rejects_new_messages(self):
        self.claim(self.cid)
        self.svc.close_conversation(self.a(self.staff), self.cid)
        for who in (self.customer, self.staff):
            with self.subTest(role=who.Role):
                self.assert_error(BusinessRuleError, "conversation_closed", lambda u=who: self.send(self.cid, by=u))
        self.assertEqual(self.messages(), [])

    def test_staff_must_be_the_assigned_staff(self):
        self.assert_error(BusinessRuleError, "conversation_not_assigned_to_you", lambda: self.send(self.cid, by=self.staff))
        self.claim(self.cid, by=self.staff2)
        self.assert_error(NotFoundError, "conversation_not_found", lambda: self.send(self.cid, by=self.staff))
        self.assert_error(BusinessRuleError, "conversation_not_assigned_to_you", lambda: self.send(self.cid, by=self.admin))
        self.assertEqual(self.messages(), [])

    def test_customer_cannot_write_into_someone_elses_conversation(self):
        self.assert_error(NotFoundError, "conversation_not_found", lambda: self.send(self.cid, by=self.other))
        self.assert_error(NotFoundError, "conversation_not_found", lambda: self.send(uuid.uuid4()))
        self.assertEqual(self.messages(), [])

    def test_product_message_requires_visible_existing_product(self):
        metadata = lambda pid: {"ProductId": str(pid)}  # noqa: E731
        self.assert_error(NotFoundError, "product_not_found",
                          lambda: self.send(self.cid, message_type="Product", content="", metadata=metadata(uuid.uuid4())))
        hidden = self.f.variant(status="Draft").product
        deleted = self.f.variant().product
        deleted.IsDeleted = True
        for product in (hidden, deleted):
            with self.subTest(product=product.Status):
                self.assert_error(NotFoundError, "product_not_found", lambda p=product: self.send(
                    self.cid, message_type="Product", content="", metadata=metadata(p.ProductId)))
        for bad in ({}, {"ProductId": "khong-phai-uuid"}, {"ProductId": str(self.product.ProductId), "Price": "1"}):
            with self.subTest(bad=bad):
                self.assert_error(BusinessRuleError, "invalid_product_message" if bad else "message_metadata_required",
                                  lambda b=bad: self.send(self.cid, message_type="Product", content="", metadata=b or None))
        before = (self.product.Name, self.product.Status, self.product.ReviewCount)
        result = self.send(self.cid, message_type="Product", content="Mẫu này còn hàng không?",
                           metadata={"ProductId": str(self.product.ProductId)})
        self.assertEqual(result.Metadata, {"ProductId": str(self.product.ProductId), "ProductName": self.product.Name,
                                           "Slug": self.product.Slug})  # thông tin do server ghi
        self.assertEqual((self.product.Name, self.product.Status, self.product.ReviewCount), before)
        self.assertEqual(self.db.get(Product, self.product.ProductId).Slug, self.product.Slug)

    def test_image_message_validation(self):
        cases = [
            (None, "message_metadata_required"),
            ({}, "message_metadata_required"),
            ({"Url": "https://cdn.vietech.vn/a.jpg"}, "invalid_image_message"),
            ({"ImageUrl": "https://cdn.vietech.vn/a.jpg", "Size": 1}, "invalid_image_message"),
            ({"ImageUrl": "http://cdn.vietech.vn/a.jpg"}, "invalid_image_url"),
            ({"ImageUrl": "javascript:alert(1)"}, "invalid_image_url"),
            ({"ImageUrl": "https:///a.jpg"}, "invalid_image_url"),
            ({"ImageUrl": "https://cdn.vietech.vn/a b.jpg"}, "invalid_image_url"),
            ({"ImageUrl": "https://cdn.vietech.vn/" + "a" * 500}, "invalid_image_url"),
            ({"ImageUrl": 123}, "invalid_image_url"),
        ]
        for metadata, code in cases:
            with self.subTest(metadata=metadata):
                self.assert_error(BusinessRuleError, code,
                                  lambda m=metadata: self.send(self.cid, message_type="Image", content="", metadata=m))
        result = self.send(self.cid, message_type="Image", content=" ảnh lỗi màn hình ",
                           metadata={"ImageUrl": " https://cdn.vietech.vn/a.jpg "})
        self.assertEqual((result.Content, result.Metadata), ("ảnh lỗi màn hình", {"ImageUrl": "https://cdn.vietech.vn/a.jpg"}))

    def test_failure_while_saving_message_rolls_back(self):
        def broken(values):
            raise RuntimeError("lưu tin lỗi")

        self.svc.messages.create = broken
        with self.assertRaises(RuntimeError):
            self.send(self.cid)
        self.assertEqual(self.messages(), [])


class AiReplyTest(ChatTestBase):
    def test_ai_messages_only_through_internal_flow(self):
        ai = self.start(mode="AI")
        self.send(ai.ConversationId, content="Shop có iPhone 16 không?")
        reply = self.svc.record_ai_reply(ai.ConversationId, "  Dạ có ạ  ")
        self.assertEqual((reply.SenderType, reply.SenderUserId, reply.MessageType, reply.Content), ("AI", None, "Text", "Dạ có ạ"))
        staff_mode = self.start(by=self.other)
        self.assert_error(BusinessRuleError, "conversation_not_ai_mode",
                          lambda: self.svc.record_ai_reply(staff_mode.ConversationId, "x"))
        self.assert_error(BusinessRuleError, "message_content_required", lambda: self.svc.record_ai_reply(ai.ConversationId, " "))
        self.db.get(Conversation, ai.ConversationId).Status = "Closed"
        self.assert_error(BusinessRuleError, "conversation_closed", lambda: self.svc.record_ai_reply(ai.ConversationId, "x"))
        self.assertEqual(sum(1 for m in self.messages() if m.SenderType == "AI"), 1)


class CloseConversationTest(ChatTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.conversation = self.start()
        self.cid = self.conversation.ConversationId

    def test_assigned_staff_closes_when_done(self):
        self.claim(self.cid)
        self.clock.now = NOW + timedelta(minutes=30)
        result = self.svc.close_conversation(self.a(self.staff), self.cid)
        self.assertEqual((result.Status, result.ClosedAt), ("Closed", NOW + timedelta(minutes=30)))
        self.assert_error(BusinessRuleError, "conversation_closed", lambda: self.svc.close_conversation(self.a(self.staff), self.cid))
        self.assert_error(BusinessRuleError, "conversation_closed", lambda: self.claim(self.cid, by=self.staff2))
        self.assertEqual(self.db.get(Conversation, self.cid).ClosedAt, NOW + timedelta(minutes=30))

    def test_only_the_assigned_staff_can_close(self):
        self.assert_error(BusinessRuleError, "conversation_not_assigned_to_you",
                          lambda: self.svc.close_conversation(self.a(self.staff), self.cid))
        self.claim(self.cid)
        self.assert_error(NotFoundError, "conversation_not_found", lambda: self.svc.close_conversation(self.a(self.staff2), self.cid))
        self.assert_error(BusinessRuleError, "conversation_not_assigned_to_you",
                          lambda: self.svc.close_conversation(self.a(self.admin), self.cid))
        # Đợt 5.3.1: Customer được đóng hội thoại của CHÍNH MÌNH; Customer khác thì không (TestCustomerClose).
        self.assert_error(NotFoundError, "conversation_not_found",
                          lambda: self.svc.close_conversation(self.a(self.other), self.cid))
        with self.assertRaises(PermissionDeniedError):
            self.svc.close_conversation(None, self.cid)
        self.assertEqual(self.db.get(Conversation, self.cid).Status, "Open")


if __name__ == "__main__":
    unittest.main()
