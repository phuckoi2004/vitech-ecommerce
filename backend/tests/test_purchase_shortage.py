"""Nhà cung cấp giao thiếu (đợt 5.1 nhóm C3): lịch sử nhận hàng, Admin đóng phiếu còn thiếu (Closed).

Fake trong bộ nhớ; không chứng minh concurrency thật của PostgreSQL.
"""

import unittest
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError

from app.models import Notification, PurchaseOrder, PurchaseOrderItem, PurchaseReceipt, PurchaseReceiptItem
from app.schemas import PurchaseOrderClose, PurchaseOrderReceive
from app.services import BusinessRuleError, NotFoundError, PermissionDeniedError

from tests.fakes import NOW
from tests.test_purchasing import PurchaseOrderTestBase


class ShortageTestBase(PurchaseOrderTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.po, self.ids = self.staff_po_approved()  # v1: 10 × 50000, v2: 4 × 120000.50
        self.po_id = self.po.PurchaseOrderId
        self.i1, self.i2 = self.ids[self.v1.ProductVariantId], self.ids[self.v2.ProductVariantId]

    def close(self, reason="Nhà cung cấp ngừng giao phần còn lại", by=None, po_id=None):
        return self.svc.close_purchase_order(self.f.actor(by or self.admin), po_id or self.po_id,
                                             PurchaseOrderClose(Reason=reason))

    def receipts(self):
        return [r for r in self.db.rows(PurchaseReceipt) if r.PurchaseOrderId == self.po_id]

    def state(self):
        po = self.db.get(PurchaseOrder, self.po_id)
        items = sorted((str(i.PurchaseOrderItemId), i.OrderedQuantity, i.ReceivedQuantity)
                       for i in self.db.rows(PurchaseOrderItem) if i.PurchaseOrderId == self.po_id)
        return (po.Status, items, self.v1.StockQuantity, self.v2.StockQuantity, len(self.receipts()),
                len(self.db.rows(PurchaseReceiptItem)))


class ReceiptHistoryTest(ShortageTestBase):
    def test_each_receipt_records_who_when_quantity_and_price(self):
        self.svc.receive_items(self.f.actor(self.staff), self.po_id, PurchaseOrderReceive(
            Items=[{"PurchaseOrderItemId": self.i1, "Quantity": 4}, {"PurchaseOrderItemId": self.i1, "Quantity": 2}],
            Note="Lô 1"))
        self.receive(self.po_id, (self.i1, 1), (self.i2, 3), by=self.admin)
        history = self.svc.list_receipts(self.f.actor(self.staff), self.po_id)
        self.assertEqual([(r.ReceivedByUserId, r.ReceivedAt, r.Note) for r in history],
                         [(self.staff.UserId, NOW, "Lô 1"), (self.admin.UserId, NOW, None)])
        self.assertEqual([(i.PurchaseOrderItemId, i.Quantity, i.UnitPrice) for i in history[0].Items],
                         [(self.i1, 6, Decimal("50000.00"))])  # dòng trùng được cộng dồn
        self.assertEqual({(i.PurchaseOrderItemId, i.Quantity) for i in history[1].Items}, {(self.i1, 1), (self.i2, 3)})
        received = {i.PurchaseOrderItemId: i.ReceivedQuantity for i in self.db.rows(PurchaseOrderItem)}
        for item_id in (self.i1, self.i2):  # lịch sử khớp số đã nhận
            self.assertEqual(sum(i.Quantity for i in self.db.rows(PurchaseReceiptItem) if i.PurchaseOrderItemId == item_id),
                             received[item_id])

    def test_failure_while_recording_history_rolls_back_receipt(self):
        def broken(values):
            raise RuntimeError("ghi lịch sử lỗi")

        self.svc.receipt_items.create = broken
        before = self.state()
        with self.assertRaises(RuntimeError):
            self.receive(self.po_id, (self.i1, 4))
        self.assertEqual(self.state(), before)  # không cộng tồn/ReceivedQuantity khi lịch sử lỗi

    def test_history_is_append_only(self):
        self.receive(self.po_id, (self.i1, 4))
        [receipt] = self.receipts()
        for repo, obj in ((self.svc.receipts, receipt), (self.svc.receipt_items, receipt.items[0])):
            with self.assertRaises(PermissionError):
                repo.update(obj, {})
            with self.assertRaises(PermissionError):
                repo.delete(obj)

    def test_listing_needs_staff_and_existing_order(self):
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_receipts(self.f.actor(self.customer), self.po_id)
        import uuid

        with self.assertRaises(NotFoundError):
            self.svc.list_receipts(self.f.actor(self.staff), uuid.uuid4())


class CloseShortageTest(ShortageTestBase):
    def test_admin_closes_short_delivery_without_counting_missing_goods(self):
        self.receive(self.po_id, (self.i1, 6))
        stock = (self.v1.StockQuantity, self.v2.StockQuantity)
        result = self.close()
        self.assertEqual((result.Status, result.ClosedByUserId, result.ClosedAt, result.CloseReason),
                         ("Closed", self.admin.UserId, NOW, "Nhà cung cấp ngừng giao phần còn lại"))
        self.assertEqual((self.v1.StockQuantity, self.v2.StockQuantity), stock)  # không cộng phần thiếu
        lines = {i.PurchaseOrderItemId: i for i in result.Items}
        self.assertEqual((lines[self.i1].OrderedQuantity, lines[self.i1].ReceivedQuantity, lines[self.i1].MissingQuantity), (10, 6, 4))
        self.assertEqual((lines[self.i2].ReceivedQuantity, lines[self.i2].MissingQuantity), (0, 4))
        self.assertEqual(result.model_dump()["Items"][0]["MissingQuantity"], lines[result.Items[0].PurchaseOrderItemId].MissingQuantity)
        notes = [n for n in self.db.rows(Notification) if n.UserId == self.staff.UserId and n.Title == "Phiếu nhập đã đóng"]
        self.assertEqual(len(notes), 1)

    def test_additional_deliveries_before_closing_are_received_normally(self):
        self.receive(self.po_id, (self.i1, 3))
        self.receive(self.po_id, (self.i1, 3), (self.i2, 2))
        self.close()
        self.assertEqual(len(self.receipts()), 2)
        self.assertEqual((self.v1.StockQuantity, self.v2.StockQuantity), (11, 2))

    def test_closed_order_cannot_receive_cancel_or_close_again(self):
        self.receive(self.po_id, (self.i1, 6))
        self.close()
        before = self.state()
        with self.assertRaises(BusinessRuleError) as ctx:
            self.receive(self.po_id, (self.i1, 1))
        self.assertEqual(ctx.exception.code, "purchase_order_not_receivable")
        with self.assertRaises(BusinessRuleError):
            self.svc.cancel_purchase_order(self.f.actor(self.admin), self.po_id)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.close()
        self.assertEqual(ctx.exception.code, "purchase_order_not_closable")
        self.assertEqual(self.state(), before)

    def test_only_admin_closes_with_a_reason(self):
        self.receive(self.po_id, (self.i1, 6))
        with self.assertRaises(PermissionDeniedError):
            self.close(by=self.staff)
        with self.assertRaises(ValidationError):
            PurchaseOrderClose(Reason="   ")
        with self.assertRaises(BusinessRuleError) as ctx:  # chặn cả khi schema bị bỏ qua
            self.svc.close_purchase_order(self.f.actor(self.admin), self.po_id, SimpleNamespace(Reason="  "))
        self.assertEqual(ctx.exception.code, "close_reason_required")
        self.assertEqual(self.db.get(PurchaseOrder, self.po_id).Status, "Receiving")

    def test_only_partially_received_orders_can_be_closed(self):
        with self.assertRaises(BusinessRuleError) as ctx:  # chưa nhận gì: dùng hủy phiếu
            self.close()
        self.assertEqual(ctx.exception.code, "purchase_order_not_closable")
        pending = self.create_po()
        with self.assertRaises(BusinessRuleError):
            self.close(po_id=pending.PurchaseOrderId)
        self.receive(self.po_id, (self.i1, 10), (self.i2, 4))  # nhận đủ → Completed
        with self.assertRaises(BusinessRuleError) as ctx:
            self.close()
        self.assertEqual(ctx.exception.code, "purchase_order_not_closable")

    def test_receiving_without_shortage_is_defensive(self):
        self.receive(self.po_id, (self.i1, 6))
        for item in self.db.rows(PurchaseOrderItem):  # dữ liệu lệch: Receiving nhưng đã đủ
            item.ReceivedQuantity = item.OrderedQuantity
        with self.assertRaises(BusinessRuleError) as ctx:
            self.close()
        self.assertEqual(ctx.exception.code, "purchase_order_not_closable")


if __name__ == "__main__":
    unittest.main()
