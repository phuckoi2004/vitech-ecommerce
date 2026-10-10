"""Quy tắc tính thời hạn bảo hành (đợt 5.1.1) — hàm thuần trong app.services.warranty_period.

Hết hạn = bắt đầu + số tháng − 1 ngày; vượt cuối tháng đích thì lấy ngày cuối tháng đích trước khi trừ một ngày;
0 tháng = không bảo hành; máy thay thế có thời hạn mới từ ngày Staff xác nhận bàn giao; serial cũ giữ nguyên lịch sử.
"""

import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError

from app.models import Product, ProductSerial
from app.schemas import ProductCreate, ProductUpdate
from app.services import BusinessRuleError, ProductService
from app.services.warranty_period import (
    WarrantyPeriod,
    add_months_clamped,
    apply_replacement_warranty,
    compute_warranty_period,
    delivery_warranty_period,
    is_under_warranty,
    replacement_warranty_period,
    stored_warranty_period,
    validate_warranty_months,
)

from tests.fakes import FakeProductRepo, FakeSession, Factory, InMemoryDB, fixed_clock


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def end_of(start, months):
    period = compute_warranty_period(start, months)
    return period.end if period else None


class PeriodCalculationTest(unittest.TestCase):
    def test_zero_months_means_no_warranty(self):
        for start in (date(2026, 10, 9), date(2028, 2, 29), date(2026, 1, 31)):
            with self.subTest(start=start):
                self.assertIsNone(compute_warranty_period(start, 0))

    def test_one_twelve_and_many_months(self):
        cases = [
            (date(2026, 10, 9), 1, date(2026, 11, 8)),
            (date(2026, 10, 9), 12, date(2027, 10, 8)),
            (date(2026, 10, 9), 24, date(2028, 10, 8)),
            (date(2026, 10, 9), 120, date(2036, 10, 8)),
            (date(2026, 2, 15), 11, date(2027, 1, 14)),  # sang năm
            (date(2026, 1, 1), 1, date(2026, 1, 31)),
        ]
        for start, months, expected in cases:
            with self.subTest(start=start, months=months):
                self.assertEqual(compute_warranty_period(start, months), WarrantyPeriod(start, expected))

    def test_start_on_day_28_29_30_31(self):
        cases = [
            # ngày 28
            (date(2026, 1, 28), 1, date(2026, 2, 27)),
            (date(2028, 2, 28), 1, date(2028, 3, 27)),
            (date(2027, 2, 28), 12, date(2028, 2, 27)),
            # ngày 29
            (date(2026, 1, 29), 1, date(2026, 2, 27)),  # 29/02/2026 không tồn tại → 28/02 → trừ 1
            (date(2028, 1, 29), 1, date(2028, 2, 28)),  # năm nhuận: 29/02/2028 tồn tại
            # ngày 30
            (date(2026, 1, 30), 1, date(2026, 2, 27)),
            (date(2028, 1, 30), 1, date(2028, 2, 28)),
            (date(2026, 4, 30), 1, date(2026, 5, 29)),
            # ngày 31
            (date(2026, 1, 31), 1, date(2026, 2, 27)),
            (date(2028, 1, 31), 1, date(2028, 2, 28)),
            (date(2026, 3, 31), 1, date(2026, 4, 29)),  # tháng đích có 30 ngày
            (date(2026, 5, 31), 12, date(2027, 5, 30)),
            (date(2026, 12, 31), 1, date(2027, 1, 30)),  # sang năm, tháng đích đủ 31 ngày
        ]
        for start, months, expected in cases:
            with self.subTest(start=start, months=months):
                self.assertEqual(end_of(start, months), expected)

    def test_february_in_normal_and_leap_years(self):
        cases = [
            (date(2026, 8, 31), 6, date(2027, 2, 27)),  # đích 02/2027 (28 ngày)
            (date(2027, 8, 31), 6, date(2028, 2, 28)),  # đích 02/2028 (29 ngày)
            (date(2026, 12, 31), 2, date(2027, 2, 27)),
            (date(2028, 2, 29), 12, date(2029, 2, 27)),  # 29/02/2029 không tồn tại → 28/02 → trừ 1
            (date(2028, 2, 29), 48, date(2032, 2, 28)),  # 2032 nhuận → 29/02/2032 → trừ 1
            (date(2100, 1, 31), 1, date(2100, 2, 27)),  # 2100 không nhuận
            (date(2000, 1, 31), 1, date(2000, 2, 28)),  # 2000 nhuận
        ]
        for start, months, expected in cases:
            with self.subTest(start=start, months=months):
                self.assertEqual(end_of(start, months), expected)

    def test_add_months_clamps_to_end_of_target_month(self):
        cases = [
            (date(2026, 1, 31), 1, date(2026, 2, 28)),
            (date(2028, 1, 31), 1, date(2028, 2, 29)),
            (date(2026, 10, 31), 1, date(2026, 11, 30)),
            (date(2026, 12, 31), 1, date(2027, 1, 31)),
            (date(2026, 1, 15), 0, date(2026, 1, 15)),
        ]
        for start, months, expected in cases:
            with self.subTest(start=start, months=months):
                self.assertEqual(add_months_clamped(start, months), expected)


class CoverageTest(unittest.TestCase):
    def test_under_warranty_until_end_of_last_day_in_vietnam(self):
        period = compute_warranty_period(date(2026, 10, 9), 12)  # 09/10/2026 → 08/10/2027
        cases = [
            (utc(2026, 10, 8, 16, 59, 59), False),  # 08/10/2026 23:59:59 giờ VN: chưa bắt đầu
            (utc(2026, 10, 8, 17, 0, 0), True),  # 09/10/2026 00:00 giờ VN
            (utc(2027, 10, 8, 16, 59, 59), True),  # 08/10/2027 23:59:59 giờ VN: ngày cuối còn bảo hành
            (utc(2027, 10, 8, 17, 0, 0), False),  # 09/10/2027 00:00 giờ VN: hết bảo hành
        ]
        for at, expected in cases:
            with self.subTest(at=at):
                self.assertEqual(is_under_warranty(period, at), expected)

    def test_no_period_is_never_covered(self):
        self.assertFalse(is_under_warranty(None, utc(2026, 10, 9, 8, 0)))

    def test_delivery_uses_vietnam_calendar_day(self):
        # 30/01/2026 17:30 UTC = 31/01/2026 00:30 giờ VN → bắt đầu 31/01, 1 tháng → 28/02 → hết hạn 27/02/2026
        self.assertEqual(delivery_warranty_period(utc(2026, 1, 30, 17, 30), 1),
                         WarrantyPeriod(date(2026, 1, 31), date(2026, 2, 27)))

    def test_stored_period_consistency(self):
        self.assertIsNone(stored_warranty_period(None, None))
        self.assertEqual(stored_warranty_period(date(2026, 1, 1), date(2026, 1, 31)),
                         WarrantyPeriod(date(2026, 1, 1), date(2026, 1, 31)))
        for start, end in ((date(2026, 1, 1), None), (None, date(2026, 1, 1)), (date(2026, 2, 1), date(2026, 1, 31))):
            with self.subTest(start=start, end=end), self.assertRaises(BusinessRuleError) as ctx:
                stored_warranty_period(start, end)
            self.assertEqual(ctx.exception.code, "invalid_stored_warranty")


class ReplacementTest(unittest.TestCase):
    def setUp(self) -> None:
        variant_id = uuid.uuid4()
        self.original = ProductSerial(ProductSerialId=uuid.uuid4(), ProductVariantId=variant_id, SerialNumber="OLD-1",
                                      Status="Warranty", WarrantyStartDate=date(2026, 10, 9),
                                      WarrantyEndDate=date(2027, 10, 8))
        self.replacement = ProductSerial(ProductSerialId=uuid.uuid4(), ProductVariantId=variant_id,
                                         SerialNumber="NEW-1", Status="Available")

    def original_history(self):
        return (self.original.WarrantyStartDate, self.original.WarrantyEndDate, self.original.Status)

    def test_replacement_starts_new_period_when_staff_confirms_handover(self):
        before = self.original_history()
        # 10/03/2027 18:00 UTC = 11/03/2027 01:00 giờ VN (thời điểm Staff xác nhận bàn giao máy thay thế)
        period = apply_replacement_warranty(self.original, self.replacement, months=12,
                                            handed_over_at=utc(2027, 3, 10, 18, 0))
        self.assertEqual(period, WarrantyPeriod(date(2027, 3, 11), date(2028, 3, 10)))
        self.assertEqual((self.replacement.WarrantyStartDate, self.replacement.WarrantyEndDate),
                         (date(2027, 3, 11), date(2028, 3, 10)))  # thời hạn mới, không nối tiếp máy cũ
        self.assertEqual(self.original_history(), before)  # lịch sử bảo hành của serial cũ giữ nguyên

    def test_handover_must_be_recorded(self):
        for call in (lambda: replacement_warranty_period(None, 12),
                     lambda: apply_replacement_warranty(self.original, self.replacement, months=12, handed_over_at=None)):
            with self.subTest(call=call), self.assertRaises(BusinessRuleError) as ctx:
                call()
            self.assertEqual(ctx.exception.code, "replacement_handover_not_recorded")
        self.assertEqual((self.replacement.WarrantyStartDate, self.replacement.WarrantyEndDate), (None, None))

    def test_replacement_must_be_a_different_serial(self):
        before = self.original_history()
        clone = ProductSerial(ProductSerialId=self.original.ProductSerialId, SerialNumber="OLD-1", Status="Warranty")
        for replacement in (self.original, clone):
            with self.subTest(replacement=replacement), self.assertRaises(BusinessRuleError) as ctx:
                apply_replacement_warranty(self.original, replacement, months=12, handed_over_at=utc(2027, 3, 10, 8))
            self.assertEqual(ctx.exception.code, "replacement_same_serial")
        self.assertEqual(self.original_history(), before)

    def test_replacement_of_item_without_warranty_has_no_period(self):
        self.replacement.WarrantyStartDate, self.replacement.WarrantyEndDate = date(2024, 1, 1), date(2025, 1, 1)
        self.assertIsNone(apply_replacement_warranty(self.original, self.replacement, months=0,
                                                     handed_over_at=utc(2027, 3, 10, 8)))
        self.assertEqual((self.replacement.WarrantyStartDate, self.replacement.WarrantyEndDate), (None, None))


class InvalidInputTest(unittest.TestCase):
    def test_invalid_months(self):
        for months in (-1, -12, True, False, 1.5, 12.0, "12", None, Decimal("12")):
            with self.subTest(months=months), self.assertRaises(BusinessRuleError) as ctx:
                compute_warranty_period(date(2026, 1, 1), months)
            self.assertEqual(ctx.exception.code, "invalid_warranty_months")
        with self.assertRaises(BusinessRuleError) as ctx:  # vượt giới hạn năm 9999
            compute_warranty_period(date(2026, 1, 1), 10**6)
        self.assertEqual(ctx.exception.code, "invalid_warranty_months")
        self.assertEqual(validate_warranty_months(0), 0)

    def test_invalid_start(self):
        for start in (None, "2026-01-01", utc(2026, 1, 1, 0, 0)):
            with self.subTest(start=start), self.assertRaises(BusinessRuleError) as ctx:
                compute_warranty_period(start, 12)
            self.assertEqual(ctx.exception.code, "invalid_warranty_start")

    def test_delivery_and_handover_timestamps(self):
        with self.assertRaises(BusinessRuleError) as ctx:  # không tự đặt thời điểm giao hàng
            delivery_warranty_period(None, 12)
        self.assertEqual(ctx.exception.code, "delivery_not_recorded")
        for call in (lambda: delivery_warranty_period(datetime(2026, 10, 9, 8), 12),
                     lambda: replacement_warranty_period(datetime(2026, 10, 9, 8), 12)):
            with self.subTest(call=call), self.assertRaises(ValueError):  # thiếu múi giờ: lỗi lập trình
                call()


class ProductWarrantyMonthsTest(unittest.TestCase):
    def test_schema_rejects_negative_months(self):
        base = dict(CategoryId=uuid.uuid4(), BrandId=uuid.uuid4(), Name="P", Slug="p", Status="Active")
        self.assertEqual(ProductCreate(**base, WarrantyMonths=0).WarrantyMonths, 0)
        with self.assertRaises(ValidationError):
            ProductCreate(**base, WarrantyMonths=-1)
        with self.assertRaises(ValidationError):
            ProductUpdate(WarrantyMonths=-1)

    def test_service_rejects_negative_months_even_if_schema_is_bypassed(self):
        db = InMemoryDB()
        session = FakeSession(db)
        f = Factory(db)
        product = f.variant().product
        svc = ProductService(session, clock=fixed_clock)
        svc.products = FakeProductRepo(db)
        bypass = SimpleNamespace(model_dump=lambda exclude_unset=True: {"WarrantyMonths": -6})
        with self.assertRaises(BusinessRuleError) as ctx:
            svc.update_product(f.actor(f.user("Admin")), product.ProductId, bypass)
        self.assertEqual(ctx.exception.code, "invalid_warranty_months")
        self.assertNotEqual(db.get(Product, product.ProductId).WarrantyMonths, -6)


if __name__ == "__main__":
    unittest.main()
