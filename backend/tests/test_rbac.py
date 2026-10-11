"""Phân quyền Service layer theo Actor: Catalog, Promotion/Coupon, User/Admin, Notification, Address.

Trường hợp bị từ chối dùng repository "cấm chạm" để chứng minh quyền được kiểm tra trước khi truy cập dữ liệu.
"""

import unittest
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.errors import AuthError

from app.models import Notification, Promotion
from app.schemas import (
    AddressCreate,
    BrandCreate,
    CategoryCreate,
    CouponCreate,
    ProductCreate,
    ProductImageCreate,
    ProductSerialCreate,
    PromotionCreate,
)
from app.schemas.account import InternalUserCreate, ManagedUserUpdate, ProfileUpdate
from app.services import (
    Actor,
    AddressService,
    BrandService,
    BusinessRuleError,
    CategoryService,
    CouponService,
    NotFoundError,
    NotificationService,
    PermissionDeniedError,
    ProductImageService,
    ProductSerialService,
    ProductService,
    PromotionService,
    UserService,
)

from tests.fakes import (
    FakeCouponRepo,
    FakeNotificationRepo,
    FakePromotionRepo,
    FakeSession,
    FakeUserRepo,
    Factory,
    InMemoryDB,
    fixed_clock,
)


class Untouchable:
    """Repository giả: bất kỳ truy cập nào cũng làm test lỗi (quyền phải bị chặn trước)."""

    def __getattr__(self, name):
        raise AssertionError(f"Repository bị truy cập ({name}) dù Actor không có quyền")


def actor(role: str) -> Actor:
    return Actor(uuid.uuid4(), role)


NON_ADMINS = (actor("Staff"), actor("Customer"), None)


class CatalogPermissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = FakeSession(InMemoryDB())

    def guarded(self, cls, *repo_names):
        svc = cls(self.session, clock=fixed_clock)
        for name in repo_names:
            setattr(svc, name, Untouchable())
        return svc

    def test_admin_only_mutations(self):
        some_id = uuid.uuid4()
        category = self.guarded(CategoryService, "categories")
        brand = self.guarded(BrandService, "brands")
        product = self.guarded(ProductService, "products", "categories", "brands")
        image = self.guarded(ProductImageService, "images", "products")
        serial = self.guarded(ProductSerialService, "serials", "variants", "order_items", "warranty_requests")
        calls = [
            lambda a: category.create_category(a, CategoryCreate(Name="A", Slug="a")),
            lambda a: category.delete_category(a, some_id),
            lambda a: brand.create_brand(a, BrandCreate(Name="B", Slug="b")),
            lambda a: brand.delete_brand(a, some_id),
            lambda a: product.create_product(a, ProductCreate(CategoryId=some_id, BrandId=some_id, Name="P", Slug="p",
                                                              WarrantyMonths=12, Status="Active")),
            lambda a: product.delete_product(a, some_id),
            lambda a: image.add_image(a, some_id, ProductImageCreate(ImageUrl="https://x/y.png")),
            lambda a: serial.create_serial(a, ProductSerialCreate(ProductVariantId=some_id, SerialNumber="S", Status="Available")),
            lambda a: serial.delete_serial(a, some_id),
        ]
        for call in calls:
            for who in NON_ADMINS:
                with self.subTest(call=call, role=getattr(who, "role", None)), self.assertRaises(PermissionDeniedError):
                    call(who)
        self.assertEqual(self.session.commits, 0)

    def test_internal_views_need_staff_or_admin(self):
        product = self.guarded(ProductService, "products")
        serial = self.guarded(ProductSerialService, "serials")
        with self.assertRaises(PermissionDeniedError):
            product.admin_list_products(actor("Customer"))
        with self.assertRaises(PermissionDeniedError):
            serial.get_by_serial_number(None, "S")

    def test_public_reads_only_active_data(self):
        category = CategoryService(self.session, clock=fixed_clock)
        category.categories = type("Repo", (), {"list_categories": lambda self, **kw: []})()
        self.assertEqual(category.list_categories(active_only=True), [])
        with self.assertRaises(PermissionDeniedError):
            category.list_categories()  # khách xem cả danh mục ẩn
        self.assertEqual(category.list_categories(actor=actor("Staff")), [])


class PromotionPermissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.admin = self.f.user("Admin")

    def promotion_input(self):
        return PromotionCreate(Name="Sale", DiscountType="Percentage", DiscountValue=Decimal("10"),
                               MinOrderValue=Decimal("0"), StartDate="2026-10-01T00:00:00Z",
                               EndDate="2026-10-31T00:00:00Z", Status="Draft")

    def test_promotion_and_coupon_management_is_admin_only(self):
        promotions = PromotionService(self.session, clock=fixed_clock)
        coupons = CouponService(self.session, clock=fixed_clock)
        for name in ("promotions", "promotion_products", "promotion_categories", "coupons", "products", "categories"):
            setattr(promotions, name, Untouchable())
        for name in ("coupons", "promotions", "orders"):
            setattr(coupons, name, Untouchable())
        for who in NON_ADMINS:
            with self.subTest(role=getattr(who, "role", None)):
                with self.assertRaises(PermissionDeniedError):
                    promotions.create_promotion(who, self.promotion_input())
                with self.assertRaises(PermissionDeniedError):
                    promotions.list_promotions(who)
                with self.assertRaises(PermissionDeniedError):
                    coupons.create_coupon(who, CouponCreate(PromotionId=uuid.uuid4(), Code="X", Name="X"))

    def test_creator_comes_from_actor(self):
        promotions = PromotionService(self.session, clock=fixed_clock)
        promotions.promotions = FakePromotionRepo(self.db)
        promotions.promotions.get_detail = promotions.promotions.get_by_id
        created = promotions.create_promotion(self.f.actor(self.admin), self.promotion_input())
        self.assertEqual(created.CreatedByUserId, self.admin.UserId)
        coupons = CouponService(self.session, clock=fixed_clock)
        coupons.promotions = FakePromotionRepo(self.db)
        coupons.coupons = FakeCouponRepo(self.db)
        coupons.coupons.exists_by_code = lambda code, exclude_id=None: False
        promotion = self.db.get(Promotion, created.PromotionId)
        coupon = coupons.create_coupon(self.f.actor(self.admin), CouponCreate(PromotionId=promotion.PromotionId, Code="OCT", Name="Oct"))
        self.assertEqual(coupons.coupons.get_by_id(coupon.CouponId).CreatedByUserId, self.admin.UserId)

    def test_coupon_preview_is_for_customers(self):
        coupons = CouponService(self.session, clock=fixed_clock)
        coupons.carts = Untouchable()
        with self.assertRaises(PermissionDeniedError):
            coupons.preview_cart_coupon(actor("Staff"), "SALE10")


class UserPermissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.f = Factory(self.db)
        self.session = Mock()
        self.runtime = SimpleNamespace(sessions=Mock())
        self.svc = UserService(self.session, self.runtime)
        self.svc.users = FakeUserRepo(self.db)
        self.customer = self.f.user("Customer")
        self.staff = self.f.user("Staff")
        self.other = self.f.user("Customer")

    def test_admin_operations_reject_staff_and_customers(self):
        self.svc.users = Untouchable()
        target = uuid.uuid4()
        data = InternalUserCreate(Email="staff@example.com", PhoneNumber="0912345678", FullName="Staff",
                                  Password="Password7!", ConfirmPassword="Password7!")
        calls = [
            lambda a: self.svc.list_users(a),
            lambda a: self.svc.get_user(a, target),
            lambda a: self.svc.create_user(a, data),
            lambda a: self.svc.update_user(a, target, ManagedUserUpdate(FullName="Changed")),
            lambda a: self.svc.delete_user(a, target),
        ]
        for call in calls:
            # Account HTTP routes pass authenticated ORM users, not domain Actor.
            for who in (self.staff, self.customer):
                with self.subTest(call=call, role=who.Role), self.assertRaises(AuthError) as raised:
                    call(who)
                self.assertEqual(raised.exception.status_code, 403)
        self.session.commit.assert_not_called()
        self.runtime.sessions.revoke_user.assert_not_called()

    def test_self_service_uses_authenticated_user_identity_only(self):
        self.svc.update_profile(self.customer, ProfileUpdate(FullName="Tên mới"))
        self.assertEqual((self.customer.FullName, self.other.FullName != "Tên mới"), ("Tên mới", True))
        self.session.refresh.assert_called_once_with(self.customer)
        self.runtime.sessions.revoke_user.assert_not_called()

    def test_inactive_admin_is_rejected_before_repository_access(self):
        self.svc.users = Untouchable()
        admin = self.f.user("Admin")
        for values in ({"AccountStatus": "Locked"}, {"AccountStatus": "Active", "IsDeleted": True}):
            for name, value in values.items():
                setattr(admin, name, value)
            with self.subTest(values=values), self.assertRaises(AuthError) as raised:
                self.svc.get_user(admin, self.customer.UserId)
            self.assertEqual(raised.exception.status_code, 403)
        self.session.commit.assert_not_called()


class NotificationAndAddressPermissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.owner, self.intruder = self.f.user("Staff"), self.f.user("Customer")

    def test_notifications_are_private_to_recipient(self):
        svc = NotificationService(self.session, clock=fixed_clock)
        svc.notifications = FakeNotificationRepo(self.db)
        note = self.db.add(Notification(UserId=self.owner.UserId, Title="T", Content="C", NotificationType="Order"))
        with self.assertRaises(NotFoundError):
            svc.mark_read(self.f.actor(self.intruder), note.NotificationId)
        self.assertFalse(note.IsRead)
        self.assertTrue(svc.mark_read(self.f.actor(self.owner), note.NotificationId).IsRead)

    def test_notify_is_internal_only(self):
        svc = NotificationService(self.session, clock=fixed_clock)
        svc.notifications = FakeNotificationRepo(self.db)
        with self.assertRaises(BusinessRuleError) as ctx:
            svc.notify(self.owner.UserId, title="x", content="y", notification_type="Order")
        self.assertEqual(ctx.exception.code, "internal_operation")
        self.assertEqual(self.db.rows(Notification), [])

    def test_address_book_is_for_customers(self):
        svc = AddressService(self.session, clock=fixed_clock)
        svc.addresses = Untouchable()
        with self.assertRaises(PermissionDeniedError):
            svc.create_address(self.f.actor(self.owner), AddressCreate(ReceiverName="A", ReceiverPhone="1",
                                                                      Province="P", Ward="W", DetailAddress="D"))


if __name__ == "__main__":
    unittest.main()
