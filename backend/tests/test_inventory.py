"""InventoryService: tồn đầu kỳ (Opening), điều chỉnh kho có lịch sử, giá vốn bình quân, tồn thấp, CRUD biến thể."""

import unittest
import uuid
from decimal import Decimal

from pydantic import ValidationError

from app.models import Notification, ProductSerial, PurchaseOrder, PurchaseOrderItem, StockAdjustment
from app.repositories import StockAdjustmentRepository
from app.schemas import ProductVariantCreate, ProductVariantUpdate, StockAdjustmentCreate, StockOpeningCreate
from app.services import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ProductVariantService,
    weighted_average_cost,
)

from tests.fakes import (
    FakeProductRepo,
    FakeSession,
    FakeUserRepo,
    FakeVariantRepo,
    Factory,
    InMemoryDB,
    fixed_clock,
    inventory_service,
    notification_service,
)


class InventoryTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = inventory_service(self.db, self.session)
        self.admin = self.f.user("Admin")
        self.staff = self.f.user("Staff")
        self.customer = self.f.user("Customer")

    def opening(self, variant, quantity, cost, *, reason="Kiểm kê đầu kỳ", serials=(), user=None):
        data = StockOpeningCreate(Quantity=quantity, UnitCost=Decimal(cost), Reason=reason, SerialNumbers=list(serials))
        return self.svc.declare_opening(self.f.actor(user or self.admin), variant.ProductVariantId, data)

    def adjust(self, variant, change, *, reason="Kiểm kê lệch", user=None):
        return self.svc.adjust_stock(
            self.f.actor(user or self.admin), variant.ProductVariantId, StockAdjustmentCreate(QuantityChange=change, Reason=reason)
        )

    def records(self, variant=None):
        return [a for a in self.db.rows(StockAdjustment) if variant is None or a.ProductVariantId == variant.ProductVariantId]

    def mark_received(self, variant):
        po = self.db.add(PurchaseOrder(PurchaseOrderCode="PN-X", SupplierId=self.f.supplier().SupplierId,
                                       CreatedByUserId=self.admin.UserId, TotalAmount=Decimal("1"), Status="Receiving"))
        self.db.add(PurchaseOrderItem(PurchaseOrderId=po.PurchaseOrderId, ProductVariantId=variant.ProductVariantId,
                                      OrderedQuantity=2, ReceivedQuantity=1, UnitPrice=Decimal("1"), LineTotal=Decimal("2")))


class OpeningTest(InventoryTestBase):
    def test_admin_declares_opening_stock_and_cost_with_history(self):
        legacy = self.f.variant(stock=3, cost="0")
        result = self.opening(legacy, 4, "65000.00", reason="  Kiểm kê 01/10  ")
        self.assertEqual((legacy.StockQuantity, legacy.CostPrice), (4, Decimal("65000.00")))
        self.assertEqual(
            (result.AdjustmentType, result.QuantityBefore, result.QuantityChange, result.QuantityAfter),
            ("Opening", 3, 1, 4),
        )
        self.assertEqual((result.CostPriceBefore, result.CostPriceAfter), (Decimal("0"), Decimal("65000.00")))
        self.assertEqual((result.AdjustedByUserId, result.Reason), (self.admin.UserId, "Kiểm kê 01/10"))
        self.assertEqual(self.session.commits, 1)

    def test_only_admin_can_declare_opening(self):
        variant = self.f.variant(stock=0, cost="0")
        for user in (self.staff, self.customer):
            with self.subTest(role=user.Role), self.assertRaises(PermissionDeniedError):
                self.opening(variant, 5, "1000", user=user)
        with self.assertRaises(PermissionDeniedError):
            self.svc.declare_opening(None, variant.ProductVariantId, StockOpeningCreate(Quantity=1, UnitCost=1, Reason="x"))
        self.assertEqual((variant.StockQuantity, self.records()), (0, []))

    def test_opening_cannot_be_repeated(self):
        variant = self.f.variant(stock=0, cost="0")
        self.opening(variant, 5, "1000")
        with self.assertRaises(ConflictError) as ctx:
            self.opening(variant, 50, "9999")
        self.assertEqual(ctx.exception.code, "opening_already_declared")
        self.assertEqual((variant.StockQuantity, variant.CostPrice, len(self.records())), (5, Decimal("1000.00"), 1))

    def test_opening_rejected_after_first_purchase_receipt(self):
        variant = self.f.variant(stock=2, cost="5000")
        self.mark_received(variant)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.opening(variant, 10, "1")
        self.assertEqual(ctx.exception.code, "opening_after_receipt")
        self.assertEqual((variant.StockQuantity, variant.CostPrice), (2, Decimal("5000")))

    def test_invalid_input_rejected_by_schema_and_service(self):
        for bad in (dict(Quantity=-1, UnitCost=1, Reason="x"), dict(Quantity=1, UnitCost=-1, Reason="x"),
                    dict(Quantity=1, UnitCost="1.005", Reason="x"), dict(Quantity=1, UnitCost=1, Reason="   "),
                    dict(Quantity=1, UnitCost=1, Reason="x", AdjustedByUserId=uuid.uuid4())):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                StockOpeningCreate(**bad)
        variant = self.f.variant(stock=0, cost="0")
        for bad, code in ((dict(Quantity=-1, UnitCost=Decimal("1")), "invalid_opening_quantity"),
                          (dict(Quantity=1, UnitCost=Decimal("1.005")), "invalid_opening_cost"),
                          (dict(Quantity=1, UnitCost=Decimal("1"), Reason=" "), "reason_required")):
            values = {"Reason": "x", "SerialNumbers": [], **bad}
            with self.subTest(code=code), self.assertRaises(BusinessRuleError) as ctx:
                self.svc.declare_opening(self.f.actor(self.admin), variant.ProductVariantId, StockOpeningCreate.model_construct(**values))
            self.assertEqual(ctx.exception.code, code)
        self.assertEqual(self.records(), [])

    def test_serial_tracked_opening_requires_matching_serials_atomically(self):
        phone = self.f.variant(stock=0, cost="0", serial_tracked=True)
        self.db.add(ProductSerial(ProductVariantId=phone.ProductVariantId, SerialNumber="OLD-1", Status="Available"))
        with self.assertRaises(BusinessRuleError) as ctx:
            self.opening(phone, 3, "9000000", serials=["N1"])  # 1 có sẵn + 1 mới ≠ 3
        self.assertEqual(ctx.exception.code, "serial_count_mismatch")
        self.db.add(ProductSerial(ProductVariantId=phone.ProductVariantId, SerialNumber="TAKEN", Status="Sold"))
        with self.assertRaises(ConflictError):
            self.opening(phone, 3, "9000000", serials=["N1", "TAKEN"])
        self.assertEqual((phone.StockQuantity, phone.CostPrice, self.records()), (0, Decimal("0"), []))
        self.assertEqual(sorted(s.SerialNumber for s in self.db.rows(ProductSerial)), ["OLD-1", "TAKEN"])
        self.opening(phone, 3, "9000000", serials=[" N1 ", "N2"])
        self.assertEqual(phone.StockQuantity, 3)
        self.assertEqual(sorted(s.SerialNumber for s in self.db.rows(ProductSerial) if s.Status == "Available"), ["N1", "N2", "OLD-1"])

    def test_serials_not_allowed_for_untracked_variant(self):
        variant = self.f.variant(stock=0, cost="0")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.opening(variant, 1, "1", serials=["X"])
        self.assertEqual(ctx.exception.code, "serials_not_allowed")

    def test_opening_below_threshold_alerts_once(self):
        variant = self.f.variant(stock=10, cost="0", min_stock=5)
        self.opening(variant, 3, "1000")
        alerts = [n for n in self.db.rows(Notification) if n.NotificationType == "LowStock"]
        self.assertEqual({n.UserId for n in alerts}, {self.staff.UserId, self.admin.UserId})


class AdjustmentTest(InventoryTestBase):
    def test_increase_and_decrease_keep_cost_and_record_history(self):
        variant = self.f.variant(stock=10, cost="70000.00")
        up = self.adjust(variant, 5, reason="Tìm thấy hàng")
        down = self.adjust(variant, -3, reason="Hàng hỏng")
        self.assertEqual((variant.StockQuantity, variant.CostPrice), (12, Decimal("70000.00")))
        self.assertEqual((up.AdjustmentType, up.QuantityBefore, up.QuantityChange, up.QuantityAfter), ("Increase", 10, 5, 15))
        self.assertEqual((down.AdjustmentType, down.QuantityBefore, down.QuantityChange, down.QuantityAfter), ("Decrease", 15, -3, 12))
        self.assertTrue(all(r.CostPriceBefore == r.CostPriceAfter == Decimal("70000.00") for r in self.records()))
        self.assertTrue(all(r.AdjustedByUserId == self.admin.UserId for r in self.records()))

    def test_cannot_go_negative_or_adjust_by_zero(self):
        variant = self.f.variant(stock=2)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.adjust(variant, -3)
        self.assertEqual(ctx.exception.code, "insufficient_stock")
        with self.assertRaises(ValidationError):
            StockAdjustmentCreate(QuantityChange=0, Reason="x")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.adjust_stock(self.f.actor(self.admin), variant.ProductVariantId,
                                  StockAdjustmentCreate.model_construct(QuantityChange=0, Reason="x"))
        self.assertEqual(ctx.exception.code, "invalid_adjustment_quantity")
        with self.assertRaises(ValidationError):
            StockAdjustmentCreate(QuantityChange=1, Reason="  ")
        self.assertEqual((variant.StockQuantity, self.records()), (2, []))

    def test_only_admin_can_adjust(self):
        variant = self.f.variant(stock=2)
        for user in (self.staff, self.customer):
            with self.subTest(role=user.Role), self.assertRaises(PermissionDeniedError):
                self.adjust(variant, 1, user=user)
        self.assertEqual((variant.StockQuantity, self.records()), (2, []))

    def test_increase_requires_cost_basis(self):
        variant = self.f.variant(stock=0, cost="0")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.adjust(variant, 1)
        self.assertEqual(ctx.exception.code, "opening_required")
        self.opening(variant, 0, "0", reason="Khai báo giá vốn 0 (hàng tặng)")
        self.adjust(variant, 1)  # Opening (kể cả giá 0) xác lập giá vốn hợp lệ
        self.assertEqual(variant.StockQuantity, 1)

    def test_history_is_append_only(self):
        variant = self.f.variant(stock=2)
        record = self.db.get(StockAdjustment, self.adjust(variant, 1).StockAdjustmentId)
        with self.assertRaises(PermissionError):
            self.svc.adjustments.delete(record)
        with self.assertRaises(PermissionError):
            self.svc.adjustments.update(record, {"QuantityChange": 99})
        real_repo = StockAdjustmentRepository(session=None)  # không truy cập database: chặn trước khi chạm Session
        with self.assertRaises(PermissionError):
            real_repo.delete(record)
        with self.assertRaises(PermissionError):
            real_repo.update(record, {"Reason": "sửa"})
        self.assertEqual(len(self.records()), 1)

    def test_list_adjustments_admin_only(self):
        variant = self.f.variant(stock=2)
        self.adjust(variant, 1)
        self.assertEqual(self.svc.list_adjustments(self.f.actor(self.admin), variant_id=variant.ProductVariantId).Total, 1)
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_adjustments(self.f.actor(self.staff))
        with self.assertRaises(BusinessRuleError):
            self.svc.list_adjustments(self.f.actor(self.admin), adjustment_type="Delete")

    def test_low_stock_list_for_staff(self):
        low = self.f.variant(stock=2, min_stock=5)
        self.f.variant(stock=10, min_stock=5)
        self.f.variant(stock=0, min_stock=0)  # ngưỡng 0: không cảnh báo
        page = self.svc.list_low_stock(self.f.actor(self.staff))
        self.assertEqual([v.ProductVariantId for v in page.Items], [low.ProductVariantId])
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_low_stock(self.f.actor(self.customer))
        self.assertEqual(self.db.rows(Notification), [])  # đọc danh sách không tạo thông báo


class SerialAdjustmentTest(InventoryTestBase):
    """Điều chỉnh kho thủ công cho biến thể IsSerialTracked (Admin chọn đúng serial)."""

    def setUp(self) -> None:
        super().setUp()
        self.phone = self.f.variant(stock=2, cost="9000000.00", serial_tracked=True)
        self.other = self.f.variant(stock=1, cost="1.00", serial_tracked=True)
        for n, variant, status in (("P-1", self.phone, "Available"), ("P-2", self.phone, "Available"),
                                   ("P-SOLD", self.phone, "Sold"), ("O-1", self.other, "Available")):
            self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId, SerialNumber=n, Status=status))

    def serial_numbers(self, variant):
        return sorted(s.SerialNumber for s in self.db.rows(ProductSerial) if s.ProductVariantId == variant.ProductVariantId)

    def adjust_serials(self, variant, change, serials, user=None):
        data = StockAdjustmentCreate(QuantityChange=change, Reason="Kiểm kê", SerialNumbers=serials)
        return self.svc.adjust_stock(self.f.actor(user or self.admin), variant.ProductVariantId, data)

    def assert_unchanged(self):
        self.assertEqual((self.phone.StockQuantity, self.records(self.phone)), (2, []))
        self.assertEqual(self.serial_numbers(self.phone), ["P-1", "P-2", "P-SOLD"])
        self.assertTrue(all(s.Status in ("Available", "Sold") for s in self.db.rows(ProductSerial)))

    def test_increase_registers_new_serials_atomically_with_history(self):
        record = self.adjust_serials(self.phone, 2, ["  P-3 ", "p-3"])  # trim; phân biệt hoa thường
        self.assertEqual((self.phone.StockQuantity, record.AdjustmentType, record.QuantityChange), (4, "Increase", 2))
        self.assertEqual(self.serial_numbers(self.phone), ["P-1", "P-2", "P-3", "P-SOLD", "p-3"])
        added = [s for s in self.db.rows(ProductSerial) if s.SerialNumber in ("P-3", "p-3")]
        self.assertTrue(all(s.Status == "Available" and s.OrderItemId is None for s in added))
        self.assertEqual(self.phone.CostPrice, Decimal("9000000.00"))

    def test_serial_count_must_match_quantity(self):
        for change, serials in ((2, ["P-3"]), (1, ["P-3", "P-4"]), (-1, []), (-1, ["P-1", "P-2"])):
            with self.subTest(change=change, serials=serials), self.assertRaises(BusinessRuleError) as ctx:
                self.adjust_serials(self.phone, change, serials)
            self.assertEqual(ctx.exception.code, "serial_count_mismatch")
        self.assert_unchanged()

    def test_increase_rejects_duplicate_or_existing_serials(self):
        with self.assertRaises(BusinessRuleError) as ctx:
            self.adjust_serials(self.phone, 2, ["N-1", " N-1"])
        self.assertEqual(ctx.exception.code, "duplicate_serial_in_request")
        with self.assertRaises(ConflictError) as ctx:
            self.adjust_serials(self.phone, 2, ["N-1", "O-1"])  # O-1 đã tồn tại (của biến thể khác)
        self.assertEqual(ctx.exception.code, "serial_exists")
        self.assert_unchanged()

    def test_decrease_validates_selected_serials(self):
        cases = [
            (["NOPE"], NotFoundError, "serial_not_found"),
            (["O-1"], BusinessRuleError, "serial_variant_mismatch"),  # thuộc biến thể khác
            (["P-SOLD"], BusinessRuleError, "serial_not_available"),  # không còn tồn khả dụng
            (["p-1"], NotFoundError, "serial_not_found"),  # phân biệt hoa thường
        ]
        for serials, error, code in cases:
            with self.subTest(serials=serials), self.assertRaises(error) as ctx:
                self.adjust_serials(self.phone, -1, serials)
            self.assertEqual(ctx.exception.code, code)
        self.assert_unchanged()

    def test_serial_held_by_an_order_cannot_be_removed(self):
        serial = [s for s in self.db.rows(ProductSerial) if s.SerialNumber == "P-2"][0]
        for status in ("Reserved", "Available"):  # "Available" nhưng vẫn gắn dòng đơn: dữ liệu không nhất quán
            with self.subTest(status=status):
                serial.Status, serial.OrderItemId = status, uuid.uuid4()
                with self.assertRaises(BusinessRuleError) as ctx:
                    self.adjust_serials(self.phone, -1, ["P-2"])
                self.assertEqual(ctx.exception.code, "serial_not_available")

    def test_valid_decrease_writes_off_selected_serials(self):
        # Quyết định đợt 5.1: serial bị loại khỏi kho → WrittenOff + liên kết Out với phiếu điều chỉnh giảm.
        record = self.adjust_serials(self.phone, -1, ["P-1"])
        self.assertEqual((self.phone.StockQuantity, record.AdjustmentType, record.QuantityChange), (1, "Decrease", -1))
        statuses = {s.SerialNumber: s.Status for s in self.db.rows(ProductSerial) if s.ProductVariantId == self.phone.ProductVariantId}
        self.assertEqual(statuses, {"P-1": "WrittenOff", "P-2": "Available", "P-SOLD": "Sold"})
        locked = [key for name, key in self.db.locks if name in ("ProductVariant", "ProductSerial")]
        self.assertEqual(locked[0], self.phone.ProductVariantId)  # khóa biến thể trước serial

    def test_failure_while_creating_serials_rolls_back(self):
        original = self.svc.serials.create
        created = []

        def fail_on_second(values):
            created.append(values)
            if len(created) == 2:
                raise RuntimeError("ghi serial lỗi")
            return original(values)

        self.svc.serials.create = fail_on_second
        rollbacks = self.session.rollbacks
        with self.assertRaises(RuntimeError):
            self.adjust_serials(self.phone, 2, ["N-1", "N-2"])
        self.assertEqual(self.session.rollbacks, rollbacks + 1)
        self.assert_unchanged()

    def test_untracked_variant_rejects_serials_and_staff_cannot_adjust(self):
        plain = self.f.variant(stock=3)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.adjust_serials(plain, 1, ["X-1"])
        self.assertEqual(ctx.exception.code, "serials_not_allowed")
        with self.assertRaises(PermissionDeniedError):
            self.adjust_serials(self.phone, 1, ["P-9"], user=self.staff)
        self.assertEqual((plain.StockQuantity, self.serial_numbers(self.phone)), (3, ["P-1", "P-2", "P-SOLD"]))


class WeightedAverageCostTest(unittest.TestCase):
    def test_formula_and_rounding(self):
        cases = [
            ((0, Decimal("0"), 10, Decimal("12345.67")), Decimal("12345.67")),
            ((0, Decimal("99999.00"), 1, Decimal("10.00")), Decimal("10.00")),  # tồn 0: giá vốn cũ không ảnh hưởng
            ((5, Decimal("70000.00"), 6, Decimal("50000.00")), Decimal("59090.91")),
            ((1, Decimal("0.01"), 1, Decimal("0.00")), Decimal("0.01")),  # 0.005 → làm tròn lên (HALF_UP)
            ((2, Decimal("10.00"), 1, Decimal("10.01")), Decimal("10.00")),  # 10.00333…
            ((10**9, Decimal("9999999999.99"), 10**9, Decimal("0.01")), Decimal("5000000000.00")),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                result = weighted_average_cost(*args)
                self.assertEqual(result, expected)
                self.assertIsInstance(result, Decimal)
                self.assertEqual(result.as_tuple().exponent, -2)

    def test_invalid_inputs(self):
        for args in ((-1, Decimal("1"), 1, Decimal("1")), (1, Decimal("1"), 0, Decimal("1")),
                     (1, Decimal("-1"), 1, Decimal("1")), (1, Decimal("1"), 1, Decimal("-0.01"))):
            with self.subTest(args=args), self.assertRaises(BusinessRuleError):
                weighted_average_cost(*args)


class VariantCrudInventoryGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.svc = ProductVariantService(self.session, clock=fixed_clock)
        self.svc.variants = FakeVariantRepo(self.db)
        self.svc.products = FakeProductRepo(self.db)
        self.svc.users = FakeUserRepo(self.db)
        self.svc.notifications = notification_service(self.db, self.session)
        self.admin = self.f.user("Admin")
        self.variant = self.f.variant(stock=5, cost="70000.00")

    def test_schema_forbids_stock_and_cost(self):
        base = {"ProductId": self.variant.ProductId, "Sku": "NEW", "VariantName": "V", "Price": "1"}
        for extra in ({"StockQuantity": 99}, {"CostPrice": "1"}):
            with self.subTest(extra=extra):
                with self.assertRaises(ValidationError):
                    ProductVariantCreate(**base, **extra)
                with self.assertRaises(ValidationError):
                    ProductVariantUpdate(**extra)

    def test_service_rejects_stock_and_cost_even_if_schema_is_bypassed(self):
        """Router truyền nhầm object khác (dict/schema khác) có StockQuantity/CostPrice: Service vẫn chặn."""
        from types import SimpleNamespace

        def payload(values):
            return SimpleNamespace(model_dump=lambda **kwargs: dict(values))

        for values in ({"StockQuantity": 99}, {"CostPrice": Decimal("1")}):
            with self.subTest(values=values):
                with self.assertRaises(BusinessRuleError) as ctx:
                    self.svc.update_variant(self.f.actor(self.admin), self.variant.ProductVariantId, payload(values))
                self.assertEqual(ctx.exception.code, "inventory_field_not_editable")
        create_values = {"ProductId": self.variant.ProductId, "Sku": "NEW", "VariantName": "V",
                         "Price": Decimal("1"), "StockQuantity": 99}
        with self.assertRaises(BusinessRuleError):
            self.svc.create_variant(self.f.actor(self.admin), payload(create_values))
        self.assertEqual((self.variant.StockQuantity, self.variant.CostPrice), (5, Decimal("70000.00")))
        # model_construct (extra="forbid") tự bỏ trường lạ: không thể bơm StockQuantity qua Schema.
        self.assertNotIn("StockQuantity", ProductVariantUpdate.model_construct(StockQuantity=99).model_dump(exclude_unset=True))

    def test_new_variant_starts_with_zero_stock_and_cost(self):
        created = self.svc.create_variant(self.f.actor(self.admin), ProductVariantCreate(
            ProductId=self.variant.ProductId, Sku="NEW", VariantName="V", Price="1", IsSerialTracked=True))
        self.assertEqual((created.StockQuantity, created.CostPrice, created.IsSerialTracked), (0, Decimal("0"), True))

    def test_only_admin_edits_variants(self):
        with self.assertRaises(PermissionDeniedError):
            self.svc.update_variant(self.f.actor(self.f.user("Staff")), self.variant.ProductVariantId,
                                    ProductVariantUpdate(Price="2"))
        self.assertEqual(self.svc.get_variant(self.f.actor(self.f.user("Staff")), self.variant.ProductVariantId).Sku,
                         self.variant.Sku)

    def test_serial_tracking_toggle_requires_zero_stock(self):
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.update_variant(self.f.actor(self.admin), self.variant.ProductVariantId,
                                    ProductVariantUpdate(IsSerialTracked=True))
        self.assertEqual(ctx.exception.code, "serial_tracking_change_requires_zero_stock")
        empty = self.f.variant(stock=0)
        updated = self.svc.update_variant(self.f.actor(self.admin), empty.ProductVariantId, ProductVariantUpdate(IsSerialTracked=True))
        self.assertTrue(updated.IsSerialTracked)


if __name__ == "__main__":
    unittest.main()
