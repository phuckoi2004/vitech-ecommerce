"""ShippingMethodService (đợt 5.10): chỉ Admin quản lý; khách chỉ xem phương thức đang hoạt động; không xóa phương thức đã
được đơn hàng tham chiếu; đổi phí không ảnh hưởng đơn cũ. Fake trong bộ nhớ; không chứng minh hành vi PostgreSQL thật.
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace

from pydantic import ValidationError

from app.models import Order, ShippingMethod
from app.schemas import ShippingMethodCreate, ShippingMethodUpdate
from app.services import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError

from tests.fakes import shipping_method_service
from tests.test_order import OrderTestBase


def bypass(values):
    """Dữ liệu đi vòng qua Schema (ví dụ Router lỗi) để kiểm tra Service tự chặn."""
    return SimpleNamespace(model_dump=lambda exclude_unset=True: dict(values))


VALID = {"Code": "GHN", "Name": "Giao hàng nhanh", "BaseFee": Decimal("30000.00"), "EstimatedDays": 2}


class ShippingMethodTestBase(OrderTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.methods = shipping_method_service(self.db, self.session)

    def a(self, user):
        return self.f.actor(user)

    def create(self, by=None, **values):
        return self.methods.create_shipping_method(self.a(by or self.admin), ShippingMethodCreate(**{**VALID, **values}))

    def update(self, method_id, by=None, **values):
        return self.methods.update_shipping_method(self.a(by or self.admin), method_id, ShippingMethodUpdate(**values))

    def stored(self):
        return sorted((m.Code, m.Name, m.BaseFee, m.EstimatedDays, m.IsActive) for m in self.db.rows(ShippingMethod))

    def assert_error(self, error, code, call):
        with self.assertRaises(error) as ctx:
            call()
        self.assertEqual(ctx.exception.code, code)


class ManageShippingMethodTest(ShippingMethodTestBase):
    def test_admin_creates_method_with_trimmed_text_and_active_by_default(self):
        created = self.create(Code="  GHN ", Name=" Giao hàng nhanh  ")
        self.assertEqual((created.Code, created.Name, created.BaseFee, created.EstimatedDays, created.IsActive),
                         ("GHN", "Giao hàng nhanh", Decimal("30000.00"), 2, True))
        self.assertEqual(self.create(Code="FREE", BaseFee=Decimal("0"), EstimatedDays=0, IsActive=False).IsActive, False)

    def test_only_admin_can_create_update_or_delete(self):
        method = self.create()
        before = self.stored()
        for user in (self.staff, self.customer):
            with self.subTest(role=user.Role):
                self.assertRaises(PermissionDeniedError, lambda: self.create(by=user, Code="X"))
                self.assertRaises(PermissionDeniedError, lambda: self.update(method.ShippingMethodId, by=user, Name="Y"))
                self.assertRaises(PermissionDeniedError, lambda: self.methods.delete_shipping_method(
                    self.a(user), method.ShippingMethodId))
        self.assertEqual(self.stored(), before)

    def test_code_must_be_unique(self):
        first = self.create()
        second = self.create(Code="GHTK")
        self.assert_error(ConflictError, "shipping_method_code_exists", lambda: self.create(Code=" GHN "))
        self.assert_error(ConflictError, "shipping_method_code_exists",
                          lambda: self.update(second.ShippingMethodId, Code="GHN"))
        self.assertEqual(self.update(first.ShippingMethodId, Code="GHN").Code, "GHN")  # giữ nguyên mã của chính nó
        self.assertEqual(self.create(Code="ghn").Code, "ghn")  # phân biệt hoa thường như UQ của database

    def test_invalid_values_are_rejected_without_writing(self):
        method = self.create()
        before = self.stored()
        for field, value, code in (("Code", "   ", "shipping_method_code_required"),
                                   ("Name", "", "shipping_method_name_required"),
                                   ("EstimatedDays", -1, "invalid_estimated_days")):
            with self.subTest(field=field):
                self.assert_error(BusinessRuleError, code, lambda: self.create(**{field: value, "Code": "NEW"}
                                                                               if field != "Code" else {field: value}))
                self.assert_error(BusinessRuleError, code, lambda: self.update(method.ShippingMethodId, **{field: value}))
        self.assertRaises(ValidationError, ShippingMethodCreate, **{**VALID, "BaseFee": Decimal("-1")})
        self.assertRaises(ValidationError, ShippingMethodUpdate, BaseFee=Decimal("1.001"))
        self.assertRaises(ValidationError, ShippingMethodUpdate, Name=None)  # cột NOT NULL
        self.assertRaises(ValidationError, ShippingMethodCreate, **VALID, ShippingMethodId=uuid.uuid4())
        self.assertEqual(self.stored(), before)

    def test_estimated_days_must_be_between_0_and_30(self):
        """Đợt 5.13: 0 <= EstimatedDays <= 30 (0 = giao trong ngày)."""
        method = self.create(Code="EDGE")
        for days in (0, 30):
            with self.subTest(days=days):
                self.assertEqual(self.create(Code=f"OK{days}", EstimatedDays=days).EstimatedDays, days)
                self.assertEqual(self.update(method.ShippingMethodId, EstimatedDays=days).EstimatedDays, days)
        before = self.stored()
        for days in (31, 365, -1):
            with self.subTest(days=days):
                self.assert_error(BusinessRuleError, "invalid_estimated_days",
                                  lambda: self.create(Code=f"BAD{days}", EstimatedDays=days))
                self.assert_error(BusinessRuleError, "invalid_estimated_days",
                                  lambda: self.update(method.ShippingMethodId, EstimatedDays=days))
        for value in (30.0, "30", True, None):  # kiểu không hợp lệ (đi vòng qua Schema)
            with self.subTest(value=value):
                self.assert_error(BusinessRuleError, "invalid_estimated_days",
                                  lambda: self.methods.update_shipping_method(
                                      self.a(self.admin), method.ShippingMethodId, bypass({"EstimatedDays": value})))
        self.assertEqual(self.stored(), before)

    def test_service_rechecks_values_when_schema_is_bypassed(self):
        method = self.create()
        before = self.stored()
        admin = self.a(self.admin)
        cases = (
            ({**VALID, "Code": "X", "ShippingMethodId": uuid.uuid4()}, "shipping_method_field_not_allowed"),
            ({"Code": "X", "Name": "Y"}, "shipping_method_field_required"),
            ({**VALID, "Code": "X", "BaseFee": Decimal("-5")}, "invalid_shipping_fee"),
            ({**VALID, "Code": "X", "BaseFee": Decimal("1.005")}, "invalid_shipping_fee"),
            ({**VALID, "Code": "X", "EstimatedDays": True}, "invalid_estimated_days"),
            ({**VALID, "Code": "X", "IsActive": "yes"}, "invalid_is_active"),
        )
        for values, code in cases:
            with self.subTest(code=code):
                self.assert_error(BusinessRuleError, code, lambda: self.methods.create_shipping_method(admin, bypass(values)))
        self.assert_error(BusinessRuleError, "shipping_method_field_not_allowed",
                          lambda: self.methods.update_shipping_method(admin, method.ShippingMethodId,
                                                                      bypass({"ShippingMethodId": uuid.uuid4()})))
        self.assertEqual(self.stored(), before)

    def test_missing_method_is_not_found(self):
        missing = uuid.uuid4()
        self.assert_error(NotFoundError, "shipping_method_not_found", lambda: self.update(missing, Name="X"))
        self.assert_error(NotFoundError, "shipping_method_not_found",
                          lambda: self.methods.delete_shipping_method(self.a(self.admin), missing))


class ViewShippingMethodTest(ShippingMethodTestBase):
    def test_public_sees_active_methods_only_and_staff_sees_all(self):
        express = self.create(Code="EXP", BaseFee=Decimal("50000.00"))
        standard = self.create(Code="STD", BaseFee=Decimal("20000.00"))
        hidden = self.create(Code="OLD", IsActive=False)
        public = [m.Code for m in self.methods.list_shipping_methods(active_only=True)]
        self.assertEqual(public, ["STD", "EXP"])  # theo phí rồi tên
        self.assertRaises(PermissionDeniedError, self.methods.list_shipping_methods)
        self.assertRaises(PermissionDeniedError, lambda: self.methods.list_shipping_methods(actor=self.a(self.customer)))
        self.assertEqual({m.Code for m in self.methods.list_shipping_methods(actor=self.a(self.staff))},
                         {"EXP", "STD", "OLD"})
        self.assertEqual(self.methods.get_shipping_method(standard.ShippingMethodId).Code, "STD")
        self.assert_error(NotFoundError, "shipping_method_not_found",
                          lambda: self.methods.get_shipping_method(hidden.ShippingMethodId, actor=self.a(self.customer)))
        self.assertEqual(self.methods.get_shipping_method(hidden.ShippingMethodId, actor=self.a(self.admin)).Code, "OLD")
        self.assertEqual(express.IsActive, True)


class ShippingMethodAndOrdersTest(ShippingMethodTestBase):
    def place_order(self, method, customer=None):
        customer = customer or self.customer  # Factory: mỗi khách một giỏ hàng
        variant = self.f.variant(stock=5, price="100000.00")
        self.f.cart_with(customer, (variant, 1))
        return self.svc.create_order(self.a(customer), self.order_input(ShippingMethodId=method.ShippingMethodId))

    def test_fee_change_applies_to_new_orders_only(self):
        method = self.create(BaseFee=Decimal("30000.00"))
        first = self.place_order(method)
        self.update(method.ShippingMethodId, BaseFee=Decimal("45000.00"), Name="Giao nhanh 2h")
        second = self.place_order(method, customer=self.other)
        self.assertEqual((self.db.get(Order, first.OrderId).ShippingFee, first.TotalAmount),
                         (Decimal("30000.00"), Decimal("130000.00")))
        self.assertEqual(second.ShippingFee, Decimal("45000.00"))

    def test_inactive_method_cannot_be_chosen_but_old_orders_keep_it(self):
        method = self.create()
        order = self.place_order(method)
        self.assertFalse(self.update(method.ShippingMethodId, IsActive=False).IsActive)
        self.assert_error(NotFoundError, "shipping_method_not_available",
                          lambda: self.place_order(method, customer=self.other))
        self.assertEqual(self.db.get(Order, order.OrderId).ShippingMethodId, method.ShippingMethodId)

    def test_method_used_by_any_order_cannot_be_deleted(self):
        method = self.create()
        order = self.place_order(method)
        for status in ("Pending", "Cancelled", "Completed"):
            with self.subTest(status=status):
                self.db.get(Order, order.OrderId).OrderStatus = status
                self.assert_error(BusinessRuleError, "shipping_method_in_use",
                                  lambda: self.methods.delete_shipping_method(self.a(self.admin), method.ShippingMethodId))
                self.assertIsNotNone(self.db.get(ShippingMethod, method.ShippingMethodId))
        self.assertIn(("ShippingMethod", method.ShippingMethodId), self.db.locks)

    def test_unused_method_can_be_deleted(self):
        method = self.create()
        self.methods.delete_shipping_method(self.a(self.admin), method.ShippingMethodId)
        self.assertIsNone(self.db.get(ShippingMethod, method.ShippingMethodId))
        self.assert_error(NotFoundError, "shipping_method_not_found",
                          lambda: self.methods.delete_shipping_method(self.a(self.admin), method.ShippingMethodId))
