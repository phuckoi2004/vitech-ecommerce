"""Checkout/cart regressions: a waiter reads after the winner commits; stale ORM data is refreshed.

The interleaving tests emulate the moment a Cart lock becomes available. SQLite tests use actual mapped
repositories but do not prove PostgreSQL row locking. The opt-in PostgreSQL suite covers real concurrency.
"""

import unittest
import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import JSON, MetaData, create_engine, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models import Base, Cart, CartItem, Order, Product, ProductVariant
from app.repositories import CartRepository, ProductVariantRepository
from app.schemas import CartItemCreate, CartItemUpdate
from app.services import BusinessRuleError, CartService, NotFoundError

from tests.fakes import (
    FakeCartItemRepo, FakeCartRepo, FakePromotionRepo, FakeSession, FakeVariantRepo, fixed_clock, order_service,
)
from tests.test_locking import RecordingSession, sql
from tests.test_order import OrderTestBase


def cart_service(db, session):
    service = CartService(session, clock=fixed_clock)
    service.carts = FakeCartRepo(db)
    service.items = FakeCartItemRepo(db)
    service.variants = FakeVariantRepo(db)
    service.promotions = FakePromotionRepo(db)
    return service


class CartWaiterTest(OrderTestBase):
    def setUp(self):
        super().setUp()
        self.variant = self.f.variant(stock=5)
        self.cart = self.f.cart_with(self.customer, (self.variant, 1))
        self.item = self.db.rows(CartItem)[0]
        self.data = self.order_input()

    def after_other_commits(self, service, callback):
        original = service.carts.get_by_user_for_update

        def acquire_after_wait(user_id):
            callback()
            # The fake rollback must retain a transaction committed by the other session while this one waited.
            service.session._snapshot = self.db.snapshot()
            return original(user_id)

        service.carts.get_by_user_for_update = acquire_after_wait

    def test_waiting_checkout_sees_cart_empty_with_stock_still_available(self):
        winner_session = FakeSession(self.db)
        winner = order_service(self.db, winner_session)
        self.after_other_commits(self.svc, lambda: winner.create_order(self.f.actor(self.customer), self.data))
        with self.assertRaises(BusinessRuleError) as caught:
            self.svc.create_order(self.f.actor(self.customer), self.data)
        self.assertEqual(caught.exception.code, "cart_empty")
        self.assertEqual((len(self.db.rows(Order)), self.variant.StockQuantity), (1, 4))
        self.assertEqual(self.db.rows(CartItem), [])
        self.assertEqual((winner_session.commits, self.session.rollbacks), (1, 1))
        self.assertEqual(self.item.Quantity, 1)  # stale Python object is still readable, but was not checked out again
        self.assertEqual(self.db.locks[0], ("Cart", self.cart.CartId))

    def test_cart_update_waiting_for_checkout_cannot_recreate_consumed_item(self):
        writer = cart_service(self.db, FakeSession(self.db))
        self.after_other_commits(writer, lambda: self.svc.create_order(self.f.actor(self.customer), self.data))
        with self.assertRaises(NotFoundError) as caught:
            writer.update_item(self.f.actor(self.customer), self.item.CartItemId, CartItemUpdate(Quantity=2))
        self.assertEqual(caught.exception.code, "cart_item_not_found")
        self.assertEqual((len(self.db.rows(Order)), self.variant.StockQuantity), (1, 4))
        self.assertEqual(self.db.rows(CartItem), [])

    def test_waiting_add_preserves_quantity_added_by_other_request(self):
        winner = cart_service(self.db, FakeSession(self.db))
        waiter = cart_service(self.db, FakeSession(self.db))
        data = CartItemCreate(ProductVariantId=self.variant.ProductVariantId, Quantity=1)
        self.after_other_commits(waiter, lambda: winner.add_item(self.f.actor(self.customer), data))
        response = waiter.add_item(self.f.actor(self.customer), data)
        self.assertEqual((response.Items[0].Quantity, self.item.Quantity), (3, 3))
        self.assertEqual(self.variant.StockQuantity, 5)  # cart writers do not reserve stock
        self.assertEqual(len(self.db.rows(CartItem)), 1)

    def test_cart_operations_acquire_cart_before_reading_items_or_variant(self):
        operations = (
            lambda svc: svc.get_cart(self.f.actor(self.customer)),
            lambda svc: svc.add_item(self.f.actor(self.customer), CartItemCreate(
                ProductVariantId=self.variant.ProductVariantId, Quantity=1)),
            lambda svc: svc.update_item(self.f.actor(self.customer), self.item.CartItemId, CartItemUpdate(Quantity=2)),
            lambda svc: svc.set_all_selected(self.f.actor(self.customer), False),
            lambda svc: svc.remove_item(self.f.actor(self.customer), self.item.CartItemId),
        )
        snapshot = self.db.snapshot()
        for operation in operations:
            with self.subTest(operation=operation):
                self.db.restore(snapshot)
                self.db.locks.clear()
                service = cart_service(self.db, FakeSession(self.db))

                def require_cart_lock(method):
                    def guarded(*args, **kwargs):
                        self.assertIn(("Cart", self.cart.CartId), self.db.locks)
                        return method(*args, **kwargs)
                    return guarded

                for name in ("list_by_cart", "get_by_cart_and_variant", "get_by_id_and_cart"):
                    setattr(service.items, name, require_cart_lock(getattr(service.items, name)))
                service.variants.get_by_id_for_update = require_cart_lock(service.variants.get_by_id_for_update)
                operation(service)
                self.assertEqual(self.db.locks[0], ("Cart", self.cart.CartId))
                self.assertNotIn("User", [model for model, _ in self.db.locks])

    def test_first_cart_is_locked_before_summary_reads_items(self):
        service = cart_service(self.db, FakeSession(self.db))
        response = service.get_cart(self.f.actor(self.other))
        created = service.carts.get_by_user(self.other.UserId)
        self.assertEqual(response.CartId, created.CartId)
        self.assertEqual(response.Items, [])
        self.assertIn(("Cart", created.CartId), self.db.locks)


class CartQueryTest(unittest.TestCase):
    def test_lock_is_by_cart_owner_and_refreshes_identity_map(self):
        session = RecordingSession()
        user_id = uuid.uuid4()
        self.assertIsNone(CartRepository(session).get_by_user_for_update(user_id))
        self.assertEqual(session.calls, ["flush", "scalars"])
        stmt = session.statements[0]
        self.assertTrue(stmt.get_execution_options().get("populate_existing"))
        self.assertIn('WHERE "Carts"."UserId" = ', sql(stmt))
        self.assertIn("FOR UPDATE", sql(stmt))
        self.assertNotIn('"Users"', sql(stmt))
        self.assertEqual(stmt.compile(dialect=postgresql.dialect()).params["UserId_1"], user_id)

    def test_cart_variant_check_locks_only_variant_and_refreshes_product(self):
        session = RecordingSession()
        self.assertIsNone(ProductVariantRepository(session).get_by_id_for_update(uuid.uuid4(), with_product=True))
        self.assertEqual(session.calls, ["flush", "scalars"])
        stmt = session.statements[0]
        self.assertTrue(stmt.get_execution_options().get("populate_existing"))
        self.assertIn('FOR UPDATE OF "ProductVariants"', sql(stmt))
        self.assertNotIn('JOIN "Products"', sql(stmt))  # Product is selectinloaded, not locked in a joined query


class CartIdentityRefreshTest(unittest.TestCase):
    """Actual ORM queries on transient SQLite; external committed writes leave deliberately stale identities."""

    def setUp(self):
        self.fixture = OrderTestBase()
        self.fixture.setUp()
        self.variant = self.fixture.f.variant(stock=5)
        self.product = self.variant.product
        self.cart = self.fixture.f.cart_with(self.fixture.customer, (self.variant, 1))
        self.item = self.fixture.db.rows(CartItem)[0]
        self.actor = self.fixture.f.actor(self.fixture.customer)
        self.engine = create_engine("sqlite://")
        # Clone only DDL types; application mappings and PostgreSQL JSONB stay untouched.
        metadata = MetaData(naming_convention=Base.metadata.naming_convention)
        for table in Base.metadata.tables.values():
            table.to_metadata(metadata)
        metadata.tables["Products"].c.Specifications.type = JSON()
        metadata.create_all(self.engine, tables=[metadata.tables[name] for name in (
            "Products", "ProductVariants", "Carts", "CartItems", "Promotions", "PromotionProducts", "PromotionCategories")])
        with Session(self.engine) as seed:
            seed.add_all((self.product, self.variant, self.cart, self.item))
            seed.commit()
            self.variant_id, self.product_id = self.variant.ProductVariantId, self.product.ProductId
            self.cart_id, self.item_id = self.cart.CartId, self.item.CartItemId
        self.session = Session(self.engine, autoflush=False)
        self.service = CartService(self.session)
        self.initial = self.service.get_cart(self.actor)
        self.cached_item = self.session.get(CartItem, self.item_id)
        self.cached_variant = self.session.get(ProductVariant, self.variant_id)
        self.cached_cart = self.session.get(Cart, self.cart_id)
        self.cached_product = self.session.get(Product, self.product_id)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_summary_refreshes_cart_item_variant_and_product_after_wait(self):
        changed_at = self.cached_cart.UpdatedAt + timedelta(seconds=10)
        with self.engine.begin() as writer:
            writer.execute(update(Cart).where(Cart.CartId == self.cart_id).values(UpdatedAt=changed_at))
            writer.execute(update(CartItem).where(CartItem.CartItemId == self.item_id).values(
                Quantity=3, IsSelected=False))
            writer.execute(update(ProductVariant).where(ProductVariant.ProductVariantId == self.variant_id).values(
                Price=Decimal("110000.00"), StockQuantity=2))
            writer.execute(update(Product).where(Product.ProductId == self.product_id).values(
                Name="Updated product", Status="Inactive"))
        self.assertEqual((self.cached_item.Quantity, self.cached_variant.StockQuantity), (1, 5))
        response = self.service.get_cart(self.actor)
        line = response.Items[0]
        self.assertEqual((line.Quantity, line.CurrentPrice, line.StockQuantity), (3, Decimal("110000.00"), 2))
        self.assertEqual((line.ProductName, line.IsSelected, line.IsAvailable), ("Updated product", False, False))
        self.assertEqual((response.SelectedQuantity, response.SelectedSubtotal), (0, Decimal("0")))
        self.assertEqual(response.UpdatedAt, changed_at)

    def test_add_uses_quantity_committed_by_other_request(self):
        with self.engine.begin() as writer:
            writer.execute(update(CartItem).where(CartItem.CartItemId == self.item_id).values(Quantity=4))
        self.assertEqual(self.cached_item.Quantity, 1)
        with self.assertRaises(BusinessRuleError) as caught:
            self.service.add_item(self.actor, CartItemCreate(ProductVariantId=self.variant_id, Quantity=2))
        self.assertEqual(caught.exception.code, "insufficient_stock")
        self.assertEqual(self.session.get(CartItem, self.item_id).Quantity, 4)

    def test_update_uses_variant_stock_committed_by_other_request(self):
        with self.engine.begin() as writer:
            writer.execute(update(ProductVariant).where(ProductVariant.ProductVariantId == self.variant_id).values(
                StockQuantity=1))
        self.assertEqual(self.cached_variant.StockQuantity, 5)
        with self.assertRaises(BusinessRuleError) as caught:
            self.service.update_item(self.actor, self.item_id, CartItemUpdate(Quantity=2))
        self.assertEqual(caught.exception.code, "insufficient_stock")
        self.assertEqual(self.session.get(CartItem, self.item_id).Quantity, 1)

    def test_add_rechecks_product_visibility_from_committed_data(self):
        with self.engine.begin() as writer:
            writer.execute(update(Product).where(Product.ProductId == self.product_id).values(Status="Inactive"))
        self.assertEqual(self.cached_product.Status, "Active")
        with self.assertRaises(NotFoundError) as caught:
            self.service.add_item(self.actor, CartItemCreate(ProductVariantId=self.variant_id, Quantity=1))
        self.assertEqual(caught.exception.code, "variant_not_available")
        self.assertEqual(self.session.get(CartItem, self.item_id).Quantity, 1)


if __name__ == "__main__":
    unittest.main()
