"""Admin order ownership and individual/shared new-order acknowledgements."""
from app.core.rbac import permissions_for
from app.models import Notification
from app.schemas import OrderAdminUpdate, OrderStatusUpdate
from app.services import BusinessRuleError, PermissionDeniedError
from tests.fakes import notification_service
from tests.test_order import OrderTestBase


class AdminOrderWorkflowTest(OrderTestBase):
    def create_cod(self, customer=None):
        customer = customer or self.customer
        self.f.cart_with(customer, (self.f.variant(stock=5), 1))
        return self.svc.create_order(self.f.actor(customer), self.order_input(PaymentMethodId=self.cod.PaymentMethodId))

    def test_all_internal_users_receive_alerts_and_reading_only_acknowledges_reader(self):
        other = self.f.user("Staff")
        locked = self.f.user("Staff", status="Locked")
        deleted = self.f.user("Staff", deleted=True)
        order = self.create_cod()
        alerts = [n for n in self.db.rows(Notification) if n.NotificationType == "NewOrder"]
        self.assertEqual({n.UserId for n in alerts}, {self.staff.UserId, self.admin.UserId, other.UserId, locked.UserId})
        self.assertNotIn(deleted.UserId, {n.UserId for n in alerts})
        self.assertTrue(all(n.ActionUrl == f"/admin/orders/{order.OrderId}" and not n.IsRead for n in alerts))
        expected_total = f"{order.TotalAmount:,.0f}".replace(",", ".")
        self.assertTrue(all(f"{expected_total}đ ({self.cod.Name})" in n.Content for n in alerts))
        self.assertEqual(len(alerts), 4)
        self.assertFalse(any(n.NotificationType == "Order" and n.UserId != self.customer.UserId
                             for n in self.db.rows(Notification)))
        own = next(n for n in alerts if n.UserId == self.staff.UserId)
        notification_service(self.db, self.session).mark_read(self.f.actor(self.staff), own.NotificationId)
        self.assertTrue(own.IsRead)
        self.assertTrue(all(not n.IsRead for n in alerts if n is not own))
        self.set_status(order.OrderId, "Confirmed")
        self.assertTrue(all(n.IsRead for n in alerts))
        self.assertTrue(any(not n.IsRead for n in self.f.notifications_for(self.customer)))

    def test_first_confirmer_owns_steps_and_admin_intervenes_without_changing_owner(self):
        order = self.create_cod()
        another = self.f.user("Staff")
        result = self.set_status(order.OrderId, "Confirmed")
        self.assertEqual(result.AssignedStaffId, self.staff.UserId)
        self.assertIsNotNone(result.ConfirmedAt)
        for target in ("Shipping", "Processing"):
            with self.assertRaises(PermissionDeniedError):
                self.svc.update_order_status(self.f.actor(another), order.OrderId, OrderStatusUpdate(OrderStatus=target))
        self.svc.update_order_status(self.f.actor(self.admin), order.OrderId, OrderStatusUpdate(OrderStatus="Processing"))
        self.svc.update_order_status(self.f.actor(self.admin), order.OrderId, OrderStatusUpdate(OrderStatus="Shipping"))
        self.assertEqual(self.svc.admin_get_order(self.f.actor(another), order.OrderId).AssignedStaffId, self.staff.UserId)
        with self.assertRaises(PermissionDeniedError):
            self.svc.confirm_cod_delivery(self.f.actor(another), order.OrderId)
        self.svc.confirm_cod_delivery(self.f.actor(self.staff), order.OrderId)

    def test_other_staff_cannot_cancel_edit_notes_or_take_over(self):
        order = self.create_cod()
        self.set_status(order.OrderId, "Confirmed")
        other = self.f.actor(self.f.user("Staff"))
        for call in (
            lambda: self.svc.update_order_status(other, order.OrderId, OrderStatusUpdate(OrderStatus="Cancelled")),
            lambda: self.svc.update_order_admin_info(other, order.OrderId, OrderAdminUpdate(InternalNote="changed")),
            lambda: self.svc.update_order_admin_info(other, order.OrderId, OrderAdminUpdate(AssignedStaffId=other.user_id)),
            lambda: self.svc.release_order_serial(other, order.OrderId, "UNASSIGNED"),
        ):
            with self.assertRaises(PermissionDeniedError): call()
        with self.assertRaises(BusinessRuleError):
            self.svc.update_order_admin_info(self.f.actor(self.admin), order.OrderId,
                                            OrderAdminUpdate(AssignedStaffId=other.user_id))

    def test_failed_confirmation_preserves_pending_owner_and_unread_alerts(self):
        order = self.create_cod()
        self.svc.orders.get_by_id(order.OrderId).PaymentMethodId = self.qr.PaymentMethodId
        with self.assertRaises(BusinessRuleError): self.set_status(order.OrderId, "Confirmed")
        stored = self.svc.orders.get_by_id(order.OrderId)
        self.assertEqual((stored.OrderStatus, stored.AssignedStaffId), ("Pending", None))
        self.assertTrue(all(not n.IsRead for n in self.db.rows(Notification) if n.NotificationType == "NewOrder"))

    def test_cancelling_resolves_only_its_orders_new_alerts(self):
        first = self.create_cod()
        self.create_cod(self.other)
        self.set_status(first.OrderId, "Cancelled")
        for note in self.db.rows(Notification):
            if note.NotificationType == "NewOrder": self.assertEqual(note.IsRead, note.ReferenceId == first.OrderId)

    def test_staff_grants_content_and_moderation_but_no_catalog_writes(self):
        granted = permissions_for("Staff")
        for permission in ("reviews:view", "reviews:delete", "news:create", "news:update", "news:delete", "banners:create", "banners:update", "banners:delete"):
            self.assertIn(permission, granted)
        self.assertNotIn("products:update", granted)
        self.assertNotIn("users:manage", granted)
