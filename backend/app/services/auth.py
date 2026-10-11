"""Auth workflows; SQL transactions stay here.

An existing account's pending OTP lives in Users.OtpCode (truncated digest only) and
Users.OtpExpiredAt; signup has no Users row yet, so its OTP stays in the state store.
Counters, cooldowns and challenge payloads always stay in the state store.
"""

import hmac
import math
import secrets
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.core.errors import AuthError
from app.core.security import hash_password, otp_digest, secret_digest, verify_password
from app.models import User
from app.repositories.user import UserRepository


def ensure_active_user(user, db, *, commit_unlock=True):
    if user is None or user.IsDeleted:
        raise AuthError(401, "Tài khoản không khả dụng", {"WWW-Authenticate": "Bearer"})
    if user.AccountStatus == "Locked":
        until = user.LockedUntil
        if until is not None:
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until <= datetime.now(timezone.utc):
                # Re-read under a row lock: a concurrent admin may have extended the lock.
                user = UserRepository(db).get_by_id_for_update(user.UserId)
                until = user.LockedUntil
                if until and until.tzinfo is None:
                    until = until.replace(tzinfo=timezone.utc)
                if user.AccountStatus == "Locked" and until and until <= datetime.now(timezone.utc):
                    user.AccountStatus, user.LockedUntil, user.LockReason = "Active", None, None
                    if commit_unlock:
                        db.commit()
        if user.AccountStatus == "Locked":
            raise AuthError(403, "Tài khoản đang bị khóa")
    if user.IsDeleted or user.AccountStatus != "Active":
        raise AuthError(403, "Tài khoản không hoạt động")
    return user


# Users.OtpCode is varchar(10): keep the first 10 hex chars (40 bits) of the HMAC.
# Without the server secret this reveals nothing, and a wrong code matches with
# probability 2^-40, far below guessing one of the 10^6 codes.
OTP_DIGEST_LENGTH = 10


def _otp_digest(code, settings, challenge_id, record):
    # A user's single OTP column must identify the exact request and recipient,
    # even when two requests happen to generate the same six-digit code.
    owner = record["payload"].get("user_id", record["identity"])
    bound_code = "\x00".join((challenge_id, owner, record["email"], code))
    return otp_digest(bound_code, settings, record["purpose"])[:OTP_DIGEST_LENGTH]


def _as_utc(value):
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


class AuthService:
    def __init__(self, db, runtime, now=time.time):
        self.db, self.runtime, self.now = db, runtime, now
        self.repo = UserRepository(db)
        self.state, self.settings = runtime.state, runtime.settings

    def _identity(self, value):
        return secret_digest(str(value).lower(), self.settings, context="identity")

    def _stamp(self, user):
        return secret_digest(user.PasswordHash + "|" + user.Email, self.settings, context="otp-user")

    def _user_by_identifier(self, identifier):
        return self.repo.get_by_email(identifier) if "@" in identifier else self.repo.get_by_phone(identifier)

    def _check_attempts(self, key):
        record = self.state.get(key) or {}
        remaining = math.ceil(record.get("blocked_until", 0) - self.now())
        if remaining > 0:
            raise AuthError(429, "Thử sai quá nhiều lần. Vui lòng thử lại sau 3 phút", {"Retry-After": str(remaining)})

    def _fail_attempt(self, key, message):
        record = self.state.get(key) or {}
        if self.now() - record.get("window_start", 0) >= self.settings.failure_window:
            record = {"window_start": self.now(), "count": 0}
        record["count"] = record.get("count", 0) + 1
        if record["count"] >= self.settings.failure_limit:
            record["blocked_until"] = self.now() + self.settings.block_ttl
            # Start a new counter after the blocking period; resends never clear this record.
            record["count"] = 0
        self.state.put(key, record, self.settings.failure_window + self.settings.block_ttl)
        self._check_attempts(key)
        raise AuthError(400, message)

    def _send(self, purpose, email, payload, ttl):
        identity = self._identity(email)
        key = f"otp-rate:{purpose}:{identity}"
        with self.state.lock(key):
            self._check_attempts(key)
            sent = self.state.get(f"otp-send:{purpose}:{identity}")
            if sent:
                remaining = max(1, int(sent["until"] - self.now()) + 1)
                raise AuthError(429, "Vui lòng chờ trước khi yêu cầu mã mới", {"Retry-After": str(remaining)})
            quota_key = f"otp-quota:{purpose}:{identity}"
            quota = self.state.get(quota_key)
            if not quota or self.now() - quota["window_start"] >= self.settings.send_window:
                quota = {"window_start": self.now(), "count": 0}
            if quota["count"] >= self.settings.send_limit:
                remaining = max(1, math.ceil(quota["window_start"] + self.settings.send_window - self.now()))
                raise AuthError(429, "Đã gửi mã quá số lần cho phép. Vui lòng thử lại sau",
                                {"Retry-After": str(remaining)})
            challenge_id = uuid.uuid4().hex
            code = f"{secrets.randbelow(1_000_000):06d}"
            record = {"purpose": purpose, "email": email, "identity": identity, "payload": payload,
                      "expires_at": self.now() + ttl, "created_at": self.now(), "sent_at": self.now()}
            digest = _otp_digest(code, self.settings, challenge_id, record)
            self.runtime.mailer.send_otp(email, code, purpose, ttl)
            if "user_id" in payload:
                self._store_user_otp(payload["user_id"], digest, record["expires_at"])
            else:
                record["digest"] = digest
            self.state.put(f"challenge:{challenge_id}", record, 1800)
            self.state.put(f"otp-send:{purpose}:{identity}", {"until": self.now() + self.settings.resend_interval}, self.settings.resend_interval)
            # Count only emails that were actually sent; the window starts at the first send.
            quota["count"] += 1
            self.state.put(quota_key, quota,
                           max(1, math.ceil(quota["window_start"] + self.settings.send_window - self.now())))
            # Only the newest challenge for this identity/purpose can be used.
            self.state.put(f"otp-current:{purpose}:{identity}", {"id": challenge_id}, 1800)
        return {"message": "Đã gửi mã xác minh qua email", "challenge_id": challenge_id,
                "expires_in": max(0, math.ceil(record["expires_at"] - self.now())),
                "resend_after": self.settings.resend_interval}

    def _store_user_otp(self, user_id, digest, expires_at):
        # One row holds one pending code: a newer OTP of any purpose replaces it.
        # The digest binds the purpose, recipient and challenge, so the latest
        # code cannot verify an older request for this account.
        user = self.repo.get_by_id_for_update(uuid.UUID(user_id))
        if user is None or user.IsDeleted:
            self.db.rollback()
            raise AuthError(400, "Tài khoản không khả dụng")
        user.OtpCode = digest
        user.OtpExpiredAt = datetime.fromtimestamp(expires_at, timezone.utc)
        self.db.commit()

    def _challenge(self, challenge_id, purpose=None):
        record = self.state.get(f"challenge:{challenge_id}")
        if not record or (purpose and record["purpose"] != purpose):
            raise AuthError(400, "Mã xác minh không hợp lệ hoặc đã hết hạn")
        current = self.state.get(f"otp-current:{record['purpose']}:{record['identity']}")
        if not current or current["id"] != challenge_id:
            raise AuthError(400, "Mã xác minh đã được thay thế hoặc đã sử dụng")
        return record

    def _verify(self, challenge_id, code, purpose):
        record = self._challenge(challenge_id, purpose)
        key = f"otp-rate:{purpose}:{record['identity']}"
        self._check_attempts(key)
        user = None
        expired = record["expires_at"] <= self.now()
        if "user_id" in record["payload"]:
            # The row stays locked until the caller commits, so a code is consumed once.
            user = self.repo.get_by_id_for_update(uuid.UUID(record["payload"]["user_id"]))
            digest = user.OtpCode if user else None
            # Compare as datetimes: both sides get the same microsecond rounding.
            expired = expired or (user is None or user.OtpExpiredAt is None
                       or _as_utc(user.OtpExpiredAt) <= datetime.fromtimestamp(self.now(), timezone.utc))
        else:
            digest = record["digest"]
        if digest is None or expired:
            raise AuthError(400, "Mã OTP đã hết hạn hoặc đã được sử dụng. Vui lòng yêu cầu mã mới")
        if not hmac.compare_digest(digest, _otp_digest(code, self.settings, challenge_id, record)):
            self._fail_attempt(key, "Mã OTP không chính xác")
        self.state.delete(key)
        return record, user

    @staticmethod
    def _clear_user_otp(user):
        user.OtpCode, user.OtpExpiredAt = None, None

    def _check_current_password(self, user, password):
        # Bounds guessing with a stolen access token; separate from the login counter.
        key = f"current-password:{user.UserId}"
        with self.state.lock(key):
            self._check_attempts(key)
            if not verify_password(password, user.PasswordHash):
                self._fail_attempt(key, "Mật khẩu hiện tại chưa chính xác")
            self.state.delete(key)

    def _commit(self):
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise AuthError(409, "Email hoặc số điện thoại đã được sử dụng") from None

    def register(self, payload):
        if self.repo.exists_by_email(payload.Email) or self.repo.exists_by_phone(payload.PhoneNumber):
            raise AuthError(409, "Email hoặc số điện thoại đã được sử dụng")
        data = {"Email": str(payload.Email), "PhoneNumber": payload.PhoneNumber, "FullName": payload.FullName,
                "PasswordHash": hash_password(payload.Password)}
        return self._send("signup", data["Email"], data, self.settings.signup_otp_ttl)

    def verify_registration(self, challenge_id, code):
        record = self._challenge(challenge_id, "signup")
        with self.state.lock(f"otp-rate:signup:{record['identity']}"):
            record, _ = self._verify(challenge_id, code, "signup")
            data = record["payload"]
            if self.repo.exists_by_email(data["Email"]) or self.repo.exists_by_phone(data["PhoneNumber"]):
                raise AuthError(409, "Email hoặc số điện thoại đã được sử dụng")
            user = self.repo.create({**data, "Role": "Customer", "AccountStatus": "Active", "IsEmailVerified": True})
            self._commit()
            self.state.delete(f"challenge:{challenge_id}")
        return user

    def resend(self, challenge_id):
        record = self._challenge(challenge_id)
        purpose = record["purpose"]
        ttl = {"signup": self.settings.signup_otp_ttl, "password_reset": self.settings.reset_otp_ttl,
               "email_change": self.settings.email_otp_ttl}[purpose]
        return self._send(purpose, record["email"], record["payload"], ttl)

    def login(self, payload):
        user = self._user_by_identifier(payload.Identifier)
        if user is not None:
            user = self.repo.get_by_id_for_update(user.UserId)
        identity = self._identity(user.Email if user else payload.Identifier)
        key = f"login-rate:{identity}"
        with self.state.lock(key):
            self._check_attempts(key)
            valid = verify_password(payload.Password, user.PasswordHash if user else self.runtime.dummy_password_hash)
            if not valid or user is None or user.IsDeleted:
                try:
                    self._fail_attempt(key, "Email/số điện thoại hoặc mật khẩu chưa đúng")
                except AuthError as error:
                    if error.status_code == 400:
                        raise AuthError(401, error.message, {"WWW-Authenticate": "Bearer"}) from None
                    raise
            # Signing in never requires email verification: customers verify at signup, and staff
            # created by an Admin can sign in at once (decision 09/10/2026).
            user = ensure_active_user(user, self.db, commit_unlock=False)
            tokens = self.runtime.sessions.issue(user, payload.Portal)
            self.state.delete(key)
            self.db.commit()
        return tokens, user

    def refresh(self, token):
        def load_user(user_id):
            return ensure_active_user(self.repo.get_by_id(uuid.UUID(str(user_id))), self.db)
        tokens = self.runtime.sessions.refresh(token, load_user)
        from app.core.security import decode_access_token
        user = self.repo.get_by_id(uuid.UUID(decode_access_token(tokens.access_token, self.settings)["sub"]))
        return tokens, user

    def forgot_password(self, identifier):
        user = self._user_by_identifier(identifier)
        if user is None or user.IsDeleted:
            raise AuthError(404, "Email hoặc số điện thoại không tồn tại")
        return self._send("password_reset", user.Email, {"user_id": str(user.UserId), "stamp": self._stamp(user)}, self.settings.reset_otp_ttl)

    def verify_reset(self, challenge_id, code):
        record = self._challenge(challenge_id, "password_reset")
        with self.state.lock(f"otp-rate:password_reset:{record['identity']}"):
            record, user = self._verify(challenge_id, code, "password_reset")
            user = ensure_active_user(user, self.db, commit_unlock=False)
            if not hmac.compare_digest(self._stamp(user), record["payload"]["stamp"]):
                raise AuthError(400, "Thông tin tài khoản đã thay đổi. Vui lòng yêu cầu mã mới")
            self._clear_user_otp(user)
            self._commit()
            grant_id, secret = uuid.uuid4().hex, secrets.token_urlsafe(32)
            self.state.put(f"reset-grant:{grant_id}", {"user_id": str(user.UserId), "stamp": self._stamp(user),
                           "digest": secret_digest(secret, self.settings, context="reset-grant")}, self.settings.reset_grant_ttl)
            self.state.delete(f"challenge:{challenge_id}")
        return {"reset_token": f"{grant_id}.{secret}", "expires_in": self.settings.reset_grant_ttl}

    def reset_password(self, payload):
        try:
            grant_id, secret = payload.ResetToken.split(".", 1)
        except ValueError:
            raise AuthError(400, "Quyền đặt lại mật khẩu không hợp lệ") from None
        with self.state.lock(f"reset-grant:{grant_id}"):
            record = self.state.get(f"reset-grant:{grant_id}")
            if not record or not hmac.compare_digest(record["digest"], secret_digest(secret, self.settings, context="reset-grant")):
                raise AuthError(400, "Quyền đặt lại mật khẩu đã hết hạn hoặc đã sử dụng")
            user = ensure_active_user(self.repo.get_by_id_for_update(uuid.UUID(record["user_id"])), self.db, commit_unlock=False)
            if not hmac.compare_digest(self._stamp(user), record["stamp"]):
                raise AuthError(400, "Quyền đặt lại mật khẩu không còn hiệu lực")
            if verify_password(payload.NewPassword, user.PasswordHash):
                raise AuthError(400, "Mật khẩu mới phải khác mật khẩu cũ")
            user.PasswordHash, user.IsEmailVerified = hash_password(payload.NewPassword), True
            self.runtime.sessions.revoke_user(user.UserId)
            self._commit()
            self.state.delete(f"reset-grant:{grant_id}")

    def change_password(self, user, payload):
        user = ensure_active_user(self.repo.get_by_id_for_update(user.UserId), self.db, commit_unlock=False)
        self._check_current_password(user, payload.CurrentPassword)
        if verify_password(payload.NewPassword, user.PasswordHash):
            raise AuthError(400, "Mật khẩu mới phải khác mật khẩu cũ")
        user.PasswordHash = hash_password(payload.NewPassword)
        self.runtime.sessions.revoke_user(user.UserId)
        self._commit()

    def request_email_change(self, user, payload):
        self._check_current_password(user, payload.CurrentPassword)
        if self.repo.exists_by_email(payload.Email):
            raise AuthError(409, "Email đã được sử dụng")
        return self._send("email_change", str(payload.Email), {"user_id": str(user.UserId), "stamp": self._stamp(user)}, self.settings.email_otp_ttl)

    def verify_email_change(self, user, challenge_id, code):
        record = self._challenge(challenge_id, "email_change")
        if record["payload"]["user_id"] != str(user.UserId):
            raise AuthError(403, "Không có quyền xác minh yêu cầu này")
        with self.state.lock(f"otp-rate:email_change:{record['identity']}"):
            record, user = self._verify(challenge_id, code, "email_change")
            user = ensure_active_user(user, self.db, commit_unlock=False)
            if not hmac.compare_digest(record["payload"]["stamp"], self._stamp(user)):
                raise AuthError(400, "Thông tin tài khoản đã thay đổi. Vui lòng yêu cầu mã mới")
            if self.repo.exists_by_email(record["email"], exclude_user_id=user.UserId):
                raise AuthError(409, "Email đã được sử dụng")
            user.Email, user.IsEmailVerified = record["email"], True
            self._clear_user_otp(user)
            self.runtime.sessions.revoke_user(user.UserId)
            self._commit()
            self.state.delete(f"challenge:{challenge_id}")
