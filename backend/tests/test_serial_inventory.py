"""Serial/IMEI và kho (đợt 5.1 nhóm B): không CRUD tạo/xóa serial, chỉ sửa số khi Available,
WrittenOff + StockAdjustmentSerials (In/Out), nguyên tử và chống điều chỉnh lặp.

Fake trong bộ nhớ: khóa dòng/UNIQUE được giả lập; không chứng minh concurrency thật của PostgreSQL.
"""

import unittest
import uuid
from types import SimpleNamespace

from pydantic import ValidationError

from app.models import ProductSerial, StockAdjustment, StockAdjustmentSerial
from app.schemas import ProductSerialCreate, ProductSerialUpdate, StockAdjustmentCreate, StockOpeningCreate
from app.services import BusinessRuleError, ConflictError, PermissionDeniedError, ProductSerialService

from tests.fakes import FakeSerialRepo, FakeSession, Factory, InMemoryDB, fixed_clock, inventory_service


class _WarrantyRequests:
    """Thay WarrantyRequestRepository: chỉ cần biết serial nào đã có yêu cầu bảo hành."""

    def __init__(self) -> None:
        self.serial_ids: set = set()

    def list_by_product_serial(self, serial_id):
        return [SimpleNamespace(ProductSerialId=serial_id)] if serial_id in self.serial_ids else []


class SerialTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.admin = self.f.user("Admin")
        self.staff = self.f.user("Staff")
        self.inventory = inventory_service(self.db, self.session)
        self.serial_svc = ProductSerialService(self.session, clock=fixed_clock)
        self.serial_svc.serials = FakeSerialRepo(self.db)
        self.serial_svc.warranty_requests = _WarrantyRequests()
        self.phone = self.f.variant(stock=2, cost="9000000.00", serial_tracked=True)
        self.p1 = self.serial("P-1")
        self.p2 = self.serial("P-2")

    def serial(self, number, status="Available", variant=None, order_item_id=None):
        return self.db.add(ProductSerial(ProductVariantId=(variant or self.phone).ProductVariantId, SerialNumber=number,
                                         Status=status, OrderItemId=order_item_id))

    def adjust(self, change, serials, user=None):
        data = StockAdjustmentCreate(QuantityChange=change, Reason="Kiểm kê", SerialNumbers=list(serials))
        return self.inventory.adjust_stock(self.f.actor(user or self.admin), self.phone.ProductVariantId, data)

    def links(self, direction=None):
        return [l for l in self.db.rows(StockAdjustmentSerial) if direction is None or l.Direction == direction]

    def snapshot(self):
        return (
            self.phone.StockQuantity,
            sorted((s.SerialNumber, s.Status) for s in self.db.rows(ProductSerial)),
            len(self.db.rows(StockAdjustment)),
            len(self.links()),
        )


class SerialCrudTest(SerialTestBase):
    def test_manual_create_is_rejected(self):
        data = ProductSerialCreate(ProductVariantId=self.phone.ProductVariantId, SerialNumber="NEW-1", Status="Available")
        with self.assertRaises(BusinessRuleError) as ctx:
            self.serial_svc.create_serial(self.f.actor(self.admin), data)
        self.assertEqual(ctx.exception.code, "serial_manual_create_not_allowed")
        self.assertEqual(sorted(s.SerialNumber for s in self.db.rows(ProductSerial)), ["P-1", "P-2"])

    def test_delete_is_rejected_and_serial_kept(self):
        with self.assertRaises(BusinessRuleError) as ctx:
            self.serial_svc.delete_serial(self.f.actor(self.admin), self.p1.ProductSerialId)
        self.assertEqual(ctx.exception.code, "serial_delete_not_allowed")
        self.assertIs(self.db.get(ProductSerial, self.p1.ProductSerialId), self.p1)

    def test_rename_available_unassigned_serial(self):
        result = self.serial_svc.update_serial(self.f.actor(self.admin), self.p1.ProductSerialId,
                                               ProductSerialUpdate(SerialNumber="  P-1X "))
        self.assertEqual((result.SerialNumber, self.p1.SerialNumber, self.p1.Status), ("P-1X", "P-1X", "Available"))
        self.assertIn(("ProductSerial", self.p1.ProductSerialId), self.db.locks)  # khóa dòng trước khi kiểm tra

    def test_rename_rejected_unless_available_and_unassigned(self):
        for status in ("Reserved", "Sold", "Warranty", "Returned", "WrittenOff"):
            with self.subTest(status=status):
                self.p1.Status = status
                with self.assertRaises(BusinessRuleError) as ctx:
                    self.serial_svc.update_serial(self.f.actor(self.admin), self.p1.ProductSerialId,
                                                  ProductSerialUpdate(SerialNumber="X-1"))
                self.assertEqual(ctx.exception.code, "serial_not_editable")
        self.p1.Status, self.p1.OrderItemId = "Available", uuid.uuid4()  # dữ liệu lệch: Available nhưng gắn đơn
        with self.assertRaises(BusinessRuleError) as ctx:
            self.serial_svc.update_serial(self.f.actor(self.admin), self.p1.ProductSerialId, ProductSerialUpdate(SerialNumber="X-1"))
        self.assertEqual(ctx.exception.code, "serial_not_editable")
        self.assertEqual(self.p1.SerialNumber, "P-1")

    def test_rename_rejects_duplicate_number_case_sensitively(self):
        with self.assertRaises(ConflictError) as ctx:
            self.serial_svc.update_serial(self.f.actor(self.admin), self.p1.ProductSerialId, ProductSerialUpdate(SerialNumber="P-2"))
        self.assertEqual(ctx.exception.code, "serial_exists")
        self.assertEqual(self.p1.SerialNumber, "P-1")
        self.serial_svc.update_serial(self.f.actor(self.admin), self.p1.ProductSerialId, ProductSerialUpdate(SerialNumber="p-2"))
        self.assertEqual(self.p1.SerialNumber, "p-2")  # UNIQUE phân biệt hoa thường

    def test_rename_rejected_when_serial_has_warranty_history(self):
        self.serial_svc.warranty_requests.serial_ids.add(self.p1.ProductSerialId)
        with self.assertRaises(BusinessRuleError) as ctx:
            self.serial_svc.update_serial(self.f.actor(self.admin), self.p1.ProductSerialId, ProductSerialUpdate(SerialNumber="X-1"))
        self.assertEqual(ctx.exception.code, "serial_has_history")

    def test_business_fields_cannot_be_edited(self):
        for extra in ({"Status": "Sold"}, {"OrderItemId": str(uuid.uuid4())}, {"WarrantyStartDate": "2026-01-01"},
                      {"WarrantyEndDate": "2027-01-01"}):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                ProductSerialUpdate(SerialNumber="X-1", **extra)
        bypass = SimpleNamespace(model_dump=lambda exclude_unset=True: {"SerialNumber": "X-1", "Status": "Available"})
        with self.assertRaises(BusinessRuleError) as ctx:
            self.serial_svc.update_serial(self.f.actor(self.admin), self.p1.ProductSerialId, bypass)
        self.assertEqual(ctx.exception.code, "serial_field_not_editable")

    def test_only_admin_edits_serials(self):
        for who in (self.staff, self.f.user("Customer")):
            with self.subTest(role=who.Role), self.assertRaises(PermissionDeniedError):
                self.serial_svc.update_serial(self.f.actor(who), self.p1.ProductSerialId, ProductSerialUpdate(SerialNumber="X"))
        self.assertEqual(self.p1.SerialNumber, "P-1")


class SerialAdjustmentLinkTest(SerialTestBase):
    def test_increase_links_new_serials_in(self):
        record = self.adjust(2, ["N-1", "N-2"])
        links = self.links("In")
        self.assertEqual({l.StockAdjustmentId for l in links}, {record.StockAdjustmentId})
        created = {s.ProductSerialId for s in self.db.rows(ProductSerial) if s.SerialNumber in ("N-1", "N-2")}
        self.assertEqual({l.ProductSerialId for l in links}, created)
        self.assertEqual(self.phone.StockQuantity, 4)

    def test_decrease_writes_off_and_links_out(self):
        record = self.adjust(-1, ["P-1"])
        [link] = self.links("Out")
        self.assertEqual((link.StockAdjustmentId, link.ProductSerialId), (record.StockAdjustmentId, self.p1.ProductSerialId))
        self.assertEqual((self.p1.Status, self.p1.OrderItemId, self.phone.StockQuantity), ("WrittenOff", None, 1))
        self.assertEqual(self.inventory.serials.count_by_variant(self.phone.ProductVariantId, status="Available"), 1)
        self.assertEqual(self.inventory.serials.list_for_update(self.phone.ProductVariantId, status="Available", limit=5), [self.p2])

    def test_opening_links_new_and_existing_available_serials(self):
        fresh = self.f.variant(stock=0, cost="0", serial_tracked=True)
        legacy = self.serial("L-1", variant=fresh)
        data = StockOpeningCreate(Quantity=2, UnitCost="5000000.00", Reason="Đầu kỳ", SerialNumbers=["N-9"])
        record = self.inventory.declare_opening(self.f.actor(self.admin), fresh.ProductVariantId, data)
        linked = {l.ProductSerialId for l in self.links("In") if l.StockAdjustmentId == record.StockAdjustmentId}
        new = [s for s in self.db.rows(ProductSerial) if s.SerialNumber == "N-9"][0]
        self.assertEqual(linked, {legacy.ProductSerialId, new.ProductSerialId})

    def test_written_off_serial_cannot_be_removed_again(self):
        self.adjust(-1, ["P-1"])
        before = self.snapshot()
        self.db.locks.clear()
        with self.assertRaises(BusinessRuleError) as ctx:
            self.adjust(-1, ["P-1"])  # yêu cầu thứ hai (lặp/đồng thời) chờ khóa rồi thấy serial không còn Available
        self.assertEqual(ctx.exception.code, "serial_not_available")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual([name for name, _ in self.db.locks][:2], ["ProductVariant", "ProductSerial"])

    def test_existing_out_link_blocks_second_write_off(self):
        """Dữ liệu lệch (serial Available nhưng đã có liên kết Out): không loại khỏi kho lần hai."""
        self.db.add(StockAdjustmentSerial(StockAdjustmentId=uuid.uuid4(), ProductSerialId=self.p2.ProductSerialId, Direction="Out"))
        before = self.snapshot()
        with self.assertRaises(ConflictError) as ctx:
            self.adjust(-1, ["P-2"])
        self.assertEqual(ctx.exception.code, "serial_already_adjusted")
        self.assertIn("P-2", str(ctx.exception))  # Service tự chặn (nêu serial), không dựa vào UNIQUE của database
        self.assertEqual(self.snapshot(), before)

    def test_database_unique_is_last_line_of_defense(self):
        self.db.add(StockAdjustmentSerial(StockAdjustmentId=uuid.uuid4(), ProductSerialId=self.p2.ProductSerialId, Direction="Out"))
        self.inventory.serial_links.linked_serial_ids = lambda ids, direction: set()  # giả lập bỏ sót kiểm tra Service
        before = self.snapshot()
        with self.assertRaises(ConflictError) as ctx:
            self.adjust(-1, ["P-2"])
        self.assertEqual(ctx.exception.code, "serial_already_adjusted")  # UNIQUE (ProductSerialId, Direction)
        self.assertEqual(self.snapshot(), before)  # rollback toàn bộ

    def test_failure_while_linking_rolls_back_stock_status_and_history(self):
        def broken(values):
            raise RuntimeError("ghi liên kết lỗi")

        self.inventory.serial_links.create = broken
        before = self.snapshot()
        for change, serials in ((-1, ["P-1"]), (1, ["N-1"])):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.adjust(change, serials)
            self.assertEqual(self.snapshot(), before)

    def test_links_are_append_only(self):
        self.adjust(-1, ["P-1"])
        [link] = self.links()
        with self.assertRaises(PermissionError):
            self.inventory.serial_links.update(link, {"Direction": "In"})
        with self.assertRaises(PermissionError):
            self.inventory.serial_links.delete(link)


if __name__ == "__main__":
    unittest.main()
