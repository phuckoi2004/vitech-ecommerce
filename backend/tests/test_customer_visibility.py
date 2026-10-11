"""Đợt 5.10: dữ liệu nội bộ không được trả ra cho khách hàng; serial có lịch sử không được sửa số.

- Yêu cầu trả hàng: CompensationAmount do hệ thống tính ở bước kiểm tra là đề xuất nội bộ, khách chỉ thấy sau khi Admin
  duyệt (CompensationApprovedAt) — cùng nguyên tắc với kết quả bảo hành chưa duyệt (đợt 5.4.1).
- Hội thoại: AssignedStaffId chỉ có trong schema Staff/Admin (như Orders/WarrantyRequests/ReturnRequests); tin nhắn của
  nhân viên không trả SenderUserId cho khách (cùng định danh nhân viên).
- Serial đã có lịch sử trả hàng/hàng hoàn (ReturnRequests/ShipmentReturnItems.ProductSerialId) không được sửa số dù đã
  về Available (giống quy tắc lịch sử bảo hành sẵn có).
Fake trong bộ nhớ; không chứng minh hành vi trên PostgreSQL thật.
"""

from datetime import timedelta

from app.models import ProductSerial, ShipmentReturn, ShipmentReturnItem
from app.schemas import ProductSerialUpdate
from app.services import BusinessRuleError, ProductSerialService

from tests.fakes import FakeSerialRepo, FakeWarrantyRequestRepo, fixed_clock
from tests.test_chat import ChatTestBase
from tests.test_return_service import ReturnTestBase


class ReturnCompensationVisibilityTest(ReturnTestBase):
    def customer_view(self, rid):
        return self.svc.get_my_return_request(self.a(self.customer), rid)

    def test_amount_is_hidden_from_customer_until_admin_approves(self):
        rid = self.received()
        self.assertEqual(self.inspect(rid).CompensationAmount, 100000)  # Staff/Admin thấy số tiền đề xuất
        self.assertIsNone(self.request(rid).CompensationApprovedAt)
        mine = self.customer_view(rid)
        self.assertEqual((mine.CompensationAmount, mine.RestockedQuantity), (None, 1))
        listed = self.svc.list_my_return_requests(self.a(self.customer)).Items
        self.assertEqual([r.CompensationAmount for r in listed], [None])
        self.assertEqual(self.svc.get_return_request(self.a(self.staff), rid).CompensationAmount, 100000)
        self.approve(rid, "100000.00")
        self.assertEqual(self.customer_view(rid).CompensationAmount, 100000)

    def test_admin_schema_is_not_masked(self):
        rid = self.received()
        self.inspect(rid)
        detail = self.svc.get_return_request(self.a(self.admin), rid)
        self.assertEqual((detail.CompensationAmount, detail.CompensationBasis["EligibleValue"]),
                         (100000, "100000.00"))


class ConversationStaffIdentityTest(ChatTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.conversation = self.start()
        self.claim(self.conversation.ConversationId)
        self.send(self.conversation.ConversationId)
        self.clock.now += timedelta(minutes=1)  # thứ tự tin nhắn theo SentAt
        self.send(self.conversation.ConversationId, by=self.staff, content="Chào bạn")
        self.clock.now += timedelta(minutes=1)

    def test_customer_views_do_not_expose_staff_ids(self):
        cid = self.conversation.ConversationId
        detail = self.svc.get_conversation(self.a(self.customer), cid)
        self.assertEqual(type(detail).__name__, "ConversationDetailResponse")
        self.assertNotIn("AssignedStaffId", detail.model_dump())
        self.assertEqual([(m.SenderType, m.SenderUserId) for m in detail.Messages],
                         [("Customer", self.customer.UserId), ("Staff", None)])
        page = self.svc.list_messages(self.a(self.customer), cid)
        self.assertEqual([m.SenderUserId for m in page.Items], [self.customer.UserId, None])
        listed = self.svc.list_my_conversations(self.a(self.customer)).Items
        self.assertNotIn("AssignedStaffId", listed[0].model_dump())
        self.assertNotIn("AssignedStaffId", self.start().model_dump())  # gọi lặp trả hội thoại đang mở
        sent = self.send(cid, content="Cảm ơn")
        self.assertEqual(sent.SenderUserId, self.customer.UserId)
        self.assertNotIn("AssignedStaffId", self.svc.close_conversation(self.a(self.customer), cid).model_dump())

    def test_staff_and_admin_views_keep_staff_ids(self):
        cid = self.conversation.ConversationId
        for user in (self.staff, self.admin):
            with self.subTest(role=user.Role):
                detail = self.svc.get_conversation(self.a(user), cid)
                self.assertEqual(type(detail).__name__, "AdminConversationDetailResponse")
                self.assertEqual(detail.AssignedStaffId, self.staff.UserId)
                self.assertEqual([m.SenderUserId for m in detail.Messages], [self.customer.UserId, self.staff.UserId])
                page = self.svc.list_messages(self.a(user), cid)
                self.assertEqual([m.SenderUserId for m in page.Items], [self.customer.UserId, self.staff.UserId])
        self.assertEqual(self.send(cid, by=self.staff).SenderUserId, self.staff.UserId)
        self.assertEqual(self.claim(cid).AssignedStaffId, self.staff.UserId)  # gọi lặp
        self.assertEqual(self.svc.list_assigned_conversations(self.a(self.staff)).Items[0].AssignedStaffId,
                         self.staff.UserId)
        closed = self.svc.close_conversation(self.a(self.staff), cid)
        self.assertEqual((closed.Status, closed.AssignedStaffId), ("Closed", self.staff.UserId))

    def test_ai_reply_has_no_sender(self):
        ai = self.start(mode="AI", by=self.other)
        reply = self.svc.record_ai_reply(ai.ConversationId, "Xin chào, tôi là trợ lý")
        self.assertEqual((reply.SenderType, reply.SenderUserId), ("AI", None))
        mine = self.svc.get_conversation(self.a(self.other), ai.ConversationId)
        self.assertEqual([(m.SenderType, m.SenderUserId) for m in mine.Messages], [("AI", None)])


class SerialWithReturnHistoryTest(ReturnTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.serial_svc = ProductSerialService(self.session, clock=fixed_clock)
        self.serial_svc.serials = FakeSerialRepo(self.db)
        self.serial_svc.warranty_requests = FakeWarrantyRequestRepo(self.db)

    def rename(self, serial, number="IMEI-NEW"):
        return self.serial_svc.update_serial(self.a(self.admin), serial.ProductSerialId,
                                             ProductSerialUpdate(SerialNumber=number))

    def assert_history_blocks(self, serial):
        before = (serial.SerialNumber, serial.Status, serial.OrderItemId)
        self.assert_error(BusinessRuleError, "serial_has_history", lambda: self.rename(serial))
        self.assertEqual((serial.SerialNumber, serial.Status, serial.OrderItemId), before)

    def test_returned_and_restocked_serial_keeps_its_number(self):
        rid = self.approved()
        self.assertEqual(self.refund_and_settle(rid).Status, "Completed")
        self.assertEqual((self.serial.Status, self.serial.OrderItemId), ("Available", None))
        self.assert_history_blocks(self.serial)
        self.assertEqual(self.request(rid).ProductSerialId, self.serial.ProductSerialId)

    def test_serial_back_from_a_failed_delivery_keeps_its_number(self):
        serial = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber="IMEI-SHIP",
                                           Status="Available"))
        record = self.db.add(ShipmentReturn(OrderId=self.order.OrderId, Status="Received"))
        self.db.add(ShipmentReturnItem(ShipmentReturnId=record.ShipmentReturnId, OrderItemId=self.item.OrderItemId,
                                       ProductSerialId=serial.ProductSerialId, ExpectedQuantity=1, RestockedQuantity=1,
                                       DamagedQuantity=0))
        self.assert_history_blocks(serial)

    def test_serial_without_after_sale_history_can_still_be_corrected(self):
        fresh = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber="IMEI-TYPO",
                                          Status="Available"))
        self.assertEqual(self.rename(fresh, "IMEI-FIXED").SerialNumber, "IMEI-FIXED")
