"""Đợt 5.8 (P1.2): không cho TẮT quản lý Serial/IMEI khi biến thể còn dữ liệu serial/lịch sử/quy trình liên quan.

Tồn kho bằng 0 là chưa đủ: serial Sold/Warranty/Reserved/Returned, dòng đơn hàng (kể cả khi serial đã bị gỡ khỏi dòng
đơn) và yêu cầu bảo hành/đổi trả/hàng hoàn đang mở đều phải chặn. Bị từ chối thì không đổi bất kỳ dữ liệu nào.
Fake trong bộ nhớ: khóa dòng/đồng thời chỉ được giả lập; câu SQL thật được kiểm tra riêng ở test_query_shapes.
"""

import unittest

from app.models import ProductSerial, ReturnRequest, ShipmentReturn, ShipmentReturnItem, WarrantyRequest
from app.schemas import ProductVariantUpdate
from app.services import BusinessRuleError

from tests.fakes import Factory, FakeSession, InMemoryDB, variant_service

IN_USE = "serial_tracking_in_use"


class SerialTrackingToggleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.admin, self.customer = self.f.user("Admin"), self.f.user()
        self.cod = self.f.payment_method("COD")
        self.svc = variant_service(self.db, self.session)
        self.variant = self.f.variant(stock=0, serial_tracked=True)

    def serial(self, status, item=None, variant=None):
        return self.db.add(ProductSerial(
            ProductVariantId=(variant or self.variant).ProductVariantId,
            OrderItemId=item.OrderItemId if item is not None else None,
            SerialNumber=f"IMEI-{self.f._next()}", Status=status,
        ))

    def line(self, status="Delivered"):
        return self.f.order(self.customer, self.cod, status=status, payment_status="Paid",
                            lines=((self.variant, 1),)).items[0]

    def turn_off(self, variant=None):
        return self.svc.update_variant(self.f.actor(self.admin), (variant or self.variant).ProductVariantId,
                                       ProductVariantUpdate(IsSerialTracked=False))

    def snapshot(self):
        return sorted((s.SerialNumber, s.Status, s.OrderItemId) for s in self.db.rows(ProductSerial))

    def assert_refused(self, *fragments, variant=None):
        variant = variant or self.variant
        before = self.snapshot()
        with self.assertRaises(BusinessRuleError) as ctx:
            self.turn_off(variant)
        self.assertEqual(ctx.exception.code, IN_USE)
        for fragment in fragments:
            self.assertIn(fragment, ctx.exception.message)
        self.assertTrue(variant.IsSerialTracked)
        self.assertEqual(self.snapshot(), before)  # không xóa/đổi trạng thái/gỡ liên kết serial
        return ctx.exception.message

    def test_zero_stock_with_sold_serial_is_refused(self):
        self.serial("Sold", self.line())
        self.assert_refused("serial chưa loại bỏ", "dòng đơn hàng")

    def test_any_serial_that_is_not_written_off_is_refused(self):
        for status in ("Sold", "Warranty", "Reserved", "Returned", "Available"):
            with self.subTest(status=status):
                variant = self.f.variant(stock=0, serial_tracked=True)
                self.serial("WrittenOff", variant=variant)
                self.serial(status, variant=variant)  # không gắn dòng đơn: chỉ quy tắc serial chặn
                message = self.assert_refused("còn 1 serial chưa loại bỏ", variant=variant)
                self.assertNotIn("dòng đơn hàng", message)

    def test_unused_variant_can_turn_off_and_back_on(self):
        self.assertFalse(self.turn_off().IsSerialTracked)
        on = self.svc.update_variant(self.f.actor(self.admin), self.variant.ProductVariantId,
                                     ProductVariantUpdate(IsSerialTracked=True))
        self.assertTrue(on.IsSerialTracked)

    def test_only_written_off_serials_without_orders_can_turn_off(self):
        self.serial("WrittenOff")
        self.serial("WrittenOff")
        before = self.snapshot()
        self.assertFalse(self.turn_off().IsSerialTracked)
        self.assertEqual(self.snapshot(), before)  # serial đã loại bỏ được giữ nguyên

    def test_order_history_is_refused_even_after_serial_was_unlinked_from_the_line(self):
        self.line("Delivered")
        self.serial("WrittenOff")  # serial từng bán đã bị gỡ khỏi dòng đơn (OrderItemId NULL) rồi loại bỏ
        message = self.assert_refused("1 dòng đơn hàng")
        self.assertNotIn("serial chưa loại bỏ", message)

    def test_order_history_of_any_status_is_refused(self):
        for status in ("Pending", "Shipping", "Completed", "Cancelled"):
            with self.subTest(status=status):
                self.line(status)
                self.assert_refused("dòng đơn hàng")

    def test_open_warranty_request_is_refused(self):
        item = self.line("Completed")
        serial = self.serial("WrittenOff", item)
        request = self.db.add(WarrantyRequest(
            RequestCode="BH-1", CustomerId=self.customer.UserId, OrderItemId=item.OrderItemId,
            ProductSerialId=serial.ProductSerialId, IssueDescription="Lỗi", Status="Processing",
        ))
        self.assert_refused("1 yêu cầu bảo hành đang mở", "dòng đơn hàng")
        request.Status = "Completed"
        self.assertNotIn("bảo hành", self.assert_refused("dòng đơn hàng"))  # đóng rồi vẫn còn lịch sử đơn

    def test_open_return_request_is_refused(self):
        item = self.line("Delivered")
        request = self.db.add(ReturnRequest(
            RequestCode="DT-1", CustomerId=self.customer.UserId, OrderItemId=item.OrderItemId,
            RequestType="Return", Reason="Lỗi", Quantity=1, Status="Receiving",
        ))
        self.assert_refused("1 yêu cầu đổi/trả đang mở")
        request.Status = "Rejected"
        self.assertNotIn("đổi/trả", self.assert_refused("dòng đơn hàng"))

    def test_awaiting_shipment_return_is_refused(self):
        item = self.line("Cancelled")
        shipment = self.db.add(ShipmentReturn(OrderId=item.OrderId, Status="AwaitingReturn"))
        self.db.add(ShipmentReturnItem(ShipmentReturnId=shipment.ShipmentReturnId, OrderItemId=item.OrderItemId,
                                       ExpectedQuantity=1))
        self.assert_refused("1 phiếu hàng hoàn chưa nhận")
        shipment.Status = "Received"
        self.assertNotIn("hàng hoàn", self.assert_refused("dòng đơn hàng"))

    def test_other_variants_data_does_not_block(self):
        other = self.f.variant(stock=0, serial_tracked=True)
        self.serial("Sold", self.f.order(self.customer, self.cod, lines=((other, 1),)).items[0], variant=other)
        self.assertFalse(self.turn_off().IsSerialTracked)

    def test_stock_rule_and_unchanged_value_are_kept(self):
        stocked = self.f.variant(stock=2, serial_tracked=True)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.turn_off(stocked)
        self.assertEqual(ctx.exception.code, "serial_tracking_change_requires_zero_stock")
        self.serial("Sold", self.line())
        same = self.svc.update_variant(self.f.actor(self.admin), self.variant.ProductVariantId,
                                       ProductVariantUpdate(IsSerialTracked=True, VariantName="Mới"))
        self.assertEqual((same.IsSerialTracked, same.VariantName), (True, "Mới"))  # không đổi cờ thì không kiểm tra
        self.assertIn(("ProductVariant", self.variant.ProductVariantId), self.db.locks)


if __name__ == "__main__":
    unittest.main()
