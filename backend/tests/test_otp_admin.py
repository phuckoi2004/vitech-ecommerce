"""OTP giới hạn tại Service và bảo vệ Admin (đợt 5.1 nhóm D).

Fake trong bộ nhớ: khóa dòng chỉ được ghi lại (db.locks); không chứng minh concurrency thật của PostgreSQL.
"""

import unittest
from datetime import timedelta
from unittest import mock

from app.models import OtpChallenge, User
from app.schemas import AdminUserUpdate, UserRegister
from app.services import BusinessRuleError, InvalidOtpError, TooManyRequestsError, UserService

from tests.fakes import NOW, FakeOtpChallengeRepo, FakeSession, FakeUserRepo, Factory, InMemoryDB


class StubHasher:
    def hash(self, password):
        return f"hashed:{password}"

    def verify(self, password, password_hash):
        return password_hash == f"hashed:{password}"


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send_registration_otp(self, email, otp_code):
        self.sent.append(("Registration", email, otp_code))

    def send_password_reset_otp(self, email, otp_code):
        self.sent.append(("PasswordReset", email, otp_code))

    def last(self, purpose):
        return [code for p, _, code in self.sent if p == purpose][-1]


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class SequentialDigits:
    """Thay ``secrets`` trong UserService: OTP lần lượt 111111, 222222, ... (xác định, không trùng nhau)."""

    def __init__(self) -> None:
        self.calls = 0

    def choice(self, alphabet):
        digit = str(self.calls // 6 % 9 + 1)
        self.calls += 1
        return digit


class UserTestBase(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch("app.services.user.secrets", SequentialDigits())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.clock = Clock()
        self.sender = RecordingSender()
        self.svc = UserService(self.session, password_hasher=StubHasher(), otp_sender=self.sender, clock=self.clock)
        self.svc.users = FakeUserRepo(self.db)
        self.svc.otp_challenges = FakeOtpChallengeRepo(self.db)


class OtpTest(UserTestBase):
    EMAIL = "khach@vietech.vn"

    def setUp(self) -> None:
        super().setUp()
        self.svc.register(UserRegister(Email=self.EMAIL, PhoneNumber="0901234567", Password="Secret#123", FullName="Khách"))
        self.user = [u for u in self.db.rows(User) if u.Email == self.EMAIL][0]

    def challenges(self, purpose="Registration"):
        return sorted((c for c in self.db.rows(OtpChallenge) if c.Purpose == purpose), key=lambda c: c.CreatedAt)

    def verify(self, code):
        return self.svc.verify_registration_otp(self.EMAIL, code)

    def wrong(self, times=1):
        for _ in range(times):
            with self.assertRaises((InvalidOtpError, TooManyRequestsError)) as ctx:
                self.verify("000000")  # mã sinh ra luôn gồm chữ số 1-9 (SequentialDigits)
        return ctx.exception

    def test_otp_is_hashed_and_purposes_are_separate(self):
        code = self.sender.last("Registration")
        self.assertEqual(code, "111111")
        [challenge] = self.challenges()
        self.assertEqual(challenge.CodeHash, "hashed:111111")  # lưu kết quả của PasswordHasher, không lưu mã gốc
        self.assertIsNone(self.user.OtpCode)  # không còn lưu OTP văn bản thuần ở Users
        with self.assertRaises(InvalidOtpError) as ctx:  # OTP đăng ký không đặt lại được mật khẩu
            self.svc.reset_password(self.EMAIL, code, "New#12345")
        self.assertEqual(ctx.exception.code, "otp_invalid")
        self.svc.request_password_reset(self.EMAIL)
        reset_code = self.sender.last("PasswordReset")
        self.assertEqual(reset_code, "222222")
        with self.assertRaises(InvalidOtpError) as ctx:  # và ngược lại
            self.verify(reset_code)
        self.assertEqual(ctx.exception.code, "otp_invalid")
        self.svc.reset_password(self.EMAIL, reset_code, "New#12345")
        self.assertEqual(self.user.PasswordHash, "hashed:New#12345")
        self.assertEqual(self.verify(code).IsEmailVerified, True)

    def test_otp_is_single_use_and_expires_after_five_minutes(self):
        code = self.sender.last("Registration")
        self.clock.advance(minutes=5)
        with self.assertRaises(InvalidOtpError) as ctx:
            self.verify(code)
        self.assertEqual(ctx.exception.code, "otp_expired")
        self.clock.advance(seconds=1)
        self.svc.resend_registration_otp(self.EMAIL)
        code = self.sender.last("Registration")
        self.clock.advance(minutes=4, seconds=59)
        self.verify(code)
        with self.assertRaises(BusinessRuleError):  # đã xác thực
            self.verify(code)
        self.svc.request_password_reset(self.EMAIL)
        reset_code = self.sender.last("PasswordReset")
        self.svc.reset_password(self.EMAIL, reset_code, "A#1234567")
        with self.assertRaises(InvalidOtpError) as ctx:  # không dùng lại OTP đã dùng
            self.svc.reset_password(self.EMAIL, reset_code, "B#1234567")
        self.assertEqual(ctx.exception.code, "otp_invalid")

    def test_five_wrong_attempts_lock_verification_and_sending_for_15_minutes(self):
        code = self.sender.last("Registration")
        for attempt in range(1, 5):
            self.assertEqual(self.wrong().code, "otp_invalid")
            self.assertEqual(self.challenges()[-1].FailedAttempts, attempt)  # đã ghi (commit) dù báo lỗi
        locked = self.wrong()
        self.assertIsInstance(locked, TooManyRequestsError)
        self.assertEqual((locked.code, locked.retry_after_seconds), ("otp_verification_locked", 900))
        with self.assertRaises(TooManyRequestsError) as ctx:  # mã đúng cũng bị chặn khi đang khóa
            self.verify(code)
        self.assertEqual(ctx.exception.code, "otp_verification_locked")
        self.clock.advance(minutes=10)
        with self.assertRaises(TooManyRequestsError) as ctx:  # chặn cả gửi OTP mới khi đang khóa
            self.svc.resend_registration_otp(self.EMAIL)
        self.assertEqual((ctx.exception.code, ctx.exception.retry_after_seconds), ("otp_verification_locked", 300))
        self.assertFalse(self.user.IsEmailVerified)
        self.clock.advance(minutes=5)
        self.svc.resend_registration_otp(self.EMAIL)
        self.assertEqual(self.challenges()[-1].FailedAttempts, 0)  # hết khóa: bắt đầu lại
        self.assertTrue(self.verify(self.sender.last("Registration")).IsEmailVerified)

    def test_resending_does_not_reset_failed_attempts(self):
        self.wrong(3)
        self.clock.advance(seconds=61)
        self.svc.resend_registration_otp(self.EMAIL)
        self.assertEqual(self.challenges()[-1].FailedAttempts, 3)
        self.assertEqual(self.wrong().code, "otp_invalid")
        self.assertEqual(self.wrong().code, "otp_verification_locked")  # lần sai thứ 5 tính cả trước khi gửi lại

    def test_failures_older_than_the_send_window_are_not_carried(self):
        self.wrong(3)
        self.clock.advance(hours=1, seconds=1)
        self.svc.resend_registration_otp(self.EMAIL)
        self.assertEqual(self.challenges()[-1].FailedAttempts, 0)

    def test_resend_needs_60_seconds(self):
        self.clock.advance(seconds=30)
        with self.assertRaises(TooManyRequestsError) as ctx:
            self.svc.resend_registration_otp(self.EMAIL)
        self.assertEqual((ctx.exception.code, ctx.exception.retry_after_seconds), ("otp_send_too_soon", 30))
        self.clock.advance(seconds=30)
        self.svc.resend_registration_otp(self.EMAIL)
        self.assertEqual(len(self.challenges()), 2)

    def test_at_most_five_sends_per_hour_per_account_and_purpose(self):
        for _ in range(4):
            self.clock.advance(seconds=61)
            self.svc.resend_registration_otp(self.EMAIL)
        self.clock.advance(seconds=61)
        with self.assertRaises(TooManyRequestsError) as ctx:
            self.svc.resend_registration_otp(self.EMAIL)
        self.assertEqual(ctx.exception.code, "otp_send_limit_exceeded")
        self.svc.request_password_reset(self.EMAIL)  # mục đích khác có giới hạn riêng
        self.clock.now = NOW + timedelta(hours=1, seconds=1)  # lần gửi đầu đã ra khỏi cửa sổ 1 giờ
        self.svc.resend_registration_otp(self.EMAIL)
        self.assertEqual(len(self.challenges()), 6)

    def test_send_and_verify_lock_the_user_row(self):
        self.db.locks.clear()
        self.clock.advance(seconds=61)
        self.svc.resend_registration_otp(self.EMAIL)
        self.assertIn(("User", self.user.UserId), self.db.locks)
        with self.assertRaises(TooManyRequestsError):  # yêu cầu đồng thời thứ hai (chạy sau khi có khóa) bị chặn
            self.svc.resend_registration_otp(self.EMAIL)
        self.assertEqual(len(self.challenges()), 2)

    def test_errors_never_contain_the_otp(self):
        code = self.sender.last("Registration")
        error = self.wrong()
        self.assertNotIn(code, str(error))
        self.clock.advance(minutes=6)
        with self.assertRaises(InvalidOtpError) as ctx:
            self.verify(code)
        self.assertNotIn(code, str(ctx.exception))


class AdminProtectionTest(UserTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.a = self.f.user("Admin")
        self.b = self.f.user("Admin")
        self.customer = self.f.user("Customer")

    def actor(self, user):
        return self.f.actor(user)

    def test_admin_cannot_lock_delete_or_demote_self(self):
        calls = [
            lambda: self.svc.lock_user(self.actor(self.a), self.a.UserId, reason="x"),
            lambda: self.svc.admin_delete_user(self.actor(self.a), self.a.UserId),
            lambda: self.svc.admin_update_user(self.actor(self.a), self.a.UserId, AdminUserUpdate(Role="Staff")),
            lambda: self.svc.admin_update_user(self.actor(self.a), self.a.UserId, AdminUserUpdate(AccountStatus="Locked")),
        ]
        for call in calls:
            with self.subTest(call=call), self.assertRaises(BusinessRuleError) as ctx:
                call()
            self.assertEqual(ctx.exception.code, "admin_self_change_not_allowed")
        self.assertEqual((self.a.Role, self.a.AccountStatus, self.a.IsDeleted), ("Admin", "Active", False))
        self.svc.admin_update_user(self.actor(self.a), self.a.UserId, AdminUserUpdate(Role="Admin"))  # không giảm quyền

    def test_admin_can_manage_another_admin_while_one_stays_active(self):
        self.svc.lock_user(self.actor(self.a), self.b.UserId, reason="Nghỉ việc")
        self.assertEqual(self.b.AccountStatus, "Locked")
        self.svc.unlock_user(self.actor(self.a), self.b.UserId)
        self.svc.admin_update_user(self.actor(self.a), self.b.UserId, AdminUserUpdate(Role="Staff"))
        self.assertEqual(self.b.Role, "Staff")

    def test_last_active_admin_is_protected(self):
        self.svc.lock_user(self.actor(self.a), self.b.UserId)  # còn A hoạt động
        # B đã bị khóa nhưng một yêu cầu của B vẫn tới (ví dụ phiên cũ): không được làm mất Admin cuối cùng (A).
        for call in (
            lambda: self.svc.lock_user(self.actor(self.b), self.a.UserId),
            lambda: self.svc.admin_delete_user(self.actor(self.b), self.a.UserId),
            lambda: self.svc.admin_update_user(self.actor(self.b), self.a.UserId, AdminUserUpdate(Role="Customer")),
        ):
            with self.subTest(call=call), self.assertRaises(BusinessRuleError) as ctx:
                call()
            self.assertEqual(ctx.exception.code, "last_active_admin")
        self.assertEqual((self.a.Role, self.a.AccountStatus, self.a.IsDeleted), ("Admin", "Active", False))

    def test_locked_or_deleted_admins_do_not_count_but_expired_locks_do(self):
        c = self.f.user("Admin")
        c.IsDeleted = True
        self.b.AccountStatus = "Locked"
        with self.assertRaises(BusinessRuleError) as ctx:
            self.svc.lock_user(self.actor(self.b), self.a.UserId)
        self.assertEqual(ctx.exception.code, "last_active_admin")
        self.b.LockedUntil = NOW - timedelta(minutes=1)  # khóa đã hết hạn: B được tính là đang hoạt động
        self.svc.lock_user(self.actor(self.b), self.a.UserId)
        self.assertEqual(self.a.AccountStatus, "Locked")

    def test_concurrent_mutual_lockout_keeps_one_admin(self):
        self.db.locks.clear()
        self.svc.lock_user(self.actor(self.a), self.b.UserId)
        admin_locks = [key for name, key in self.db.locks if name == "User"]
        self.assertEqual(admin_locks, sorted([self.a.UserId, self.b.UserId], key=str))  # khóa mọi Admin theo thứ tự
        with self.assertRaises(BusinessRuleError) as ctx:  # yêu cầu thứ hai chạy sau, thấy B đã bị khóa
            self.svc.lock_user(self.actor(self.b), self.a.UserId)
        self.assertEqual(ctx.exception.code, "last_active_admin")
        self.assertEqual([u.AccountStatus for u in (self.a, self.b)], ["Active", "Locked"])

    def test_non_admin_targets_skip_admin_locking(self):
        self.db.locks.clear()
        self.svc.lock_user(self.actor(self.a), self.customer.UserId)
        self.svc.admin_delete_user(self.actor(self.a), self.customer.UserId)
        self.assertEqual(self.db.locks, [])
        self.assertTrue(self.customer.IsDeleted)


if __name__ == "__main__":
    unittest.main()
