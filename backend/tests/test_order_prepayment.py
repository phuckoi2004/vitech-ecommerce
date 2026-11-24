"""Mandatory high-value prepayment: server pricing, QR receipts, COD balance and refunds.

Isolated fake storage; never modifies the configured database.
"""
from datetime import timedelta
from decimal import Decimal

from app.models import Order, PaymentTransaction
from app.schemas import OrderCancelRequest, OrderCreate, OrderDetailResponse, OrderStatusUpdate
from app.services import BusinessRuleError
from app.services.payment import BankTransfer
from tests.fakes import NOW, order_service
from tests.test_payment import PaymentTestBase


class PrepaymentTest(PaymentTestBase):
    def setUp(self):
        super().setUp()
        self.orders = order_service(self.db, self.session)

    def create_order(self, total="12000000", *, method=None, fee="0", coupon=None):
        self.customer = self.f.user()
        variant = self.f.variant(stock=5, price=total, cost="1")
        self.f.cart_with(self.customer, (variant, 1))
        result = self.orders.create_order(self.f.actor(self.customer), OrderCreate(
            ShippingMethodId=self.f.shipping_method(fee).ShippingMethodId,
            PaymentMethodId=(method or self.cod).PaymentMethodId,
            ReceiverName="Customer", ReceiverPhone="0912345678", ShippingAddress="Address",
            CouponCode=coupon))
        order = self.db.get(Order, result.OrderId)
        order.payment_method = method or self.cod
        return order

    def pay(self, order, amount=None, *, key="deposit-1"):
        qr = self.svc.create_qr_payment(self.f.actor(self.customer), order.OrderId)
        tx = self.db.get(PaymentTransaction, qr.PaymentTransactionId)
        with self.svc.transaction():
            outcome, _ = self.svc.apply_bank_transfer(BankTransfer(
                reconciliation_key=key, payment_code=tx.GatewayTransactionCode,
                amount=tx.Amount if amount is None else Decimal(amount), response_data={"id": key}))
        return qr, outcome

    def advance(self, order, target):
        return self.orders.update_order_status(self.f.actor(self.staff), order.OrderId,
                                               OrderStatusUpdate(OrderStatus=target))

    def test_strict_threshold_fee_and_whole_dong_rounding(self):
        for total, fee, expected in [("9999999", "0", "0"), ("10000000", "0", "0"),
                                      ("10000001", "0", "2000001"),
                                      ("9990000", "30000", "2004000"),
                                      ("12000000", "0", "2400000")]:
            with self.subTest(total=total, fee=fee):
                order = self.create_order(total, fee=fee)
                self.assertEqual(order.PrepaymentAmount, Decimal(expected))

    def test_coupon_can_bring_order_below_threshold(self):
        self.f.coupon(self.admin)
        order = self.create_order("11000000", coupon="SALE10")
        self.assertEqual(order.TotalAmount, Decimal("9900000"))
        self.assertEqual(order.PrepaymentAmount, 0)

    def test_full_qr_and_historical_cod_do_not_become_deposit_orders(self):
        order = self.create_order(method=self.qr)
        qr, outcome = self.pay(order)
        self.assertEqual((qr.Amount, outcome, order.PaymentStatus), (Decimal("12000000"), "paid", "Paid"))
        historical = self.f.order(self.customer, self.cod, total="12000000")
        self.assertEqual(historical.PrepaymentAmount, 0)
        self.assertEqual(self.advance(historical, "Confirmed").OrderStatus, "Confirmed")

    def test_cannot_confirm_or_bypass_prepayment_as_staff_or_admin(self):
        order = self.create_order()
        for operator in (self.staff, self.admin):
            with self.subTest(role=operator.Role), self.assertRaises(BusinessRuleError) as error:
                self.orders.update_order_status(self.f.actor(operator), order.OrderId,
                                                OrderStatusUpdate(OrderStatus="Confirmed"))
            self.assertEqual(error.exception.code, "order_prepayment_required")
        self.assertEqual(order.OrderStatus, "Pending")

    def test_qr_collects_only_twenty_percent_then_cod_only_collects_balance(self):
        order = self.create_order()
        qr, outcome = self.pay(order)
        self.assertEqual((qr.Amount, qr.PaymentMethodId), (Decimal("2400000"), self.qr.PaymentMethodId))
        self.assertEqual(self.gateway.qr_calls[0]["amount"], Decimal("2400000"))
        self.assertEqual((outcome, order.PaymentStatus), ("partially_paid", "PartiallyPaid"))
        response = OrderDetailResponse.model_validate(order)
        self.assertEqual((response.ReceivedAmount, response.RemainingAmount), (Decimal("2400000"), Decimal("9600000")))
        with self.assertRaises(BusinessRuleError):
            self.svc.create_qr_payment(self.f.actor(self.customer), order.OrderId)
        for target in ("Confirmed", "Processing", "Shipping"):
            self.advance(order, target)
        result = self.orders.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId)
        self.assertEqual((result.PaymentStatus, result.ReceivedAmount, result.RemainingAmount),
                         ("Paid", Decimal("12000000"), 0))
        self.assertEqual(sorted(t.Amount for t in self.txs(order)), [Decimal("2400000"), Decimal("9600000")])
        with self.assertRaises(BusinessRuleError):
            self.orders.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId)
        self.assertEqual(len(self.txs(order)), 2)

    def test_short_transfer_is_not_accepted_as_a_deposit(self):
        order = self.create_order()
        _, outcome = self.pay(order, "2300000")
        self.assertEqual((outcome, order.PaymentStatus, order.ReceivedAmount), ("amount_mismatch", "Pending", 0))
        with self.assertRaises(BusinessRuleError):
            self.advance(order, "Confirmed")

    def test_deposit_orders_expire_without_money_but_not_after_receipt(self):
        unpaid = self.create_order()
        paid = self.create_order()
        self.pay(paid)
        unpaid.OrderedAt = paid.OrderedAt = NOW - timedelta(minutes=16)
        self.assertEqual(self.orders.expire_unpaid_qr_orders().processed, 1)
        self.assertEqual((unpaid.OrderStatus, paid.OrderStatus, paid.PaymentStatus), ("Cancelled", "Pending", "PartiallyPaid"))

    def test_partial_payment_cancellation_is_staff_only_and_refunds_actual_receipt(self):
        order = self.create_order()
        self.pay(order)
        with self.assertRaises(BusinessRuleError) as error:
            self.orders.cancel_customer_order(self.f.actor(self.customer), order.OrderId, OrderCancelRequest())
        self.assertEqual(error.exception.code, "order_paid_not_cancellable")
        self.advance(order, "Cancelled")
        waiting = self.svc.list_orders_awaiting_refund(self.f.actor(self.staff))
        self.assertIn(order.OrderId, [o.OrderId for o in waiting.Items])
        refund = self.svc.refund_order(self.f.actor(self.staff), order.OrderId)
        self.assertEqual(refund.Amount, Decimal("2400000"))
        self.assertEqual(order.PaymentStatus, "Refunded")

    def test_failed_cod_completion_rolls_back_balance_and_status(self):
        order = self.create_order()
        self.pay(order)
        for target in ("Confirmed", "Processing", "Shipping"):
            self.advance(order, target)
        def fail(*args, **kwargs):
            raise RuntimeError("history persistence failed")
        self.orders._record_history = fail
        with self.assertRaises(RuntimeError):
            self.orders.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId)
        self.assertEqual((order.OrderStatus, order.PaymentStatus), ("Shipping", "PartiallyPaid"))
        self.assertEqual(len(self.txs(order)), 1)

    def test_late_deposit_is_recorded_for_refund_without_reopening_order(self):
        order = self.create_order()
        qr = self.svc.create_qr_payment(self.f.actor(self.customer), order.OrderId)
        order.OrderedAt = NOW - timedelta(minutes=16)
        self.orders.expire_unpaid_qr_orders()
        self.callback(self.db.get(PaymentTransaction, qr.PaymentTransactionId).GatewayTransactionCode, qr.Amount)
        self.assertEqual((order.OrderStatus, order.PaymentStatus), ("Cancelled", "PartiallyPaid"))
        self.assertIn(order.OrderId, [o.OrderId for o in self.svc.list_orders_awaiting_refund(self.f.actor(self.staff)).Items])
