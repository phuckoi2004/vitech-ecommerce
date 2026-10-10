"""PurchaseOrderService + nhận hàng qua InventoryService: quyền lập/duyệt/từ chối, nhận hàng, giá vốn bình quân, serial."""

import unittest
import uuid
from decimal import Decimal

from pydantic import ValidationError

from app.models import Notification, ProductSerial, PurchaseOrder, PurchaseOrderItem, StockAdjustment
from app.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderDecision,
    PurchaseOrderItemCreate,
    PurchaseOrderItemUpdate,
    PurchaseOrderReceive,
    SupplierCreate,
)
from app.services import Actor, BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError, SupplierService

from tests.fakes import (
    FakePurchaseOrderRepo,
    FakeSession,
    FakeSupplierRepo,
    Factory,
    InMemoryDB,
    fixed_clock,
    purchase_order_service,
)


class PurchaseOrderTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = purchase_order_service(self.db, self.session)
        self.staff = self.f.user("Staff")
        self.admin = self.f.user("Admin")
        self.admin2 = self.f.user("Admin")
        self.customer = self.f.user("Customer")
        self.supplier = self.f.supplier()
        self.v1 = self.f.variant(stock=5, cost="70000.00")
        self.v2 = self.f.variant(stock=0, cost="0")

    def create_po(self, actor_user=None, lines=None):
        lines = lines or [(self.v1, 10, "50000.00"), (self.v2, 4, "120000.50")]
        data = PurchaseOrderCreate(
            SupplierId=self.supplier.SupplierId,
            Items=[
                PurchaseOrderItemCreate(ProductVariantId=v.ProductVariantId, OrderedQuantity=q, UnitPrice=Decimal(p))
                for v, q, p in lines
            ],
        )
        return self.svc.create_purchase_order(self.f.actor(actor_user or self.staff), data)

    def approve(self, po_id, by=None):
        return self.svc.decide_purchase_order(
            self.f.actor(by or self.admin), po_id, PurchaseOrderDecision(Status="Approved")
        )

    def reject(self, po_id, reason="Giá cao", by=None):
        return self.svc.decide_purchase_order(
            self.f.actor(by or self.admin), po_id, PurchaseOrderDecision(Status="Rejected", RejectReason=reason)
        )

    def item_ids(self, po_id):
        return {i.ProductVariantId: i.PurchaseOrderItemId for i in self.db.rows(PurchaseOrderItem) if i.PurchaseOrderId == po_id}

    def receive(self, po_id, *lines, by=None):
        items = []
        for line in lines:
            item_id, quantity, *serials = line
            items.append({"PurchaseOrderItemId": item_id, "Quantity": quantity, "SerialNumbers": serials[0] if serials else []})
        return self.svc.receive_items(self.f.actor(by or self.staff), po_id, PurchaseOrderReceive(Items=items))

    def staff_po_approved(self, lines=None):
        po = self.create_po(lines=lines)
        self.approve(po.PurchaseOrderId)
        return po, self.item_ids(po.PurchaseOrderId)


class CreateAndDecideTest(PurchaseOrderTestBase):
    def test_staff_creates_pending_po_with_server_computed_totals(self):
        po = self.create_po()
        self.assertEqual((po.Status, po.CreatedByUserId), ("Pending", self.staff.UserId))
        self.assertEqual(po.TotalAmount, Decimal("980002.00"))  # 10×50000 + 4×120000.50
        self.assertEqual(sorted(i.LineTotal for i in po.Items), [Decimal("480002.00"), Decimal("500000.00")])
        self.assertTrue(all(i.ReceivedQuantity == 0 for i in po.Items))
        self.assertEqual((self.v1.StockQuantity, self.v2.StockQuantity), (5, 0))
        self.assertEqual(len(self.f.notifications_for(self.admin)), 1)
        self.assertEqual(len(self.f.notifications_for(self.admin2)), 1)

    def test_admin_created_po_needs_no_approval(self):
        po = self.create_po(self.admin)
        self.assertEqual((po.Status, po.CreatedByUserId), ("Approved", self.admin.UserId))
        self.assertEqual((po.DecidedByUserId, po.DecidedAt), (None, None))
        self.assertEqual(self.db.rows(Notification), [])  # không có bước chờ duyệt
        ids = self.item_ids(po.PurchaseOrderId)
        self.assertEqual(self.receive(po.PurchaseOrderId, (ids[self.v1.ProductVariantId], 2)).Status, "Receiving")
        with self.assertRaises(BusinessRuleError):  # không có gì để duyệt
            self.approve(po.PurchaseOrderId, by=self.admin2)

    def test_customer_cannot_create_or_read_po(self):
        with self.assertRaises(PermissionDeniedError):
            self.create_po(self.customer)
        self.assertEqual(self.db.rows(PurchaseOrder), [])
        po = self.create_po()
        with self.assertRaises(PermissionDeniedError):
            self.svc.get_purchase_order(self.f.actor(self.customer), po.PurchaseOrderId)
        with self.assertRaises(PermissionDeniedError):
            self.svc.get_purchase_order(None, po.PurchaseOrderId)

    def test_raw_user_id_cannot_be_used_as_actor(self):
        data = PurchaseOrderCreate(
            SupplierId=self.supplier.SupplierId,
            Items=[PurchaseOrderItemCreate(ProductVariantId=self.v1.ProductVariantId, OrderedQuantity=1, UnitPrice=1)],
        )
        with self.assertRaises(TypeError):
            self.svc.create_purchase_order(self.admin.UserId, data)

    def test_service_rejects_invalid_lines_even_if_schema_is_bypassed(self):
        bad = [
            PurchaseOrderItemCreate.model_construct(ProductVariantId=self.v1.ProductVariantId, OrderedQuantity=0, UnitPrice=Decimal("1")),
            PurchaseOrderItemCreate.model_construct(ProductVariantId=self.v1.ProductVariantId, OrderedQuantity=1, UnitPrice=Decimal("-1")),
        ]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(BusinessRuleError):
                self.svc.create_purchase_order(
                    self.f.actor(self.staff),
                    PurchaseOrderCreate.model_construct(SupplierId=self.supplier.SupplierId, Note=None, Items=[item]),
                )
        empty = PurchaseOrderCreate.model_construct(SupplierId=self.supplier.SupplierId, Note=None, Items=[])
        with self.assertRaises(BusinessRuleError):
            self.svc.create_purchase_order(self.f.actor(self.staff), empty)
        self.assertEqual(self.db.rows(PurchaseOrder), [])

    def test_duplicate_variant_and_inactive_supplier_rejected(self):
        with self.assertRaises(BusinessRuleError):
            self.create_po(lines=[(self.v1, 1, "1"), (self.v1, 2, "1")])
        self.supplier.IsActive = False
        with self.assertRaises(NotFoundError):
            self.create_po()

    def test_only_admin_can_decide(self):
        po = self.create_po()
        other_staff = self.f.user("Staff")
        for decision in (PurchaseOrderDecision(Status="Approved"), PurchaseOrderDecision(Status="Rejected", RejectReason="x")):
            with self.subTest(status=decision.Status), self.assertRaises(PermissionDeniedError) as ctx:
                self.svc.decide_purchase_order(self.f.actor(other_staff), po.PurchaseOrderId, decision)
            self.assertEqual(ctx.exception.code, "permission_denied")
        self.assertEqual(self.db.get(PurchaseOrder, po.PurchaseOrderId).Status, "Pending")

    def test_admin_approves_staff_po(self):
        po = self.create_po()
        decided = self.approve(po.PurchaseOrderId)
        self.assertEqual((decided.Status, decided.DecidedByUserId), ("Approved", self.admin.UserId))
        self.assertIsNotNone(decided.DecidedAt)
        self.assertEqual(self.v1.StockQuantity, 5)  # duyệt không tăng tồn kho
        self.assertEqual(len(self.f.notifications_for(self.staff)), 1)

    def test_creator_cannot_decide_own_po(self):
        # Người lập phiếu khi còn là Staff, sau đó được nâng thành Admin: vẫn không được tự duyệt/từ chối.
        po = self.create_po(self.staff)
        promoted = Actor(self.staff.UserId, "Admin")
        for decision in (PurchaseOrderDecision(Status="Approved"), PurchaseOrderDecision(Status="Rejected", RejectReason="x")):
            with self.subTest(status=decision.Status), self.assertRaises(PermissionDeniedError) as ctx:
                self.svc.decide_purchase_order(promoted, po.PurchaseOrderId, decision)
            self.assertEqual(ctx.exception.code, "self_approval_forbidden")
        stored = self.db.get(PurchaseOrder, po.PurchaseOrderId)
        self.assertEqual((stored.Status, stored.DecidedByUserId), ("Pending", None))

    def test_reject_requires_non_blank_reason(self):
        po = self.create_po()
        for reason in (None, "", "   \t "):
            with self.subTest(reason=reason), self.assertRaises(ValidationError):
                PurchaseOrderDecision(Status="Rejected", RejectReason=reason)
            # Bỏ qua Schema: Service vẫn chặn.
            with self.subTest(reason=reason, bypass=True), self.assertRaises(BusinessRuleError) as ctx:
                self.svc.decide_purchase_order(
                    self.f.actor(self.admin), po.PurchaseOrderId,
                    PurchaseOrderDecision.model_construct(Status="Rejected", RejectReason=reason),
                )
            self.assertEqual(ctx.exception.code, "reject_reason_required")
        self.assertEqual(self.db.get(PurchaseOrder, po.PurchaseOrderId).Status, "Pending")
        with self.assertRaises(ValidationError):
            PurchaseOrderDecision(Status="Approved", RejectReason="không cần")

    def test_reject_trims_reason_then_edit_and_resubmit(self):
        po = self.create_po()
        rejected = self.reject(po.PurchaseOrderId, reason="  Giá cao  ")
        self.assertEqual((rejected.Status, rejected.RejectReason), ("Rejected", "Giá cao"))
        item_id = self.item_ids(po.PurchaseOrderId)[self.v1.ProductVariantId]
        edited = self.svc.update_item(
            self.f.actor(self.staff), po.PurchaseOrderId, item_id, PurchaseOrderItemUpdate(UnitPrice=Decimal("40000"))
        )
        self.assertEqual(edited.TotalAmount, Decimal("880002.00"))
        resubmitted = self.svc.resubmit_purchase_order(self.f.actor(self.staff), po.PurchaseOrderId)
        self.assertEqual((resubmitted.Status, resubmitted.RejectReason, resubmitted.DecidedByUserId), ("Pending", None, None))

    def test_decide_twice_is_rejected(self):
        po = self.create_po()
        self.approve(po.PurchaseOrderId)
        with self.assertRaises(BusinessRuleError):
            self.reject(po.PurchaseOrderId, by=self.admin2)

    def test_received_quantity_not_editable_via_update(self):
        po = self.create_po()
        item_id = self.item_ids(po.PurchaseOrderId)[self.v1.ProductVariantId]
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.update_item(self.f.actor(self.staff), po.PurchaseOrderId, item_id, PurchaseOrderItemUpdate(ReceivedQuantity=3))
        self.assertEqual(ctx.exception.code, "received_quantity_not_editable")


class ReceiveTest(PurchaseOrderTestBase):
    def test_unapproved_staff_po_cannot_be_received(self):
        po = self.create_po()
        item_id = self.item_ids(po.PurchaseOrderId)[self.v1.ProductVariantId]
        for status in ("Pending", "Rejected", "Cancelled", "Completed"):
            with self.subTest(status=status):
                self.db.get(PurchaseOrder, po.PurchaseOrderId).Status = status
                with self.assertRaises(BusinessRuleError) as ctx:
                    self.receive(po.PurchaseOrderId, (item_id, 1))
                self.assertEqual(ctx.exception.code, "purchase_order_not_receivable")
        self.assertEqual(self.v1.StockQuantity, 5)

    def test_partial_then_full_receipt_with_weighted_average_cost(self):
        po, ids = self.staff_po_approved()
        partial = self.receive(po.PurchaseOrderId, (ids[self.v1.ProductVariantId], 4), (ids[self.v1.ProductVariantId], 2))
        self.assertEqual(partial.Status, "Receiving")
        self.assertEqual(self.v1.StockQuantity, 11)  # 5 + (4 + 2): cộng dồn dòng trùng
        # (5 × 70000 + 6 × 50000) / 11 = 59090.909… → 59090.91
        self.assertEqual(self.v1.CostPrice, Decimal("59090.91"))
        done = self.receive(po.PurchaseOrderId, (ids[self.v1.ProductVariantId], 4), (ids[self.v2.ProductVariantId], 4))
        self.assertEqual(done.Status, "Completed")
        self.assertEqual((self.v1.StockQuantity, self.v2.StockQuantity), (15, 4))
        # (11 × 59090.91 + 4 × 50000) / 15 = 56666.6673… → 56666.67
        self.assertEqual(self.v1.CostPrice, Decimal("56666.67"))
        self.assertEqual(self.v2.CostPrice, Decimal("120000.50"))  # tồn trước = 0 → đơn giá nhập
        with self.assertRaises(BusinessRuleError):
            self.receive(po.PurchaseOrderId, (ids[self.v1.ProductVariantId], 1))

    def test_sequential_receipts_from_two_pos_use_refreshed_stock_and_cost(self):
        po_a, ids_a = self.staff_po_approved(lines=[(self.v1, 5, "80000.00")])
        po_b = self.create_po(self.admin, lines=[(self.v1, 5, "100000.00")])
        ids_b = self.item_ids(po_b.PurchaseOrderId)
        self.receive(po_a.PurchaseOrderId, (ids_a[self.v1.ProductVariantId], 5))
        self.assertEqual(self.v1.CostPrice, Decimal("75000.00"))  # (5×70000 + 5×80000)/10
        self.receive(po_b.PurchaseOrderId, (ids_b[self.v1.ProductVariantId], 5))
        self.assertEqual((self.v1.StockQuantity, self.v1.CostPrice), (15, Decimal("83333.33")))  # (10×75000 + 5×100000)/15
        locked_variants = [key for name, key in self.db.locks if name == "ProductVariant"]
        self.assertEqual(locked_variants.count(self.v1.ProductVariantId), 2)  # khóa lại trước mỗi lần tính

    def test_over_receipt_rejected_without_any_change(self):
        po, ids = self.staff_po_approved()
        with self.assertRaises(BusinessRuleError) as ctx:
            self.receive(po.PurchaseOrderId, (ids[self.v2.ProductVariantId], 1), (ids[self.v1.ProductVariantId], 11))
        self.assertEqual(ctx.exception.code, "receive_exceeds_ordered")
        self.assertEqual((self.v1.StockQuantity, self.v2.StockQuantity, self.v1.CostPrice), (5, 0, Decimal("70000.00")))
        self.assertTrue(all(i.ReceivedQuantity == 0 for i in self.db.rows(PurchaseOrderItem)))
        self.assertEqual(self.db.get(PurchaseOrder, po.PurchaseOrderId).Status, "Approved")

    def test_receipt_beyond_remaining_quantity_after_partial(self):
        po, ids = self.staff_po_approved()
        self.receive(po.PurchaseOrderId, (ids[self.v1.ProductVariantId], 8))
        with self.assertRaises(BusinessRuleError):
            self.receive(po.PurchaseOrderId, (ids[self.v1.ProductVariantId], 3))  # còn lại 2
        self.assertEqual(self.v1.StockQuantity, 13)

    def test_failure_mid_receipt_rolls_back_everything(self):
        po, ids = self.staff_po_approved()
        self.db.remove(self.v2)  # biến thể biến mất → InventoryService lỗi sau khi đã cộng ReceivedQuantity
        rollbacks = self.session.rollbacks
        with self.assertRaises(NotFoundError):
            self.receive(po.PurchaseOrderId, (ids[self.v1.ProductVariantId], 3), (ids[self.v2.ProductVariantId], 1))
        self.assertEqual(self.session.rollbacks, rollbacks + 1)
        self.assertEqual((self.v1.StockQuantity, self.v1.CostPrice), (5, Decimal("70000.00")))
        self.assertTrue(all(i.ReceivedQuantity == 0 for i in self.db.rows(PurchaseOrderItem)))
        self.assertEqual(self.db.get(PurchaseOrder, po.PurchaseOrderId).Status, "Approved")

    def test_unknown_line_and_customer_actor_rejected(self):
        po, ids = self.staff_po_approved()
        with self.assertRaises(NotFoundError):
            self.receive(po.PurchaseOrderId, (uuid.uuid4(), 1))
        with self.assertRaises(PermissionDeniedError):
            self.receive(po.PurchaseOrderId, (ids[self.v1.ProductVariantId], 1), by=self.customer)
        self.assertEqual(self.v1.StockQuantity, 5)

    def test_empty_receipt_rejected_even_if_schema_is_bypassed(self):
        po, _ = self.staff_po_approved()
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.receive_items(self.f.actor(self.staff), po.PurchaseOrderId, PurchaseOrderReceive.model_construct(Items=[]))
        self.assertEqual(ctx.exception.code, "receive_items_empty")

    def test_cancel_only_before_any_receipt(self):
        po, ids = self.staff_po_approved()
        self.receive(po.PurchaseOrderId, (ids[self.v1.ProductVariantId], 1))
        with self.assertRaises(BusinessRuleError):
            self.svc.cancel_purchase_order(self.f.actor(self.staff), po.PurchaseOrderId)
        other = self.create_po()
        self.assertEqual(self.svc.cancel_purchase_order(self.f.actor(self.staff), other.PurchaseOrderId).Status, "Cancelled")
        with self.assertRaises(BusinessRuleError):
            self.svc.cancel_purchase_order(self.f.actor(self.staff), other.PurchaseOrderId)


class ReceiveRequiresOpeningCostTest(PurchaseOrderTestBase):
    def test_stock_without_cost_basis_blocks_receipt_until_opening(self):
        legacy = self.f.variant(stock=3, cost="0")  # tồn cũ chưa có giá vốn
        po = self.create_po(self.admin, lines=[(legacy, 2, "90000.00")])
        item_id = self.item_ids(po.PurchaseOrderId)[legacy.ProductVariantId]
        with self.assertRaises(BusinessRuleError) as ctx:
            self.receive(po.PurchaseOrderId, (item_id, 2))
        self.assertEqual(ctx.exception.code, "opening_required")
        self.assertEqual((legacy.StockQuantity, legacy.CostPrice), (3, Decimal("0")))
        # Sau khi Admin khai báo tồn đầu kỳ (giá vốn 0 hợp lệ vì đã được khai báo): nhận được, tính bình quân.
        self.db.add(StockAdjustment(ProductVariantId=legacy.ProductVariantId, AdjustedByUserId=self.admin.UserId,
                                    AdjustmentType="Opening", QuantityBefore=3, QuantityChange=0, QuantityAfter=3,
                                    CostPriceBefore=Decimal("0"), CostPriceAfter=Decimal("60000.00"), Reason="Kiểm kê"))
        legacy.CostPrice = Decimal("60000.00")
        self.receive(po.PurchaseOrderId, (item_id, 2))
        self.assertEqual((legacy.StockQuantity, legacy.CostPrice), (5, Decimal("72000.00")))  # (3×60000 + 2×90000)/5


class SerialReceiptTest(PurchaseOrderTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.phone = self.f.variant(stock=0, cost="0", serial_tracked=True)
        self.po = self.create_po(self.admin, lines=[(self.phone, 3, "10000000.00"), (self.v1, 2, "1.00")])
        ids = self.item_ids(self.po.PurchaseOrderId)
        self.phone_item, self.plain_item = ids[self.phone.ProductVariantId], ids[self.v1.ProductVariantId]

    def serials(self):
        return sorted(s.SerialNumber for s in self.db.rows(ProductSerial))

    def assert_nothing_received(self):
        self.assertEqual(self.serials(), [])
        self.assertEqual((self.phone.StockQuantity, self.v1.StockQuantity), (0, 5))
        self.assertTrue(all(i.ReceivedQuantity == 0 for i in self.db.rows(PurchaseOrderItem)))

    def test_serials_recorded_trimmed_and_case_sensitive(self):
        self.receive(self.po.PurchaseOrderId, (self.phone_item, 3, ["  IMEI-a ", "IMEI-A", "imei-a"]))
        self.assertEqual(self.serials(), ["IMEI-A", "IMEI-a", "imei-a"])
        self.assertTrue(all(s.Status == "Available" and s.ProductVariantId == self.phone.ProductVariantId
                            for s in self.db.rows(ProductSerial)))
        self.assertEqual(self.phone.StockQuantity, 3)

    def test_serial_count_must_match_quantity(self):
        for serials in (["A", "B"], ["A", "B", "C", "D"], []):
            with self.subTest(serials=serials), self.assertRaises(BusinessRuleError) as ctx:
                self.receive(self.po.PurchaseOrderId, (self.phone_item, 3, serials))
            self.assertEqual(ctx.exception.code, "serial_count_mismatch")
        self.assert_nothing_received()

    def test_serials_rejected_for_untracked_variant(self):
        with self.assertRaises(BusinessRuleError) as ctx:
            self.receive(self.po.PurchaseOrderId, (self.plain_item, 1, ["X1"]))
        self.assertEqual(ctx.exception.code, "serials_not_allowed")
        self.assert_nothing_received()

    def test_duplicate_serial_in_request_or_database_is_rejected_atomically(self):
        with self.assertRaises(BusinessRuleError) as ctx:
            self.receive(self.po.PurchaseOrderId, (self.phone_item, 2, ["S1", " S1"]), (self.plain_item, 2))
        self.assertEqual(ctx.exception.code, "duplicate_serial_in_request")
        self.assert_nothing_received()
        self.db.add(ProductSerial(ProductVariantId=self.phone.ProductVariantId, SerialNumber="S9", Status="Sold"))
        with self.assertRaises(ConflictError) as ctx:
            self.receive(self.po.PurchaseOrderId, (self.phone_item, 2, ["S8", "S9"]), (self.plain_item, 2))
        self.assertEqual(ctx.exception.code, "serial_exists")
        self.assertEqual(self.serials(), ["S9"])
        self.assertEqual((self.phone.StockQuantity, self.v1.StockQuantity), (0, 5))

    def test_blank_or_too_long_serial_rejected(self):
        for bad in (["   "], ["x" * 101]):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                PurchaseOrderReceive(Items=[{"PurchaseOrderItemId": self.phone_item, "Quantity": 1, "SerialNumbers": bad}])


class SupplierPermissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = SupplierService(self.session, clock=fixed_clock)
        self.svc.suppliers = FakeSupplierRepo(self.db)
        self.svc.purchase_orders = FakePurchaseOrderRepo(self.db)

    def test_admin_manages_staff_reads(self):
        data = SupplierCreate(SupplierCode="NCC-X", Name="X", PhoneNumber="1", Address="A")
        with self.assertRaises(PermissionDeniedError):
            self.svc.create_supplier(self.f.actor(self.f.user("Staff")), data)
        self.svc.suppliers.exists_by_code = lambda code, exclude_id=None: False
        created = self.svc.create_supplier(self.f.actor(self.f.user("Admin")), data)
        self.assertEqual(self.svc.get_supplier(self.f.actor(self.f.user("Staff")), created.SupplierId).SupplierCode, "NCC-X")
        with self.assertRaises(PermissionDeniedError):
            self.svc.get_supplier(self.f.actor(self.f.user("Customer")), created.SupplierId)


if __name__ == "__main__":
    unittest.main()
