"""Đợt 5.9: chuyển đơn sang Completed khi có yêu cầu đổi/trả, và bộ đếm bán hàng sau trả hàng/hoàn tiền.

B — Không chuyển Delivered → Completed khi đơn còn yêu cầu đổi/trả đang xử lý (RETURN_OPEN_STATUSES: Pending, Approved,
Receiving, Processing — gồm cả yêu cầu có Refund đang Pending). Yêu cầu đã Completed/Rejected/Cancelled không chặn.
A — Cố định định nghĩa HIỆN TẠI (chưa có quyết định khác): Users.TotalSpent/TotalOrders và Products.SoldQuantity là số
liệu lịch sử, cộng đúng một lần khi đơn chuyển Completed theo giá trị đơn; trả hàng/hoàn tiền (Success, Pending hay
Failed) không làm thay đổi; Coupons.UsedCount chỉ trả lại khi hủy đơn. Đổi định nghĩa thì phải sửa các test này.
Fake trong bộ nhớ: khóa dòng/đồng thời chỉ được giả lập; không chứng minh hành vi trên PostgreSQL thật.
"""

from decimal import Decimal

from app.models import Notification, OrderStatusHistory
from app.schemas import OrderStatusUpdate, ServiceRequestNote
from app.services import BusinessRuleError, PaymentGatewayError

from tests.fakes import order_service, resolve_refund
from tests.test_payment import FakeGateway
from tests.test_return_service import ReturnTestBase

ORDER_TOTAL = Decimal("190000.00")  # phone 100.000 + cable 3 × 30.000
COMPLETED_COUNTERS = (ORDER_TOTAL, 1, 1, 3)
ZERO_COUNTERS = (Decimal("0"), 0, 0, 0)


class CompletionTestBase(ReturnTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.orders_svc = order_service(self.db, self.session, clock=self.clock)
        self.coupon = self.f.coupon(self.admin, used=1)
        self.order.CouponId = self.coupon.CouponId

    def complete(self, order=None):
        return self.orders_svc.update_order_status(self.a(self.staff), (order or self.order).OrderId,
                                                   OrderStatusUpdate(OrderStatus="Completed"))

    def counters(self):
        return (self.customer.TotalSpent, self.customer.TotalOrders,
                self.phone.product.SoldQuantity, self.cable.product.SoldQuantity)

    def completed_histories(self):
        return [h for h in self.db.rows(OrderStatusHistory)
                if h.OrderId == self.order.OrderId and h.NewStatus == "Completed"]

    def assert_blocked(self, *codes):
        notifications = len(self.db.rows(Notification))
        error = self.assert_error(BusinessRuleError, "order_has_open_returns", self.complete)
        for code in codes:
            self.assertIn(code, error.message)
        self.assertEqual((self.order.OrderStatus, self.order.CompletedAt), ("Delivered", None))
        self.assertEqual((self.completed_histories(), self.counters()), ([], ZERO_COUNTERS))
        self.assertEqual(len(self.db.rows(Notification)), notifications)

    def assert_completed_once(self):
        self.assertEqual(self.complete().OrderStatus, "Completed")
        self.assertEqual(self.order.CompletedAt, self.clock.now)
        self.assertEqual((len(self.completed_histories()), self.counters()), (1, COMPLETED_COUNTERS))

    def full_cable_return(self):
        rid = self.received(item=self.cable_item, serial=None, quantity=3)
        self.approve(rid, str(self.inspect(rid, 3, 0).CompensationAmount))
        self.assertEqual(self.refund_and_settle(rid).Status, "Completed")


class OpenReturnBlocksCompletionTest(CompletionTestBase):
    def test_every_open_return_status_blocks_completion(self):
        rid = self.create().ReturnRequestId
        code = self.request(rid).RequestCode
        self.assert_blocked(code)  # Pending
        self.accept(rid)
        self.assert_blocked(code)  # Approved
        self.receiving(rid)
        self.assert_blocked(code)  # Receiving
        self.receive(rid)
        self.assert_blocked(code)  # Processing (hàng đã về)
        self.inspect(rid)
        self.approve(rid, "100000.00")
        self.assert_blocked(code)  # Processing, đã duyệt nhưng chưa hoàn tiền
        self.assertEqual(self.refund(rid).Status, "Processing")
        self.assert_blocked(code)  # Refund COD Pending (đợt 5.11): chưa phải đã hoàn
        self.assertEqual(self.settle(rid).Status, "Completed")
        self.assert_completed_once()

    def test_open_exchange_request_also_blocks(self):
        rid = self.create(request_type="Exchange", item=self.cable_item, quantity=1).ReturnRequestId
        self.assert_blocked(self.request(rid).RequestCode)

    def test_all_open_requests_are_listed(self):
        phone = self.create().RequestCode
        cable = self.create(item=self.cable_item, quantity=2).RequestCode
        self.assert_blocked(phone, cable)

    def test_rejected_and_cancelled_requests_do_not_block(self):
        rejected = self.create().ReturnRequestId
        self.reject(rejected)
        cancelled = self.create(item=self.cable_item, quantity=1).ReturnRequestId
        self.svc.cancel_return_request(self.a(self.customer), cancelled, ServiceRequestNote(Note="Đổi ý"))
        self.assertEqual((self.request(rejected).Status, self.request(cancelled).Status), ("Rejected", "Cancelled"))
        self.assert_completed_once()

    def test_open_return_of_another_order_does_not_block(self):
        other = self.delivered_order(self.customer, ((self.cable, 1),), total="30000.00")
        self.create(item=self.item_of(other, self.cable), quantity=1)
        self.assert_completed_once()

    def test_blocked_completion_can_be_retried_after_the_request_is_closed_and_not_repeated(self):
        rid = self.create().ReturnRequestId
        self.assert_blocked()
        self.reject(rid)
        self.assert_completed_once()
        self.assert_error(BusinessRuleError, "invalid_status_transition", self.complete)  # gọi lặp
        self.assertEqual((len(self.completed_histories()), self.counters()), (1, COMPLETED_COUNTERS))

    def test_admin_is_blocked_too_and_order_is_locked(self):
        self.create()
        with self.assertRaises(BusinessRuleError) as ctx:
            self.orders_svc.update_order_status(self.a(self.admin), self.order.OrderId,
                                               OrderStatusUpdate(OrderStatus="Completed"))
        self.assertEqual(ctx.exception.code, "order_has_open_returns")
        self.assertIn(("Order", self.order.OrderId), self.db.locks)

    def test_returns_remain_possible_after_completion_within_the_window(self):
        self.assert_completed_once()
        self.assertEqual(self.create().Status, "Pending")  # hành vi hiện có: đơn Completed vẫn đổi/trả được


class PendingRefundBlocksCompletionTest(CompletionTestBase):
    payment_code = "QR"
    gateway_code = "GW-ORDER-1"

    def make_gateway(self):
        return FakeGateway(self.session)

    def test_pending_refund_keeps_return_open_until_confirmed(self):
        rid = self.approved()
        self.gateway.refund_error = TimeoutError("cổng không phản hồi")
        self.assert_error(PaymentGatewayError, "refund_pending_reconciliation", lambda: self.refund(rid))
        [refund] = self.refunds()
        self.assertEqual((refund.Status, self.request(rid).Status), ("Pending", "Processing"))
        self.assert_blocked()  # Refund Pending chưa phải đã hoàn
        resolve_refund(self.svc.payments, self.a(self.admin), refund.PaymentTransactionId, evidence="RF-BANK-1")
        self.assert_blocked()  # chưa xác nhận hoàn tất yêu cầu
        self.svc.confirm_return_refund(self.a(self.staff), rid)
        self.assert_completed_once()

    def test_failed_refund_keeps_return_open(self):
        rid = self.approved()
        self.gateway.refund_result = self.gateway.refund_result.__class__(success=False, response_data={"r": "x"})
        self.assertEqual(self.refund(rid).Status, "Processing")
        self.assertEqual([t.Status for t in self.refunds()], ["Failed"])
        self.assert_blocked()


class SalesCountersAfterReturnsTest(CompletionTestBase):
    """Định nghĩa hiện tại: số liệu lịch sử theo giá trị đơn tại thời điểm Completed (không phải số thuần)."""

    def test_full_return_before_completion_still_counts_the_order_value(self):
        self.assertEqual(self.refund_and_settle(self.approved()).Status, "Completed")
        self.full_cable_return()
        self.assert_completed_once()
        self.assertEqual(self.coupon.UsedCount, 1)

    def test_full_return_after_completion_does_not_change_counters(self):
        self.assert_completed_once()
        self.assertEqual(self.refund_and_settle(self.approved()).Status, "Completed")
        self.full_cable_return()
        self.assertEqual((self.counters(), self.coupon.UsedCount), (COMPLETED_COUNTERS, 1))

    def test_partial_return_does_not_change_counters(self):
        self.assert_completed_once()
        rid = self.received(item=self.cable_item, serial=None, quantity=1)
        self.approve(rid, str(self.inspect(rid, 1, 0).CompensationAmount))
        self.assertEqual(self.refund_and_settle(rid).Status, "Completed")
        self.assertEqual((self.counters(), self.coupon.UsedCount), (COMPLETED_COUNTERS, 1))

    def test_counters_are_not_touched_before_completion(self):
        self.assertEqual(self.refund_and_settle(self.approved()).Status, "Completed")
        self.assertEqual(self.counters(), ZERO_COUNTERS)

    def test_cancelled_order_never_counts_and_releases_coupon_once(self):
        order = self.f.order(self.customer, self.method, status="Processing", payment_status="Paid",
                             total="30000.00", lines=((self.cable, 1),), coupon=self.coupon)
        cancel = OrderStatusUpdate(OrderStatus="Cancelled", CancelReason="Khách đổi ý")
        self.orders_svc.update_order_status(self.a(self.staff), order.OrderId, cancel)
        self.assert_error(BusinessRuleError, "order_not_cancellable",
                          lambda: self.orders_svc.update_order_status(self.a(self.staff), order.OrderId, cancel))
        self.assertEqual((self.counters(), self.coupon.UsedCount), (ZERO_COUNTERS, 0))


class SalesCountersWithGatewayRefundsTest(CompletionTestBase):
    payment_code = "QR"
    gateway_code = "GW-ORDER-1"

    def make_gateway(self):
        return FakeGateway(self.session)

    def test_pending_failed_and_successful_refunds_do_not_change_counters(self):
        self.assert_completed_once()
        rid = self.approved()
        self.gateway.refund_result = self.gateway.refund_result.__class__(success=False, response_data={"r": "x"})
        self.refund(rid)  # Failed
        self.gateway.refund_error = TimeoutError("cổng không phản hồi")
        self.assert_error(PaymentGatewayError, "refund_pending_reconciliation", lambda: self.refund(rid))  # Pending
        self.assertEqual(sorted(t.Status for t in self.refunds()), ["Failed", "Pending"])
        self.assertEqual((self.counters(), self.order.PaymentStatus), (COMPLETED_COUNTERS, "Paid"))
        pending = next(t for t in self.refunds() if t.Status == "Pending")
        resolve_refund(self.svc.payments, self.a(self.admin), pending.PaymentTransactionId, evidence="RF-BANK-1")
        self.assertEqual(self.svc.confirm_return_refund(self.a(self.staff), rid).Status, "Completed")
        self.assertEqual((self.counters(), self.order.PaymentStatus, self.coupon.UsedCount),
                         (COMPLETED_COUNTERS, "Paid", 1))
