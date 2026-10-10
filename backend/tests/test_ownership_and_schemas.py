"""Quyền sở hữu dữ liệu (Cart, Wishlist, Address) và chống mass assignment ở Schema."""

import unittest
import uuid
from decimal import Decimal

from pydantic import ValidationError

from app.models import Address, Wishlist, WishlistItem
from app.schemas import (
    AdminUserUpdate,
    CartItemCreate,
    CartItemUpdate,
    OrderCreate,
    PurchaseOrderCreate,
    PurchaseOrderDecision,
    PurchaseOrderItemCreate,
    PurchaseOrderReceive,
    UserRegister,
)
from app.services import AddressService, CartService, NotFoundError, WishlistService

from tests.fakes import (
    FakeAddressRepo,
    FakeCartItemRepo,
    FakeCartRepo,
    FakeProductRepo,
    FakeRepo,
    FakeSession,
    FakeVariantRepo,
    Factory,
    InMemoryDB,
    fixed_clock,
)


class FakeWishlistRepo(FakeRepo):
    model = Wishlist

    def get_by_user(self, user_id, *, with_items=False):
        rows = self._rows(lambda w: w.UserId == user_id)
        return rows[0] if rows else None


class FakeWishlistItemRepo(FakeRepo):
    model = WishlistItem


class OwnershipTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = InMemoryDB()
        self.session = FakeSession(self.db)
        self.f = Factory(self.db)
        self.owner, self.intruder = self.f.user(), self.f.user()

    def test_cart_item_of_another_user_cannot_be_changed(self):
        svc = CartService(self.session, clock=fixed_clock)
        svc.carts, svc.items, svc.variants = FakeCartRepo(self.db), FakeCartItemRepo(self.db), FakeVariantRepo(self.db)
        variant = self.f.variant(stock=5)
        cart = self.f.cart_with(self.owner, (variant, 1))
        self.f.cart_with(self.intruder)
        [item] = svc.items.list_by_cart(cart.CartId)
        with self.assertRaises(NotFoundError):
            svc.update_item(self.f.actor(self.intruder), item.CartItemId, CartItemUpdate(Quantity=5))
        with self.assertRaises(NotFoundError):
            svc.remove_item(self.f.actor(self.intruder), item.CartItemId)
        self.assertEqual(item.Quantity, 1)
        self.assertIsNotNone(self.db.get(type(item), item.CartItemId))

    def test_wishlist_item_of_another_user_cannot_be_removed(self):
        svc = WishlistService(self.session, clock=fixed_clock)
        svc.wishlists, svc.items, svc.products = FakeWishlistRepo(self.db), FakeWishlistItemRepo(self.db), FakeProductRepo(self.db)
        variant = self.f.variant()
        wishlist = self.db.add(Wishlist(UserId=self.owner.UserId))
        self.db.add(Wishlist(UserId=self.intruder.UserId))
        item = self.db.add(WishlistItem(WishlistId=wishlist.WishlistId, ProductId=variant.ProductId))
        with self.assertRaises(NotFoundError):
            svc.remove_item(self.f.actor(self.intruder), item.WishlistItemId)
        self.assertIsNotNone(self.db.get(WishlistItem, item.WishlistItemId))

    def test_address_of_another_user_is_not_visible(self):
        svc = AddressService(self.session, clock=fixed_clock)
        svc.addresses = FakeAddressRepo(self.db)
        address = self.db.add(Address(UserId=self.owner.UserId, ReceiverName="A", ReceiverPhone="09", Province="P",
                                      Ward="W", DetailAddress="D"))
        with self.assertRaises(NotFoundError):
            svc.get_address(self.f.actor(self.intruder), address.AddressId)
        self.assertEqual(svc.get_address(self.f.actor(self.owner), address.AddressId).AddressId, address.AddressId)


class SchemaGuardTest(unittest.TestCase):
    """Client không tự quyết định người lập, trạng thái, tổng tiền, giá, role."""

    def rejects(self, schema, **values):
        with self.assertRaises(ValidationError):
            schema(**values)

    def test_purchase_order_create(self):
        line = {"ProductVariantId": uuid.uuid4(), "OrderedQuantity": 1, "UnitPrice": "1000"}
        base = {"SupplierId": uuid.uuid4(), "Items": [line]}
        PurchaseOrderCreate(**base)
        self.rejects(PurchaseOrderCreate, SupplierId=uuid.uuid4(), Items=[])
        for extra in ({"CreatedByUserId": uuid.uuid4()}, {"Status": "Approved"}, {"TotalAmount": "1"}):
            with self.subTest(extra=extra):
                self.rejects(PurchaseOrderCreate, **base, **extra)
        for bad in ({"OrderedQuantity": 0}, {"OrderedQuantity": -1}, {"UnitPrice": "-1"}, {"UnitPrice": "1.005"},
                    {"LineTotal": "1"}, {"ReceivedQuantity": 1}):
            with self.subTest(bad=bad):
                self.rejects(PurchaseOrderItemCreate, **{**line, **bad})

    def test_purchase_order_receive_and_decision(self):
        self.rejects(PurchaseOrderReceive, Items=[])
        self.rejects(PurchaseOrderReceive, Items=[{"PurchaseOrderItemId": uuid.uuid4(), "Quantity": 0}])
        self.rejects(PurchaseOrderDecision, Status="Completed")
        self.rejects(PurchaseOrderDecision, Status="Approved", DecidedByUserId=uuid.uuid4())

    def test_order_and_cart_money_fields_are_server_side(self):
        base = {"ShippingMethodId": uuid.uuid4(), "PaymentMethodId": uuid.uuid4(), "AddressId": uuid.uuid4()}
        OrderCreate(**base)
        for extra in ({"TotalAmount": "1"}, {"DiscountAmount": "1"}, {"OrderStatus": "Delivered"},
                      {"PaymentStatus": "Paid"}, {"CustomerId": uuid.uuid4()}):
            with self.subTest(extra=extra):
                self.rejects(OrderCreate, **base, **extra)
        self.rejects(CartItemCreate, ProductVariantId=uuid.uuid4(), Quantity=1, UnitPrice=Decimal("1"))
        self.rejects(CartItemCreate, ProductVariantId=uuid.uuid4(), Quantity=0)

    def test_roles(self):
        self.rejects(UserRegister, Email="a@b.c", PhoneNumber="1", Password="x", FullName="A", Role="Admin")
        self.rejects(AdminUserUpdate, Role="SuperAdmin")


if __name__ == "__main__":
    unittest.main()
