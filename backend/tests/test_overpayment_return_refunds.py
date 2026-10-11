"""Đợt 5.8 (P1.1): hoàn khoản thu trùng/thu vượt và hoàn trả hàng trên cùng một đơn đã giao.

Khoản hoàn trả hàng (liên kết qua ReturnRequests.RefundPaymentTransactionId) không thuộc phần thu vượt: hoàn trả hàng
trước không được làm mất khả năng hoàn phần thu trùng, và tổng tiền hoàn (Success + Pending) không vượt số đã thu.
Fake trong bộ nhớ: khóa dòng/đồng thời chỉ được giả lập; không chứng minh hành vi trên PostgreSQL thật.
"""

from decimal import Decimal

from app.models import PaymentTransaction
from app.services import BusinessRuleError, GatewayRefundResult, PaymentGatewayError

from tests.fakes import resolve_refund
from tests.test_payment import FakeGateway
from tests.test_return_service import ReturnTestBase
from tests.test_refund_sources import ManualRefundGateway

ORDER_TOTAL = Decimal("190000.00")  # phone 100.000 + cable 3 × 30.000


class OverpaymentRefundBase(ReturnTestBase):
    def setUp(self) -> None:
        super().setUp()
        # Khách thanh toán trùng: đã thu 2 × TotalAmount, phần thu vượt = 190.000.
        self.duplicate = self.f.payment(self.order, status="Success", amount=str(ORDER_TOTAL),
                                        gateway_code=self.second_gateway_code())

    def second_gateway_code(self):
        return None

    def overpay(self, amount=None, source=None):
        return self.svc.payments.refund_order(
            self.a(self.staff), self.order.OrderId,
            amount=Decimal(amount) if amount is not None else None,
            payment_transaction_id=source.PaymentTransactionId if source is not None else None,
        )

    def return_cable(self):
        rid = self.received(item=self.cable_item, serial=None, quantity=3)
        self.approve(rid, str(self.inspect(rid, 3, 0).CompensationAmount))
        return rid

    def total(self, *statuses):
        return sum((t.Amount for t in self.db.rows(PaymentTransaction)
                    if t.TransactionType == "Refund" and t.Status in statuses), Decimal("0"))

    def paid(self):
        return sum((t.Amount for t in self.db.rows(PaymentTransaction)
                    if t.TransactionType == "Payment" and t.Status == "Success"), Decimal("0"))

    def assert_within_paid(self):
        self.assertLessEqual(self.total("Success", "Pending"), self.paid())


class DirectRefundOrderTest(OverpaymentRefundBase):
    """COD: hoàn trực tiếp. Từ đợt 5.11 giao dịch Refund tạo Pending và chỉ Success sau khi Admin khác người tạo xác nhận;
    các bước dưới đây xác nhận ngay sau khi tạo để giữ nguyên kịch bản hồi quy đợt 5.8."""

    def overpay(self, amount=None, source=None):
        pending = super().overpay(amount, source)
        self.assertEqual((pending.Status, pending.CreatedByUserId), ("Pending", self.staff.UserId))
        return resolve_refund(self.svc.payments, self.a(self.admin), pending.PaymentTransactionId)

    def refund(self, rid, by=None, source=None):
        self.assertEqual(super().refund(rid, by=by, source=source).Status, "Processing")  # Refund Pending
        return self.settle(rid)

    def test_overpayment_first_then_returns(self):
        self.assertEqual(self.overpay().Amount, ORDER_TOTAL)
        self.assertEqual(self.refund(self.approved()).Status, "Completed")  # điện thoại 100.000
        self.assertEqual(self.refund(self.return_cable()).Status, "Completed")  # 3 dây cáp 90.000
        self.assertEqual(self.total("Success"), self.paid())  # hoàn đủ 380.000
        self.assert_error(BusinessRuleError, "nothing_to_refund", lambda: self.overpay())

    def test_return_first_then_overpayment_is_still_refundable(self):
        self.assertEqual(self.refund(self.approved()).Status, "Completed")  # 100.000
        refund = self.overpay()
        self.assertEqual(refund.Amount, ORDER_TOTAL)  # phần thu trùng không bị trừ bởi hoàn trả hàng
        self.assertEqual(self.refund(self.return_cable()).Status, "Completed")
        self.assertEqual(self.total("Success"), self.paid())
        self.assert_error(BusinessRuleError, "nothing_to_refund", lambda: self.overpay())
        self.assert_within_paid()

    def test_overpayment_limit_is_exact_after_returns(self):
        self.refund(self.approved())
        self.assert_error(BusinessRuleError, "refund_exceeds_paid", lambda: self.overpay("190000.01"))
        self.assertEqual(self.overpay("90000.00").Amount, Decimal("90000.00"))
        self.assertEqual(self.overpay().Amount, Decimal("100000.00"))  # phần thu vượt còn lại
        self.assert_error(BusinessRuleError, "nothing_to_refund", lambda: self.overpay("0.01"))
        self.assert_within_paid()

    def test_total_cap_holds_even_if_linked_return_refunds_exceed_order_value(self):
        # Dữ liệu bất thường dựng tay (luồng trả hàng giới hạn theo giá trị dòng nên không tự tạo ra trạng thái này):
        # trần tổng "đã thu − mọi Refund Success/Pending" vẫn chặn, kể cả khi phần thu vượt còn 190.000.
        self.refund(self.approved())
        [return_refund] = [t for t in self.db.rows(PaymentTransaction) if t.TransactionType == "Refund"]
        return_refund.Amount = Decimal("250000.00")
        self.assert_error(BusinessRuleError, "refund_exceeds_paid", lambda: self.overpay("130000.01"))
        self.assertEqual(self.overpay().Amount, Decimal("130000.00"))
        self.assertEqual(self.total("Success"), self.paid())
        self.assert_error(BusinessRuleError, "nothing_to_refund", lambda: self.overpay())

    def test_order_without_overpayment_still_rejects_refund_order(self):
        self.duplicate.Status = "Failed"  # chỉ còn một khoản thu đúng TotalAmount
        self.refund(self.approved())
        self.assert_error(BusinessRuleError, "refund_not_allowed", lambda: self.overpay())


class GatewayRefundOrderTest(OverpaymentRefundBase):
    payment_code = "QR"
    gateway_code = "GW-ORDER-1"

    def make_gateway(self):
        return FakeGateway(self.session)

    def second_gateway_code(self):
        return "GW-ORDER-2"

    def test_pending_return_refund_holds_money_without_blocking_overpayment(self):
        rid = self.approved()
        self.gateway.refund_error = TimeoutError("cổng không phản hồi")
        self.assert_error(PaymentGatewayError, "refund_pending_reconciliation", lambda: self.refund(rid))
        self.gateway.refund_error = None
        self.assertEqual(self.overpay().Amount, ORDER_TOTAL)  # Refund trả hàng Pending không thuộc phần thu vượt
        self.assertEqual((self.total("Pending"), self.total("Success")), (Decimal("100000.00"), ORDER_TOTAL))
        self.assert_error(BusinessRuleError, "nothing_to_refund", lambda: self.overpay())
        self.assertEqual(len(self.gateway.refund_calls), 2)  # không gọi cổng thêm lần nào
        self.assert_within_paid()

    def test_pending_overpayment_refund_blocks_a_second_one_but_not_returns(self):
        self.gateway.refund_error = TimeoutError("cổng không phản hồi")
        self.assert_error(PaymentGatewayError, "refund_pending_reconciliation", lambda: self.overpay())
        self.assert_error(BusinessRuleError, "refund_pending", lambda: self.overpay())  # không tạo giao dịch trùng
        self.gateway.refund_error = None
        self.assertEqual(self.refund(self.approved()).Status, "Completed")
        self.assertEqual(len([t for t in self.db.rows(PaymentTransaction) if t.TransactionType == "Refund"]), 2)
        self.assertEqual(len(self.gateway.refund_calls), 2)
        self.assert_within_paid()

    def test_failed_refunds_do_not_hold_money_and_can_be_retried(self):
        self.gateway.refund_result = GatewayRefundResult(success=False, response_data={"r": "declined"})
        self.assertEqual(self.overpay().Status, "Failed")
        rid = self.approved()
        self.assertEqual(self.refund(rid).Status, "Processing")  # Refund trả hàng Failed
        self.gateway.refund_result = GatewayRefundResult(success=True, response_data={}, gateway_transaction_code="RF")
        self.assertEqual(self.overpay().Amount, ORDER_TOTAL)  # Failed không giữ tiền: thử lại được
        self.assertEqual(self.refund(rid).Status, "Completed")
        self.assertEqual((self.total("Success"), self.total("Failed")), (Decimal("290000.00"), Decimal("290000.00")))
        self.assert_within_paid()

    def test_multiple_payments_keep_per_source_and_total_limits(self):
        self.duplicate.Amount = Decimal("120000.00")
        third = self.f.payment(self.order, status="Success", amount="70000.00", gateway_code="GW-ORDER-3")
        self.assertEqual(self.refund(self.approved()).Status, "Completed")  # 100.000 từ khoản đầu (còn 90.000)
        self.assert_error(BusinessRuleError, "refund_requires_source_payment", lambda: self.overpay())
        self.assert_error(BusinessRuleError, "refund_exceeds_source_payment",
                          lambda: self.overpay(source=self.duplicate))  # 190.000 > số dư 120.000 của khoản nguồn
        self.assertEqual(self.overpay("120000.00", source=self.duplicate).Amount, Decimal("120000.00"))
        self.assertEqual(self.overpay("70000.00", source=third).Amount, Decimal("70000.00"))
        self.assert_error(BusinessRuleError, "nothing_to_refund", lambda: self.overpay())
        self.assertEqual(self.refund(self.return_cable()).Status, "Completed")  # 90.000 còn lại của khoản đầu
        self.assertEqual(self.total("Success"), self.paid())
        self.assert_error(BusinessRuleError, "nothing_to_refund", lambda: self.overpay("0.01"))


class ManualGatewayRefundOrderTest(OverpaymentRefundBase):
    payment_code = "QR"
    gateway_code = "SEPAY-1"

    def make_gateway(self):
        return ManualRefundGateway(self.session)

    def second_gateway_code(self):
        return "SEPAY-2"

    def test_manual_pending_refunds_hold_money_until_resolved(self):
        rid = self.approved()
        self.assertEqual(self.refund(rid).Status, "Processing")  # Pending, chưa gọi API
        self.assertEqual(self.overpay().Status, "Pending")
        self.assert_error(BusinessRuleError, "refund_pending", lambda: self.overpay())
        self.assertEqual((self.total("Pending"), self.gateway.refund_calls), (Decimal("290000.00"), []))
        self.assert_within_paid()
