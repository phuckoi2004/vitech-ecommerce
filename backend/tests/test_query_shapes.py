"""Hình dạng câu SQL của các truy vấn Repository thêm ở đợt 5.1 (compile dialect PostgreSQL, KHÔNG kết nối database).

Fake trong các test nghiệp vụ không chứng minh câu SQL thật đúng; các test này kiểm tra khóa dòng, thứ tự khóa,
lọc và tổng hợp được dựng đúng trong câu lệnh.
"""

import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.repositories import (
    BannerRepository,
    NewsArticleRepository,
    ConversationRepository,
    OrderRepository,
    OtpChallengeRepository,
    PaymentTransactionRepository,
    ProductSerialRepository,
    ProductVariantRepository,
    ReturnRequestRepository,
    ReviewRepository,
    ServiceRequestHistoryRepository,
    ShipmentReturnRepository,
    StockAdjustmentSerialRepository,
    UserRepository,
    WarrantyRequestRepository,
)


class _Result:
    def __iter__(self):
        return iter(())

    def first(self):
        return None

    def one_or_none(self):
        return None

    def one(self):
        return (0, None)


class RecordingSession:
    """Chỉ ghi lại câu lệnh; không có kết nối database."""

    def __init__(self) -> None:
        self.calls: list = []
        self.statements: list = []

    def flush(self, objects=None) -> None:
        self.calls.append("flush")

    def scalars(self, stmt):
        self.calls.append("scalars")
        self.statements.append(stmt)
        return _Result()

    def scalar(self, stmt):
        self.calls.append("scalar")
        self.statements.append(stmt)
        return 0

    def execute(self, stmt):
        self.calls.append("execute")
        self.statements.append(stmt)
        return _Result()


def sql(stmt) -> str:
    return " ".join(str(stmt.compile(dialect=postgresql.dialect())).split())


class LockQueryShapeTest(unittest.TestCase):
    def test_admin_rows_are_locked_in_user_id_order(self):
        session = RecordingSession()
        UserRepository(session).list_admins_for_update()
        stmt = session.statements[0]
        text = sql(stmt)
        self.assertEqual(session.calls[0], "flush")
        self.assertTrue(stmt.get_execution_options().get("populate_existing"))
        self.assertIn('"Users"."Role" = %(Role_1)s', text)
        self.assertIn('"Users"."IsDeleted" IS false', text)
        self.assertIn('ORDER BY "Users"."UserId" FOR UPDATE', text)
        self.assertEqual(stmt.compile(dialect=postgresql.dialect()).params["Role_1"], "Admin")

    def test_shipment_return_is_locked_by_order(self):
        session = RecordingSession()
        ShipmentReturnRepository(session).get_by_order_for_update(uuid.uuid4())
        stmt = session.statements[0]
        self.assertEqual(session.calls[0], "flush")
        self.assertTrue(stmt.get_execution_options().get("populate_existing"))
        self.assertIn('WHERE "ShipmentReturns"."OrderId" = %(OrderId_1)s::UUID FOR UPDATE', sql(stmt))


class AggregateQueryShapeTest(unittest.TestCase):
    def test_refund_sums_are_grouped_by_source_in_database(self):
        session = RecordingSession()
        PaymentTransactionRepository(session).sum_refunds_by_source(uuid.uuid4(), statuses=("Pending", "Success"))
        text = sql(session.statements[0])
        self.assertIn('sum("PaymentTransactions"."Amount")', text)
        self.assertIn('"PaymentTransactions"."TransactionType" = %(TransactionType_1)s', text)
        self.assertIn('"PaymentTransactions"."Status" IN (__[POSTCOMPILE_Status_1])', text)
        self.assertIn('GROUP BY "PaymentTransactions"."RefundOfPaymentTransactionId"', text)

    def test_serial_link_lookup_filters_by_direction(self):
        session = RecordingSession()
        self.assertEqual(StockAdjustmentSerialRepository(session).linked_serial_ids([], "Out"), set())
        self.assertEqual(session.statements, [])  # danh sách rỗng: không truy vấn
        StockAdjustmentSerialRepository(session).linked_serial_ids([uuid.uuid4()], "Out")
        text = sql(session.statements[0])
        self.assertIn('"StockAdjustmentSerials"."ProductSerialId" IN (__[POSTCOMPILE_ProductSerialId_1])', text)
        self.assertIn('"StockAdjustmentSerials"."Direction" = %(Direction_1)s', text)

    def test_review_rating_summary_aggregates_visible_reviews_in_database(self):
        session = RecordingSession()
        self.assertEqual(ReviewRepository(session).rating_summary(uuid.uuid4()), (0, None))
        text = sql(session.statements[0])
        self.assertIn('count("Reviews"."ReviewId")', text)
        self.assertIn('avg("Reviews"."Rating")', text)
        self.assertIn('"Reviews"."ProductId" = %(ProductId_1)s::UUID', text)
        self.assertIn('"Reviews"."IsDeleted" IS false', text)
        ReviewRepository(session).count_by_user(uuid.uuid4())
        count = sql(session.statements[1])
        self.assertIn("count(*)", count)
        self.assertIn('"Reviews"."IsDeleted" IS false', count)

    def test_conversation_queries_filter_open_and_unassigned(self):
        session = RecordingSession()
        repo = ConversationRepository(session)
        repo.get_open_by_customer(uuid.uuid4())
        repo.list_conversations(status="Open", mode="Staff", unassigned=True)
        repo.count_conversations(unassigned=True)
        open_one, queue, count = (sql(s) for s in session.statements)
        self.assertIn('"Conversations"."CustomerId" = %(CustomerId_1)s::UUID', open_one)
        self.assertIn('"Conversations"."Status" = %(Status_1)s', open_one)
        self.assertIn('"Conversations"."AssignedStaffId" IS NULL', queue)
        self.assertIn('"Conversations"."Mode" = %(Mode_1)s', queue)
        self.assertIn('"Conversations"."AssignedStaffId" IS NULL', count)
        self.assertEqual(session.statements[0].compile(dialect=postgresql.dialect()).params["Status_1"], "Open")

    def test_otp_queries_use_latest_send_and_window_count(self):
        session = RecordingSession()
        repo = OtpChallengeRepository(session)
        repo.latest_for(uuid.uuid4(), "Registration")
        repo.count_sent_since(uuid.uuid4(), "Registration", datetime(2026, 1, 1, tzinfo=timezone.utc))
        latest, count = (sql(s) for s in session.statements)
        self.assertIn('ORDER BY "OtpChallenges"."CreatedAt" DESC, "OtpChallenges"."OtpChallengeId" DESC', latest)
        self.assertIn("LIMIT %(param_1)s", latest)
        self.assertIn('"OtpChallenges"."Purpose" = %(Purpose_1)s', latest)
        self.assertIn("count(*)", count)
        self.assertIn('"OtpChallenges"."CreatedAt" > %(CreatedAt_1)s', count)

    def test_warranty_open_request_queries_match_partial_unique_indexes(self):
        """Đợt 5.4: điều kiện 'đang xử lý' trong truy vấn trùng với WHERE của UX_WarrantyRequests_*_Open."""
        session = RecordingSession()
        repo = WarrantyRequestRepository(session)
        repo.get_open_by_product_serial(uuid.uuid4())
        repo.get_open_by_order_item_without_serial(uuid.uuid4())
        repo.get_latest_replacement_handover(uuid.uuid4())
        by_serial, by_item, replacement = session.statements
        serial_sql, item_sql, replacement_sql = (sql(s) for s in session.statements)
        self.assertIn('"WarrantyRequests"."ProductSerialId" = %(ProductSerialId_1)s::UUID', serial_sql)
        self.assertIn('"WarrantyRequests"."Status" IN (__[POSTCOMPILE_Status_1])', serial_sql)
        self.assertEqual(by_serial.compile(dialect=postgresql.dialect()).params["Status_1"],
                         ["New", "HandedOver", "Processing"])
        self.assertIn('"WarrantyRequests"."OrderItemId" = %(OrderItemId_1)s::UUID', item_sql)
        self.assertIn('"WarrantyRequests"."ProductSerialId" IS NULL', item_sql)
        self.assertEqual(by_item.compile(dialect=postgresql.dialect()).params["Status_1"],
                         ["New", "HandedOver", "Processing"])
        self.assertIn('"WarrantyRequests"."ReplacementProductSerialId" = %(ReplacementProductSerialId_1)s::UUID',
                      replacement_sql)
        self.assertIn('"WarrantyRequests"."ReplacementHandedOverAt" IS NOT NULL', replacement_sql)
        self.assertIn('ORDER BY "WarrantyRequests"."ReplacementHandedOverAt" DESC', replacement_sql)
        self.assertIn("LIMIT %(param_1)s", replacement_sql)
        self.assertEqual(session.calls, ["scalars", "scalars", "scalars"])  # không khóa dòng, không flush

    def test_history_queries_hide_internal_rows_by_default(self):
        """Đợt 5.4.1: lịch sử mặc định chỉ dòng công khai; Staff/Admin mới truyền include_internal=True."""
        session = RecordingSession()
        repo = ServiceRequestHistoryRepository(session)
        repo.list_by_warranty_request(uuid.uuid4())
        repo.list_by_return_request(uuid.uuid4())
        repo.list_by_warranty_request(uuid.uuid4(), include_internal=True)
        public_w, public_r, staff = (sql(s) for s in session.statements)
        for text in (public_w, public_r):
            self.assertIn('"ServiceRequestHistories"."IsInternal" IS false', text)
        self.assertIn('"ServiceRequestHistories"."WarrantyRequestId" = %(WarrantyRequestId_1)s::UUID', public_w)
        self.assertIn('"ServiceRequestHistories"."ReturnRequestId" = %(ReturnRequestId_1)s::UUID', public_r)
        self.assertNotIn("IsInternal", staff.split("WHERE", 1)[1])
        self.assertIn('ORDER BY "ServiceRequestHistories"."ChangedAt"', staff)

    def test_content_queries_filter_visibility_in_sql(self):
        """Đợt 5.5: banner hiển thị lọc IsActive + khung [StartDate, EndDate] trong SQL; tin đăng lọc theo Status."""
        session = RecordingSession()
        at = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)
        BannerRepository(session).list_displayable(at)
        NewsArticleRepository(session).list_articles(status="Published", offset=0, limit=20)
        banners, articles = session.statements
        banner_sql, article_sql = sql(banners), sql(articles)
        self.assertIn('"Banners"."IsActive" IS true', banner_sql)
        self.assertIn('("Banners"."StartDate" IS NULL OR "Banners"."StartDate" <= %(StartDate_1)s::TIMESTAMP WITH TIME ZONE)', banner_sql)
        self.assertIn('("Banners"."EndDate" IS NULL OR "Banners"."EndDate" >= %(EndDate_1)s::TIMESTAMP WITH TIME ZONE)', banner_sql)
        self.assertIn('ORDER BY "Banners"."DisplayOrder", "Banners"."BannerId"', banner_sql)
        params = banners.compile(dialect=postgresql.dialect()).params
        self.assertEqual((params["StartDate_1"], params["EndDate_1"]), (at, at))
        self.assertIn('"NewsArticles"."Status" = %(Status_1)s', article_sql)
        self.assertIn('ORDER BY "NewsArticles"."PublishedAt" DESC NULLS LAST', article_sql)
        self.assertRegex(article_sql, r"LIMIT %\(param_\d\)s::INTEGER OFFSET %\(param_\d\)s::INTEGER$")  # phân trang SQL

    def test_open_return_query_matches_partial_unique_index(self):
        session = RecordingSession()
        ReturnRequestRepository(session).get_open_by_product_serial(uuid.uuid4())
        [stmt] = session.statements
        text = sql(stmt)
        self.assertIn('"ReturnRequests"."ProductSerialId" = %(ProductSerialId_1)s::UUID', text)
        self.assertIn('"ReturnRequests"."Status" IN (__[POSTCOMPILE_Status_1])', text)
        self.assertEqual(stmt.compile(dialect=postgresql.dialect()).params["Status_1"],
                         ["Pending", "Approved", "Receiving", "Processing"])

    def test_return_refund_links_of_an_order_are_selected_through_order_items(self):
        session = RecordingSession()
        order_id = uuid.uuid4()
        self.assertEqual(ReturnRequestRepository(session).list_refund_transaction_ids_for_order(order_id), set())
        [stmt] = session.statements
        text = sql(stmt)
        self.assertIn('SELECT "ReturnRequests"."RefundPaymentTransactionId" FROM "ReturnRequests" JOIN "OrderItems" '
                      'ON "OrderItems"."OrderItemId" = "ReturnRequests"."OrderItemId"', text)
        self.assertIn('"OrderItems"."OrderId" = %(OrderId_1)s::UUID', text)
        self.assertIn('"ReturnRequests"."RefundPaymentTransactionId" IS NOT NULL', text)
        self.assertEqual(stmt.compile(dialect=postgresql.dialect()).params["OrderId_1"], order_id)

    def test_serial_return_history_checks_both_history_tables_without_status_filter(self):
        session = RecordingSession()
        serial_id = uuid.uuid4()
        self.assertFalse(ProductSerialRepository(session).has_return_history(serial_id))
        [stmt] = session.statements
        text = sql(stmt)
        params = stmt.compile(dialect=postgresql.dialect()).params
        self.assertIn('SELECT (EXISTS (SELECT * FROM "ReturnRequests" WHERE "ReturnRequests"."ProductSerialId" = '
                      '%(ProductSerialId_1)s::UUID)) OR (EXISTS (SELECT * FROM "ShipmentReturnItems" WHERE '
                      '"ShipmentReturnItems"."ProductSerialId" = %(ProductSerialId_2)s::UUID))', text)
        self.assertNotIn("Status", text)  # mọi trạng thái (kể cả đã đóng) đều là lịch sử
        self.assertEqual({params["ProductSerialId_1"], params["ProductSerialId_2"]}, {serial_id})

    def test_shipping_method_usage_counts_orders_of_any_status(self):
        session = RecordingSession()
        method_id = uuid.uuid4()
        self.assertFalse(OrderRepository(session).exists_by_shipping_method(method_id))
        [stmt] = session.statements
        text = sql(stmt)
        self.assertIn('FROM "Orders" WHERE "Orders"."ShippingMethodId" = %(ShippingMethodId_1)s::UUID', text)
        self.assertNotIn("OrderStatus", text)
        self.assertEqual(stmt.compile(dialect=postgresql.dialect()).params["ShippingMethodId_1"], method_id)

    def test_open_return_codes_of_an_order_use_the_open_status_list(self):
        session = RecordingSession()
        order_id = uuid.uuid4()
        self.assertEqual(ReturnRequestRepository(session).list_open_request_codes_for_order(order_id), [])
        [stmt] = session.statements
        text = sql(stmt)
        params = stmt.compile(dialect=postgresql.dialect()).params
        self.assertIn('SELECT "ReturnRequests"."RequestCode" FROM "ReturnRequests" JOIN "OrderItems" '
                      'ON "OrderItems"."OrderItemId" = "ReturnRequests"."OrderItemId"', text)
        self.assertIn('"OrderItems"."OrderId" = %(OrderId_1)s::UUID AND "ReturnRequests"."Status" IN', text)
        self.assertIn('ORDER BY "ReturnRequests"."RequestCode"', text)
        self.assertEqual((params["OrderId_1"], params["Status_1"]),
                         (order_id, ["Pending", "Approved", "Receiving", "Processing"]))

    def test_serial_tracking_usage_counts_everything_in_one_statement(self):
        class UsageSession(RecordingSession):
            def execute(self, stmt):
                super().execute(stmt)
                return type("Row", (), {"one": staticmethod(lambda: (1, 2, 3, 4, 5))})()

        session = UsageSession()
        variant_id = uuid.uuid4()
        usage = ProductVariantRepository(session).serial_tracking_usage(variant_id)
        self.assertEqual(tuple(usage), (1, 2, 3, 4, 5))
        self.assertEqual(usage.awaiting_shipment_returns, 5)
        [stmt] = session.statements
        self.assertEqual(session.calls, ["execute"])
        text = sql(stmt)
        params = stmt.compile(dialect=postgresql.dialect()).params
        lines = ('IN (SELECT "OrderItems"."OrderItemId" FROM "OrderItems" '
                 'WHERE "OrderItems"."ProductVariantId" = %(ProductVariantId_3)s::UUID)')
        self.assertIn('FROM "ProductSerials" WHERE "ProductSerials"."ProductVariantId" = %(ProductVariantId_1)s::UUID '
                      'AND "ProductSerials"."Status" != %(Status_1)s::VARCHAR', text)
        self.assertIn('(SELECT count(*) AS count_2 FROM "OrderItems" '
                      'WHERE "OrderItems"."ProductVariantId" = %(ProductVariantId_2)s::UUID)', text)  # mọi trạng thái đơn
        self.assertIn(f'"WarrantyRequests"."OrderItemId" {lines} AND "WarrantyRequests"."Status" IN', text)
        self.assertIn(f'"ReturnRequests"."OrderItemId" {lines} AND "ReturnRequests"."Status" IN', text)
        self.assertIn('count(DISTINCT "ShipmentReturns"."ShipmentReturnId")', text)
        self.assertIn(f'"ShipmentReturnItems"."OrderItemId" {lines} AND "ShipmentReturns"."Status" = %(Status_4)s', text)
        self.assertNotIn("FOR UPDATE", text)
        self.assertEqual({params[k] for k in ("ProductVariantId_1", "ProductVariantId_2", "ProductVariantId_3")},
                         {variant_id})
        self.assertEqual((params["Status_1"], params["Status_2"], params["Status_3"], params["Status_4"]),
                         ("WrittenOff", ["New", "HandedOver", "Processing"],
                          ["Pending", "Approved", "Receiving", "Processing"], "AwaitingReturn"))


if __name__ == "__main__":
    unittest.main()
