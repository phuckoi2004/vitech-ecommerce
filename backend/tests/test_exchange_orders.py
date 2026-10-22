"""Exchange workflow tests: real services, fake persistence; no writes to a real database."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
import uuid

from app.models import Order, OrderItem, ProductSerial, PaymentTransaction
from app.schemas import ReturnRequestCreate, ServiceRequestRejection, OrderStatusUpdate, OrderCancelRequest
from app.schemas.exchange import ExchangeOrderCreate
from app.services import BusinessRuleError, ConflictError, NotFoundError
from tests.test_return_service import ReturnTestBase


class ExchangeOrderTest(ReturnTestBase):
    def setUp(self):
        super().setUp()
        self.qr = self.f.payment_method("QR")
        shipping = self.f.shipping_method()
        shipping.Code, shipping.Name = "STANDARD", "Giao hàng tiêu chuẩn"
        self.created = self.create(request_type="Exchange")
        self.request = self.svc.requests.get_by_id(self.created.ReturnRequestId)
        self.rid = self.request.ReturnRequestId
        # Existing manual-choice tests start with an out-of-stock SKU at acceptance.
        stock = self.phone.StockQuantity
        self.phone.StockQuantity = 0
        self.advance()
        self.phone.StockQuantity = stock

    def advance(self):
        return self.svc.advance_status(self.a(self.staff), self.rid, self.request.Status)

    def place(self, variant=None, by=None):
        return self.svc.exchange.create_order(self.a(by or self.customer), self.rid,
                                              ExchangeOrderCreate(ProductVariantId=variant.ProductVariantId if variant else None))

    def replacement(self, price="120000.00", stock=3):
        replacement = self.f.variant(price=price, stock=stock)
        replacement.product.CategoryId = self.phone.product.CategoryId
        self.phone.StockQuantity = 0
        return replacement

    def stored(self, order):
        return self.svc.orders.get_by_id(order.OrderId)

    def test_acceptance_creates_order_for_customer_without_any_customer_action(self):
        self.request.Status = 'Pending'
        serial = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId,
                         SerialNumber='AUTO-ACCEPT', Status='Available'))
        before = self.phone.StockQuantity
        result = self.advance()
        order = self.svc.orders.exchange_order(self.rid)
        assert result.Exchange['OrderId'] == order.OrderId
        assert order.CustomerId == self.customer.UserId and order.PaymentStatus == 'Paid'
        assert self.phone.StockQuantity == before - 1
        assert serial.Status == 'Reserved' and serial.OrderItemId != self.item.OrderItemId
        assert not result.Exchange['CanChoose']
        self.advance()
        assert self.svc.orders.exchange_order(self.rid).OrderId == order.OrderId
        assert self.phone.StockQuantity == before - 1
        assert len([o for o in self.db.rows(Order) if o.SourceReturnRequestId == self.rid]) == 1

    def test_acceptance_out_of_stock_keeps_customer_choice_without_an_order(self):
        self.request.Status = 'Pending'
        self.phone.StockQuantity = 0
        result = self.advance()
        assert result.Exchange['OrderId'] is None and result.Exchange['CanChoose']
        assert self.svc.orders.exchange_order(self.rid) is None

    def test_acceptance_and_automatic_order_roll_back_together_on_failure(self):
        self.request.Status = 'Pending'
        before = self.phone.StockQuantity
        with patch.object(self.svc.exchange.sales, '_auto_assign_order_serials', side_effect=RuntimeError('fail')):
            with self.assertRaises(RuntimeError):
                self.advance()
        assert self.request.Status == 'Pending' and self.phone.StockQuantity == before
        assert self.svc.orders.exchange_order(self.rid) is None

    def test_even_exchange_is_zero_and_staff_can_process_despite_current_price_increase(self):
        self.request.Status = 'Pending'
        self.phone.Price = Decimal('120000')
        result = self.advance()
        order = self.svc.orders.exchange_order(self.rid)
        assert order.CustomerId == self.customer.UserId
        assert order.TotalAmount == 0 and order.PaymentStatus == 'Paid'
        assert order.ExchangeCreditAmount == order.Subtotal == order.DiscountAmount == 120000
        assert result.Exchange['OrderId'] == order.OrderId and not result.Exchange['CanChoose']
        sales = self.svc.exchange.sales
        sales.update_order_status(self.a(self.staff), order.OrderId, OrderStatusUpdate(OrderStatus='Confirmed'))
        sales.update_order_status(self.a(self.staff), order.OrderId, OrderStatusUpdate(OrderStatus='Processing'))
        assert order.OrderStatus == 'Processing'
        assert len(self.db.rows(PaymentTransaction)) == 1  # Only the original purchase payment.

    def test_customer_detail_refresh_recovers_automatic_order_after_qr_expiry(self):
        replacement = self.replacement('120000')
        placed = self.place(replacement)
        first = self.stored(placed)
        self.phone.StockQuantity = 1  # The original SKU came back in stock while QR was pending.
        self.clock.now += timedelta(minutes=16)
        result = self.svc.get_my_return_request(self.a(self.customer), self.rid)
        assert first.OrderStatus == 'Cancelled'
        assert result.Exchange['OrderId'] != first.OrderId
        assert not result.Exchange['CanChoose'] and self.phone.StockQuantity == 0
        assert result.Exchange['Committed'] and result.Exchange['TotalAmount'] == 0
        assert replacement.StockQuantity == 3

    def test_pending_request_read_never_creates_replacement(self):
        self.request.Status = 'Pending'
        result = self.svc.get_my_return_request(self.a(self.customer), self.rid)
        assert result.Exchange['OrderId'] is None and not result.Exchange['CanChoose']

    def test_available_original_restocked_after_acceptance_is_automatic_on_refresh(self):
        # setUp accepted the request with zero stock; now the same SKU is available again.
        result = self.svc.get_my_return_request(self.a(self.customer), self.rid)
        assert result.Exchange['OrderId'] and not result.Exchange['CanChoose']
        assert self.svc.orders.exchange_order(self.rid).CustomerId == self.customer.UserId

    def test_same_variant_automatically_selected_zero_due_and_one_serial_reserved(self):
        serial = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId,
                         SerialNumber="NEW-001", Status="Available"))
        before = self.phone.StockQuantity
        order = self.place()
        assert order.TotalAmount == 0 and order.ExchangeCreditAmount == self.item.UnitPrice
        assert order.PaymentStatus == "Paid" and order.ShippingFee == 0
        assert order.SourceReturnRequestId == self.rid
        assert self.phone.StockQuantity == before - 1
        assert serial.Status == "Reserved" and serial.OrderItemId != self.item.OrderItemId
        assert self.place().OrderId == order.OrderId
        assert self.phone.StockQuantity == before - 1
        assert len(self.db.rows(PaymentTransaction)) == 1  # original sale only; no fake zero transfer

    def test_cheaper_replacement_uses_only_new_price_no_carryover(self):
        replacement = self.replacement("80000")
        order = self.place(replacement)
        assert order.TotalAmount == 0 and order.ExchangeCreditAmount == 80000
        assert order.Items[0].Quantity == 1
        assert self.svc.exchange.context(self.a(self.customer), self.rid)["Committed"]

    def test_more_expensive_is_pending_qr_for_difference_only(self):
        order = self.place(self.replacement())
        assert order.TotalAmount == 20000 and order.ExchangeCreditAmount == 100000
        assert order.PaymentStatus == "Pending" and order.ShippingFee == 0
        assert self.place().OrderId == order.OrderId

    def test_promotions_are_applied_before_exchange_credit(self):
        replacement = self.replacement("120000")
        fake_price = dict(OriginalPrice=Decimal("120000"), SalePrice=Decimal("90000"), DiscountAmount=Decimal("30000"))
        with patch("app.services.order.variant_price", return_value=fake_price):
            order = self.place(replacement)
        assert order.TotalAmount == 0 and order.ExchangeCreditAmount == 90000
        assert order.DiscountAmount == 120000 and order.Items[0].LineTotal == 0

    def test_same_variant_still_available_blocks_other_choice(self):
        other = self.f.variant()
        other.product.CategoryId = self.phone.product.CategoryId
        self.assert_error(BusinessRuleError, "exchange_original_available", lambda: self.place(other))

    def test_wrong_category_unavailable_stock_and_other_customer_rejected(self):
        other = self.f.variant()
        self.phone.StockQuantity = 0
        self.assert_error(BusinessRuleError, "exchange_category_mismatch", lambda: self.place(other))
        other.product.CategoryId = self.phone.product.CategoryId
        other.StockQuantity = 0
        self.assert_error(BusinessRuleError, "insufficient_stock", lambda: self.place(other))
        self.assert_error(NotFoundError, "return_request_not_found", lambda: self.place(by=self.other))
        assert not any(o.SourceReturnRequestId for o in self.db.rows(Order))

    def test_stock_is_rechecked_at_commit(self):
        replacement = self.replacement()
        assert self.svc.exchange.context(self.a(self.customer), self.rid)["CanChoose"]
        replacement.StockQuantity = 0
        self.assert_error(BusinessRuleError, "insufficient_stock", lambda: self.place(replacement))

    def test_qr_expiry_releases_stock_and_serial_keeps_request_open_allows_retry(self):
        replacement = self.replacement()
        serial = self.db.add(ProductSerial(ProductVariantId=replacement.ProductVariantId, SerialNumber="RETRY", Status="Available"))
        order = self.place(replacement)
        self.clock.now += timedelta(minutes=16)
        context = self.svc.exchange.context(self.a(self.customer), self.rid)
        assert context["OrderId"] is None and context["CanChoose"]
        assert self.stored(order).OrderStatus == "Cancelled" and replacement.StockQuantity == 3
        assert serial.Status == "Available" and serial.OrderItemId is None
        again = self.place(replacement)
        assert again.OrderId != order.OrderId and replacement.StockQuantity == 2

    def test_customer_cancel_unpaid_order_cancels_request_and_releases_only_replacement(self):
        replacement = self.replacement()
        order = self.place(replacement)
        self.assert_error(BusinessRuleError, 'exchange_cancel_via_request', lambda:
            self.svc.exchange.sales.cancel_customer_order(self.a(self.customer), order.OrderId, OrderCancelRequest()))
        assert self.request.Status == 'Approved' and replacement.StockQuantity == 2
        self.svc.cancel_return_request(self.a(self.customer), self.rid)
        assert self.stored(order).OrderStatus == "Cancelled" and replacement.StockQuantity == 3
        assert self.request.Status == "Cancelled" and self.phone.StockQuantity == 0
        assert self.serial.Status == "Sold"

    def test_paid_or_zero_order_locks_cancellation(self):
        order = self.place()
        self.assert_error(BusinessRuleError, "return_not_cancellable",
                          lambda: self.svc.cancel_return_request(self.a(self.customer), self.rid))
        sales = self.svc.exchange.sales
        self.assert_error(BusinessRuleError, "exchange_order_not_cancellable_by_staff",
                          lambda: sales.update_order_status(self.a(self.admin), order.OrderId, OrderStatusUpdate(OrderStatus="Cancelled")))

    def test_complete_requires_settlement_then_restocks_exactly_once(self):
        replacement = self.replacement()
        order = self.place(replacement)
        self.advance(); self.advance()
        self.assert_error(BusinessRuleError, "exchange_order_not_settled", self.advance)
        assert self.phone.StockQuantity == 0 and self.request.Status == "Processing"
        self.stored(order).PaymentStatus = "Paid"
        self.advance()
        assert self.request.Status == "Completed" and self.phone.StockQuantity == 1
        assert self.serial.Status == "Available" and self.serial.OrderItemId is None
        assert self.request.RestockedQuantity == 1
        self.assert_error(ConflictError, "service_request_stale", lambda: self.svc.advance_status(self.a(self.staff), self.rid, "Processing"))
        assert self.phone.StockQuantity == 1

    def test_finish_restocks_even_without_original_serial(self):
        self.request.ProductSerialId = None
        self.place()
        self.advance(); self.advance()
        before = self.phone.StockQuantity
        self.advance()
        assert self.phone.StockQuantity == before + 1

    def test_restocks_roll_back_when_history_write_fails(self):
        self.place(); self.advance(); self.advance()
        before = self.phone.StockQuantity
        with patch.object(self.svc, "_history", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.advance()
        assert self.phone.StockQuantity == before and self.request.Status == "Processing"
        assert self.serial.Status == "Sold"

    def test_cannot_reject_after_acceptance(self):
        self.assert_error(BusinessRuleError, "return_rejection_not_allowed", lambda: self.svc.reject_status(
            self.a(self.admin), self.rid, ServiceRequestRejection(Reason="Không nhận")))

    def test_client_cannot_supply_credit_or_quantity(self):
        from pydantic import ValidationError
        for field, value in (("ExchangeCreditAmount", 999999), ("Quantity", 2), ("CustomerId", str(uuid.uuid4()))):
            with self.assertRaises(ValidationError):
                ExchangeOrderCreate(**{field: value})

    def test_create_is_one_unit_exchange_only(self):
        for kind, quantity, code in (("Return", 1, "invalid_return_type"), ("Exchange", 2, "invalid_return_quantity")):
            self.assert_error(BusinessRuleError, code, lambda: self.svc.create_return_request(self.a(self.customer),
                ReturnRequestCreate(OrderItemId=self.cable_item.OrderItemId, RequestType=kind, Quantity=quantity, Reason="Lỗi")))

    def test_new_warranty_starts_only_on_delivery_not_when_zero_order_is_created(self):
        serial = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId,
                                          SerialNumber="WARRANTY-NEW", Status="Available"))
        order = self.place()
        assert serial.WarrantyStartDate is None and serial.Status == "Reserved"
        for status in ("Confirmed", "Processing", "Shipping", "Delivered"):
            self.svc.exchange.sales.update_order_status(self.a(self.admin), order.OrderId, OrderStatusUpdate(OrderStatus=status))
        assert serial.Status == "Sold" and serial.WarrantyStartDate is not None
        assert serial.WarrantyEndDate > serial.WarrantyStartDate

    def test_restocked_serial_does_not_become_a_new_serialless_return_entitlement(self):
        self.place(); self.advance(); self.advance(); self.advance()
        state = self.svc._customer_return_option(self.item, None)
        assert not state["CanRequest"] and state["MaxQuantity"] == 0

    def test_true_legacy_no_serial_unit_can_be_exchanged_even_if_tracking_now_enabled(self):
        self.item.Quantity = 2  # one numbered unit plus one historical unit without a code
        created = self.svc.create_return_request(self.a(self.customer), ReturnRequestCreate(
            OrderItemId=self.item.OrderItemId, RequestType="Exchange", Quantity=1, Reason="Lỗi thiết bị cũ"))
        assert created.ProductSerialId is None
        state = self.svc._customer_return_option(self.item, None)
        assert state["MaxQuantity"] == 0

    def test_order_page_polling_releases_expired_exchange_without_waiting_for_external_job(self):
        replacement = self.replacement()
        order = self.place(replacement)
        self.clock.now += timedelta(minutes=16)
        read = self.svc.exchange.sales.get_order(self.a(self.customer), order.OrderId)
        assert read.OrderStatus == "Cancelled" and replacement.StockQuantity == 3
        assert self.svc.exchange.context(self.a(self.customer), self.rid)["CanChoose"]
