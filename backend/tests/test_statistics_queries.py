"""Cấu trúc câu SQL của StatisticsRepository (compile dialect PostgreSQL, KHÔNG kết nối database).

Kiểm tra lọc trạng thái/giao dịch Success, khoảng thời gian nửa mở [start, end), cộng giao dịch theo đơn trong subquery
trước khi JOIN (không nhân bản dòng), tổng hợp/phân trang trong SQL và chỉ đọc. Không chứng minh kết quả hay hiệu năng
trên PostgreSQL thật.
"""

import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.repositories import StatisticsRepository

START = datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc)
END = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)


class _Result:
    def __init__(self, width: int) -> None:
        self.width = width

    def __iter__(self):
        return iter(())

    def one(self):
        return (0,) * self.width


class RecordingSession:
    """Ghi lại câu lệnh; mọi thao tác ghi/khóa làm test lỗi."""

    def __init__(self) -> None:
        self.statements: list = []

    def execute(self, stmt):
        self.statements.append(stmt)
        return _Result(len(stmt.selected_columns))

    def scalar(self, stmt):
        self.statements.append(stmt)
        return 0

    def __getattr__(self, name):
        raise AssertionError(f"Truy vấn thống kê không được gọi Session.{name}")


def compiled(stmt):
    result = stmt.compile(dialect=postgresql.dialect())
    return " ".join(str(result).split()), result.params


class StatisticsQueryShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = RecordingSession()
        self.repo = StatisticsRepository(self.session)

    def only(self):
        [stmt] = self.session.statements
        return compiled(stmt)

    def assert_read_only(self, text):
        for keyword in ("FOR UPDATE", "INSERT", "UPDATE ", "DELETE"):
            self.assertNotIn(keyword, text)

    def test_orders_grouped_by_status_in_half_open_period(self):
        self.assertEqual(self.repo.count_orders_by_status(START, END), {})
        text, params = self.only()
        self.assertIn('"Orders"."OrderedAt" >= %(OrderedAt_1)s', text)
        self.assertIn('"Orders"."OrderedAt" < %(OrderedAt_2)s', text)
        self.assertIn('GROUP BY "Orders"."OrderStatus"', text)
        self.assertEqual((params["OrderedAt_1"], params["OrderedAt_2"]), (START, END))
        self.assert_read_only(text)

    def test_revenue_aggregates_transactions_per_order_before_joining(self):
        totals = self.repo.revenue_totals(START, END)
        self.assertEqual(totals.order_count, 0)
        text, params = self.only()
        # Ba subquery cộng tiền theo OrderId (Payment Success, Refund Success, Refund Pending)
        self.assertEqual(text.count('GROUP BY "PaymentTransactions"."OrderId"'), 3)
        self.assertIn('FROM "Orders" JOIN (SELECT "PaymentTransactions"."OrderId" AS "OrderId", '
                      'sum("PaymentTransactions"."Amount") AS "Amount"', text)
        self.assertEqual(text.count("LEFT OUTER JOIN (SELECT"), 2)
        self.assertIn('"Orders"."OrderStatus" IN (__[POSTCOMPILE_OrderStatus_1])', text)
        self.assertIn('"Orders"."DeliveredAt" >= %(DeliveredAt_1)s', text)
        self.assertIn('"Orders"."DeliveredAt" < %(DeliveredAt_2)s', text)
        self.assertEqual(params["OrderStatus_1"], ["Delivered", "Completed"])
        transaction_filters = sorted((params[k], params[k.replace("TransactionType", "Status")])
                                     for k in params if k.startswith("TransactionType"))
        self.assertEqual(transaction_filters, [("Payment", "Success"), ("Refund", "Pending"), ("Refund", "Success")])
        self.assertEqual((params["DeliveredAt_1"], params["DeliveredAt_2"]), (START, END))
        self.assert_read_only(text)

    def test_delivered_without_payment_uses_not_exists(self):
        self.assertEqual(self.repo.count_delivered_without_payment(START, END), 0)
        text, params = self.only()
        self.assertIn("NOT (EXISTS (SELECT", text)
        self.assertIn('"PaymentTransactions"."OrderId" = "Orders"."OrderId"', text)
        self.assertEqual(sorted(v for k, v in params.items() if k.startswith(("TransactionType", "Status"))),
                         ["Payment", "Success"])

    def test_cogs_uses_order_item_snapshot_of_revenue_orders(self):
        self.repo.cogs_totals(START, END)
        text, params = self.only()
        self.assertIn('"OrderItems"."UnitCost" * "OrderItems"."Quantity"', text)
        self.assertIn('CASE WHEN ("OrderItems"."UnitCost" = %(UnitCost_2)s::INTEGER) THEN', text)
        self.assertIn('CASE WHEN ("OrderItems"."UnitCost" > %(UnitCost_1)s::INTEGER) THEN '
                      '"OrderItems"."UnitCost" * "OrderItems"."Quantity"', text)
        self.assertEqual((params["UnitCost_1"], params["UnitCost_2"]), (0, 0))
        self.assertIn('"OrderItems"."OrderId" IN (SELECT "Orders"."OrderId" FROM "Orders" WHERE', text)
        self.assertIn("EXISTS (SELECT *", text)
        self.assertNotIn("CostPrice", text)  # không dùng giá vốn catalog hiện tại
        self.assertEqual(params["OrderStatus_1"], ["Delivered", "Completed"])

    def test_top_products_group_rank_and_limit_in_sql(self):
        self.repo.top_products(START, END, rank_by="quantity", limit=10)
        self.repo.top_products(START, END, rank_by="revenue", limit=5)
        (by_quantity, q_params), (by_revenue, r_params) = (compiled(s) for s in self.session.statements)
        self.assertIn('sum("OrderItems"."Quantity") AS "Quantity"', by_quantity)
        self.assertIn('sum("OrderItems"."LineTotal") AS "Revenue"', by_quantity)
        self.assertIn('GROUP BY "ProductVariants"."ProductVariantId"', by_quantity)
        self.assertIn('ORDER BY "Quantity" DESC, "Revenue" DESC, "ProductVariants"."ProductVariantId"', by_quantity)
        self.assertIn('ORDER BY "Revenue" DESC, "Quantity" DESC, "ProductVariants"."ProductVariantId"', by_revenue)
        self.assertNotIn('"ProductVariants"."Price"', by_quantity)  # doanh thu theo LineTotal lịch sử
        self.assertEqual((q_params["param_1"], r_params["param_1"]), (10, 5))

    def test_returned_quantities_count_completed_returns_only(self):
        self.assertEqual(self.repo.returned_quantities(START, END, []), {})
        self.assertEqual(self.session.statements, [])  # danh sách rỗng: không truy vấn
        self.repo.returned_quantities(START, END, [uuid.uuid4()])
        text, params = self.only()
        self.assertIn('sum("ReturnRequests"."Quantity")', text)
        self.assertIn('JOIN "OrderItems" ON "OrderItems"."OrderItemId" = "ReturnRequests"."OrderItemId"', text)
        self.assertEqual((params["RequestType_1"], params["Status_1"]), ("Return", "Completed"))
        self.assertIn('GROUP BY "OrderItems"."ProductVariantId"', text)

    def test_inventory_queries_exclude_deleted_variants_and_page_in_sql(self):
        self.repo.list_inventory(offset=20, limit=10)
        self.repo.serial_status_counts([uuid.uuid4()])
        self.repo.serial_status_totals()
        self.repo.stock_total()
        self.repo.count_inventory_variants()
        texts = [compiled(s)[0] for s in self.session.statements]
        page, counts, totals, stock, count = texts
        for text in texts:
            self.assertIn('"ProductVariants"."IsDeleted" IS false', text)
            self.assert_read_only(text)
        self.assertIn("LIMIT %(param_1)s::INTEGER OFFSET %(param_2)s::INTEGER", page)
        self.assertIn('GROUP BY "ProductSerials"."ProductVariantId", "ProductSerials"."Status"', counts)
        self.assertIn('"ProductSerials"."ProductVariantId" IN (__[POSTCOMPILE_ProductVariantId_1])', counts)
        self.assertIn('GROUP BY "ProductSerials"."Status"', totals)
        self.assertIn('sum("ProductVariants"."StockQuantity")', stock)
        self.assertIn("count(", count)
        self.assertEqual(self.repo.serial_status_counts([]), {})


if __name__ == "__main__":
    unittest.main()
