"""WarrantyService (đợt 5.4): gửi yêu cầu, hệ thống kiểm tra điều kiện, Staff tiếp nhận/kiểm tra/bàn giao,
Staff đề xuất – Admin duyệt kết quả, hoàn tất, đổi máy thay thế, lịch sử và rollback.

Fake trong bộ nhớ: khóa dòng/partial UNIQUE chỉ được giả lập (db.locks, IntegrityError); không chứng minh concurrency
thật của PostgreSQL.
"""

import unittest
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

from pydantic import ValidationError

import app.schemas
from app.models import Notification, ProductSerial, ServiceRequestAttachment, ServiceRequestHistory, WarrantyRequest
from app.schemas import (
    ServiceRequestAttachmentCreate,
    ServiceRequestNote,
    ServiceRequestRejection,
    WarrantyCompletion,
    WarrantyEligibilityUpdate,
    WarrantyHandoverCreate,
    WarrantyRequestCreate,
    WarrantyResultProposal,
    WarrantyResultRejection,
)
from app.services import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError

from tests.fakes import NOW, Factory, FakeSession, InMemoryDB, warranty_service
from tests.test_chat import bypass


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# Giao hàng 10:00 ngày 15/03/2026 giờ Việt Nam; 12 tháng → bảo hành 15/03/2026 – 14/03/2027.
DELIVERED_AT = utc(2026, 3, 15, 3, 0)
START, END = date(2026, 3, 15), date(2027, 3, 14)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):
        return self.now


class WarrantyTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.clock = Clock()
        self.svc = warranty_service(self.db, self.session, clock=self.clock)
        self.customer = self.f.user()
        self.other = self.f.user()
        self.staff = self.f.user("Staff")
        self.staff2 = self.f.user("Staff")
        self.admin = self.f.user("Admin")
        self.admin2 = self.f.user("Admin")
        self.cod = self.f.payment_method("COD")
        self.phone = self.f.variant(stock=3, serial_tracked=True)
        self.cable = self.f.variant(stock=10)
        self.order = self.delivered_order(self.customer, ((self.phone, 1), (self.cable, 2)))
        self.item = self.item_of(self.order, self.phone)
        self.cable_item = self.item_of(self.order, self.cable)
        self.serial = self.sold_serial(self.item, "IMEI-001")
        self.spare = self.stock_serial(self.phone, "IMEI-101")

    # ------------------------------------------------------------------ dữ liệu

    def delivered_order(self, customer, lines, status="Delivered"):
        order = self.f.order(customer, self.cod, status=status, payment_status="Paid", lines=lines)
        order.DeliveredAt = DELIVERED_AT
        return order

    @staticmethod
    def item_of(order, variant):
        return next(i for i in order.items if i.ProductVariantId == variant.ProductVariantId)

    def sold_serial(self, item, number, start=START, end=END):
        return self.db.add(ProductSerial(ProductVariantId=item.ProductVariantId, OrderItemId=item.OrderItemId,
                                         SerialNumber=number, Status="Sold", WarrantyStartDate=start,
                                         WarrantyEndDate=end))

    def stock_serial(self, variant, number, status="Available"):
        return self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId, SerialNumber=number, Status=status))

    # ------------------------------------------------------------------ thao tác

    def a(self, user):
        return self.f.actor(user)

    def create(self, item=None, serial="default", by=None, description="Máy không lên nguồn", attachments=()):
        item = item or self.item
        if serial == "default":
            serial = self.serial if item is self.item else None
        data = WarrantyRequestCreate(
            OrderItemId=item.OrderItemId,
            ProductSerialId=serial.ProductSerialId if serial is not None else None,
            IssueDescription=description,
            Attachments=[ServiceRequestAttachmentCreate(FileUrl=u, FileType=t) for u, t in attachments],
        )
        return self.svc.create_warranty_request(self.a(by or self.customer), data)

    def receive(self, rid, by=None):
        return self.svc.receive_warranty_request(self.a(by or self.staff), rid, ServiceRequestNote(Note="Máy trầy nhẹ"))

    def inspect(self, rid, status="Eligible", reason=None, by=None):
        return self.svc.inspect_warranty_request(
            self.a(by or self.staff), rid, WarrantyEligibilityUpdate(EligibilityStatus=status, EligibilityReason=reason))

    def handover(self, rid, by=None, supplier=None, center="TTBH Samsung Q1"):
        data = WarrantyHandoverCreate(ServiceCenter=center, HandoverCode="BG-01",
                                      SupplierId=supplier.SupplierId if supplier else None)
        return self.svc.hand_over_warranty_request(self.a(by or self.staff), rid, data)

    def start(self, rid, by=None):
        return self.svc.start_warranty_processing(self.a(by or self.staff), rid)

    def propose(self, rid, result="Repaired", note="Thay main", by=None):
        return self.svc.propose_warranty_result(self.a(by or self.staff), rid,
                                                WarrantyResultProposal(ResultType=result, ResultNote=note))

    def approve(self, rid, by=None):
        return self.svc.approve_warranty_result(self.a(by or self.admin), rid, ServiceRequestNote(Note="Đồng ý"))

    def reject(self, rid, reason="Thiếu biên bản", by=None):
        return self.svc.reject_warranty_result(self.a(by or self.admin), rid, WarrantyResultRejection(Reason=reason))

    def complete(self, rid, replacement=None, by=None):
        data = WarrantyCompletion(ReplacementProductSerialId=replacement.ProductSerialId if replacement else None)
        return self.svc.complete_warranty_request(self.a(by or self.staff), rid, data)

    def to_processing(self, item=None, serial="default"):
        rid = self.create(item=item, serial=serial).WarrantyRequestId
        self.receive(rid)
        self.inspect(rid)
        self.handover(rid)
        self.start(rid)
        return rid

    def approved(self, result="Repaired"):
        rid = self.to_processing()
        self.propose(rid, result=result)
        self.approve(rid)
        return rid

    # ------------------------------------------------------------------ kiểm tra

    def request(self, rid) -> WarrantyRequest:
        return self.db.get(WarrantyRequest, rid)

    def requests(self):
        return self.db.rows(WarrantyRequest)

    def histories(self, rid):
        return [h for h in self.db.rows(ServiceRequestHistory) if h.WarrantyRequestId == rid]

    def transitions(self, rid):
        return [(h.OldStatus, h.NewStatus) for h in self.histories(rid)]

    def assert_error(self, error, code, call):
        with self.assertRaises(error) as ctx:
            call()
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception


class CreateWarrantyRequestTest(WarrantyTestBase):
    def test_owner_creates_request_for_serial_item_in_warranty(self):
        result = self.create(attachments=(("https://cdn.vietech.vn/a.jpg", "Image"),
                                          ("https://cdn.vietech.vn/b.mp4", "Video")))
        self.assertEqual((result.Status, result.EligibilityStatus, result.EligibilityReason), ("New", "Pending", None))
        self.assertEqual((result.OrderItemId, result.ProductSerialId), (self.item.OrderItemId, self.serial.ProductSerialId))
        self.assertTrue(result.RequestCode.startswith("BH261009"))
        self.assertEqual([(a.FileUrl, a.FileType) for a in result.Attachments],
                         [("https://cdn.vietech.vn/a.jpg", "Image"), ("https://cdn.vietech.vn/b.mp4", "Video")])
        [history] = self.histories(result.WarrantyRequestId)
        self.assertEqual((history.OldStatus, history.NewStatus, history.ChangedByUserId, history.ChangedAt),
                         (None, "New", self.customer.UserId, NOW))
        self.assertIn("còn bảo hành đến 14/03/2027", history.Note)
        self.assertEqual(self.serial.Status, "Sold")  # chưa tiếp nhận sản phẩm
        self.assertEqual(len(self.f.notifications_for(self.customer)), 1)
        self.assertEqual(self.session.commits, 1)

    def test_completed_order_is_also_delivered(self):
        order = self.delivered_order(self.customer, ((self.phone, 1),), status="Completed")
        serial = self.sold_serial(order.items[0], "IMEI-002")
        self.assertEqual(self.create(item=order.items[0], serial=serial).Status, "New")

    def test_customer_cannot_use_another_customers_order(self):
        self.assert_error(NotFoundError, "order_item_not_found", lambda: self.create(by=self.other))
        self.assert_error(NotFoundError, "order_item_not_found", lambda: self.svc.create_warranty_request(
            self.a(self.customer), WarrantyRequestCreate(OrderItemId=uuid.uuid4(), IssueDescription="x")))
        self.assertEqual(self.requests(), [])

    def test_order_not_delivered_is_rejected_without_record(self):
        for status in ("Pending", "Confirmed", "Processing", "Shipping", "Cancelled"):
            with self.subTest(status=status):
                self.order.OrderStatus = status
                self.assert_error(BusinessRuleError, "warranty_order_not_delivered", lambda: self.create())
        self.assertEqual(self.requests(), [])

    def test_delivered_without_delivery_time_is_reported(self):
        self.order.DeliveredAt = None
        self.assert_error(BusinessRuleError, "delivery_not_recorded", lambda: self.create(item=self.cable_item))
        self.assertEqual(self.requests(), [])

    def test_last_day_of_warranty_is_still_covered(self):
        self.clock.now = utc(2027, 3, 14, 16, 59, 59)  # 23:59:59 ngày 14/03/2027 giờ Việt Nam
        self.assertEqual(self.create().Status, "New")

    def test_expired_warranty_is_automatically_rejected_and_notified(self):
        self.clock.now = utc(2027, 3, 14, 17, 0)  # 00:00 ngày 15/03/2027 giờ Việt Nam
        result = self.create()
        self.assertEqual((result.Status, result.EligibilityStatus), ("Rejected", "Ineligible"))
        self.assertIn("14/03/2027", result.EligibilityReason)
        [history] = self.histories(result.WarrantyRequestId)
        self.assertEqual((history.OldStatus, history.NewStatus, history.ChangedByUserId), (None, "Rejected", None))
        self.assertIn("Hệ thống tự động từ chối", history.Note)
        [notification] = self.f.notifications_for(self.customer)
        self.assertIn(result.EligibilityReason, notification.Content)
        self.assertEqual(self.serial.Status, "Sold")
        self.assertEqual(self.create().Status, "Rejected")  # yêu cầu bị từ chối không chặn lần gửi sau

    def test_zero_month_warranty_is_automatically_rejected(self):
        self.item.WarrantyMonths = 0
        self.serial.WarrantyStartDate = self.serial.WarrantyEndDate = None
        result = self.create()
        self.assertEqual((result.Status, result.EligibilityStatus), ("Rejected", "Ineligible"))
        self.assertIn("không có bảo hành", result.EligibilityReason)

    def test_non_serial_item_uses_delivery_date_and_purchased_months(self):
        self.assertEqual(self.create(item=self.cable_item).Status, "New")
        other = self.delivered_order(self.customer, ((self.cable, 1),))
        other.items[0].WarrantyMonths = 6  # 15/03/2026 + 6 tháng − 1 ngày = 14/09/2026 < 09/10/2026
        self.cable.product.WarrantyMonths = 24  # giá trị catalog hiện tại không được dùng
        result = self.create(item=other.items[0])
        self.assertEqual(result.Status, "Rejected")
        self.assertIn("14/09/2026", result.EligibilityReason)

    def test_serial_must_belong_to_the_order_line(self):
        other_order = self.delivered_order(self.other, ((self.phone, 1),))
        foreign = self.sold_serial(other_order.items[0], "IMEI-OTHER")
        wrong_variant = self.stock_serial(self.f.variant(serial_tracked=True), "IMEI-WRONG-VARIANT", status="Sold")
        wrong_variant.OrderItemId = self.item.OrderItemId  # gắn nhầm dòng đơn nhưng khác biến thể
        cases = [foreign, self.spare, wrong_variant, SimpleNamespace(ProductSerialId=uuid.uuid4())]
        for serial in cases:
            with self.subTest(serial=serial.ProductSerialId):
                self.assert_error(BusinessRuleError, "serial_not_in_order_item", lambda s=serial: self.create(serial=s))
        self.assert_error(BusinessRuleError, "warranty_serial_required", lambda: self.create(serial=None))
        self.assert_error(BusinessRuleError, "serial_not_applicable",
                          lambda: self.create(item=self.cable_item, serial=self.serial))
        self.assertEqual(self.requests(), [])

    def test_serial_no_longer_with_customer(self):
        for status in ("Returned", "Warranty", "Available"):
            with self.subTest(status=status):
                self.serial.Status = status
                self.assert_error(BusinessRuleError, "serial_not_with_customer", lambda: self.create())
        self.assertEqual(self.requests(), [])

    def test_serial_with_open_request_cannot_get_another(self):
        first = self.create()
        error = self.assert_error(ConflictError, "warranty_request_open", lambda: self.create())
        self.assertIn(first.RequestCode, str(error))
        self.svc.cancel_warranty_request(self.a(self.customer), first.WarrantyRequestId)
        self.assertEqual(self.create().Status, "New")  # yêu cầu đã hủy không còn chặn
        cable = self.create(item=self.cable_item)
        self.assert_error(ConflictError, "warranty_request_open", lambda: self.create(item=self.cable_item))
        self.assertEqual(sum(1 for r in self.requests() if r.Status == "New"), 2)
        self.assertEqual(self.request(cable.WarrantyRequestId).ProductSerialId, None)

    def test_database_unique_index_backs_up_the_open_request_check(self):
        """Hai yêu cầu đồng thời cùng qua kiểm tra: partial UNIQUE chặn bản sau → ConflictError, rollback."""
        self.create()
        self.svc.requests.get_open_by_product_serial = lambda serial_id: None  # transaction kia chưa commit
        self.assert_error(ConflictError, "warranty_request_open", lambda: self.create())
        self.assertEqual(len(self.requests()), 1)
        self.assertEqual(len(self.db.rows(ServiceRequestHistory)), 1)

    def test_inconsistent_stored_warranty_is_reported_not_fixed(self):
        self.serial.WarrantyEndDate = date(2027, 3, 15)  # công thức cũ (không trừ 1 ngày)
        self.assert_error(BusinessRuleError, "warranty_data_inconsistent", lambda: self.create())
        self.assertEqual(self.serial.WarrantyEndDate, date(2027, 3, 15))
        self.serial.WarrantyStartDate = None
        self.assert_error(BusinessRuleError, "invalid_stored_warranty", lambda: self.create())
        self.serial.WarrantyStartDate = self.serial.WarrantyEndDate = None  # đã bán nhưng thiếu ngày bảo hành
        self.assert_error(BusinessRuleError, "warranty_data_inconsistent", lambda: self.create())
        self.assertEqual(self.requests(), [])

    def test_description_and_attachments_are_validated(self):
        self.assert_error(BusinessRuleError, "issue_description_required", lambda: self.create(description="   "))
        with self.assertRaises(ValidationError):
            ServiceRequestAttachmentCreate(FileUrl="https://cdn.vietech.vn/a.pdf", FileType="Document")
        with self.assertRaises(ValidationError):
            ServiceRequestAttachmentCreate(FileUrl="https://cdn.vietech.vn/" + "a" * 480, FileType="Image")
        bad = [("Document", "https://cdn.vietech.vn/a.pdf", "invalid_attachment_type"),
               ("Image", "http://cdn.vietech.vn/a.jpg", "invalid_attachment_url"),
               ("Image", "https://cdn.vietech.vn/a b.jpg", "invalid_attachment_url"),
               ("Video", "https://cdn.vietech.vn/" + "a" * 480, "invalid_attachment_url")]
        for file_type, url, code in bad:
            with self.subTest(code=code, url=url[:40]):
                data = bypass({"OrderItemId": self.item.OrderItemId, "ProductSerialId": self.serial.ProductSerialId,
                               "IssueDescription": "Lỗi", "Attachments": [SimpleNamespace(FileUrl=url, FileType=file_type)]})
                self.assert_error(BusinessRuleError, code,
                                  lambda d=data: self.svc.create_warranty_request(self.a(self.customer), d))
        self.assertEqual((self.requests(), self.db.rows(ServiceRequestAttachment)), ([], []))

    def test_customer_cannot_set_server_controlled_fields(self):
        with self.assertRaises(ValidationError):
            WarrantyRequestCreate(OrderItemId=self.item.OrderItemId, IssueDescription="x", Status="Completed")
        base = {"OrderItemId": self.item.OrderItemId, "ProductSerialId": self.serial.ProductSerialId,
                "IssueDescription": "Lỗi"}
        for extra in ({"Status": "Completed"}, {"EligibilityStatus": "Eligible"}, {"ResultType": "ProductReplaced"},
                      {"CustomerId": self.other.UserId}, {"AssignedStaffId": self.staff.UserId}):
            with self.subTest(extra=extra):
                self.assert_error(BusinessRuleError, "warranty_field_not_allowed",
                                  lambda e=extra: self.svc.create_warranty_request(self.a(self.customer), bypass({**base, **e})))
        self.assertEqual(self.requests(), [])

    def test_only_customers_create_requests(self):
        for user in (self.staff, self.admin):
            with self.subTest(role=user.Role):
                self.assert_error(PermissionDeniedError, "permission_denied", lambda u=user: self.create(by=u))
        self.assert_error(PermissionDeniedError, "authentication_required",
                          lambda: self.svc.create_warranty_request(None, WarrantyRequestCreate(
                              OrderItemId=self.item.OrderItemId, IssueDescription="x")))


class ProcessingFlowTest(WarrantyTestBase):
    def test_full_repair_flow_records_every_step(self):
        supplier = self.f.supplier()
        rid = self.create().WarrantyRequestId
        self.clock.now = utc(2026, 10, 10, 2, 0)
        received = self.receive(rid)
        self.assertEqual((received.Status, received.ReceivedAt, received.AssignedStaffId),
                         ("New", utc(2026, 10, 10, 2, 0), self.staff.UserId))
        self.assertEqual(self.serial.Status, "Warranty")
        self.assertEqual(self.inspect(rid).EligibilityStatus, "Eligible")
        handed = self.handover(rid, by=self.staff2, supplier=supplier)
        self.assertEqual((handed.Status, handed.ServiceCenter, handed.HandoverCode, handed.SupplierId, handed.HandedOverAt),
                         ("HandedOver", "TTBH Samsung Q1", "BG-01", supplier.SupplierId, utc(2026, 10, 10, 2, 0)))
        self.assertEqual(handed.AssignedStaffId, self.staff.UserId)  # người tiếp nhận giữ nguyên
        self.assertEqual(self.start(rid).Status, "Processing")
        proposed = self.propose(rid)
        self.assertEqual((proposed.ResultType, proposed.ResultNote, proposed.ResultApprovedAt), ("Repaired", "Thay main", None))
        self.clock.now = utc(2026, 10, 20, 3, 0)
        approved = self.approve(rid)
        self.assertEqual((approved.ResultApprovedAt, approved.ResultApprovedByUserId), (self.clock.now, self.admin.UserId))
        self.assertEqual(approved.Status, "Processing")  # duyệt chưa phải hoàn tất
        done = self.complete(rid)
        self.assertEqual((done.Status, done.CompletedAt, done.ReplacementProductSerialId), ("Completed", self.clock.now, None))
        self.assertEqual((self.serial.Status, self.serial.WarrantyStartDate, self.serial.WarrantyEndDate), ("Sold", START, END))
        self.assertEqual(self.transitions(rid), [
            (None, "New"), ("New", "New"), ("New", "New"), ("New", "HandedOver"), ("HandedOver", "Processing"),
            ("Processing", "Processing"), ("Processing", "Processing"), ("Processing", "Completed")])
        actors = [h.ChangedByUserId for h in self.histories(rid)]
        self.assertEqual(actors, [self.customer.UserId, self.staff.UserId, self.staff.UserId, self.staff2.UserId,
                                  self.staff.UserId, self.staff.UserId, self.admin.UserId, self.staff.UserId])
        self.assertTrue(all(h.Note or h.InternalNote for h in self.histories(rid)))
        self.assertEqual([h.IsInternal for h in self.histories(rid)], [False] * 5 + [True] + [False] * 2)  # đề xuất
        self.assertIn("Máy trầy nhẹ", self.histories(rid)[1].Note)
        self.assertEqual((approved.ResultProposedByUserId, approved.ResultProposedAt),
                         (self.staff.UserId, utc(2026, 10, 10, 2, 0)))
        detail = self.svc.get_my_warranty_request(self.a(self.customer), rid)
        self.assertEqual(len(detail.Histories), 7)  # khách không thấy dòng đề xuất nội bộ
        self.assertFalse(hasattr(detail.Histories[0], "ChangedByUserId"))
        admin_detail = self.svc.get_warranty_request(self.a(self.staff), rid)
        self.assertEqual(admin_detail.Histories[-1].ChangedByUserId, self.staff.UserId)
        self.assertEqual(len(self.f.notifications_for(self.customer)), 6)

    def test_inspection_failure_rejects_with_reason_and_returns_device(self):
        rid = self.create().WarrantyRequestId
        self.receive(rid)
        self.assert_error(BusinessRuleError, "eligibility_reason_required", lambda: self.inspect(rid, "Ineligible"))
        self.assertEqual(self.request(rid).EligibilityStatus, "Pending")
        result = self.inspect(rid, "Ineligible", reason="Máy vào nước")
        self.assertEqual((result.Status, result.EligibilityStatus, result.EligibilityReason),
                         ("Rejected", "Ineligible", "Máy vào nước"))
        self.assertEqual(self.serial.Status, "Sold")
        self.assertEqual(self.transitions(rid)[-1], ("New", "Rejected"))
        self.assertIn("Máy vào nước", self.f.notifications_for(self.customer)[-1].Content)
        self.assertEqual(self.create().Status, "New")  # không còn yêu cầu đang xử lý

    def test_steps_out_of_order_are_rejected_without_changes(self):
        rid = self.create().WarrantyRequestId
        attempts = [
            (BusinessRuleError, "warranty_not_received", lambda: self.inspect(rid)),
            (BusinessRuleError, "warranty_not_received", lambda: self.handover(rid)),
            (BusinessRuleError, "invalid_warranty_transition", lambda: self.start(rid)),
            (BusinessRuleError, "invalid_warranty_transition", lambda: self.propose(rid)),
            (BusinessRuleError, "invalid_warranty_transition", lambda: self.approve(rid)),
            (BusinessRuleError, "invalid_warranty_transition", lambda: self.complete(rid)),
        ]
        self.run_attempts(rid, attempts)
        self.receive(rid)
        self.run_attempts(rid, [
            (BusinessRuleError, "warranty_already_received", lambda: self.receive(rid)),
            (BusinessRuleError, "warranty_not_eligible", lambda: self.handover(rid)),
        ])
        self.inspect(rid)
        self.run_attempts(rid, [(BusinessRuleError, "warranty_already_inspected", lambda: self.inspect(rid))])
        self.handover(rid)
        self.run_attempts(rid, [
            (BusinessRuleError, "invalid_warranty_transition", lambda: self.handover(rid)),
            (BusinessRuleError, "invalid_warranty_transition", lambda: self.propose(rid)),
        ])
        self.start(rid)
        self.run_attempts(rid, [
            (BusinessRuleError, "warranty_result_not_proposed", lambda: self.approve(rid)),
            (BusinessRuleError, "warranty_result_not_proposed", lambda: self.reject(rid)),
            (BusinessRuleError, "warranty_result_not_approved", lambda: self.complete(rid)),
        ])
        self.propose(rid)
        self.run_attempts(rid, [(BusinessRuleError, "warranty_result_not_approved", lambda: self.complete(rid))])
        self.approve(rid)
        self.complete(rid)
        self.run_attempts(rid, [
            (BusinessRuleError, "invalid_warranty_transition", lambda: self.complete(rid)),
            (BusinessRuleError, "invalid_warranty_transition", lambda: self.propose(rid)),
            (BusinessRuleError, "invalid_warranty_transition", lambda: self.receive(rid)),
        ])
        self.assertEqual(self.request(rid).Status, "Completed")

    def run_attempts(self, rid, attempts):
        for error, code, call in attempts:
            with self.subTest(code=code):
                before = (self.request(rid).Status, len(self.histories(rid)), self.serial.Status)
                self.assert_error(error, code, call)
                self.assertEqual((self.request(rid).Status, len(self.histories(rid)), self.serial.Status), before)

    def test_customer_cannot_act_as_staff_or_admin(self):
        rid = self.create().WarrantyRequestId
        customer = self.a(self.customer)
        calls = [
            lambda a: self.svc.receive_warranty_request(a, rid),
            lambda a: self.svc.inspect_warranty_request(a, rid, WarrantyEligibilityUpdate(EligibilityStatus="Eligible")),
            lambda a: self.svc.hand_over_warranty_request(a, rid, WarrantyHandoverCreate(ServiceCenter="TT")),
            lambda a: self.svc.start_warranty_processing(a, rid),
            lambda a: self.svc.propose_warranty_result(a, rid, WarrantyResultProposal(ResultType="Repaired", ResultNote="x")),
            lambda a: self.svc.approve_warranty_result(a, rid),
            lambda a: self.svc.reject_warranty_result(a, rid, ServiceRequestRejection(Reason="x")),
            lambda a: self.svc.complete_warranty_request(a, rid),
            lambda a: self.svc.list_warranty_requests(a),
            lambda a: self.svc.get_warranty_request(a, rid),
        ]
        for index, call in enumerate(calls):
            with self.subTest(call=index):
                self.assert_error(PermissionDeniedError, "permission_denied", lambda c=call: c(customer))
        forged = SimpleNamespace(user_id=self.customer.UserId, role="Admin")  # role do client tự khai
        with self.assertRaises(TypeError):
            self.svc.approve_warranty_result(forged, rid)
        for call in (calls[5], calls[6]):  # Staff không duyệt/từ chối kết quả thay Admin
            self.assert_error(PermissionDeniedError, "permission_denied", lambda c=call: c(self.a(self.staff)))
        self.assertEqual((self.request(rid).Status, self.request(rid).ReceivedAt, len(self.histories(rid))), ("New", None, 1))

    def test_admin_inherits_staff_steps(self):
        rid = self.create().WarrantyRequestId
        self.receive(rid, by=self.admin)
        self.inspect(rid, by=self.admin)
        self.handover(rid, by=self.admin)
        self.start(rid, by=self.admin)
        self.propose(rid, by=self.admin)
        self.assert_error(BusinessRuleError, "warranty_self_review_not_allowed", lambda: self.approve(rid))
        self.approve(rid, by=self.admin2)  # Admin khác người đề xuất
        self.assertEqual(self.complete(rid, by=self.admin).Status, "Completed")
        self.assertEqual(self.request(rid).AssignedStaffId, self.admin.UserId)

    def test_customer_cancels_only_new_request_not_yet_received(self):
        first = self.create().WarrantyRequestId
        self.assert_error(NotFoundError, "warranty_request_not_found",
                          lambda: self.svc.cancel_warranty_request(self.a(self.other), first))
        cancelled = self.svc.cancel_warranty_request(self.a(self.customer), first, ServiceRequestNote(Note="Hết lỗi"))
        self.assertEqual(cancelled.Status, "Cancelled")
        self.assertEqual(self.transitions(first)[-1], ("New", "Cancelled"))
        self.assertIn("Hết lỗi", self.histories(first)[-1].Note)
        self.assert_error(BusinessRuleError, "warranty_not_cancellable",
                          lambda: self.svc.cancel_warranty_request(self.a(self.customer), first))
        second = self.create().WarrantyRequestId
        self.receive(second)
        self.assert_error(BusinessRuleError, "warranty_not_cancellable",
                          lambda: self.svc.cancel_warranty_request(self.a(self.customer), second))
        self.assertEqual((self.request(second).Status, self.serial.Status), ("New", "Warranty"))
        self.assert_error(PermissionDeniedError, "permission_denied",
                          lambda: self.svc.cancel_warranty_request(self.a(self.staff), second))

    def test_serial_state_is_rechecked_at_each_physical_step(self):
        """Dữ liệu serial bị đổi ngoài luồng sau khi gửi yêu cầu: báo lỗi rõ ràng, không tự sửa."""
        rid = self.create().WarrantyRequestId
        self.serial.Status = "Returned"
        self.assert_error(BusinessRuleError, "serial_not_with_customer", lambda: self.receive(rid))
        self.serial.Status = "Sold"
        self.serial.OrderItemId = self.cable_item.OrderItemId
        self.assert_error(BusinessRuleError, "serial_state_inconsistent", lambda: self.receive(rid))
        self.serial.OrderItemId = self.item.OrderItemId
        self.receive(rid)
        self.inspect(rid)
        self.handover(rid)
        self.start(rid)
        self.propose(rid)
        self.approve(rid)
        self.serial.Status = "Sold"  # không còn ở trạng thái đang bảo hành
        self.assert_error(BusinessRuleError, "serial_state_inconsistent", lambda: self.complete(rid))
        self.assertEqual((self.request(rid).Status, self.request(rid).ReceivedAt is not None), ("Processing", True))

    def test_inspection_decision_must_be_eligible_or_ineligible(self):
        rid = self.create().WarrantyRequestId
        self.receive(rid)
        self.assert_error(BusinessRuleError, "invalid_eligibility_decision", lambda: self.svc.inspect_warranty_request(
            self.a(self.staff), rid, bypass({"EligibilityStatus": "Pending"})))
        self.assert_error(BusinessRuleError, "warranty_field_not_allowed", lambda: self.svc.inspect_warranty_request(
            self.a(self.staff), rid, bypass({"EligibilityStatus": "Eligible", "Status": "HandedOver"})))
        self.assertEqual((self.request(rid).EligibilityStatus, self.request(rid).Status), ("Pending", "New"))

    def test_handover_requires_service_center_and_active_supplier(self):
        rid = self.create().WarrantyRequestId
        self.receive(rid)
        self.inspect(rid)
        self.assert_error(BusinessRuleError, "service_center_required", lambda: self.svc.hand_over_warranty_request(
            self.a(self.staff), rid, WarrantyHandoverCreate(ServiceCenter="   ")))
        inactive = self.f.supplier(active=False)
        self.assert_error(NotFoundError, "supplier_not_available", lambda: self.handover(rid, supplier=inactive))
        self.assert_error(BusinessRuleError, "warranty_field_not_allowed", lambda: self.svc.hand_over_warranty_request(
            self.a(self.staff), rid, bypass({"ServiceCenter": "TT", "Status": "Processing"})))
        self.assertEqual((self.request(rid).Status, self.request(rid).HandedOverAt), ("New", None))

    def test_staff_lists_and_customer_sees_only_own(self):
        mine = self.create().WarrantyRequestId
        other_order = self.delivered_order(self.other, ((self.cable, 1),))
        theirs = self.create(item=other_order.items[0], by=self.other).WarrantyRequestId
        self.receive(theirs)
        page = self.svc.list_my_warranty_requests(self.a(self.customer))
        self.assertEqual([r.WarrantyRequestId for r in page.Items], [mine])
        self.assert_error(NotFoundError, "warranty_request_not_found",
                          lambda: self.svc.get_my_warranty_request(self.a(self.customer), theirs))
        staff_page = self.svc.list_warranty_requests(self.a(self.staff), assigned_staff_id=self.staff.UserId)
        self.assertEqual([r.WarrantyRequestId for r in staff_page.Items], [theirs])
        self.assertEqual(self.svc.list_warranty_requests(self.a(self.admin), status="New").Total, 2)


class ResultApprovalTest(WarrantyTestBase):
    def test_proposal_notifies_admins_and_approval_notifies_staff(self):
        rid = self.to_processing()
        self.propose(rid)
        self.assertEqual([n.Title for n in self.f.notifications_for(self.admin)], ["Kết quả bảo hành chờ duyệt"])
        self.approve(rid)
        self.assertEqual(self.f.notifications_for(self.staff)[-1].Title, "Kết quả bảo hành đã được duyệt")
        last = self.histories(rid)[-1]
        self.assertEqual((last.IsInternal, last.ChangedByUserId), (False, self.admin.UserId))
        self.assertIn("Kết quả bảo hành được duyệt: Sửa chữa", last.Note)
        self.assertIn("Đồng ý", last.Note)

    def test_admin_rejects_proposal_with_reason_then_staff_proposes_again(self):
        rid = self.to_processing()
        self.propose(rid, result="ProductReplaced", note="Lỗi main")
        with self.assertRaises(ValidationError):
            WarrantyResultRejection(Reason="  ")
        self.assert_error(BusinessRuleError, "rejection_reason_required",
                          lambda: self.svc.reject_warranty_result(self.a(self.admin), rid, bypass({"Reason": " "})))
        rejected = self.reject(rid)
        self.assertEqual((rejected.ResultType, rejected.ResultNote, rejected.ResultApprovedAt, rejected.Status),
                         (None, None, None, "Processing"))
        last = self.histories(rid)[-1]  # đề xuất bị từ chối còn trong lịch sử nội bộ
        self.assertEqual((last.IsInternal, last.Note), (True, None))
        self.assertIn("Đổi máy", last.InternalNote)
        self.assertIn("Thiếu biên bản", last.InternalNote)
        self.assertEqual((self.request(rid).ResultProposedByUserId, self.request(rid).ResultProposedAt), (None, None))
        self.assert_error(BusinessRuleError, "warranty_result_not_approved", lambda: self.complete(rid))
        self.propose(rid, result="PartReplaced", note="Thay pin")
        self.assertEqual(self.approve(rid).ResultType, "PartReplaced")
        self.assertEqual(self.complete(rid).Status, "Completed")

    def test_approved_result_cannot_be_changed_or_reviewed_again(self):
        rid = self.approved()
        approved_at = self.request(rid).ResultApprovedAt
        self.assert_error(BusinessRuleError, "warranty_result_already_approved",
                          lambda: self.propose(rid, result="NotRepairable"))
        self.assert_error(BusinessRuleError, "warranty_result_already_approved", lambda: self.approve(rid))
        self.assert_error(BusinessRuleError, "warranty_result_already_approved", lambda: self.reject(rid))
        self.assertEqual((self.request(rid).ResultType, self.request(rid).ResultApprovedAt), ("Repaired", approved_at))

    def test_result_values_are_validated(self):
        rid = self.to_processing()
        with self.assertRaises(ValidationError):
            WarrantyResultProposal(ResultType="Refunded", ResultNote="x")
        with self.assertRaises(ValidationError):
            WarrantyResultProposal(ResultType="Repaired", ResultNote="  ")
        self.assert_error(BusinessRuleError, "invalid_warranty_result", lambda: self.svc.propose_warranty_result(
            self.a(self.staff), rid, bypass({"ResultType": "Refunded", "ResultNote": "x"})))
        self.assert_error(BusinessRuleError, "result_note_required", lambda: self.svc.propose_warranty_result(
            self.a(self.staff), rid, bypass({"ResultType": "Repaired", "ResultNote": " "})))
        self.assert_error(BusinessRuleError, "warranty_field_not_allowed", lambda: self.svc.propose_warranty_result(
            self.a(self.staff), rid, bypass({"ResultType": "Repaired", "ResultNote": "x", "ResultApprovedAt": NOW})))
        self.assertIsNone(self.request(rid).ResultType)

    def test_not_repairable_returns_original_device(self):
        rid = self.approved(result="NotRepairable")
        self.assertEqual(self.complete(rid).Status, "Completed")
        self.assertEqual((self.serial.Status, self.serial.WarrantyEndDate), ("Sold", END))

    def test_product_replacement_needs_a_serial_tracked_line(self):
        rid = self.to_processing(item=self.cable_item, serial=None)
        self.assert_error(BusinessRuleError, "replacement_requires_serial",
                          lambda: self.propose(rid, result="ProductReplaced"))
        self.propose(rid, result="Repaired")
        self.approve(rid)
        self.assertEqual(self.complete(rid).Status, "Completed")


class ReplacementTest(WarrantyTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.rid = self.approved(result="ProductReplaced")

    def state(self):
        request = self.request(self.rid)
        return (request.Status, request.ReplacementProductSerialId, request.ReplacementHandedOverAt,
                self.phone.StockQuantity, self.spare.Status, self.spare.OrderItemId, self.serial.Status,
                len(self.histories(self.rid)))

    def test_replacement_needs_a_real_serial(self):
        before = self.state()
        self.assert_error(BusinessRuleError, "replacement_serial_required", lambda: self.complete(self.rid))
        self.assert_error(NotFoundError, "replacement_serial_not_found",
                          lambda: self.complete(self.rid, replacement=SimpleNamespace(ProductSerialId=uuid.uuid4())))
        self.assert_error(BusinessRuleError, "replacement_same_serial", lambda: self.complete(self.rid, replacement=self.serial))
        self.assertEqual(self.state(), before)

    def test_replacement_serial_must_be_in_stock_and_same_variant(self):
        before = self.state()
        other_variant = self.stock_serial(self.f.variant(serial_tracked=True), "IMEI-OTHER")
        self.assert_error(BusinessRuleError, "replacement_variant_mismatch",
                          lambda: self.complete(self.rid, replacement=other_variant))
        unavailable = [self.stock_serial(self.phone, f"IMEI-{s}", status=s) for s in ("Reserved", "Sold", "Returned",
                                                                                    "WrittenOff", "Warranty")]
        assigned = self.stock_serial(self.phone, "IMEI-ASSIGNED")
        assigned.OrderItemId = self.delivered_order(self.other, ((self.phone, 1),)).items[0].OrderItemId
        for serial in unavailable + [assigned]:
            with self.subTest(serial=serial.SerialNumber):
                self.assert_error(BusinessRuleError, "replacement_serial_unavailable",
                                  lambda s=serial: self.complete(self.rid, replacement=s))
        self.assertEqual(self.state(), before)

    def test_original_serial_must_still_be_in_warranty(self):
        self.serial.Status = "Sold"
        self.assert_error(BusinessRuleError, "serial_state_inconsistent",
                          lambda: self.complete(self.rid, replacement=self.spare))
        self.assertEqual((self.spare.Status, self.phone.StockQuantity, self.request(self.rid).Status),
                         ("Available", 3, "Processing"))

    def test_replacement_cannot_take_stock_promised_to_other_orders(self):
        self.phone.StockQuantity = 0  # serial Available còn lại đã thuộc đơn chưa đóng gói
        self.assert_error(BusinessRuleError, "insufficient_stock", lambda: self.complete(self.rid, replacement=self.spare))
        self.assertEqual((self.spare.Status, self.spare.OrderItemId, self.request(self.rid).Status),
                         ("Available", None, "Processing"))

    def test_handover_starts_new_warranty_and_keeps_old_serial_history(self):
        self.clock.now = utc(2026, 12, 31, 18, 30)  # 01:30 ngày 01/01/2027 giờ Việt Nam
        self.db.locks.clear()
        done = self.complete(self.rid, replacement=self.spare)
        self.assertEqual((done.Status, done.CompletedAt), ("Completed", self.clock.now))
        self.assertEqual((done.ReplacementProductSerialId, done.ReplacementHandedOverAt, done.ReplacementHandedOverByUserId),
                         (self.spare.ProductSerialId, self.clock.now, self.staff.UserId))
        self.assertEqual((self.spare.Status, self.spare.OrderItemId), ("Sold", self.item.OrderItemId))
        self.assertEqual((self.spare.WarrantyStartDate, self.spare.WarrantyEndDate), (date(2027, 1, 1), date(2027, 12, 31)))
        # Serial cũ: không đổi ngày bảo hành, dòng đơn, không thành serial mới.
        self.assertEqual((self.serial.WarrantyStartDate, self.serial.WarrantyEndDate, self.serial.OrderItemId,
                          self.serial.SerialNumber, self.serial.Status),
                         (START, END, self.item.OrderItemId, "IMEI-001", "Returned"))  # máy cũ đã thu về
        available = self.svc.serials.list_by_variant(self.phone.ProductVariantId, status="Available")
        self.assertNotIn(self.serial, available)  # không tự coi máy cũ là hàng bán được
        self.assertEqual(self.request(self.rid).ProductSerialId, self.serial.ProductSerialId)
        self.assertEqual(self.phone.StockQuantity, 2)
        self.assertIn("IMEI-101", self.histories(self.rid)[-1].Note)
        locked = [name for name, _ in self.db.locks]
        self.assertEqual(locked, ["Order", "WarrantyRequest", "ProductVariant", "ProductSerial", "ProductSerial"])

    def test_replacement_device_can_get_warranty_later_but_old_device_cannot(self):
        self.clock.now = utc(2026, 12, 1, 3, 0)
        self.complete(self.rid, replacement=self.spare)
        self.clock.now = utc(2027, 11, 30, 3, 0)  # máy cũ đã hết hạn 14/03/2027, máy thay thế còn đến 30/11/2027
        later = self.create(serial=self.spare)
        self.assertEqual(later.Status, "New")
        self.assertIn("30/11/2027", self.histories(later.WarrantyRequestId)[0].Note)
        self.assert_error(BusinessRuleError, "serial_not_with_customer", lambda: self.create(serial=self.serial))

    def test_other_results_do_not_take_a_replacement(self):
        rid = self.approved_other()
        self.assert_error(BusinessRuleError, "replacement_not_applicable", lambda: self.complete(rid, replacement=self.spare))
        self.assertEqual((self.spare.Status, self.phone.StockQuantity), ("Available", 3))

    def approved_other(self):
        order = self.delivered_order(self.customer, ((self.phone, 1),))
        serial = self.sold_serial(order.items[0], "IMEI-003")
        rid = self.to_processing(item=order.items[0], serial=serial)
        self.propose(rid, result="Repaired")
        self.approve(rid)
        return rid


class ReviewRightsTest(WarrantyTestBase):
    def test_proposer_cannot_review_own_proposal_but_another_admin_can(self):
        rid = self.to_processing()
        self.propose(rid, by=self.admin, result="PartReplaced", note="Thay pin")
        for call in (lambda: self.approve(rid), lambda: self.reject(rid)):
            self.assert_error(BusinessRuleError, "warranty_self_review_not_allowed", call)
        self.assertEqual((self.request(rid).ResultApprovedAt, self.request(rid).ResultType), (None, "PartReplaced"))
        approved = self.approve(rid, by=self.admin2)
        self.assertEqual((approved.ResultProposedByUserId, approved.ResultApprovedByUserId),
                         (self.admin.UserId, self.admin2.UserId))
        other = self.to_processing(item=self.cable_item, serial=None)
        self.propose(other, by=self.admin)
        self.assertEqual(self.reject(other, by=self.admin2).ResultType, None)  # Admin khác từ chối được

    def test_unknown_proposer_must_propose_again(self):
        rid = self.to_processing()
        self.propose(rid)
        self.request(rid).ResultProposedByUserId = None  # người đề xuất đã bị xóa (SET NULL)
        self.assert_error(BusinessRuleError, "warranty_result_proposer_unknown", lambda: self.approve(rid))
        self.propose(rid)
        self.assertEqual(self.approve(rid).ResultApprovedByUserId, self.admin.UserId)

    def test_database_declares_four_eyes_constraint(self):
        checks = {c.name: str(c.sqltext) for c in WarrantyRequest.__table__.constraints
                  if c.__class__.__name__ == "CheckConstraint"}
        self.assertIn('"ResultApprovedByUserId" <> "ResultProposedByUserId"',
                      checks["CK_WarrantyRequests_Approval_NotByProposer"])
        self.assertIn('"ResultProposedAt" IS NOT NULL', checks["CK_WarrantyRequests_Proposal_Recorded"])


class AdminRejectsRequestTest(WarrantyTestBase):
    def reject_request(self, rid, reason="Máy vào nước theo kết luận trung tâm", internal=None, by=None):
        return self.svc.reject_warranty_request(self.a(by or self.admin), rid,
                                                ServiceRequestRejection(Reason=reason, InternalNote=internal))

    def test_admin_rejects_request_during_processing_with_reason_and_history(self):
        rid = self.to_processing()
        self.propose(rid, result="ProductReplaced", note="Lỗi main")
        self.clock.now = utc(2026, 10, 15, 2, 0)
        result = self.reject_request(rid, internal="Biên bản TT số 12: dấu hiệu oxy hóa")
        self.assertEqual((result.Status, result.EligibilityStatus, result.EligibilityReason),
                         ("Rejected", "Ineligible", "Máy vào nước theo kết luận trung tâm"))
        self.assertEqual((result.ResultType, result.ResultNote, result.ResultProposedByUserId), (None, None, None))
        self.assertEqual(self.serial.Status, "Sold")  # trả sản phẩm cho khách theo khả năng hiện có
        last = self.histories(rid)[-1]
        self.assertEqual((last.OldStatus, last.NewStatus, last.ChangedByUserId, last.ChangedAt, last.IsInternal),
                         ("Processing", "Rejected", self.admin.UserId, self.clock.now, False))
        self.assertIn("Máy vào nước", last.Note)
        self.assertEqual(last.InternalNote, "Biên bản TT số 12: dấu hiệu oxy hóa")
        self.assertIn("Máy vào nước", self.f.notifications_for(self.customer)[-1].Content)
        self.assertEqual(self.create().Status, "New")  # không còn yêu cầu đang xử lý

    def test_rejection_rules(self):
        rid = self.create().WarrantyRequestId
        self.assert_error(BusinessRuleError, "warranty_not_received", lambda: self.reject_request(rid))
        self.receive(rid)
        self.inspect(rid)
        self.handover(rid)
        self.assert_error(PermissionDeniedError, "permission_denied", lambda: self.reject_request(rid, by=self.staff))
        self.assert_error(PermissionDeniedError, "permission_denied", lambda: self.reject_request(rid, by=self.customer))
        with self.assertRaises(ValidationError):
            ServiceRequestRejection(Reason=" ")
        self.assert_error(BusinessRuleError, "rejection_reason_required", lambda: self.svc.reject_warranty_request(
            self.a(self.admin), rid, bypass({"Reason": " "})))
        self.assert_error(BusinessRuleError, "warranty_field_not_allowed", lambda: self.svc.reject_warranty_request(
            self.a(self.admin), rid, bypass({"Reason": "x", "Status": "Completed"})))
        self.assertEqual(self.reject_request(rid).Status, "Rejected")  # đang HandedOver
        self.assert_error(BusinessRuleError, "invalid_warranty_transition", lambda: self.reject_request(rid))
        approved = self.approved_other_line()
        self.assert_error(BusinessRuleError, "warranty_result_already_approved", lambda: self.reject_request(approved))
        self.assertEqual(self.request(approved).Status, "Processing")

    def approved_other_line(self):
        rid = self.to_processing(item=self.cable_item, serial=None)
        self.propose(rid)
        self.approve(rid)
        return rid


class InternalNotesTest(WarrantyTestBase):
    INTERNAL_TEXT = "NOI-BO: khách có dấu hiệu gian lận"

    def test_customer_never_sees_internal_notes_or_unapproved_results(self):
        rid = self.create().WarrantyRequestId
        staff = self.a(self.staff)
        self.svc.receive_warranty_request(staff, rid, ServiceRequestNote(Note="Đã nhận máy", InternalNote=self.INTERNAL_TEXT))
        self.svc.inspect_warranty_request(staff, rid, WarrantyEligibilityUpdate(EligibilityStatus="Eligible",
                                                                               InternalNote=self.INTERNAL_TEXT))
        self.svc.hand_over_warranty_request(staff, rid, WarrantyHandoverCreate(ServiceCenter="TT", InternalNote=self.INTERNAL_TEXT))
        self.svc.start_warranty_processing(staff, rid, ServiceRequestNote(InternalNote=self.INTERNAL_TEXT))
        self.propose(rid, result="ProductReplaced", note=self.INTERNAL_TEXT)
        customer = self.a(self.customer)
        mine = self.svc.get_my_warranty_request(customer, rid)
        self.assertEqual((mine.ResultType, mine.ResultNote), (None, None))  # đề xuất chưa duyệt là nội bộ
        listed = self.svc.list_my_warranty_requests(customer).Items[0]
        self.assertEqual((listed.ResultType, listed.ResultNote), (None, None))
        self.reject(rid, reason=self.INTERNAL_TEXT)
        self.propose(rid, result="Repaired", note="Đã thay main")
        self.svc.approve_warranty_result(self.a(self.admin), rid, ServiceRequestNote(Note="OK", InternalNote=self.INTERNAL_TEXT))
        for view in (self.svc.get_my_warranty_request(customer, rid), self.svc.list_my_warranty_requests(customer)):
            with self.subTest(view=type(view).__name__):
                self.assertNotIn("NOI-BO", view.model_dump_json())
                self.assertNotIn("InternalNote", view.model_dump_json())
        mine = self.svc.get_my_warranty_request(customer, rid)
        self.assertEqual((mine.ResultType, mine.ResultNote), ("Repaired", "Đã thay main"))  # đã duyệt: công khai
        self.assertFalse(any(h.Note is None for h in mine.Histories))
        self.assertEqual(len(mine.Histories), len([h for h in self.histories(rid) if not h.IsInternal]))
        admin_view = self.svc.get_warranty_request(staff, rid)
        self.assertEqual(sum(1 for h in admin_view.Histories if h.IsInternal), 3)  # 2 đề xuất + 1 từ chối đề xuất
        self.assertGreaterEqual(admin_view.model_dump_json().count("NOI-BO"), 6)

    def test_customer_cannot_write_internal_notes(self):
        rid = self.create().WarrantyRequestId
        self.assert_error(BusinessRuleError, "warranty_field_not_allowed", lambda: self.svc.cancel_warranty_request(
            self.a(self.customer), rid, ServiceRequestNote(Note="Hết lỗi", InternalNote="x")))
        self.assertEqual(self.request(rid).Status, "New")
        self.assertEqual(self.svc.cancel_warranty_request(self.a(self.customer), rid,
                                                         ServiceRequestNote(Note="Hết lỗi")).Status, "Cancelled")

    def test_history_rows_for_customers_exclude_internal_rows(self):
        rid = self.to_processing()
        self.propose(rid)
        request = self.request(rid)
        self.assertEqual([h.IsInternal for h in request.histories][-1], True)
        self.assertTrue(all(not h.IsInternal for h in request.public_histories))
        self.assertEqual(len(request.public_histories), len(request.histories) - 1)


class RollbackTest(WarrantyTestBase):
    def test_failure_after_replacement_rolls_back_every_change(self):
        rid = self.approved(result="ProductReplaced")
        before = (self.request(rid).Status, self.phone.StockQuantity, self.spare.Status, self.spare.OrderItemId,
                  self.spare.WarrantyStartDate, len(self.db.rows(ServiceRequestHistory)), len(self.db.rows(Notification)))

        def fail(*args, **kwargs):
            raise RuntimeError("lỗi giữa chừng")

        self.svc.notifications.notify = fail  # bước cuối của use case
        with self.assertRaises(RuntimeError):
            self.complete(rid, replacement=self.spare)
        request = self.request(rid)
        self.assertEqual((request.Status, request.ReplacementProductSerialId, request.ReplacementHandedOverAt,
                          request.CompletedAt), ("Processing", None, None, None))
        after = (request.Status, self.phone.StockQuantity, self.spare.Status, self.spare.OrderItemId,
                 self.spare.WarrantyStartDate, len(self.db.rows(ServiceRequestHistory)), len(self.db.rows(Notification)))
        self.assertEqual(after, before)
        self.assertEqual(self.session.events[-1], "rollback")

    def test_failure_while_creating_leaves_nothing(self):
        self.svc.notifications.notify = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("lỗi"))
        with self.assertRaises(RuntimeError):
            self.create(attachments=(("https://cdn.vietech.vn/a.jpg", "Image"),))
        self.assertEqual((self.requests(), self.db.rows(ServiceRequestAttachment), self.db.rows(ServiceRequestHistory)),
                         ([], [], []))

    def test_failure_while_receiving_restores_serial(self):
        rid = self.create().WarrantyRequestId
        self.svc.notifications.notify = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("lỗi"))
        with self.assertRaises(RuntimeError):
            self.receive(rid)
        self.assertEqual((self.serial.Status, self.request(rid).ReceivedAt, self.request(rid).AssignedStaffId),
                         ("Sold", None, None))
        self.assertEqual(len(self.histories(rid)), 1)


class WarrantySchemaAndModelTest(unittest.TestCase):
    def test_generic_update_schema_is_gone(self):
        self.assertFalse(hasattr(app.schemas, "WarrantyRequestUpdate"))
        self.assertNotIn("WarrantyRequestUpdate", app.schemas.__all__)

    def test_closed_value_sets(self):
        for value in ("Image", "Video"):
            self.assertEqual(ServiceRequestAttachmentCreate(FileUrl="https://x.vn/a", FileType=value).FileType, value)
        for value in ("image", "Audio", ""):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ServiceRequestAttachmentCreate(FileUrl="https://x.vn/a", FileType=value)
        with self.assertRaises(ValidationError):
            WarrantyEligibilityUpdate(EligibilityStatus="Pending")

    def test_model_declares_new_constraints_and_partial_unique_indexes(self):
        table = WarrantyRequest.__table__
        checks = {c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"}
        for name in ("CK_WarrantyRequests_ResultType_Valid", "CK_WarrantyRequests_Replacement_OnlyProductReplaced",
                     "CK_WarrantyRequests_Approval_RequiresResult",
                     "CK_WarrantyRequests_Completed_RequiresApprovedResult"):
            self.assertIn(name, checks)
        indexes = {i.name: i for i in table.indexes}
        for name, column in (("UX_WarrantyRequests_Serial_Open", "ProductSerialId"),
                             ("UX_WarrantyRequests_OrderItem_Open_NoSerial", "OrderItemId")):
            index = indexes[name]
            self.assertTrue(index.unique)
            self.assertEqual([c.name for c in index.columns], [column])
            where = str(index.dialect_options["postgresql"]["where"])
            self.assertIn("'New', 'HandedOver', 'Processing'", where)
        attachment_checks = {c.name for c in ServiceRequestAttachment.__table__.constraints
                             if c.__class__.__name__ == "CheckConstraint"}
        self.assertIn("CK_ServiceRequestAttachments_FileType_Valid", attachment_checks)


if __name__ == "__main__":
    unittest.main()
