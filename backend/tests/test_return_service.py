"""ReturnService (đợt 5.4): yêu cầu đổi/trả, chính sách thời hạn (cấu hình), nhận hàng và kiểm tra thực tế, nhập lại
tồn khi Admin duyệt, hoàn tiền qua PaymentService (RefundOfPaymentTransactionId), chống lặp, rollback.

Fake trong bộ nhớ: khóa dòng/UNIQUE chỉ được giả lập (db.locks, IntegrityError); không chứng minh concurrency thật của
PostgreSQL.
"""

import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError

import app.schemas
from app.models import (
    Notification,
    PaymentTransaction,
    ProductSerial,
    ReturnRequest,
    ServiceRequestAttachment,
    ServiceRequestHistory,
)
from app.schemas import (
    ReturnApproval,
    ReturnGoodsReceive,
    ReturnInspection,
    ReturnRefundCreate,
    ReturnRequestCreate,
    ServiceRequestAttachmentCreate,
    ServiceRequestNote,
    ServiceRequestRejection,
    WarrantyRequestCreate,
)
from app.services import (
    BusinessRuleError,
    ConflictError,
    GatewayRefundResult,
    NotFoundError,
    PaymentGatewayError,
    PermissionDeniedError,
    ReturnPolicy,
)
from app.services.base import _DEPTH_KEY

from tests.fakes import NOW, Factory, FakeSession, InMemoryDB, resolve_refund, return_service, warranty_service
from tests.test_chat import bypass
from tests.test_payment import FakeGateway
from tests.test_refund_sources import ManualRefundGateway


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


# Giao hàng 10:00 ngày 05/10/2026 giờ Việt Nam. Chính sách thử nghiệm 7 ngày → ngày cuối 11/10/2026.
DELIVERED_AT = utc(2026, 10, 5, 3, 0)
POLICY = ReturnPolicy(window_days=7)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):
        return self.now


class ReturnTestBase(unittest.TestCase):
    payment_code = "COD"
    gateway_code = None  # COD: khoản thu không qua cổng

    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.clock = Clock()
        self.gateway = self.make_gateway()
        self.svc = self.service(POLICY)
        self.customer = self.f.user()
        self.other = self.f.user()
        self.staff = self.f.user("Staff")
        self.admin = self.f.user("Admin")
        self.method = self.f.payment_method(self.payment_code)
        self.phone = self.f.variant(stock=5, serial_tracked=True, price="100000.00")
        self.cable = self.f.variant(stock=10, price="30000.00")
        self.order = self.delivered_order(self.customer, ((self.phone, 1), (self.cable, 3)), total="190000.00")
        self.item = self.item_of(self.order, self.phone)
        self.cable_item = self.item_of(self.order, self.cable)
        self.serial = self.db.add(ProductSerial(
            ProductVariantId=self.phone.ProductVariantId, OrderItemId=self.item.OrderItemId, SerialNumber="IMEI-001",
            Status="Sold", WarrantyStartDate=date(2026, 10, 5), WarrantyEndDate=date(2027, 10, 4)))
        self.payment = self.f.payment(self.order, status="Success", gateway_code=self.gateway_code)

    def make_gateway(self):
        return None

    def service(self, policy):
        return return_service(self.db, self.session, clock=self.clock, policy=policy, gateway=self.gateway)

    def delivered_order(self, customer, lines, total="130000.00", status="Delivered"):
        order = self.f.order(customer, self.method, status=status, payment_status="Paid", total=total, lines=lines)
        order.DeliveredAt = DELIVERED_AT
        return order

    @staticmethod
    def item_of(order, variant):
        return next(i for i in order.items if i.ProductVariantId == variant.ProductVariantId)

    # ------------------------------------------------------------------ thao tác

    def a(self, user):
        return self.f.actor(user)

    def create(self, request_type="Return", item=None, serial="default", quantity=None, by=None, reason="Không ưng ý",
               attachments=(), svc=None):
        item = item or self.item
        if serial == "default":
            serial = self.serial if item is self.item else None
        values = {"OrderItemId": item.OrderItemId, "RequestType": request_type, "Reason": reason,
                  "ProductSerialId": serial.ProductSerialId if serial is not None else None,
                  "Attachments": [ServiceRequestAttachmentCreate(FileUrl=u, FileType=t) for u, t in attachments]}
        if quantity is not None:
            values["Quantity"] = quantity
        return (svc or self.svc).create_return_request(self.a(by or self.customer), ReturnRequestCreate(**values))

    def accept(self, rid, by=None):
        return self.svc.accept_return_request(self.a(by or self.staff), rid, ServiceRequestNote(Note="Hợp lệ"))

    def receiving(self, rid, by=None):
        return self.svc.start_return_receiving(self.a(by or self.staff), rid)

    def receive(self, rid, serial_number="IMEI-001", by=None):
        return self.svc.receive_return_goods(self.a(by or self.staff), rid,
                                             ReturnGoodsReceive(SerialNumber=serial_number))

    def inspect(self, rid, restocked=1, damaged=0, assessment=None, by=None):
        data = ReturnInspection(RestockedQuantity=restocked, DamagedQuantity=damaged, DamageAssessment=assessment)
        return self.svc.inspect_return_goods(self.a(by or self.staff), rid, data)

    def approve(self, rid, amount, by=None):
        return self.svc.approve_return_request(self.a(by or self.admin), rid,
                                               ReturnApproval(CompensationAmount=Decimal(amount)))

    def reject(self, rid, reason="Không đủ điều kiện", by=None):
        return self.svc.reject_return_request(self.a(by or self.staff), rid, ServiceRequestRejection(Reason=reason))

    def refund(self, rid, by=None, source=None):
        data = ReturnRefundCreate(PaymentTransactionId=source.PaymentTransactionId) if source is not None else None
        return self.svc.refund_return_request(self.a(by or self.staff), rid, data)

    def settle(self, rid, by=None, success=True):
        """Đợt 5.11: Admin khác người tạo xác nhận Refund Pending của yêu cầu; thành công thì hoàn tất yêu cầu."""
        refund = self.db.get(PaymentTransaction, self.request(rid).RefundPaymentTransactionId)
        checker = by or (self.admin if refund.CreatedByUserId != self.admin.UserId else self.f.user("Admin"))
        resolve_refund(self.svc.payments, self.a(checker), refund.PaymentTransactionId, success=success)
        if not success:
            return self.svc.get_return_request(self.a(self.staff), rid)
        return self.svc.confirm_return_refund(self.a(self.staff), rid)

    def refund_and_settle(self, rid, by=None, source=None):
        self.assertEqual(self.refund(rid, by=by, source=source).Status, "Processing")  # Refund Pending, chưa hoàn
        return self.settle(rid)

    def received(self, item=None, serial="default", quantity=None, request_type="Return"):
        item = item or self.item
        rid = self.create(request_type=request_type, item=item, serial=serial, quantity=quantity).ReturnRequestId
        self.accept(rid)
        self.receiving(rid)
        self.receive(rid, serial_number="IMEI-001" if item is self.item else None)
        return rid

    def approved(self, amount="100000.00"):
        rid = self.received()
        self.inspect(rid)
        self.approve(rid, amount)
        return rid

    # ------------------------------------------------------------------ kiểm tra

    def request(self, rid) -> ReturnRequest:
        return self.db.get(ReturnRequest, rid)

    def requests(self):
        return self.db.rows(ReturnRequest)

    def histories(self, rid):
        return [h for h in self.db.rows(ServiceRequestHistory) if h.ReturnRequestId == rid]

    def transitions(self, rid):
        return [(h.OldStatus, h.NewStatus) for h in self.histories(rid)]

    def refunds(self):
        return [t for t in self.db.rows(PaymentTransaction) if t.TransactionType == "Refund"]

    def assert_error(self, error, code, call):
        with self.assertRaises(error) as ctx:
            call()
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception


class CreateReturnRequestTest(ReturnTestBase):
    def test_valid_return_and_exchange_requests(self):
        result = self.create(attachments=(("https://cdn.vietech.vn/box.jpg", "Image"),))
        self.assertEqual((result.Status, result.RequestType, result.ProductSerialId, result.Quantity),
                         ("Pending", "Return", self.serial.ProductSerialId, 1))
        self.assertTrue(result.RequestCode.startswith("DT261009"))
        self.assertEqual([a.FileType for a in result.Attachments], ["Image"])
        [history] = self.histories(result.ReturnRequestId)
        self.assertEqual((history.OldStatus, history.NewStatus, history.ChangedByUserId), (None, "Pending", self.customer.UserId))
        exchange = self.create(request_type="Exchange", item=self.cable_item, quantity=2)
        self.assertEqual((exchange.Status, exchange.RequestType, exchange.ProductSerialId, exchange.Quantity),
                         ("Pending", "Exchange", None, 2))
        self.assertEqual((self.serial.Status, self.phone.StockQuantity, self.cable.StockQuantity), ("Sold", 5, 10))
        self.assertEqual(len(self.f.notifications_for(self.customer)), 2)

    def test_missing_policy_refuses_without_inventing_a_deadline(self):
        svc = self.service(None)
        self.clock.now = DELIVERED_AT  # kể cả ngay lúc giao hàng
        self.assert_error(BusinessRuleError, "return_policy_not_configured", lambda: self.create(svc=svc))
        self.assert_error(BusinessRuleError, "return_policy_not_configured",
                          lambda: self.create(svc=svc, request_type="Exchange", item=self.cable_item, quantity=1))
        self.assertEqual(self.requests(), [])
        self.assertIsNone(svc.policy.window_days)

    def test_configured_window_is_enforced_inclusive_of_last_day(self):
        self.clock.now = utc(2026, 10, 11, 16, 59, 59)  # 23:59:59 ngày 11/10 giờ Việt Nam
        self.assertEqual(self.create(item=self.cable_item, quantity=1).Status, "Pending")
        self.clock.now = utc(2026, 10, 11, 17, 0)  # 00:00 ngày 12/10 giờ Việt Nam
        error = self.assert_error(BusinessRuleError, "return_window_expired", lambda: self.create())
        self.assertIn("11/10/2026", str(error))
        for bad in (0, -1, True, 1.5):
            with self.subTest(window_days=bad), self.assertRaises(ValueError):
                ReturnPolicy(window_days=bad)

    def test_customer_cannot_use_another_customers_order(self):
        self.assert_error(NotFoundError, "order_item_not_found", lambda: self.create(by=self.other))
        self.assertEqual(self.requests(), [])

    def test_order_must_be_delivered(self):
        for status in ("Pending", "Confirmed", "Processing", "Shipping", "Cancelled"):
            with self.subTest(status=status):
                self.order.OrderStatus = status
                self.assert_error(BusinessRuleError, "return_order_not_delivered", lambda: self.create())
        self.order.OrderStatus = "Completed"
        self.assertEqual(self.create().Status, "Pending")
        self.order.DeliveredAt = None
        self.assert_error(BusinessRuleError, "delivery_not_recorded", lambda: self.create(item=self.cable_item, quantity=1))

    def test_quantity_must_be_positive_and_within_remaining(self):
        with self.assertRaises(ValidationError):
            ReturnRequestCreate(OrderItemId=self.cable_item.OrderItemId, RequestType="Return", Reason="x", Quantity=0)
        base = {"OrderItemId": self.cable_item.OrderItemId, "RequestType": "Return", "Reason": "Lỗi"}
        for bad in (0, -1, True, 1.5):
            with self.subTest(quantity=bad):
                self.assert_error(BusinessRuleError, "invalid_return_quantity", lambda q=bad: self.svc.create_return_request(
                    self.a(self.customer), bypass({**base, "Quantity": q})))
        self.assert_error(BusinessRuleError, "return_quantity_exceeded",
                          lambda: self.create(item=self.cable_item, quantity=4))
        first = self.create(item=self.cable_item, quantity=2).ReturnRequestId
        self.assert_error(BusinessRuleError, "return_quantity_exceeded",
                          lambda: self.create(request_type="Exchange", item=self.cable_item, quantity=2))
        self.svc.cancel_return_request(self.a(self.customer), first)  # yêu cầu đã hủy trả lại số lượng
        second = self.create(item=self.cable_item, quantity=3).ReturnRequestId
        self.reject(second)  # bị từ chối cũng trả lại số lượng
        self.assertEqual(self.create(item=self.cable_item, quantity=3).Quantity, 3)
        self.assert_error(BusinessRuleError, "invalid_return_quantity", lambda: self.create(quantity=2))

    def test_serial_must_be_the_one_bought_on_this_line(self):
        other_order = self.delivered_order(self.other, ((self.phone, 1),))
        foreign = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber="IMEI-X",
                                            OrderItemId=other_order.items[0].OrderItemId, Status="Sold"))
        stock = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber="IMEI-S",
                                          Status="Available"))
        for serial in (foreign, stock, SimpleNamespace(ProductSerialId=uuid.uuid4())):
            with self.subTest(serial=serial.ProductSerialId):
                self.assert_error(BusinessRuleError, "serial_not_in_order_item", lambda s=serial: self.create(serial=s))
        self.assert_error(BusinessRuleError, "return_serial_required", lambda: self.create(serial=None))
        self.assert_error(BusinessRuleError, "serial_not_applicable",
                          lambda: self.create(item=self.cable_item, serial=self.serial))
        self.serial.Status = "Warranty"
        self.assert_error(BusinessRuleError, "serial_not_with_customer", lambda: self.create())
        self.assertEqual(self.requests(), [])

    def test_same_serial_cannot_be_returned_twice(self):
        first = self.create()
        error = self.assert_error(ConflictError, "return_request_open", lambda: self.create(request_type="Exchange"))
        self.assertIn(first.RequestCode, str(error))
        self.svc.requests.get_open_by_product_serial = lambda serial_id: None  # yêu cầu đồng thời chưa commit
        self.assert_error(ConflictError, "return_request_open", lambda: self.create())
        self.assertEqual(len(self.requests()), 1)

    def test_returned_serial_cannot_be_requested_again(self):
        rid = self.approved()
        self.refund_and_settle(rid)
        self.assertEqual(self.request(rid).Status, "Completed")
        self.assert_error(BusinessRuleError, "serial_not_in_order_item", lambda: self.create())  # đã nhập lại kho

    def test_warranty_and_return_do_not_overlap(self):
        warranty = warranty_service(self.db, self.session, clock=self.clock)
        claim = WarrantyRequestCreate(OrderItemId=self.item.OrderItemId, ProductSerialId=self.serial.ProductSerialId,
                                      IssueDescription="Không lên nguồn")
        self.assertEqual(warranty.create_warranty_request(self.a(self.customer), claim).Status, "New")
        self.assert_error(ConflictError, "serial_has_open_warranty", lambda: self.create())
        cable_claim = WarrantyRequestCreate(OrderItemId=self.cable_item.OrderItemId, IssueDescription="Đứt dây")
        warranty.create_warranty_request(self.a(self.customer), cable_claim)
        self.assert_error(ConflictError, "item_has_open_warranty", lambda: self.create(item=self.cable_item, quantity=1))
        # chiều ngược lại: đang đổi/trả thì không nhận bảo hành
        order = self.delivered_order(self.customer, ((self.phone, 1), (self.cable, 1)))
        serial = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber="IMEI-002",
                                           OrderItemId=order.items[0].OrderItemId, Status="Sold",
                                           WarrantyStartDate=date(2026, 10, 5), WarrantyEndDate=date(2027, 10, 4)))
        self.create(item=order.items[0], serial=serial)
        self.create(item=order.items[1], quantity=1)
        self.assert_error(ConflictError, "serial_has_open_return", lambda: warranty.create_warranty_request(
            self.a(self.customer), WarrantyRequestCreate(OrderItemId=order.items[0].OrderItemId,
                                                         ProductSerialId=serial.ProductSerialId, IssueDescription="x")))
        self.assert_error(ConflictError, "item_has_open_return", lambda: warranty.create_warranty_request(
            self.a(self.customer), WarrantyRequestCreate(OrderItemId=order.items[1].OrderItemId, IssueDescription="x")))

    def test_type_reason_and_server_fields_are_validated(self):
        with self.assertRaises(ValidationError):
            ReturnRequestCreate(OrderItemId=self.item.OrderItemId, RequestType="Refund", Reason="x")
        base = {"OrderItemId": self.item.OrderItemId, "ProductSerialId": self.serial.ProductSerialId,
                "RequestType": "Return", "Reason": "Lỗi"}
        self.assert_error(BusinessRuleError, "invalid_return_type", lambda: self.svc.create_return_request(
            self.a(self.customer), bypass({**base, "RequestType": "Refund"})))
        self.assert_error(BusinessRuleError, "return_reason_required", lambda: self.create(reason="  "))
        for extra in ({"Status": "Approved"}, {"CompensationAmount": Decimal("1")}, {"CustomerId": self.other.UserId},
                      {"RestockedQuantity": 1}):
            with self.subTest(extra=extra):
                self.assert_error(BusinessRuleError, "return_field_not_allowed", lambda e=extra: self.svc.create_return_request(
                    self.a(self.customer), bypass({**base, **e})))
        self.assert_error(PermissionDeniedError, "permission_denied", lambda: self.create(by=self.staff))
        self.assertEqual((self.requests(), self.db.rows(ServiceRequestAttachment)), ([], []))


class ReturnFlowTest(ReturnTestBase):
    def test_received_and_passed_goods_are_restocked_on_approval_and_refunded(self):
        rid = self.create().ReturnRequestId
        self.assertEqual(self.accept(rid).AssignedStaffId, self.staff.UserId)
        self.receiving(rid)
        self.clock.now = utc(2026, 10, 9, 9, 0)
        received = self.receive(rid, serial_number="  IMEI-001 ")
        self.assertEqual((received.Status, received.ReceivedAt), ("Processing", self.clock.now))
        self.assertEqual((self.serial.Status, self.phone.StockQuantity), ("Returned", 5))  # đã về, chưa nhập tồn
        inspected = self.inspect(rid)
        self.assertEqual((inspected.RestockedQuantity, inspected.DamagedQuantity, inspected.CompensationAmount),
                         (1, 0, Decimal("100000.00")))
        self.assertEqual((inspected.CompensationBasis["LineTotal"], inspected.CompensationBasis["EligibleValue"],
                          inspected.CompensationBasis["Deductions"]), ("100000.00", "100000.00", []))
        self.assertEqual(self.phone.StockQuantity, 5)  # chưa duyệt → chưa nhập tồn
        approved = self.approve(rid, "100000.00")
        self.assertEqual((approved.CompensationApprovedAt, approved.CompensationApprovedByUserId, approved.Status),
                         (self.clock.now, self.admin.UserId, "Processing"))
        self.assertEqual((self.serial.Status, self.serial.OrderItemId, self.phone.StockQuantity), ("Available", None, 6))
        pending = self.refund(rid)
        [refund] = self.refunds()
        self.assertEqual((refund.Status, refund.Amount, refund.RefundOfPaymentTransactionId, refund.CreatedByUserId),
                         ("Pending", Decimal("100000.00"), self.payment.PaymentTransactionId, self.staff.UserId))
        self.assertEqual((pending.Status, pending.CompletedAt), ("Processing", None))  # COD: chờ Admin xác nhận
        done = self.settle(rid)
        self.assertEqual((refund.Status, refund.ResolutionSource, refund.ResolvedByUserId),
                         ("Success", "Manual", self.admin.UserId))
        self.assertEqual((done.Status, done.RefundPaymentTransactionId, done.CompletedAt),
                         ("Completed", refund.PaymentTransactionId, self.clock.now))
        self.assertEqual(self.payment.Status, "Success")  # khoản thu gốc giữ nguyên
        self.assertEqual(self.order.PaymentStatus, "Paid")  # đơn đã giao: chưa có quy tắc đổi PaymentStatus
        self.assertEqual(self.transitions(rid), [
            (None, "Pending"), ("Pending", "Approved"), ("Approved", "Receiving"), ("Receiving", "Processing"),
            ("Processing", "Processing"), ("Processing", "Processing"), ("Processing", "Processing"),
            ("Processing", "Completed")])
        actors = [h.ChangedByUserId for h in self.histories(rid)]
        self.assertEqual(actors, [self.customer.UserId] + [self.staff.UserId] * 4 + [self.admin.UserId] +
                         [self.staff.UserId] * 2)

    def test_damaged_goods_are_not_restocked_and_money_waits_for_policy(self):
        rid = self.received()
        self.assert_error(BusinessRuleError, "damage_assessment_required", lambda: self.inspect(rid, 0, 1))
        inspected = self.inspect(rid, 0, 1, assessment="Vỡ màn hình")
        self.assertIsNone(inspected.CompensationAmount)
        self.assertIn("Pending", inspected.CompensationBasis)
        self.assert_error(BusinessRuleError, "return_damage_policy_missing", lambda: self.approve(rid, "100000.00"))
        self.assertEqual((self.serial.Status, self.phone.StockQuantity), ("Returned", 5))  # không Available, không cộng tồn
        self.assertNotEqual(self.serial.Status, "WrittenOff")
        rejected = self.reject(rid, by=self.admin)
        self.assertEqual((rejected.Status, rejected.DecisionReason), ("Rejected", "Không đủ điều kiện"))
        self.assertEqual((self.serial.Status, self.serial.OrderItemId, self.phone.StockQuantity),
                         ("Sold", self.item.OrderItemId, 5))  # trả lại hàng cho khách
        partial = self.received(item=self.cable_item, serial=None, quantity=3)
        self.inspect(partial, 2, 1, assessment="1 sợi bị đứt")
        self.assert_error(BusinessRuleError, "return_damage_policy_missing", lambda: self.approve(partial, "0"))
        self.assertEqual(self.cable.StockQuantity, 10)

    def test_refund_before_goods_are_received_is_refused(self):
        rid = self.create().ReturnRequestId
        self.assert_error(BusinessRuleError, "return_not_received", lambda: self.refund(rid))
        self.accept(rid)
        self.assert_error(BusinessRuleError, "return_not_received", lambda: self.refund(rid))
        self.receiving(rid)
        self.assert_error(BusinessRuleError, "return_not_received", lambda: self.refund(rid))
        self.receive(rid)
        self.assert_error(BusinessRuleError, "return_not_approved", lambda: self.refund(rid))
        self.inspect(rid)
        self.assert_error(BusinessRuleError, "return_not_approved", lambda: self.refund(rid))
        self.assertEqual((self.refunds(), self.request(rid).RefundPaymentTransactionId), ([], None))

    def test_admin_approves_only_the_calculated_amount(self):
        rid = self.received()
        self.assert_error(BusinessRuleError, "return_not_inspected", lambda: self.approve(rid, "100000.00"))
        self.inspect(rid)
        self.assert_error(PermissionDeniedError, "permission_denied", lambda: self.approve(rid, "100000.00", by=self.staff))
        self.assert_error(BusinessRuleError, "compensation_amount_mismatch", lambda: self.approve(rid, "120000.00"))
        self.assertEqual((self.request(rid).CompensationApprovedAt, self.phone.StockQuantity), (None, 5))
        self.assert_error(BusinessRuleError, "return_field_not_allowed", lambda: self.svc.approve_return_request(
            self.a(self.admin), rid, bypass({"CompensationAmount": Decimal("100000.00"), "Deductions": []})))
        self.assertEqual(self.approve(rid, "100000.00").CompensationAmount, Decimal("100000.00"))

    def test_rejection_rights_and_reasons(self):
        rid = self.create().ReturnRequestId
        with self.assertRaises(ValidationError):
            ServiceRequestRejection(Reason=" ")
        self.assert_error(BusinessRuleError, "rejection_reason_required", lambda: self.svc.reject_return_request(
            self.a(self.staff), rid, bypass({"Reason": " "})))
        self.assertEqual(self.reject(rid).Status, "Rejected")  # Staff từ chối khi còn chờ
        rid = self.received()
        self.assert_error(PermissionDeniedError, "permission_denied", lambda: self.reject(rid))  # sau nhận hàng: Admin
        self.assertEqual(self.reject(rid, by=self.admin).Status, "Rejected")
        self.assert_error(BusinessRuleError, "invalid_return_transition", lambda: self.reject(rid, by=self.admin))
        approved = self.approved_for_new_serial()
        self.assert_error(BusinessRuleError, "return_already_approved", lambda: self.reject(approved, by=self.admin))

    def approved_for_new_serial(self):
        order = self.delivered_order(self.customer, ((self.phone, 1),), total="100000.00")
        self.f.payment(order, status="Success", gateway_code=self.gateway_code, amount="100000.00")
        serial = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber="IMEI-009",
                                           OrderItemId=order.items[0].OrderItemId, Status="Sold"))
        rid = self.create(item=order.items[0], serial=serial).ReturnRequestId
        self.accept(rid)
        self.receiving(rid)
        self.receive(rid, serial_number="IMEI-009")
        self.inspect(rid)
        self.approve(rid, "100000.00")
        return rid

    def test_no_double_restock_or_double_refund(self):
        rid = self.approved()
        self.assert_error(BusinessRuleError, "return_already_approved", lambda: self.approve(rid, "100000.00"))
        self.assertEqual(self.phone.StockQuantity, 6)
        self.refund(rid)
        self.assert_error(ConflictError, "return_refund_exists", lambda: self.refund(rid))  # Refund đang Pending
        self.settle(rid)
        self.assert_error(BusinessRuleError, "invalid_return_transition", lambda: self.refund(rid))
        self.assertEqual(len(self.refunds()), 1)

    def test_serial_state_is_rechecked_at_each_physical_step(self):
        """Serial bị đổi ngoài luồng: báo lỗi rõ ràng, không nhận hàng/nhập tồn theo dữ liệu sai."""
        rid = self.create().ReturnRequestId
        self.accept(rid)
        self.receiving(rid)
        self.serial.Status = "Warranty"
        self.assert_error(BusinessRuleError, "serial_state_inconsistent", lambda: self.receive(rid))
        self.serial.Status = "Sold"
        self.receive(rid)
        self.inspect(rid)
        self.serial.Status = "Sold"  # không còn ở trạng thái đã về cửa hàng
        self.assert_error(BusinessRuleError, "serial_state_inconsistent", lambda: self.approve(rid, "100000.00"))
        self.assertEqual((self.phone.StockQuantity, self.request(rid).CompensationApprovedAt), (5, None))

    def test_steps_out_of_order_are_rejected(self):
        rid = self.create().ReturnRequestId
        for code, call in (("invalid_return_transition", lambda: self.receiving(rid)),
                           ("invalid_return_transition", lambda: self.receive(rid)),
                           ("invalid_return_transition", lambda: self.inspect(rid))):
            with self.subTest(code=code):
                self.assert_error(BusinessRuleError, code, call)
        self.accept(rid)
        self.assert_error(BusinessRuleError, "invalid_return_transition", lambda: self.accept(rid))
        self.assert_error(BusinessRuleError, "invalid_return_transition", lambda: self.receive(rid))
        self.receiving(rid)
        self.assert_error(BusinessRuleError, "return_serial_mismatch", lambda: self.receive(rid, serial_number="IMEI-999"))
        self.assert_error(BusinessRuleError, "return_serial_required", lambda: self.receive(rid, serial_number=None))
        self.assertEqual((self.request(rid).Status, self.request(rid).ReceivedAt, self.serial.Status),
                         ("Receiving", None, "Sold"))
        self.receive(rid)
        self.assert_error(BusinessRuleError, "return_inspection_quantity_mismatch", lambda: self.inspect(rid, 1, 1, "x"))
        self.inspect(rid)
        self.assert_error(BusinessRuleError, "return_already_inspected", lambda: self.inspect(rid))
        cable = self.create(item=self.cable_item, quantity=1).ReturnRequestId
        self.accept(cable)
        self.receiving(cable)
        self.assert_error(BusinessRuleError, "serial_not_applicable", lambda: self.receive(cable, serial_number="ABC"))
        self.assertEqual(self.receive(cable, serial_number=None).Status, "Processing")

    def test_customer_cannot_act_as_staff_or_admin(self):
        rid = self.create().ReturnRequestId
        customer = self.a(self.customer)
        calls = [
            lambda a: self.svc.accept_return_request(a, rid),
            lambda a: self.svc.reject_return_request(a, rid, ServiceRequestRejection(Reason="x")),
            lambda a: self.svc.start_return_receiving(a, rid),
            lambda a: self.svc.receive_return_goods(a, rid, ReturnGoodsReceive(SerialNumber="IMEI-001")),
            lambda a: self.svc.inspect_return_goods(a, rid, ReturnInspection(RestockedQuantity=1, DamagedQuantity=0)),
            lambda a: self.svc.approve_return_request(a, rid, ReturnApproval(CompensationAmount=Decimal("1"))),
            lambda a: self.svc.refund_return_request(a, rid),
            lambda a: self.svc.confirm_return_refund(a, rid),
            lambda a: self.svc.list_return_requests(a),
            lambda a: self.svc.get_return_request(a, rid),
        ]
        for index, call in enumerate(calls):
            with self.subTest(call=index):
                self.assert_error(PermissionDeniedError, "permission_denied", lambda c=call: c(customer))
        with self.assertRaises(TypeError):
            self.svc.approve_return_request(SimpleNamespace(user_id=self.customer.UserId, role="Admin"), rid,
                                            ReturnApproval(CompensationAmount=Decimal("1")))
        self.assertEqual((self.request(rid).Status, len(self.histories(rid))), ("Pending", 1))

    def test_customer_cancels_only_pending_and_sees_only_own(self):
        rid = self.create().ReturnRequestId
        self.assert_error(NotFoundError, "return_request_not_found",
                          lambda: self.svc.cancel_return_request(self.a(self.other), rid))
        self.assert_error(NotFoundError, "return_request_not_found",
                          lambda: self.svc.get_my_return_request(self.a(self.other), rid))
        self.assertEqual(self.svc.list_my_return_requests(self.a(self.other)).Items, [])
        self.assertEqual([r.ReturnRequestId for r in self.svc.list_my_return_requests(self.a(self.customer)).Items],
                         [rid])
        self.accept(rid)
        self.assert_error(BusinessRuleError, "return_not_cancellable",
                          lambda: self.svc.cancel_return_request(self.a(self.customer), rid))
        mine = self.svc.get_my_return_request(self.a(self.customer), rid)
        self.assertFalse(hasattr(mine, "CompensationBasis"))
        self.assertEqual(self.svc.list_return_requests(self.a(self.staff), status="Approved").Total, 1)


class CompensationTest(ReturnTestBase):
    def test_return_value_uses_historical_line_total_not_catalog_price(self):
        self.cable_item.DiscountAmount = Decimal("10000.00")
        self.cable_item.LineTotal = Decimal("80000.00")  # 3 × 30.000 − giảm giá phân bổ 10.000
        self.cable.Price = Decimal("50000.00")  # giá catalog hiện tại không được dùng
        self.f.payment(self.order, status="Success", gateway_code=None, amount="100000.00")
        amounts = []
        for _ in range(3):
            rid = self.received(item=self.cable_item, serial=None, quantity=1)
            amount = self.inspect(rid, 1, 0).CompensationAmount
            self.approve(rid, str(amount))
            amounts.append(amount)
            self.refund(rid)
        self.assertEqual(amounts, [Decimal("26666.67"), Decimal("26666.66"), Decimal("26666.67")])
        self.assertEqual(sum(amounts), Decimal("80000.00"))  # tổng các lần trả đúng bằng giá trị lịch sử của dòng
        self.assertEqual(self.cable.StockQuantity, 13)
        self.assert_error(BusinessRuleError, "return_quantity_exceeded",
                          lambda: self.create(item=self.cable_item, quantity=1))

    def test_partial_returns_inspected_together_are_allocated_when_approved(self):
        self.cable_item.LineTotal = Decimal("80000.00")
        first = self.received(item=self.cable_item, serial=None, quantity=1)
        second = self.received(item=self.cable_item, serial=None, quantity=1)
        self.assertEqual(self.inspect(first, 1, 0).CompensationAmount, Decimal("26666.67"))
        self.assertEqual(self.inspect(second, 1, 0).CompensationAmount, Decimal("26666.67"))  # chưa có yêu cầu nào duyệt
        self.approve(first, "26666.67")
        self.assert_error(BusinessRuleError, "compensation_amount_mismatch", lambda: self.approve(second, "26666.67"))
        approved = self.approve(second, "26666.66")  # tính lại theo phần đã duyệt: tổng không vượt giá trị dòng
        self.assertEqual(approved.CompensationBasis["PreviouslyApprovedQuantity"], 1)
        self.assertEqual(self.request(first).CompensationAmount + approved.CompensationAmount, Decimal("53333.33"))

    def test_shipping_fee_is_not_refunded(self):
        self.order.ShippingFee = Decimal("30000.00")
        rid = self.received()
        inspected = self.inspect(rid)
        self.assertEqual(inspected.CompensationAmount, Decimal("100000.00"))
        self.assertFalse(inspected.CompensationBasis["ShippingFeeRefunded"])

    def test_exchange_difference_uses_historical_prices(self):
        self.phone.Price = Decimal("150000.00")  # giá catalog tăng sau khi mua
        rid = self.received(request_type="Exchange")
        inspected = self.inspect(rid)
        basis = inspected.CompensationBasis
        self.assertEqual(inspected.CompensationAmount, Decimal("0.00"))
        self.assertEqual((basis["OldValue"], basis["NewValue"], basis["Difference"]), ("100000.00", "100000.00", "0.00"))
        self.assertIn("Giá sản phẩm mới − Giá sản phẩm cũ", basis["Formula"])
        self.assert_error(BusinessRuleError, "exchange_fulfillment_policy_missing", lambda: self.approve(rid, "0.00"))
        self.assert_error(BusinessRuleError, "refund_requires_return_request", lambda: self.refund(rid))
        self.assertEqual((self.phone.StockQuantity, self.serial.Status, self.refunds()), (5, "Returned", []))

    def test_refund_requires_a_paid_delivered_order(self):
        rid = self.approved()
        self.order.PaymentStatus = "Refunded"
        self.assert_error(BusinessRuleError, "refund_not_allowed", lambda: self.refund(rid))
        self.assertEqual((self.refunds(), self.request(rid).Status), ([], "Processing"))

    def test_fully_returned_line_cannot_get_warranty(self):
        for _ in range(3):
            rid = self.received(item=self.cable_item, serial=None, quantity=1)
            self.approve(rid, str(self.inspect(rid, 1, 0).CompensationAmount))
            self.refund_and_settle(rid)
        warranty = warranty_service(self.db, self.session, clock=self.clock)
        self.assert_error(BusinessRuleError, "item_fully_returned", lambda: warranty.create_warranty_request(
            self.a(self.customer), WarrantyRequestCreate(OrderItemId=self.cable_item.OrderItemId, IssueDescription="x")))

    def test_refund_never_exceeds_what_was_paid(self):
        self.payment.Amount = Decimal("60000.00")  # chỉ thu được một phần
        rid = self.approved()
        self.assert_error(BusinessRuleError, "refund_exceeds_paid", lambda: self.refund(rid))
        self.assertEqual((self.refunds(), self.request(rid).RefundPaymentTransactionId, self.request(rid).Status),
                         ([], None, "Processing"))


class GatewayRefundTest(ReturnTestBase):
    payment_code = "QR"
    gateway_code = "GW-ORDER-1"

    def make_gateway(self):
        return FakeGateway(self.session)

    def test_gateway_refund_is_called_outside_the_transaction_and_completes(self):
        rid = self.approved()
        done = self.refund(rid)
        [call] = self.gateway.refund_calls
        self.assertEqual((call["code"], call["amount"], call["depth"]), ("GW-ORDER-1", Decimal("100000.00"), 0))
        [refund] = self.refunds()
        self.assertEqual((refund.Status, refund.RefundOfPaymentTransactionId), ("Success", self.payment.PaymentTransactionId))
        self.assertEqual((done.Status, done.RefundPaymentTransactionId), ("Completed", refund.PaymentTransactionId))

    def test_gateway_error_keeps_refund_pending_and_request_open(self):
        rid = self.approved()
        self.gateway.refund_error = RuntimeError("timeout")
        self.assert_error(PaymentGatewayError, "refund_pending_reconciliation", lambda: self.refund(rid))
        [refund] = self.refunds()
        self.assertEqual((refund.Status, self.request(rid).Status, self.request(rid).RefundPaymentTransactionId),
                         ("Pending", "Processing", refund.PaymentTransactionId))
        self.assert_error(BusinessRuleError, "return_refund_pending",
                          lambda: self.svc.confirm_return_refund(self.a(self.staff), rid))
        self.assert_error(ConflictError, "return_refund_exists", lambda: self.refund(rid))  # Pending vẫn giữ tiền
        self.assertEqual(len(self.gateway.refund_calls), 1)

    def test_failed_refund_can_be_retried_once_more(self):
        rid = self.approved()
        self.gateway.refund_result = GatewayRefundResult(success=False, response_data={"r": "declined"})
        self.assertEqual(self.refund(rid).Status, "Processing")
        self.assertEqual([t.Status for t in self.refunds()], ["Failed"])
        self.gateway.refund_result = GatewayRefundResult(success=True, response_data={}, gateway_transaction_code="RF-2")
        done = self.refund(rid)
        self.assertEqual(sorted(t.Status for t in self.refunds()), ["Failed", "Success"])
        success = next(t for t in self.refunds() if t.Status == "Success")
        self.assertEqual((done.Status, done.RefundPaymentTransactionId), ("Completed", success.PaymentTransactionId))
        created = [h for h in self.histories(rid) if (h.InternalNote or "").startswith("Giao dịch Refund")]
        self.assertEqual(len(created), 2)  # cả hai lần tạo giao dịch đều có lịch sử
        self.assertTrue(any("Failed" in (h.InternalNote or "") and h.IsInternal for h in self.histories(rid)))


class ManualRefundTest(ReturnTestBase):
    payment_code = "QR"
    gateway_code = "SEPAY-1"

    def make_gateway(self):
        return ManualRefundGateway(self.session)

    def test_pending_manual_refund_is_not_success_until_confirmed(self):
        rid = self.approved()
        self.assertEqual(self.refund(rid).Status, "Processing")
        [refund] = self.refunds()
        self.assertEqual((refund.Status, self.gateway.refund_calls), ("Pending", []))  # không gọi API hoàn tiền
        self.assert_error(BusinessRuleError, "return_refund_pending",
                          lambda: self.svc.confirm_return_refund(self.a(self.staff), rid))
        with self.assertRaises(PermissionDeniedError):  # đợt 5.11: Staff không xác nhận được
            resolve_refund(self.svc.payments, self.a(self.staff), refund.PaymentTransactionId)
        resolve_refund(self.svc.payments, self.a(self.admin), refund.PaymentTransactionId)
        self.assertEqual((refund.ResolutionSource, refund.ResolvedByUserId), ("Manual", self.admin.UserId))
        done = self.svc.confirm_return_refund(self.a(self.staff), rid)
        self.assertEqual((done.Status, self.histories(rid)[-1].NewStatus), ("Completed", "Completed"))


class ReturnPolicyConfigTest(ReturnTestBase):
    """Đợt 5.4.1: thời hạn đổi trả từ cấu hình ứng dụng (RETURN_WINDOW_DAYS), mặc định 7 ngày."""

    def test_default_is_seven_days_and_env_overrides(self):
        self.assertEqual(ReturnPolicy.from_env({}).window_days, 7)
        self.assertEqual(ReturnPolicy.from_env({"RETURN_WINDOW_DAYS": "  "}).window_days, 7)
        self.assertEqual(ReturnPolicy.from_env({"RETURN_WINDOW_DAYS": " 10 "}).window_days, 10)
        for bad in ("0", "-1", "abc", "7.5"):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                ReturnPolicy.from_env({"RETURN_WINDOW_DAYS": bad})

    def test_seven_day_window_first_day_last_day_and_expiry(self):
        svc = self.service(ReturnPolicy.from_env({}))
        cases = [
            (DELIVERED_AT, True),  # ngay lúc giao (ngày thứ nhất)
            (utc(2026, 10, 4, 17, 0), None),  # 00:00 ngày 05/10 giờ VN nhưng TRƯỚC thời điểm giao → dữ liệu sai
            (utc(2026, 10, 11, 16, 59, 59), True),  # 23:59:59 ngày 11/10 giờ VN = ngày thứ 7
            (utc(2026, 10, 11, 17, 0), False),  # 00:00 ngày 12/10 giờ VN = ngày thứ 8
        ]
        for now, allowed in cases:
            with self.subTest(now=now):
                self.clock.now = now
                if allowed is True:
                    request = self.create(svc=svc, item=self.cable_item, quantity=1)
                    svc.cancel_return_request(self.a(self.customer), request.ReturnRequestId)
                elif allowed is False:
                    self.assert_error(BusinessRuleError, "return_window_expired",
                                      lambda: self.create(svc=svc, item=self.cable_item, quantity=1))
                else:
                    self.assert_error(BusinessRuleError, "invalid_delivery_time",
                                      lambda: self.create(svc=svc, item=self.cable_item, quantity=1))

    def test_delivery_late_at_night_vietnam_time_counts_as_next_day(self):
        self.order.DeliveredAt = utc(2026, 10, 5, 17, 30)  # 00:30 ngày 06/10 giờ VN → ngày cuối 12/10
        svc = self.service(ReturnPolicy.from_env({}))
        self.clock.now = utc(2026, 10, 12, 16, 0)  # 23:00 ngày 12/10 giờ VN
        self.assertEqual(self.create(svc=svc).Status, "Pending")

    def test_invalid_or_missing_delivery_data_is_rejected(self):
        self.order.DeliveredAt = datetime(2026, 10, 5, 3, 0)  # thiếu múi giờ
        self.assert_error(BusinessRuleError, "invalid_delivery_time", lambda: self.create())
        self.order.DeliveredAt = utc(2026, 10, 10, 3, 0)  # sau thời điểm hiện tại
        self.assert_error(BusinessRuleError, "invalid_delivery_time", lambda: self.create())
        self.order.DeliveredAt = None
        self.assert_error(BusinessRuleError, "delivery_not_recorded", lambda: self.create())
        self.assertEqual(self.requests(), [])

    def test_service_without_policy_refuses_clearly(self):
        svc = self.service(None)
        error = self.assert_error(BusinessRuleError, "return_policy_not_configured", lambda: self.create(svc=svc))
        self.assertIn("thời hạn", str(error))


class RefundSafetyTest(ReturnTestBase):
    payment_code = "QR"
    gateway_code = "GW-ORDER-1"

    def make_gateway(self):
        return FakeGateway(self.session)

    def test_timeout_is_not_treated_as_failure_and_retry_creates_no_duplicate(self):
        rid = self.approved()
        self.gateway.refund_error = TimeoutError("cổng không phản hồi")
        self.assert_error(PaymentGatewayError, "refund_pending_reconciliation", lambda: self.refund(rid))
        [refund] = self.refunds()
        self.assertEqual((refund.Status, self.request(rid).Status), ("Pending", "Processing"))
        note = self.histories(rid)[-1]
        self.assertEqual((note.IsInternal, note.Note), (True, None))
        self.assertIn("Chưa xác định kết quả", note.InternalNote)
        self.gateway.refund_error = None
        for _ in range(2):  # gọi lặp: không tạo giao dịch mới, không gọi lại cổng
            self.assert_error(ConflictError, "return_refund_exists", lambda: self.refund(rid))
        self.assertEqual((len(self.refunds()), len(self.gateway.refund_calls)), (1, 1))
        self.assert_error(BusinessRuleError, "return_refund_pending",
                          lambda: self.svc.confirm_return_refund(self.a(self.staff), rid))
        # Đối soát: cổng xác nhận thất bại → được tạo lại giao dịch
        resolve_refund(self.svc.payments, self.a(self.admin), refund.PaymentTransactionId, success=False)
        self.assert_error(BusinessRuleError, "return_refund_failed",
                          lambda: self.svc.confirm_return_refund(self.a(self.staff), rid))
        self.assertEqual(self.refund(rid).Status, "Completed")
        self.assertEqual(sorted(t.Status for t in self.refunds()), ["Failed", "Success"])

    def test_pending_failed_and_success_are_distinguished(self):
        rid = self.approved()
        self.gateway.refund_error = TimeoutError()
        with self.assertRaises(PaymentGatewayError):
            self.refund(rid)
        [refund] = self.refunds()
        confirm = lambda: self.svc.confirm_return_refund(self.a(self.staff), rid)  # noqa: E731
        self.assert_error(BusinessRuleError, "return_refund_pending", confirm)
        resolve_refund(self.svc.payments, self.a(self.admin), refund.PaymentTransactionId)
        self.assertEqual(confirm().Status, "Completed")  # chỉ Success mới hoàn tất
        self.assertEqual(self.request(rid).CompletedAt, self.clock.now)
        self.assert_error(BusinessRuleError, "invalid_return_transition", confirm)

    def test_total_refunds_never_exceed_paid_across_requests(self):
        self.payment.Amount = Decimal("150000.00")  # thu thiếu so với tổng giá trị dòng (190.000)
        phone = self.approved()
        cable = self.received(item=self.cable_item, serial=None, quantity=3)
        self.approve(cable, str(self.inspect(cable, 3, 0).CompensationAmount))  # 90.000
        self.gateway.refund_error = TimeoutError()
        with self.assertRaises(PaymentGatewayError):
            self.refund(phone)  # 100.000 đang Pending vẫn giữ tiền
        self.assert_error(BusinessRuleError, "refund_exceeds_paid", lambda: self.refund(cable))  # chỉ còn 50.000
        self.assertEqual(self.request(cable).RefundPaymentTransactionId, None)
        [pending] = self.refunds()
        resolve_refund(self.svc.payments, self.a(self.admin), pending.PaymentTransactionId, success=False)
        self.gateway.refund_error = None
        self.assertEqual(self.refund(cable).Status, "Completed")  # Failed không giữ tiền
        self.assert_error(BusinessRuleError, "refund_exceeds_paid", lambda: self.refund(phone))  # 150k − 90k < 100k
        held = sum(t.Amount for t in self.refunds() if t.Status in ("Pending", "Success"))
        self.assertLessEqual(held, Decimal("150000.00"))

    def test_shipping_fee_and_payment_status_are_unchanged(self):
        self.order.ShippingFee = Decimal("30000.00")
        rid = self.approved()
        self.assertEqual(self.refund(rid).Status, "Completed")
        [refund] = self.refunds()
        self.assertEqual(refund.Amount, Decimal("100000.00"))  # không gồm phí vận chuyển
        self.assertEqual(self.order.PaymentStatus, "Paid")  # không tự đổi vì đã phát sinh hoàn tiền


class ReturnHistoryAndStockTest(ReturnTestBase):
    INTERNAL_TEXT = "NOI-BO: nghi khách đổi linh kiện"

    def test_customer_never_sees_internal_notes(self):
        rid = self.create().ReturnRequestId
        staff = self.a(self.staff)
        self.svc.accept_return_request(staff, rid, ServiceRequestNote(Note="Đã tiếp nhận", InternalNote=self.INTERNAL_TEXT))
        self.svc.start_return_receiving(staff, rid, ServiceRequestNote(InternalNote=self.INTERNAL_TEXT))
        self.svc.receive_return_goods(staff, rid, ReturnGoodsReceive(SerialNumber="IMEI-001", InternalNote=self.INTERNAL_TEXT))
        self.svc.inspect_return_goods(staff, rid, ReturnInspection(RestockedQuantity=1, DamagedQuantity=0,
                                                                   InternalNote=self.INTERNAL_TEXT))
        self.svc.approve_return_request(self.a(self.admin), rid, ReturnApproval(
            CompensationAmount=Decimal("100000.00"), InternalNote=self.INTERNAL_TEXT))
        mine = self.svc.get_my_return_request(self.a(self.customer), rid)
        for view in (mine, self.svc.list_my_return_requests(self.a(self.customer))):
            with self.subTest(view=type(view).__name__):
                self.assertNotIn("NOI-BO", view.model_dump_json())
                self.assertNotIn("InternalNote", view.model_dump_json())
                self.assertNotIn("Nhập lại tồn", view.model_dump_json())  # thông tin kho là nội bộ
        self.assertTrue(all(h.Note for h in mine.Histories))
        admin_view = self.svc.get_return_request(staff, rid)
        self.assertEqual(admin_view.model_dump_json().count("NOI-BO"), 5)
        self.assert_error(BusinessRuleError, "return_field_not_allowed", lambda: self.svc.cancel_return_request(
            self.a(self.customer), self.create(item=self.cable_item, quantity=1).ReturnRequestId,
            ServiceRequestNote(InternalNote="x")))

    def test_restocked_serial_keeps_warranty_history_and_return_link(self):
        rid = self.approved()
        self.assertEqual((self.serial.Status, self.serial.OrderItemId), ("Available", None))
        self.assertEqual((self.serial.WarrantyStartDate, self.serial.WarrantyEndDate),
                         (date(2026, 10, 5), date(2027, 10, 4)))  # không xóa lịch sử bảo hành
        request = self.request(rid)
        self.assertEqual((request.ProductSerialId, request.OrderItemId),
                         (self.serial.ProductSerialId, self.item.OrderItemId))  # liên kết đơn gốc còn trên yêu cầu
        stock_note = next(h.InternalNote for h in self.histories(rid) if "Nhập lại tồn" in (h.InternalNote or ""))
        self.assertIn("IMEI-001", stock_note)
        self.assertIn(str(self.item.OrderItemId), stock_note)

    def test_exchange_cannot_be_completed_or_change_stock(self):
        rid = self.received(request_type="Exchange")
        self.inspect(rid)
        for code, call in (("exchange_fulfillment_policy_missing", lambda: self.approve(rid, "0.00")),
                           ("refund_requires_return_request", lambda: self.refund(rid)),
                           ("return_refund_missing", lambda: self.svc.confirm_return_refund(self.a(self.staff), rid))):
            with self.subTest(code=code):
                self.assert_error(BusinessRuleError, code, call)
        self.assertEqual((self.request(rid).Status, self.request(rid).CompensationApprovedAt, self.phone.StockQuantity,
                          self.serial.Status), ("Processing", None, 5, "Returned"))


class RollbackAndLockingTest(ReturnTestBase):
    def fail(self, *args, **kwargs):
        raise RuntimeError("lỗi giữa chừng")

    def test_failure_during_approval_rolls_back_restock(self):
        rid = self.received()
        self.inspect(rid)
        before = (len(self.db.rows(ServiceRequestHistory)), len(self.db.rows(Notification)))
        self.svc.histories.create = self.fail  # sau khi đã nhập tồn và đổi serial
        with self.assertRaises(RuntimeError):
            self.approve(rid, "100000.00")
        self.assertEqual((self.phone.StockQuantity, self.serial.Status, self.serial.OrderItemId),
                         (5, "Returned", self.item.OrderItemId))
        self.assertIsNone(self.request(rid).CompensationApprovedAt)
        self.assertEqual((len(self.db.rows(ServiceRequestHistory)), len(self.db.rows(Notification))), before)

    def test_failure_after_refund_created_rolls_back_refund_and_link(self):
        rid = self.approved()
        self.svc.histories.create = self.fail  # ghi lịch sử sau khi đã tạo Refund (bước cuối của transaction)
        with self.assertRaises(RuntimeError):
            self.refund(rid)
        request = self.request(rid)
        self.assertEqual((self.refunds(), request.RefundPaymentTransactionId, request.Status, request.CompletedAt),
                         ([], None, "Processing", None))

    def test_failure_while_creating_leaves_nothing(self):
        self.svc.notifications.notify = self.fail
        with self.assertRaises(RuntimeError):
            self.create(attachments=(("https://cdn.vietech.vn/a.jpg", "Image"),))
        self.assertEqual((self.requests(), self.db.rows(ServiceRequestAttachment), self.db.rows(ServiceRequestHistory)),
                         ([], [], []))

    def test_lock_order(self):
        rid = self.received()
        self.inspect(rid)
        self.db.locks.clear()
        self.approve(rid, "100000.00")
        self.assertEqual([n for n, _ in self.db.locks], ["Order", "ReturnRequest", "ProductVariant", "ProductSerial"])
        self.db.locks.clear()
        self.refund(rid)
        self.assertEqual([n for n, _ in self.db.locks], ["Order", "ReturnRequest", "PaymentTransaction"])

    def test_refund_requires_its_own_transaction(self):
        rid = self.approved()
        with self.svc.transaction():
            self.assert_error(BusinessRuleError, "refund_requires_own_transaction", lambda: self.refund(rid))
        self.assertEqual(self.refunds(), [])
        self.assertEqual(self.session.info.get(_DEPTH_KEY), 0)


class ReturnPaymentGuardTest(ReturnTestBase):
    payment_code = "QR"
    gateway_code = "GW-ORDER-1"

    def make_gateway(self):
        return FakeGateway(self.session)

    def test_create_return_refund_is_internal_only(self):
        """Router không gọi thẳng được bước ghi Refund của trả hàng (bỏ qua kiểm tra nhận hàng/duyệt)."""
        self.assert_error(BusinessRuleError, "internal_operation",
                          lambda: self.svc.payments.create_return_refund(self.order, Decimal("100000.00"),
                                                                         created_by=self.staff.UserId))
        self.assertEqual(self.refunds(), [])

    def test_gateway_is_never_called_inside_a_transaction(self):
        payments = self.svc.payments
        with self.assertRaises(BusinessRuleError) as ctx:
            with payments.transaction():
                _, dispatch = payments.create_return_refund(self.order, Decimal("100000.00"),
                                                            created_by=self.staff.UserId)
                dispatch()
        self.assertEqual(ctx.exception.code, "refund_requires_own_transaction")
        self.assertEqual((self.gateway.refund_calls, self.refunds()), ([], []))


class ReturnSchemaAndModelTest(unittest.TestCase):
    def test_generic_update_schema_is_gone(self):
        self.assertFalse(hasattr(app.schemas, "ReturnRequestUpdate"))
        self.assertNotIn("ReturnRequestUpdate", app.schemas.__all__)

    def test_model_declares_constraints_and_partial_unique_index(self):
        table = ReturnRequest.__table__
        checks = {c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"}
        for name in ("CK_ReturnRequests_RequestType_Valid", "CK_ReturnRequests_Quantity_Positive",
                     "CK_ReturnRequests_Serial_SingleUnit", "CK_ReturnRequests_Inspection_Consistent",
                     "CK_ReturnRequests_Inspection_RequiresReceipt", "CK_ReturnRequests_Approval_RequiresAssessment",
                     "CK_ReturnRequests_Refund_RequiresApprovedReturn", "CK_ReturnRequests_Completed_RequiresApproval"):
            self.assertIn(name, checks)
        index = {i.name: i for i in table.indexes}["UX_ReturnRequests_Serial_Open"]
        self.assertTrue(index.unique)
        self.assertIn("'Pending', 'Approved', 'Receiving', 'Processing'", str(index.dialect_options["postgresql"]["where"]))
        self.assertTrue(table.c.RefundPaymentTransactionId.unique)


if __name__ == "__main__":
    unittest.main()
