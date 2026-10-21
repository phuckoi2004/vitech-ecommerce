"""Read-only customer return choices enforce the same ownership, window and quantity rules as creation."""

from app.models import ProductSerial, ReturnRequest
from app.schemas import WarrantyRequestCreate
from app.services import BusinessRuleError, NotFoundError, PermissionDeniedError, ReturnPolicy
from tests.fakes import warranty_service
from tests.test_return_service import ReturnTestBase, utc


class CustomerReturnOptionsTest(ReturnTestBase):
    def options(self, by=None):
        return self.svc.customer_return_items(self.a(by or self.customer), self.order.OrderId)

    def test_only_devices_assigned_to_own_order_are_disclosed(self):
        self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber='STOCK-PRIVATE', Status='Available'))
        rows = {row.OrderItemId: row for row in self.options()}
        phone = rows[self.item.OrderItemId]
        assert phone.CanRequest and phone.IsSerialTracked and phone.MaxQuantity == 1
        assert phone.ProductName == self.item.ProductName
        assert phone.WindowDays == 7 and phone.ReturnDeadline.isoformat() == '2026-10-11'
        assert [row.ProductSerialId for row in phone.Serials] == [self.serial.ProductSerialId]
        assert self.db.rows(ReturnRequest) == []

    def test_ownership_role_and_delivery_state(self):
        self.assert_error(NotFoundError, 'order_not_found', lambda: self.options(by=self.other))
        self.assert_error(PermissionDeniedError, 'permission_denied', lambda: self.options(by=self.staff))
        self.order.OrderStatus = 'Shipping'
        self.assert_error(BusinessRuleError, 'return_order_not_delivered', self.options)

    def test_partial_return_reserves_quantity_until_cancellation(self):
        created = self.create(item=self.cable_item, quantity=2)
        cable = next(row for row in self.options() if row.OrderItemId == self.cable_item.OrderItemId)
        assert cable.CanRequest and cable.MaxQuantity == 1 and cable.Quantity == 3
        self.svc.cancel_return_request(self.a(self.customer), created.ReturnRequestId)
        cable = next(row for row in self.options() if row.OrderItemId == self.cable_item.OrderItemId)
        assert cable.CanRequest and cable.MaxQuantity == 3

    def test_full_return_disables_nonserial_line(self):
        self.create(item=self.cable_item, quantity=3)
        cable = next(row for row in self.options() if row.OrderItemId == self.cable_item.OrderItemId)
        assert not cable.CanRequest and cable.MaxQuantity == 0
        assert 'Toàn bộ' in cable.Reason

    def test_duplicate_device_does_not_block_another_device_in_same_line(self):
        self.item.Quantity = 2
        other = self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId,
                            OrderItemId=self.item.OrderItemId, SerialNumber='IMEI-002', Status='Sold'))
        self.create()
        phone = next(row for row in self.options() if row.OrderItemId == self.item.OrderItemId)
        devices = {row.ProductSerialId: row for row in phone.Serials}
        assert not devices[self.serial.ProductSerialId].CanRequest
        assert 'đang có yêu cầu đổi/trả' in devices[self.serial.ProductSerialId].Reason
        assert devices[other.ProductSerialId].CanRequest and phone.CanRequest

    def test_deadline_is_inclusive_in_vietnam_and_expiry_is_explained(self):
        self.clock.now = utc(2026, 10, 11, 16, 59)
        assert all(row.CanRequest for row in self.options())
        self.clock.now = utc(2026, 10, 11, 17, 0)
        for row in self.options():
            assert not row.CanRequest and 'quá thời hạn' in row.Reason
            assert row.ReturnDeadline.isoformat() == '2026-10-11'

    def test_custom_policy_is_used_instead_of_hardcoded_seven_days(self):
        self.svc.policy = ReturnPolicy(window_days=14)
        assert all(row.ReturnDeadline.isoformat() == '2026-10-18' and row.WindowDays == 14 for row in self.options())
        self.svc.policy = ReturnPolicy()
        assert all(not row.CanRequest and 'Chưa cấu hình' in row.Reason for row in self.options())

    def test_open_warranty_blocks_the_exact_serial_and_nonserial_line(self):
        warranty = warranty_service(self.db, self.session, clock=self.clock)
        for item, serial_id in [(self.item, self.serial.ProductSerialId), (self.cable_item, None)]:
            warranty.create_warranty_request(self.a(self.customer), WarrantyRequestCreate(
                OrderItemId=item.OrderItemId, ProductSerialId=serial_id, IssueDescription='Không lên nguồn'))
        for row in self.options():
            assert not row.CanRequest
            reason = row.Serials[0].Reason if row.IsSerialTracked else row.Reason
            assert 'bảo hành' in reason

    def test_missing_delivery_timestamp_is_reported_without_inventing_a_deadline(self):
        self.order.DeliveredAt = None
        for row in self.options():
            assert not row.CanRequest and row.ReturnDeadline is None
            assert 'Chưa ghi nhận' in row.Reason
