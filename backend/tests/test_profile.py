"""Profile page: avatar upload and default address."""

import unittest
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import ValidationError
from sqlalchemy import DefaultClause, MetaData, create_engine, text
from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.storage import AvatarStorage, detect_image_type
from app.models import Address, User
from app.schemas.account import DefaultAddressUpdate, ProfileUpdate
from app.services.user import UserService


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
STORAGE_PREFIX = "https://demo.supabase.co/storage/v1/object/public/avatars/"


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        metadata = MetaData()
        for model in (User, Address):
            table = model.__table__.to_metadata(metadata)
            for column in table.columns:
                if column.name in {"UserId", "AddressId"} and column.primary_key:
                    column.server_default = None
                elif column.name in {"CreatedAt", "UpdatedAt"}:
                    column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
        metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.service = UserService(self.db, SimpleNamespace(sessions=Mock()))
        identity = uuid.uuid4()
        self.user = User(UserId=identity, FullName="Khách VieTech", Email=f"{identity}@example.com",
                         PhoneNumber="0912345678", PasswordHash="test-hash", Role="Customer",
                         AccountStatus="Active", IsEmailVerified=True, TotalSpent=Decimal("0"),
                         TotalOrders=0, IsDeleted=False)
        self.db.add(self.user)
        self.db.commit()
        self.storage = AvatarStorage("https://demo.supabase.co", "service-key", "avatars")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_image_type_comes_from_file_signature(self):
        self.assertEqual(detect_image_type(PNG), "image/png")
        self.assertEqual(detect_image_type(b"\xff\xd8\xff\xe0rest"), "image/jpeg")
        self.assertEqual(detect_image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")
        self.assertIsNone(detect_image_type(b"<svg onload=alert(1)>"))

    def test_avatar_upload_saves_public_url_and_removes_only_our_previous_file(self):
        previous = f"{self.user.UserId}/{uuid.uuid4().hex}.png"
        self.user.AvatarUrl = self.storage.public_url(previous)
        self.db.commit()
        with patch.object(AvatarStorage, "_call") as call:
            user = self.service.update_avatar(self.user, PNG, self.storage)
        self.assertTrue(user.AvatarUrl.startswith(f"{STORAGE_PREFIX}{self.user.UserId}/"))
        self.assertTrue(user.AvatarUrl.endswith(".png"))
        self.assertEqual([c.args[0] for c in call.call_args_list], ["POST", "DELETE"])
        self.assertEqual(call.call_args_list[1].args[1], previous)

        self.user.AvatarUrl = "https://elsewhere.example/me.png"
        self.db.commit()
        with patch.object(AvatarStorage, "_call") as call:
            self.service.update_avatar(self.user, PNG, self.storage)
        self.assertEqual([c.args[0] for c in call.call_args_list], ["POST"])

    def test_customer_cannot_delete_foreign_or_noncanonical_avatar_urls(self):
        self.user.Role = "Customer"
        self.db.commit()
        owner, foreign, filename = self.user.UserId, uuid.uuid4(), f"{uuid.uuid4().hex}.png"
        unsafe_urls = (
            self.storage.public_url(f"{foreign}/{filename}"),
            self.storage.public_url(f"{owner}/../{foreign}/{filename}"),
            self.storage.public_url(f"{owner}/%2e%2e/{foreign}/{filename}"),
            self.storage.public_url(f"{owner}/%252e%252e/{foreign}/{filename}"),
            self.storage.public_url(f"{owner}%2f{filename}"),
            self.storage.public_url(f"{owner}/nested/{filename}"),
            self.storage.public_url(f"{owner}\\{filename}"),
            self.storage.public_url(f"{owner}/{filename}?download=1"),
            self.storage.public_url(f"{owner}/{filename}#image"),
            self.storage.public_url(f"{owner}/{filename}%00"),
            self.storage.public_url(f"{owner}/picture.png"),
            "https://elsewhere.example/me.png",
            "http://[invalid-url",
        )
        for avatar_url in unsafe_urls:
            with self.subTest(avatar_url=avatar_url):
                # This is the same editable field an authenticated client can PATCH.
                self.service.update_profile(self.user, ProfileUpdate(AvatarUrl=avatar_url))
                with patch.object(AvatarStorage, "_call") as call:
                    self.service.update_avatar(self.user, PNG, self.storage)
                self.assertEqual([c.args[0] for c in call.call_args_list], ["POST"])

    def test_avatar_refresh_failure_after_commit_keeps_the_saved_image(self):
        previous = f"{self.user.UserId}/{uuid.uuid4().hex}.png"
        self.user.AvatarUrl = self.storage.public_url(previous)
        self.db.commit()
        user_id = self.user.UserId
        failure = RuntimeError("database refresh unavailable")
        with patch.object(AvatarStorage, "_call") as call:
            with patch.object(self.db, "refresh", side_effect=failure):
                with self.assertRaises(RuntimeError) as caught:
                    self.service.update_avatar(self.user, PNG, self.storage)
        self.assertIs(caught.exception, failure)
        self.assertEqual([c.args[0] for c in call.call_args_list], ["POST"])
        uploaded_path = call.call_args_list[0].args[1]
        with Session(self.engine) as db:
            self.assertEqual(db.get(User, user_id).AvatarUrl, self.storage.public_url(uploaded_path))

    def test_failed_avatar_commit_cleans_only_the_new_upload_and_preserves_error(self):
        previous = f"{self.user.UserId}/{uuid.uuid4().hex}.png"
        self.user.AvatarUrl = self.storage.public_url(previous)
        self.db.commit()
        user_id = self.user.UserId
        failure = RuntimeError("database commit unavailable")
        with patch.object(AvatarStorage, "_call") as call:
            with patch.object(self.db, "commit", side_effect=failure):
                with self.assertRaises(RuntimeError) as caught:
                    self.service.update_avatar(self.user, PNG, self.storage)
        self.assertIs(caught.exception, failure)
        self.assertEqual([c.args[0] for c in call.call_args_list], ["POST", "DELETE"])
        self.assertEqual(call.call_args_list[1].args[1], call.call_args_list[0].args[1])
        self.assertNotEqual(call.call_args_list[1].args[1], previous)
        with Session(self.engine) as db:
            self.assertEqual(db.get(User, user_id).AvatarUrl, self.storage.public_url(previous))

    def test_failed_avatar_cleanup_does_not_hide_the_commit_error(self):
        failure = RuntimeError("database commit unavailable")
        with patch.object(AvatarStorage, "_call") as call:
            with patch.object(self.db, "commit", side_effect=failure):
                with patch.object(AvatarStorage, "delete", side_effect=ValueError("cleanup unavailable")) as delete:
                    with self.assertRaises(RuntimeError) as caught:
                        self.service.update_avatar(self.user, PNG, self.storage)
        self.assertIs(caught.exception, failure)
        delete.assert_called_once_with(call.call_args_list[0].args[1])
        self.db.refresh(self.user)
        self.assertIsNone(self.user.AvatarUrl)

    def test_avatar_rejects_non_images_missing_storage_and_upload_failures(self):
        with patch.object(AvatarStorage, "_call") as call:
            with self.assertRaises(AuthError) as caught:
                self.service.update_avatar(self.user, b"GIF89a", self.storage)
            self.assertEqual(caught.exception.status_code, 415)
            call.assert_not_called()
        with self.assertRaises(AuthError) as caught:
            self.service.update_avatar(self.user, PNG, None)
        self.assertEqual(caught.exception.status_code, 503)
        with patch.object(AvatarStorage, "_call", side_effect=OSError("down")):
            with self.assertRaises(AuthError) as caught:
                self.service.update_avatar(self.user, PNG, self.storage)
        self.assertEqual(caught.exception.status_code, 502)
        self.db.refresh(self.user)
        self.assertIsNone(self.user.AvatarUrl)

    def test_default_address_is_created_once_then_updated_in_place(self):
        self.assertIsNone(self.service.get_default_address(self.user))
        first = self.service.save_default_address(self.user, DefaultAddressUpdate(
            Province=" Hà Nội ", Ward="Phường Hoàn Kiếm", DetailAddress="123 Đường ABC"))
        self.assertEqual((first.Province, first.ReceiverName, first.ReceiverPhone, first.IsDefault),
                         ("Hà Nội", "Khách VieTech", "0912345678", True))
        second = self.service.save_default_address(self.user, DefaultAddressUpdate(
            Province="TP. Hồ Chí Minh", Ward="Phường Bến Nghé", DetailAddress="1 Lê Lợi"))
        self.assertEqual(second.AddressId, first.AddressId)
        self.assertEqual(self.db.query(Address).count(), 1)
        self.assertEqual(self.service.get_default_address(self.user).Province, "TP. Hồ Chí Minh")

    def test_default_address_requires_every_part(self):
        with self.assertRaises(ValidationError):
            DefaultAddressUpdate(Province="Hà Nội", Ward="  ", DetailAddress="123")
        with self.assertRaises(ValidationError):
            DefaultAddressUpdate(Province="Hà Nội", DetailAddress="123")

    def test_staff_and_admin_have_no_address_book(self):
        for role in ("Staff", "Admin"):
            self.user.Role = role
            self.db.commit()
            with self.subTest(role=role):
                for call in (lambda: self.service.get_default_address(self.user),
                             lambda: self.service.save_default_address(self.user, DefaultAddressUpdate(
                                 Province="Hà Nội", Ward="Phường A", DetailAddress="123"))):
                    with self.assertRaises(AuthError) as caught:
                        call()
                    self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(self.db.query(Address).count(), 0)

    def test_locked_account_cannot_change_avatar_or_address(self):
        self.user.AccountStatus = "Locked"
        self.db.commit()
        with self.assertRaises(AuthError):
            self.service.update_avatar(self.user, PNG, self.storage)
        with self.assertRaises(AuthError):
            self.service.save_default_address(self.user, DefaultAddressUpdate(
                Province="Hà Nội", Ward="Phường A", DetailAddress="123"))


if __name__ == "__main__":
    unittest.main()
