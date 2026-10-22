"""Customer selection reuses warranty rules; no database writes or foreign/stock serial disclosure."""

from app.services import NotFoundError, PermissionDeniedError, BusinessRuleError
from tests.test_warranty_service import WarrantyTestBase, END, START


class CustomerWarrantyOptionsTest(WarrantyTestBase):
    def options(self, by=None, order=None):
        return self.svc.customer_warranty_items(self.a(by or self.customer), (order or self.order).OrderId)

    def test_selects_only_assigned_devices_and_preserves_period_and_snapshot(self):
        rows = {row.OrderItemId: row for row in self.options()}
        phone = rows[self.item.OrderItemId]
        assert phone.ProductName == self.item.ProductName
        assert phone.WarrantyMonths == self.item.WarrantyMonths
        assert phone.IsSerialTracked and phone.CanRequest
        assert [row.ProductSerialId for row in phone.Serials] == [self.serial.ProductSerialId]
        assert phone.Serials[0].WarrantyStartDate == START
        assert phone.Serials[0].WarrantyEndDate == END
        assert rows[self.cable_item.OrderItemId].CanRequest
        assert self.requests() == []  # preview never creates a request

    def test_foreign_order_is_not_found_and_staff_cannot_use_customer_selector(self):
        self.assert_error(NotFoundError, 'order_not_found', lambda: self.options(by=self.other))
        self.assert_error(PermissionDeniedError, 'permission_denied', lambda: self.options(by=self.staff))

    def test_only_delivered_orders(self):
        self.order.OrderStatus = 'Shipping'
        self.assert_error(BusinessRuleError, 'warranty_order_not_delivered', self.options)

    def test_duplicate_blocks_only_the_requested_device(self):
        second = self.sold_serial(self.item, 'IMEI-002')
        self.create()
        phone = next(row for row in self.options() if row.OrderItemId == self.item.OrderItemId)
        devices = {row.ProductSerialId: row for row in phone.Serials}
        assert not devices[self.serial.ProductSerialId].CanRequest
        assert 'chưa xử lý xong' in devices[self.serial.ProductSerialId].Reason
        assert devices[second.ProductSerialId].CanRequest and phone.CanRequest

    def test_inconsistent_serial_is_explained_without_breaking_other_lines(self):
        self.serial.WarrantyEndDate = START
        rows = {row.OrderItemId: row for row in self.options()}
        device = rows[self.item.OrderItemId].Serials[0]
        assert not device.CanRequest and 'không khớp' in device.Reason
        assert rows[self.cable_item.OrderItemId].CanRequest

    def test_zero_warranty_is_disabled_and_explained(self):
        self.cable_item.WarrantyMonths = 0
        cable = next(row for row in self.options() if row.OrderItemId == self.cable_item.OrderItemId)
        assert not cable.CanRequest and '0 tháng' in cable.Reason
