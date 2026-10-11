"""Account authorization tests against an isolated SQLite Users table."""

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import get_args
from unittest.mock import Mock, patch

from pydantic import ValidationError
from sqlalchemy import MetaData, create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.rbac import (
    ACTIONS, ADMIN_FUNCTIONS, ROLE_PERMISSIONS, has_permission, permissions_for,
)
from app.core.security import verify_password
from app.models import User
from app.schemas.account import InternalUserCreate, ManagedUserUpdate, ProfileUpdate
from app.schemas.auth import normalize_phone_number
from app.schemas.common import UserRole
from app.schemas.user import AdminUserCreate, AdminUserResponse, AdminUserUpdate, UserResponse
from app.services.user import UserService


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        # Keep production models intact. SQLite only needs this table and portable defaults.
        metadata = MetaData()
        table = User.__table__.to_metadata(metadata)
        for column in table.columns:
            if column.name == "UserId":
                column.server_default = None
            elif column.name in {"CreatedAt", "UpdatedAt"}:
                from sqlalchemy import DefaultClause
                column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
        metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.runtime = SimpleNamespace(sessions=Mock())
        self.service = UserService(self.db, self.runtime)
        self.admin = self.add_user("Admin")
        self.staff = self.add_user("Staff")
        self.customer = self.add_user("Customer")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_user(self, role):
        identity = uuid.uuid4()
        user = User(UserId=identity, FullName=f"Test {role}", Email=f"{identity}@example.com",
                    PhoneNumber=f"{identity.hex[:20]}", PasswordHash="test-hash",
                    Role=role, AccountStatus="Active", IsEmailVerified=True,
                    TotalSpent=Decimal("0"), TotalOrders=0, IsDeleted=False)
        self.db.add(user)
        self.db.commit()
        return user

    def assert_auth_error(self, code, fn, *args, **kwargs):
        with self.assertRaises(AuthError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.status_code, code)

    def test_role_permissions_follow_report_tables(self):
        self.assertEqual(set(ROLE_PERMISSIONS), {"Customer", "Staff", "Admin"})
        self.assertEqual(set(get_args(UserRole)), {"Customer", "Staff", "Admin"})
        # Admin holds every Staff permission, including replying to chats (B3.37).
        self.assertLessEqual(ROLE_PERMISSIONS["Staff"], ROLE_PERMISSIONS["Admin"])
        for role in ("Staff", "Admin"):
            for permission in ("chat:create", "chat:view", "purchases:view", "purchases:create",
                               "purchase_history:view", "suppliers:view", "orders:update"):
                self.assertTrue(has_permission(role, permission), (role, permission))
        for permission in ("purchases:update", "purchases:delete", "products:create",
                           "promotions:view", "suppliers:create", "payment_methods:update",
                           "inventory:update", "users:manage"):
            self.assertFalse(has_permission("Staff", permission), permission)
            self.assertTrue(has_permission("Admin", permission), permission)
        # Decisions of 09/10/2026: refunds for Staff and Admin, exports for Admin only.
        for action in ("view", "create", "update", "delete"):
            self.assertTrue(has_permission("Staff", f"refunds:{action}"))
        for function in ADMIN_FUNCTIONS:
            self.assertFalse(has_permission("Staff", f"{function}:export"), function)
            for action in ACTIONS:
                self.assertTrue(has_permission("Admin", f"{function}:{action}"), (function, action))
        self.assertFalse(has_permission("Customer", "admin.portal"))
        self.assertEqual(permissions_for("unknown"), [])

    def test_admin_cannot_promote_or_touch_peers_and_self(self):
        self.assert_auth_error(403, self.service.update_user, self.admin, self.staff.UserId,
                               ManagedUserUpdate(Role="Admin"))
        for target in (self.admin, self.add_user("Admin")):
            self.assert_auth_error(403, self.service.update_user, self.admin, target.UserId,
                                   ManagedUserUpdate(FullName="Changed"))
            self.assert_auth_error(403, self.service.delete_user, self.admin, target.UserId)
        self.assertEqual(self.staff.Role, "Staff")
        self.runtime.sessions.revoke_user.assert_not_called()

    def test_admin_cannot_cross_customer_staff_boundary_and_role_noop_is_safe(self):
        for target, new_role in ((self.staff, "Customer"), (self.customer, "Staff"), (self.customer, "Admin")):
            self.assert_auth_error(403, self.service.update_user, self.admin, target.UserId,
                                   ManagedUserUpdate(Role=new_role))
        result = self.service.update_user(self.admin, self.staff.UserId,
                                          ManagedUserUpdate(Role="Staff", FullName="Updated Staff"))
        self.assertEqual(result.Role, "Staff")
        self.assertEqual(result.FullName, "Updated Staff")
        self.runtime.sessions.revoke_user.assert_not_called()

    def test_admin_list_is_limited_to_customer_and_staff_with_correct_pagination(self):
        self.add_user("Admin")
        page = self.service.list_users(self.admin, page_size=1)
        self.assertEqual(page.Total, 2)
        self.assertEqual(len(page.Items), 1)
        self.assertIn(page.Items[0].Role, {"Customer", "Staff"})
        filtered = self.service.list_users(self.admin, role="Customer")
        self.assertEqual(filtered.Total, 1)
        self.assertEqual(filtered.Items[0].UserId, self.customer.UserId)
        self.assert_auth_error(403, self.service.list_users, self.admin, role="Admin")

    def test_admin_views_customer_or_staff_detail_but_not_admins_or_deleted(self):
        self.assertEqual(self.service.get_user(self.admin, self.staff.UserId).UserId, self.staff.UserId)
        self.assertEqual(self.service.get_user(self.admin, self.customer.UserId).Role, "Customer")
        for target in (self.admin, self.add_user("Admin")):
            self.assert_auth_error(404, self.service.get_user, self.admin, target.UserId)
        self.assert_auth_error(404, self.service.get_user, self.admin, uuid.uuid4())
        for actor in (self.staff, self.customer):
            self.assert_auth_error(403, self.service.get_user, actor, self.customer.UserId)
        self.service.delete_user(self.admin, self.customer.UserId)
        self.assert_auth_error(404, self.service.get_user, self.admin, self.customer.UserId)
        self.assertTrue(self.service.get_user(self.admin, self.customer.UserId, include_deleted=True).IsDeleted)

    def test_staff_and_customer_cannot_manage_accounts(self):
        for actor in (self.staff, self.customer):
            self.assert_auth_error(403, self.service.list_users, actor)
            self.assert_auth_error(403, self.service.delete_user, actor, self.customer.UserId)

    def test_database_rejects_unknown_roles_and_rollback_retains_existing_accounts(self):
        existing_ids = set(self.db.scalars(select(User.UserId)))
        with self.assertRaises(IntegrityError):
            self.add_user("Owner")
        self.db.rollback()
        self.assertEqual(set(self.db.scalars(select(User.UserId))), existing_ids)
        self.assertEqual({user.Role for user in self.db.scalars(select(User))},
                         {"Customer", "Staff", "Admin"})

    def test_database_enforces_account_status_on_updates_and_inserts(self):
        for status in ("Locked", "Active"):
            self.customer.AccountStatus = status
            self.db.commit()
            self.db.refresh(self.customer)
            self.assertEqual(self.customer.AccountStatus, status)

        for status in ("UnexpectedStatus", "", "active", "LOCKED"):
            with self.subTest(status=status):
                self.customer.AccountStatus = status
                with self.assertRaises(IntegrityError):
                    self.db.commit()
                self.db.rollback()
                self.assertEqual(self.customer.AccountStatus, "Active")

        existing_ids = set(self.db.scalars(select(User.UserId)))
        identity = uuid.uuid4()
        invalid = User(UserId=identity, FullName="Invalid status", Email=f"{identity}@example.com",
                       PhoneNumber=identity.hex[:20], PasswordHash="test-hash", Role="Customer",
                       AccountStatus="UnexpectedStatus", IsEmailVerified=True, IsDeleted=False)
        self.db.add(invalid)
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(set(self.db.scalars(select(User.UserId))), existing_ids)

    def test_lock_requires_future_deadline_and_revokes_sessions(self):
        self.assert_auth_error(422, self.service.update_user, self.admin, self.staff.UserId,
                               ManagedUserUpdate(AccountStatus="Locked"))
        self.assert_auth_error(422, self.service.update_user, self.admin, self.staff.UserId,
                               ManagedUserUpdate(AccountStatus="Locked", LockReason="Policy",
                                                 LockedUntil=datetime.now(timezone.utc) - timedelta(seconds=1)))
        result = self.service.update_user(self.admin, self.staff.UserId,
                                         ManagedUserUpdate(AccountStatus="Locked", LockReason="Policy",
                                                           LockedUntil=datetime.now(timezone.utc) + timedelta(hours=1)))
        self.assertEqual(result.AccountStatus, "Locked")
        self.runtime.sessions.revoke_user.assert_called_with(self.staff.UserId)
        result = self.service.update_user(self.admin, self.staff.UserId, ManagedUserUpdate(AccountStatus="Active"))
        self.assertEqual(result.AccountStatus, "Active")
        self.assertIsNone(result.LockedUntil)
        self.assertIsNone(result.LockReason)

    def test_state_failure_prevents_account_mutation(self):
        self.runtime.sessions.revoke_user.side_effect = AuthError(503, "Unavailable")
        self.assert_auth_error(503, self.service.delete_user, self.admin, self.customer.UserId)
        self.assertFalse(self.customer.IsDeleted)
        self.assert_auth_error(503, self.service.update_user, self.admin, self.staff.UserId,
                               ManagedUserUpdate(AccountStatus="Locked", LockReason="Policy",
                                                 LockedUntil=datetime.now(timezone.utc) + timedelta(hours=1)))
        self.assertEqual(self.staff.AccountStatus, "Active")

    def test_delete_is_soft_hides_from_list_and_retains_unique_phone(self):
        self.service.delete_user(self.admin, self.customer.UserId)
        self.assertTrue(self.db.get(User, self.customer.UserId).IsDeleted)
        self.runtime.sessions.revoke_user.assert_called_with(self.customer.UserId)
        page = self.service.list_users(self.admin)
        self.assertEqual(page.Total, 1)
        self.assertNotIn(self.customer.UserId, {item.UserId for item in page.Items})
        self.assertEqual(self.service.list_users(self.admin, include_deleted=True).Total, 2)
        self.assert_auth_error(404, self.service.delete_user, self.admin, self.customer.UserId)

    def test_list_searches_name_email_phone_and_filters_deleted_only(self):
        self.customer.FullName, self.customer.PhoneNumber = "Nguyễn Minh Anh", "0901234567"
        self.staff.FullName, self.staff.Email = "Trần Quốc Huy", "huy.tran@vietech.vn"
        self.db.commit()
        def found(**filters):
            return {item.UserId for item in self.service.list_users(self.admin, **filters).Items}
        self.assertEqual(found(search="minh anh"), {self.customer.UserId})
        self.assertEqual(found(search="HUY.TRAN@"), {self.staff.UserId})
        self.assertEqual(found(search="0901 234"), {self.customer.UserId})
        self.assertEqual(found(search="+84 901 234 567"), {self.customer.UserId})
        self.assertEqual(found(search="0084 901 234 567"), {self.customer.UserId})
        self.assertEqual(found(search="00 84 (901) 234-567"), {self.customer.UserId})
        # LIKE wildcards are literal text, and an Admin never matches.
        self.assertEqual(found(search="%"), set())
        self.assertEqual(found(search=self.admin.FullName), set())
        self.assertEqual(found(search="   "), {self.customer.UserId, self.staff.UserId})
        self.service.delete_user(self.admin, self.customer.UserId)
        self.assertEqual(found(deleted_only=True), {self.customer.UserId})
        self.assertEqual(found(deleted_only=True, search="huy"), set())
        self.assertEqual(found(), {self.staff.UserId})

    def test_profile_ignores_no_unapproved_fields_and_serialization_is_safe(self):
        for payload in ({"Role": "Admin"}, {"Email": "new@example.com"}, {"IsDeleted": True},
                        {"FullName": None}, {}, {"FullName": "   "}):
            with self.assertRaises(ValidationError):
                ProfileUpdate(**payload)
        result = self.service.update_profile(self.customer, ProfileUpdate(FullName="  New name  ", Gender=None))
        self.assertEqual(result.FullName, "New name")
        serialized = UserResponse.model_validate(result).model_dump()
        self.assertNotIn("PasswordHash", serialized)
        self.assertNotIn("OtpCode", serialized)
        serialized = AdminUserResponse.model_validate(result).model_dump()
        self.assertNotIn("PasswordHash", serialized)
        self.assertNotIn("OtpExpiredAt", serialized)

    def test_admin_can_create_staff_only(self):
        payload = dict(Email="new@example.com", PhoneNumber="0912345678", FullName="New staff",
                       Password="ABCDEF1!", ConfirmPassword="ABCDEF1!")
        for role in ("Admin", "Customer", "Owner"):
            with self.assertRaises(ValidationError):
                InternalUserCreate(**payload, Role=role)
            with self.assertRaises(ValidationError):
                AdminUserCreate(**{key: value for key, value in payload.items() if key != "ConfirmPassword"},
                                Role=role, AccountStatus="Active")
            # The service remains safe for internal callers bypassing request validation.
            self.assert_auth_error(403, self.service.create_user, self.admin,
                                   InternalUserCreate.model_construct(**payload, Role=role))
        with self.assertRaises(ValidationError):
            AdminUserUpdate(Role="Admin")
        with self.assertRaises(ValidationError):
            InternalUserCreate(**{**payload, "ConfirmPassword": "different1!"})
        user = self.service.create_user(self.admin, InternalUserCreate(**payload))
        self.assertEqual(user.Role, "Staff")
        self.assertEqual(user.AccountStatus, "Active")
        self.assertTrue(user.IsEmailVerified)
        self.assertTrue(verify_password(payload["Password"], user.PasswordHash))
        self.assertNotEqual(user.PasswordHash, payload["Password"])

    def test_conflicting_phone_is_rejected_without_changing_profile(self):
        normalized_phone = normalize_phone_number("0912345678")
        self.staff.PhoneNumber = normalized_phone
        self.db.commit()
        self.assert_auth_error(409, self.service.update_profile, self.customer,
                               ProfileUpdate(PhoneNumber="0912345678"))
        self.assertNotEqual(self.customer.PhoneNumber, normalized_phone)

    def test_database_conflict_rolls_back_and_hides_raw_exception(self):
        original_name = self.customer.FullName
        conflict = IntegrityError("sensitive SQL", {}, Exception("private database detail"))
        with patch.object(self.db, "commit", side_effect=conflict):
            with self.assertRaises(AuthError) as caught:
                self.service.update_profile(self.customer, ProfileUpdate(FullName="Changed"))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertNotIn("private database detail", str(caught.exception))
        self.assertEqual(self.customer.FullName, original_name)


if __name__ == "__main__":
    unittest.main()
