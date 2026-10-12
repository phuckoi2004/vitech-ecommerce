"""Merged account regressions for the chosen Phase 5 OTP and Admin policies.

Uses isolated SQLite and memory auth state. Phase 4 account APIs were replaced
by AuthService/UserService; address and notification domain tests remain separate.
"""

import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.core.auth_state import MemoryStateStore
from app.core.config import AuthSettings
from app.core.errors import AuthError
from app.core.security import decode_access_token, hash_password, verify_password
from app.core.sessions import SessionManager
from app.models import User
from app.schemas.account import InternalUserCreate, ManagedUserUpdate
from app.schemas.auth import EmailChangeRequest, LoginRequest, RegistrationRequest
from app.services import UserService
from app.services.auth import AuthService


PASSWORD = "Password7!"


class Clock:
    def __init__(self):
        self.value = time.time()

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class RecordingMailer:
    def __init__(self):
        self.sent = []

    def send_otp(self, email, code, purpose, ttl):
        self.sent.append((email, code, purpose, ttl))

    @property
    def code(self):
        return self.sent[-1][1]


class AccountPolicyTestBase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def sqlite_defaults(connection, _):
            connection.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)
            connection.create_function("now", 0, lambda: datetime.now(timezone.utc).isoformat())

        # No OtpChallenges table: the chosen Auth workflow uses state + Users.
        User.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.clock = Clock()
        settings = AuthSettings(jwt_secret="merged-account-test-key-" * 3, app_env="test")
        state = MemoryStateStore(self.clock)
        mailer = RecordingMailer()
        self.runtime = SimpleNamespace(
            settings=settings, state=state, mailer=mailer,
            sessions=SessionManager(state, settings, self.clock),
            dummy_password_hash=hash_password(PASSWORD),
        )
        self.auth = AuthService(self.db, self.runtime, self.clock)
        self.accounts = UserService(self.db, self.runtime)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def assert_error(self, status, function, *args):
        with self.assertRaises(AuthError) as raised:
            function(*args)
        self.assertEqual(raised.exception.status_code, status)
        return raised.exception

    def registration(self, email="customer@example.com", phone="0912345678"):
        return RegistrationRequest(Email=email, PhoneNumber=phone, FullName="Khách hàng",
                                   Password=PASSWORD, ConfirmPassword=PASSWORD)

    def signup(self):
        challenge = self.auth.register(self.registration())
        return self.auth.verify_registration(challenge["challenge_id"], self.runtime.mailer.code)

    def seed_user(self, role):
        identity = uuid.uuid4()
        user = User(UserId=identity, FullName=role, Email=f"{identity.hex}@example.com",
                    PhoneNumber=f"09{str(identity.int)[-8:]}", PasswordHash=hash_password(PASSWORD),
                    Role=role, AccountStatus="Active", IsEmailVerified=True, IsDeleted=False)
        self.db.add(user)
        self.db.commit()
        return user


class OtpPolicyTest(AccountPolicyTestBase):
    def test_signup_resend_preserves_partial_failure_counter(self):
        with patch("app.services.auth.secrets.randbelow", return_value=123456):
            first = self.auth.register(self.registration())
            for _ in range(3):
                self.assert_error(400, self.auth.verify_registration, first["challenge_id"], "000000")
            self.clock.advance(60)
            latest = self.auth.resend(first["challenge_id"])
            self.assert_error(400, self.auth.verify_registration, latest["challenge_id"], "000000")
            error = self.assert_error(429, self.auth.verify_registration, latest["challenge_id"], "000000")
            self.assertEqual(error.headers["Retry-After"], "180")
            self.assert_error(429, self.auth.verify_registration, latest["challenge_id"], "123456")
            self.assert_error(429, self.auth.resend, latest["challenge_id"])
            self.assertIsNone(self.db.scalar(select(User)))
            self.clock.advance(180)
            fresh = self.auth.resend(latest["challenge_id"])
            user = self.auth.verify_registration(fresh["challenge_id"], "123456")
            self.assertEqual(user.Role, "Customer")
            self.assertTrue(user.IsEmailVerified)

    def test_reset_and_email_change_same_code_cannot_verify_other_purpose(self):
        user = self.signup()
        with patch("app.services.auth.secrets.randbelow", return_value=123456):
            reset = self.auth.forgot_password(user.Email)
            email_change = self.auth.request_email_change(
                user, EmailChangeRequest(Email="new@example.com", CurrentPassword=PASSWORD))
            # The shared Users OTP slot is bound to purpose, recipient and challenge.
            error = self.assert_error(400, self.auth.verify_reset, reset["challenge_id"], "123456")
            self.assertNotIn("123456", str(error))
            self.assertEqual(user.Email, "customer@example.com")
            self.auth.verify_email_change(user, email_change["challenge_id"], "123456")
            self.assertEqual(user.Email, "new@example.com")
            self.assertIsNone(user.OtpCode)
            self.assertIsNone(user.OtpExpiredAt)
            self.assert_error(400, self.auth.verify_reset, reset["challenge_id"], "123456")

    def test_one_signup_lock_does_not_block_another_customer(self):
        with patch("app.services.auth.secrets.randbelow", return_value=123456):
            blocked = self.auth.register(self.registration())
            for _ in range(4):
                self.assert_error(400, self.auth.verify_registration, blocked["challenge_id"], "000000")
            self.assert_error(429, self.auth.verify_registration, blocked["challenge_id"], "000000")
            other = self.auth.register(self.registration("other@example.com", "0987654321"))
            user = self.auth.verify_registration(other["challenge_id"], "123456")
            self.assertEqual(user.Email, "other@example.com")
            self.assert_error(429, self.auth.verify_registration, blocked["challenge_id"], "123456")


class AdminPolicyTest(AccountPolicyTestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.seed_user("Admin")

    def create_staff(self):
        return self.accounts.create_user(self.admin, InternalUserCreate(
            Email="staff@example.com", PhoneNumber="0987654321", FullName="Nhân viên",
            Password=PASSWORD, ConfirmPassword=PASSWORD))

    def login_staff(self, staff):
        return self.auth.login(LoginRequest(Identifier=staff.Email, Password=PASSWORD, Portal="admin"))[0]

    def assert_revoked(self, tokens, user):
        self.assert_error(401, self.runtime.sessions.validate_access,
                          decode_access_token(tokens.access_token, self.runtime.settings), user)

    def test_admin_created_staff_uses_internal_auth_without_registration_otp(self):
        staff = self.create_staff()
        self.assertTrue(staff.IsEmailVerified)
        self.assertEqual(self.runtime.mailer.sent, [])
        self.assertTrue(verify_password(PASSWORD, staff.PasswordHash))
        tokens = self.login_staff(staff)
        self.runtime.sessions.validate_access(decode_access_token(tokens.access_token, self.runtime.settings), staff)
        self.assert_error(403, self.auth.login,
                          LoginRequest(Identifier=staff.Email, Password=PASSWORD, Portal="customer"))
        # Internal users imported with unverified email keep the chosen login policy.
        staff.IsEmailVerified = False
        self.db.commit()
        self.login_staff(staff)

    def test_deleting_staff_clears_pending_otp_and_revokes_all_devices(self):
        staff = self.create_staff()
        devices = [self.login_staff(staff), self.login_staff(staff)]
        challenge = self.auth.forgot_password(staff.Email)
        code = self.runtime.mailer.code
        self.assertIsNotNone(staff.OtpCode)
        self.accounts.delete_user(self.admin, staff.UserId)
        self.assertTrue(staff.IsDeleted)
        self.assertIsNone(staff.OtpCode)
        self.assertIsNone(staff.OtpExpiredAt)
        self.assert_error(400, self.auth.verify_reset, challenge["challenge_id"], code)
        for tokens in devices:
            self.assert_revoked(tokens, staff)
        self.assert_error(401, self.auth.login,
                          LoginRequest(Identifier=staff.Email, Password=PASSWORD, Portal="admin"))

    def test_lock_then_unlock_keeps_previous_staff_sessions_revoked(self):
        staff = self.create_staff()
        tokens = self.login_staff(staff)
        self.accounts.update_user(self.admin, staff.UserId, ManagedUserUpdate(
            AccountStatus="Locked", LockReason="Kiểm thử",
            LockedUntil=datetime.now(timezone.utc) + timedelta(minutes=5)))
        self.assert_error(403, self.auth.login,
                          LoginRequest(Identifier=staff.Email, Password=PASSWORD, Portal="admin"))
        self.accounts.update_user(self.admin, staff.UserId, ManagedUserUpdate(AccountStatus="Active"))
        self.assert_revoked(tokens, staff)
        self.login_staff(staff)

    def test_admin_peer_is_protected_even_with_multiple_active_admins(self):
        peer = self.seed_user("Admin")
        own_session = self.runtime.sessions.issue(self.admin, "admin")
        peer_session = self.runtime.sessions.issue(peer, "admin")
        for target in (self.admin, peer):
            self.assert_error(403, self.accounts.delete_user, self.admin, target.UserId)
            self.assert_error(403, self.accounts.update_user, self.admin, target.UserId,
                              ManagedUserUpdate(FullName="Changed"))
        for user, tokens in ((self.admin, own_session), (peer, peer_session)):
            self.assertFalse(user.IsDeleted)
            self.assertEqual(user.AccountStatus, "Active")
            self.runtime.sessions.validate_access(decode_access_token(tokens.access_token, self.runtime.settings), user)


if __name__ == "__main__":
    unittest.main()
