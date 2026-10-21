"""Automatic immutable order serial allocation; all tests use an isolated in-memory database."""
import unittest
from unittest.mock import Mock
from app.models import ProductSerial, Order, Notification, ShipmentReturnItem
from app.schemas import OrderItemSerialAssign, OrderSerialAssign, OrderStatusUpdate, ShipmentReturnReceive, ShipmentReturnItemReceive
from app.services import BusinessRuleError, ConflictError, PermissionDeniedError
from tests.test_order import OrderTestBase
from tests.test_router_flows import flow


class AutomaticSerialTest(OrderTestBase):
    def setUp(self):
        super().setUp()
        self.phone = self.f.variant(stock=4, serial_tracked=True)
        self.codes = [self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId,
                      SerialNumber=f"PHONE-{i}", Status="Available")) for i in range(4)]

    def checkout(self, quantity=2, customer=None):
        customer = customer or self.customer
        self.f.cart_with(customer, (self.phone, quantity))
        response = self.svc.create_order(self.f.actor(customer), self.order_input(PaymentMethodId=self.cod.PaymentMethodId))
        return self.db.get(Order, response.OrderId)

    def confirm(self, order):
        return self.set_status(order.OrderId, "Confirmed")

    def test_confirmation_automatically_allocates_exact_quantity_and_keeps_stock(self):
        order = self.checkout()
        self.assertEqual(self.phone.StockQuantity, 2)
        self.assertTrue(all(s.Status == "Available" for s in self.codes))
        self.confirm(order)
        summary = self.svc.get_order_serials(self.f.actor(self.staff), order.OrderId)[0]
        self.assertEqual(summary.SerialNumbers, ["PHONE-0", "PHONE-1"])
        self.assertEqual(self.phone.StockQuantity, 2)
        self.assertTrue(all(s.OrderItemId == order.items[0].OrderItemId for s in self.codes[:2]))
        names = [n for n, _ in self.db.locks]
        self.assertIn("ProductVariant", names)
        self.assertIn("ProductSerial", names)
        self.assertEqual(order.OrderStatus, "Confirmed")
        self.set_status(order.OrderId, "Processing")
        self.assertEqual(self.svc.get_order_serials(self.f.actor(self.staff), order.OrderId)[0].SerialNumbers,
                         summary.SerialNumbers)
        self.assertEqual(self.phone.StockQuantity, 2)

    def test_other_orders_never_get_a_device_already_reserved(self):
        first, second = self.checkout(), self.checkout(customer=self.other)
        self.confirm(first)
        self.confirm(second)
        self.assertEqual({s.OrderItemId for s in self.codes}, {first.items[0].OrderItemId, second.items[0].OrderItemId})
        self.assertTrue(all(s.Status == "Reserved" for s in self.codes))
        self.assertEqual(self.phone.StockQuantity, 0)

    def test_manual_assignment_and_release_rejected_for_both_internal_roles(self):
        order = self.checkout()
        self.confirm(order)
        before = [(s.Status, s.OrderItemId) for s in self.codes]
        body = OrderSerialAssign(Items=[OrderItemSerialAssign(OrderItemId=order.items[0].OrderItemId,
                                                             SerialNumbers=["PHONE-3"])])
        for user in (self.staff, self.admin):
            for call in (lambda: self.svc.assign_order_serials(self.f.actor(user), order.OrderId, body),
                         lambda: self.svc.release_order_serial(self.f.actor(user), order.OrderId, "PHONE-0")):
                with self.subTest(role=user.Role), self.assertRaises(BusinessRuleError) as error:
                    call()
                self.assertEqual(error.exception.code, "order_serials_read_only")
        self.assertEqual(before, [(s.Status, s.OrderItemId) for s in self.codes])

    def test_customer_cannot_use_serial_endpoints(self):
        order = self.checkout()
        with self.assertRaises(PermissionDeniedError):
            self.svc.release_order_serial(self.f.actor(self.customer), order.OrderId, "PHONE-0")

    def test_codes_are_allocated_before_using_legacy_stock_and_delivery_allows_missing_codes(self):
        order = self.checkout()
        for s in self.codes[1:]:
            s.Status = "WrittenOff"
        self.confirm(order)
        self.assertEqual(self.svc.get_order_serials(self.f.actor(self.staff), order.OrderId)[0].SerialNumbers, ['PHONE-0'])
        self.set_status(order.OrderId, "Processing")
        self.set_status(order.OrderId, 'Shipping')
        self.svc.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId)
        self.assertEqual((order.OrderStatus, self.codes[0].Status, self.phone.StockQuantity), ('Delivered', 'Sold', 2))

    def test_locked_codes_do_not_silently_fall_back_to_legacy_and_failure_rolls_back(self):
        order = self.checkout()
        self.svc.serials.list_available_for_update = Mock(return_value=[])
        before = [(s.Status, s.OrderItemId) for s in self.codes]
        with self.assertRaises(ConflictError) as error:
            self.confirm(order)
        self.assertEqual(error.exception.code, "serial_not_available")
        self.assertEqual((order.OrderStatus, order.AssignedStaffId), ("Pending", None))
        self.assertEqual(before, [(s.Status, s.OrderItemId) for s in self.codes])
        self.assertTrue(all(not n.IsRead for n in self.db.rows(Notification) if n.NotificationType == "NewOrder"))

    def test_second_line_lock_conflict_rolls_back_first_line_assignments(self):
        other = self.f.variant(stock=1, serial_tracked=True)
        self.f.cart_with(self.customer, (self.phone, 1), (other, 1))
        response = self.svc.create_order(self.f.actor(self.customer), self.order_input(PaymentMethodId=self.cod.PaymentMethodId))
        order = self.db.get(Order, response.OrderId)
        self.db.add(ProductSerial(ProductVariantId=other.ProductVariantId, SerialNumber='OTHER', Status='Available'))
        select = self.svc.serials.list_available_for_update
        last_variant = max(other.ProductVariantId, self.phone.ProductVariantId)
        self.svc.serials.list_available_for_update = lambda variant_id, **kwargs: [] if variant_id == last_variant else select(variant_id, **kwargs)
        before = [(s.Status, s.OrderItemId) for s in self.db.rows(ProductSerial)]
        with self.assertRaises(ConflictError):
            self.confirm(order)
        self.assertEqual(before, [(s.Status, s.OrderItemId) for s in self.db.rows(ProductSerial)])
        self.assertEqual(order.OrderStatus, "Pending")

    def test_entirely_unnumbered_old_stock_can_be_sold(self):
        order = self.checkout()
        for serial in self.codes:
            serial.Status = 'WrittenOff'
        self.confirm(order)
        self.assertEqual(self.svc.get_order_serials(self.f.actor(self.staff), order.OrderId)[0].SerialNumbers, [])
        self.set_status(order.OrderId, "Processing")
        self.set_status(order.OrderId, 'Shipping')
        self.svc.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId)
        self.assertEqual(order.OrderStatus, 'Delivered')

    def test_mixed_shipping_cancellation_preserves_both_kinds_of_returned_devices(self):
        order = self.checkout()
        for serial in self.codes[1:]: serial.Status = 'WrittenOff'
        self.confirm(order)
        self.set_status(order.OrderId, "Processing")
        self.set_status(order.OrderId, 'Shipping')
        self.set_status(order.OrderId, 'Cancelled')
        rows = self.db.rows(ShipmentReturnItem)
        self.assertEqual(sorted(r.ExpectedQuantity for r in rows), [1, 1])
        self.assertEqual(sum(r.ProductSerialId is None for r in rows), 1)
        self.svc.receive_shipment_return(self.f.actor(self.staff), order.OrderId,
            ShipmentReturnReceive(Items=[ShipmentReturnItemReceive(OrderItemId=order.items[0].OrderItemId,
                RestockedQuantity=1, DamagedQuantity=0)], RestockedSerialNumbers=['PHONE-0']))
        self.assertEqual((self.phone.StockQuantity, self.codes[0].Status), (4, 'Available'))

    def test_flush_failure_rolls_back_allocation_and_confirmation(self):
        order = self.checkout()
        self.svc.serials.flush = Mock(side_effect=RuntimeError("write failure"))
        with self.assertRaises(RuntimeError):
            self.confirm(order)
        self.assertEqual(order.OrderStatus, "Pending")
        self.assertTrue(all(s.Status == "Available" and s.OrderItemId is None for s in self.codes))

    def test_delivery_preserves_order_codes_and_does_not_deduct_stock_again(self):
        order = self.checkout()
        self.confirm(order)
        assigned = self.svc.get_order_serials(self.f.actor(self.staff), order.OrderId)[0].SerialNumbers
        self.set_status(order.OrderId, "Processing")
        self.set_status(order.OrderId, "Shipping")
        self.svc.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId)
        self.assertEqual(self.phone.StockQuantity, 2)
        self.assertEqual(self.svc.get_order_serials(self.f.actor(self.staff), order.OrderId)[0].SerialNumbers, assigned)
        self.assertTrue(all(s.Status == "Sold" and s.OrderItemId == order.items[0].OrderItemId for s in self.codes[:2]))

    def test_cancel_before_shipping_returns_exact_devices_and_stock(self):
        order = self.checkout()
        self.confirm(order)
        self.set_status(order.OrderId, "Cancelled")
        self.assertEqual(self.phone.StockQuantity, 4)
        self.assertTrue(all(s.Status == "Available" and s.OrderItemId is None for s in self.codes))

    def test_shipping_cancellation_keeps_devices_until_returned(self):
        order = self.checkout()
        self.confirm(order)
        self.set_status(order.OrderId, "Processing")
        self.set_status(order.OrderId, "Shipping")
        self.set_status(order.OrderId, "Cancelled")
        self.assertEqual(self.phone.StockQuantity, 2)
        self.assertTrue(all(s.Status == "Reserved" for s in self.codes[:2]))

    def test_legacy_confirmed_orders_get_allocation_when_processing(self):
        order = self.checkout()
        order.OrderStatus = "Confirmed"
        order.AssignedStaffId = self.staff.UserId
        self.set_status(order.OrderId, "Processing")
        self.assertEqual(sum(s.Status == "Reserved" for s in self.codes), 2)


def test_http_confirmation_allocates_and_all_internal_roles_cannot_change_serials(flow):
    _, db, factory, as_user = flow
    customer, staff, admin = factory.user(), factory.user('Staff'), factory.user('Admin')
    variant = factory.variant(stock=0, serial_tracked=True)
    order = factory.order(customer, factory.payment_method('COD'), status='Pending', lines=((variant, 1),))
    serial = db.add(ProductSerial(ProductVariantId=variant.ProductVariantId, SerialNumber='AUTO-HTTP', Status='Available'))
    base = f'/admin/orders/{order.OrderId}'
    assert as_user(staff).post(base + '/status', json={'OrderStatus': 'Confirmed'}).status_code == 200
    for user in (staff, admin):
        client = as_user(user)
        assert client.get(base + '/serials').json()[0]['SerialNumbers'] == ['AUTO-HTTP']
        assert client.post(base + '/serials', json={'Items': [{
            'OrderItemId': str(order.items[0].OrderItemId), 'SerialNumbers': ['AUTO-HTTP'],
        }]}).status_code == 400
        assert client.delete(base + '/serials/AUTO-HTTP').status_code == 400
    assert (serial.Status, serial.OrderItemId) == ('Reserved', order.items[0].OrderItemId)
