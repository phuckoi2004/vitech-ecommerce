"""Ranh giới transaction của BaseService: commit/rollback và chuyển IntegrityError thành lỗi nghiệp vụ."""

import unittest
from types import SimpleNamespace

from sqlalchemy.exc import IntegrityError

from app.services import BusinessRuleError, ConflictError
from app.services.base import BaseService

from tests.fakes import FakeSession, InMemoryDB


def integrity_error(sqlstate: str, constraint: str | None) -> IntegrityError:
    orig = SimpleNamespace(sqlstate=sqlstate, diag=SimpleNamespace(constraint_name=constraint))
    return IntegrityError("INSERT ...", {}, orig)


class TransactionBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = FakeSession(InMemoryDB())
        self.service = BaseService(self.session)

    def test_outermost_use_case_commits_once(self):
        with self.service.transaction():
            with self.service.transaction():
                self.assertTrue(self.service.in_transaction())
        self.assertEqual((self.session.commits, self.session.rollbacks), (1, 0))
        self.assertFalse(self.service.in_transaction())

    def test_error_in_nested_use_case_rolls_back_whole_transaction(self):
        with self.assertRaises(RuntimeError):
            with self.service.transaction():
                with self.service.transaction():
                    raise RuntimeError("boom")
        self.assertEqual((self.session.commits, self.session.rollbacks), (0, 1))
        self.assertFalse(self.service.in_transaction())

    def test_unique_violation_becomes_conflict_with_known_code(self):
        with self.assertRaises(ConflictError) as ctx:
            with self.service.transaction():
                raise integrity_error("23505", "UQ_ProductVariants_Sku")
        self.assertEqual(ctx.exception.code, "sku_exists")
        self.assertIsInstance(ctx.exception.__cause__, IntegrityError)
        self.assertEqual(self.session.rollbacks, 1)

    def test_unique_violation_on_unknown_constraint_uses_generic_code(self):
        with self.assertRaises(ConflictError) as ctx:
            with self.service.transaction():
                raise integrity_error("23505", "UQ_Something_New")
        self.assertEqual(ctx.exception.code, "duplicate_value")

    def test_unique_violation_at_commit_is_mapped(self):
        self.session.commit = lambda: (_ for _ in ()).throw(integrity_error("23505", "UX_Coupons_Code_Lower"))
        with self.assertRaises(ConflictError) as ctx:
            with self.service.transaction():
                pass
        self.assertEqual(ctx.exception.code, "coupon_code_exists")
        self.assertEqual(self.session.rollbacks, 1)

    def test_check_and_foreign_key_violations_become_business_errors(self):
        for sqlstate, code in (("23514", "check_violation"), ("23503", "reference_violation"), ("23502", "not_null_violation")):
            with self.subTest(sqlstate=sqlstate):
                with self.assertRaises(BusinessRuleError) as ctx:
                    with self.service.transaction():
                        raise integrity_error(sqlstate, "CK_X")
                self.assertEqual(ctx.exception.code, code)

    def test_unknown_integrity_error_is_reraised_after_rollback(self):
        before = self.session.rollbacks
        with self.assertRaises(IntegrityError):
            with self.service.transaction():
                raise integrity_error("99999", None)
        self.assertEqual(self.session.rollbacks, before + 1)

    def test_integrity_error_in_nested_use_case_is_mapped_only_once_by_outermost(self):
        with self.assertRaises(ConflictError):
            with self.service.transaction():
                with self.service.transaction():
                    raise integrity_error("23505", "UQ_Users_PhoneNumber")
        self.assertEqual(self.session.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
