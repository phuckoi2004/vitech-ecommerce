"""Truy vấn khóa dòng của Repository: FOR UPDATE + populate_existing, flush trước khi khóa.

Kiểm tra câu lệnh được dựng (compile với dialect PostgreSQL), không thực thi trên database.
"""

import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.models import Order
from app.repositories import (
    CouponRepository,
    OrderRepository,
    PaymentReconciliationRepository,
    ProductSerialRepository,
    ProductVariantRepository,
    PurchaseOrderItemRepository,
    StockAdjustmentRepository,
)


class RecordingSession:
    """Chỉ ghi lại lời gọi; không có kết nối database."""

    def __init__(self) -> None:
        self.calls: list = []
        self.statements: list = []

    def flush(self, objects=None) -> None:
        self.calls.append("flush")

    def get(self, model, ident, **kwargs):
        self.calls.append(("get", model, kwargs))
        return None

    def scalars(self, stmt):
        self.calls.append("scalars")
        self.statements.append(stmt)
        return iter(())

    def scalar(self, stmt):
        self.calls.append("scalar")
        self.statements.append(stmt)
        return None


def sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


class LockingQueryTest(unittest.TestCase):
    def test_get_by_id_for_update_flushes_then_reloads_locked_row(self):
        session = RecordingSession()
        OrderRepository(session).get_by_id_for_update(uuid.uuid4())
        self.assertEqual(session.calls[0], "flush")
        _, model, kwargs = session.calls[1]
        self.assertIs(model, Order)
        self.assertEqual(kwargs, {"with_for_update": True, "populate_existing": True})

    def test_variant_lock_orders_by_id_and_populates_existing(self):
        session = RecordingSession()
        ProductVariantRepository(session).get_many_by_ids_for_update({uuid.uuid4(), uuid.uuid4()})
        self.assertEqual(session.calls, ["flush", "scalars"])
        stmt = session.statements[0]
        self.assertTrue(stmt.get_execution_options().get("populate_existing"))
        text = sql(stmt)
        self.assertIn("FOR UPDATE", text)
        self.assertIn('ORDER BY "ProductVariants"."ProductVariantId"', text)

    def test_variant_lock_with_no_ids_does_not_touch_database(self):
        session = RecordingSession()
        self.assertEqual(ProductVariantRepository(session).get_many_by_ids_for_update(set()), [])
        self.assertEqual(session.calls, [])

    def test_serial_lock_skips_locked_rows_and_populates_existing(self):
        session = RecordingSession()
        ProductSerialRepository(session).list_for_update(uuid.uuid4(), status="Available", limit=2)
        stmt = session.statements[0]
        self.assertTrue(stmt.get_execution_options().get("populate_existing"))
        self.assertIn("FOR UPDATE SKIP LOCKED", sql(stmt))
        self.assertEqual(session.calls[0], "flush")

    def test_coupon_lock_is_case_insensitive_and_populates_existing(self):
        session = RecordingSession()
        self.assertIsNone(CouponRepository(session).get_by_code_for_update("Sale10"))
        stmt = session.statements[0]
        self.assertTrue(stmt.get_execution_options().get("populate_existing"))
        text = sql(stmt)
        self.assertIn("FOR UPDATE", text)
        self.assertIn('lower("Coupons"."Code")', text)
        self.assertEqual(session.calls[0], "flush")


class SerialAndReconciliationQueryTest(unittest.TestCase):
    def test_serial_locks_for_order_item_and_adjustment(self):
        for call in (
            lambda repo: repo.list_by_order_item_for_update(uuid.uuid4()),
            lambda repo: repo.list_by_serial_numbers_for_update(["B", "A"]),
        ):
            session = RecordingSession()
            call(ProductSerialRepository(session))
            self.assertEqual(session.calls, ["flush", "scalars"])
            stmt = session.statements[0]
            self.assertTrue(stmt.get_execution_options().get("populate_existing"))
            text = sql(stmt)
            self.assertIn("FOR UPDATE", text)
            self.assertIn('ORDER BY "ProductSerials"."SerialNumber"', text)
            self.assertNotIn("lower(", text)  # so khớp chính xác, phân biệt hoa thường
        self.assertEqual(ProductSerialRepository(RecordingSession()).list_by_serial_numbers_for_update([]), [])

    def test_reconciliation_lookup_uses_idempotency_key(self):
        session = RecordingSession()
        session.scalars = lambda stmt: (session.statements.append(stmt), _Empty())[1]
        PaymentReconciliationRepository(session).get_by_key("GW-1", "AmountMismatch")
        text = sql(session.statements[0])
        self.assertIn('"PaymentReconciliations"."GatewayTransactionCode" = ', text)
        self.assertIn('"PaymentReconciliations"."IssueType" = ', text)


class _Empty:
    def one_or_none(self):
        return None


class InventoryQueryTest(unittest.TestCase):
    """Câu SQL của các truy vấn kho/thanh toán mới (compile PostgreSQL, không thực thi)."""

    def test_existing_serial_lookup_is_exact_and_case_sensitive(self):
        session = RecordingSession()
        self.assertEqual(ProductSerialRepository(session).find_existing_serial_numbers(["A1", "a1"]), set())
        text = sql(session.statements[0])
        self.assertIn('"ProductSerials"."SerialNumber" IN', text)
        self.assertNotIn("lower(", text)
        self.assertEqual(ProductSerialRepository(RecordingSession()).find_existing_serial_numbers([]), set())

    def test_low_stock_query(self):
        session = RecordingSession()
        ProductVariantRepository(session).list_low_stock(limit=10)
        text = sql(session.statements[0])
        self.assertIn('"ProductVariants"."MinStockLevel" > ', text)
        self.assertIn('"ProductVariants"."StockQuantity" <= "ProductVariants"."MinStockLevel"', text)
        self.assertIn('"ProductVariants"."IsDeleted" IS false', text)

    def test_received_lines_query(self):
        session = RecordingSession()
        PurchaseOrderItemRepository(session).has_received_for_variant(uuid.uuid4())
        text = sql(session.statements[0])
        self.assertIn('"PurchaseOrderItems"."ReceivedQuantity" > ', text)

    def test_expired_unpaid_orders_query_excludes_cod(self):
        session = RecordingSession()
        OrderRepository(session).list_expired_unpaid_order_ids(
            ordered_before=datetime(2026, 1, 1, tzinfo=timezone.utc), order_status="Pending",
            payment_statuses=("Pending", "Failed"), excluded_payment_method_code="COD", limit=50,
        )
        text = sql(session.statements[0])
        self.assertIn('JOIN "PaymentMethods"', text)
        self.assertIn('"PaymentMethods"."Code" != ', text)
        self.assertIn('"Orders"."OrderedAt" <= ', text)
        self.assertIn("LIMIT", text)
        self.assertNotIn("FOR UPDATE", text)  # chỉ liệt kê; Service khóa và kiểm tra lại từng đơn

    def test_opening_lookup(self):
        session = RecordingSession()
        StockAdjustmentRepository(session).has_opening(uuid.uuid4())
        self.assertIn('"StockAdjustments"."AdjustmentType" = ', sql(session.statements[0]))


if __name__ == "__main__":
    unittest.main()
