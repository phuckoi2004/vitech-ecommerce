"""Direct Admin stock/serial edits: no operation history, never negative, all-or-nothing."""
from decimal import Decimal
from unittest.mock import Mock

from pydantic import ValidationError
from app.models import ProductSerial, StockAdjustment
from app.schemas import StockQuantityUpdate
from app.services import BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError
from tests.test_inventory import InventoryTestBase
from tests.test_router_flows import flow  # HTTP fixture with only in-memory service dependencies
from tests.fakes import FakeSession, inventory_service


class StockQuantityEditTest(InventoryTestBase):
    def edit(self, variant, value, *, expected=None, user=None, serials=()):
        return self.svc.set_stock_quantity(self.f.actor(user or self.admin), variant.ProductVariantId,
            StockQuantityUpdate(StockQuantity=value,
                ExpectedStockQuantity=variant.StockQuantity if expected is None else expected, SerialNumbers=list(serials)))

    def test_admin_increases_decreases_and_sets_zero_without_adjustment_history(self):
        variant = self.f.variant(stock=3, cost="70000")
        for value in (10, 2, 0):
            result = self.edit(variant, value)
            self.assertEqual((result.StockQuantity, variant.StockQuantity), (value, value))
            self.assertEqual(variant.CostPrice, Decimal("70000"))
            self.assertEqual(self.db.rows(StockAdjustment), [])
        self.assertIn(("ProductVariant", variant.ProductVariantId), self.db.locks)

    def test_negative_fractional_boolean_and_out_of_range_counts_are_rejected(self):
        for field in ("StockQuantity", "ExpectedStockQuantity"):
            for value in (-1, 1.5, True, "3", 2147483648):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    StockQuantityUpdate(**{**{"StockQuantity": 1, "ExpectedStockQuantity": 3}, field: value})

    def test_direct_service_also_rejects_negative_values_without_schema_validation(self):
        variant = self.f.variant(stock=3)
        body = StockQuantityUpdate.model_construct(StockQuantity=-1, ExpectedStockQuantity=3)
        with self.assertRaises(BusinessRuleError):
            self.svc.set_stock_quantity(self.f.actor(self.admin), variant.ProductVariantId, body)
        self.assertEqual(variant.StockQuantity, 3)

    def test_staff_and_customers_cannot_edit(self):
        variant = self.f.variant(stock=3)
        for user in (self.staff, self.customer):
            with self.subTest(role=user.Role), self.assertRaises(PermissionDeniedError):
                self.edit(variant, 5, user=user)
        self.assertEqual(variant.StockQuantity, 3)

    def test_stale_screen_does_not_overwrite_a_sale_or_receipt(self):
        variant = self.f.variant(stock=2)
        with self.assertRaises(ConflictError) as error: self.edit(variant, 10, expected=3)
        self.assertEqual(error.exception.code, "stock_quantity_changed")
        self.assertEqual(variant.StockQuantity, 2)

    def test_serial_increase_requires_codes_and_does_not_write_partial_changes(self):
        variant = self.f.variant(stock=1, serial_tracked=True)
        serial = self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId, SerialNumber="REAL-1", Status="Available"))
        with self.assertRaises(BusinessRuleError) as error: self.edit(variant, 2)
        self.assertEqual(error.exception.code, "serial_count_mismatch")
        self.assertEqual((variant.StockQuantity, serial.Status, serial.SerialNumber), (1, "Available", "REAL-1"))
        self.assertEqual(self.db.rows(StockAdjustment), [])

        self.edit(variant, 3, serials=[' REAL-2 ', 'REAL-3'])
        self.assertEqual(variant.StockQuantity, 3)
        self.assertEqual({s.SerialNumber for s in self.db.rows(ProductSerial)}, {'REAL-1', 'REAL-2', 'REAL-3'})
        self.assertEqual(self.db.rows(StockAdjustment), [])

    def test_duplicate_and_wrong_count_serials_never_change_stock(self):
        variant = self.f.variant(stock=0, serial_tracked=True)
        self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId, SerialNumber='OLD', Status='Sold'))
        for codes, error_type in ((['NEW'], BusinessRuleError), (['NEW', 'NEW'], BusinessRuleError),
                                  (['NEW', 'OLD'], ConflictError)):
            with self.subTest(codes=codes), self.assertRaises(error_type):
                self.edit(variant, 2, serials=codes)
            self.assertEqual(variant.StockQuantity, 0)
            self.assertEqual(len(self.db.rows(ProductSerial)), 1)

    def test_reduction_excludes_reserved_sold_and_other_variants(self):
        variant = self.f.variant(stock=2, serial_tracked=True)
        free = [self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId,
                SerialNumber=f'FREE-{i}', Status='Available')) for i in range(2)]
        reserved = self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId,
                  SerialNumber='HELD', Status='Reserved'))
        sold = self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId,
              SerialNumber='SOLD', Status='Sold'))
        other = self.db.add(ProductSerial(ProductVariantId=self.f.variant().ProductVariantId,
               SerialNumber='OTHER', Status='Available'))
        self.edit(variant, 1)
        self.assertEqual(sorted(s.Status for s in free), ['Available', 'WrittenOff'])
        self.assertEqual((reserved.Status, sold.Status, other.Status), ('Reserved', 'Sold', 'Available'))
        self.assertEqual(self.db.rows(StockAdjustment), [])

    def test_pending_orders_already_hold_quantity_before_they_hold_serials(self):
        variant = self.f.variant(stock=2, serial_tracked=True)
        self.f.order(self.customer, self.f.payment_method('COD'), lines=((variant, 1),), status='Pending')
        for i in range(3):
            self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId,
                        SerialNumber=f'PENDING-{i}', Status='Available'))
        self.edit(variant, 0)
        self.assertEqual(sum(s.Status == 'Available' for s in self.db.rows(ProductSerial)), 1)
        self.assertEqual(variant.StockQuantity, 0)

    def test_inconsistent_stock_or_locked_serials_require_reload_and_no_mutation(self):
        variant = self.f.variant(stock=1, serial_tracked=True)
        serial = self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId,
                  SerialNumber='FREE', Status='Available'))
        excess = self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId,
                  SerialNumber='EXCESS', Status='Available'))
        with self.assertRaises(ConflictError) as error:
            self.edit(variant, 0)
        self.assertEqual(error.exception.code, 'serial_stock_mismatch')
        excess.Status = 'WrittenOff'
        self.svc.serials.list_available_for_update = Mock(return_value=[])
        with self.assertRaises(ConflictError): self.edit(variant, 0)
        self.assertEqual((variant.StockQuantity, serial.Status), (1, 'Available'))

    def test_enabling_tracking_and_increasing_requires_only_new_units_then_commits_together(self):
        variant = self.f.variant(stock=10, serial_tracked=False)
        body = StockQuantityUpdate(StockQuantity=13, ExpectedStockQuantity=10, IsSerialTracked=True,
                                   ExpectedIsSerialTracked=False, SerialNumbers=['NEW-1', 'NEW-2', 'NEW-3'])
        response = self.svc.set_stock_quantity(self.f.actor(self.admin), variant.ProductVariantId, body)
        self.assertEqual((response.StockQuantity, response.IsSerialTracked), (13, True))
        self.assertEqual(len(self.db.rows(ProductSerial)), 3)
        self.assertEqual(self.db.rows(StockAdjustment), [])
        self.edit(variant, 8)  # First remove five old devices, without removing any code.
        self.assertTrue(all(s.Status == 'Available' for s in self.db.rows(ProductSerial)))
        self.edit(variant, 2)  # Five remaining old devices, then one coded device.
        self.assertEqual(sum(s.Status == 'WrittenOff' for s in self.db.rows(ProductSerial)), 1)

    def test_missing_codes_duplicate_codes_and_flush_failure_do_not_enable_tracking(self):
        variant = self.f.variant(stock=3, serial_tracked=False)
        for codes in ([], ['DUP', 'DUP']):
            with self.subTest(codes=codes), self.assertRaises(BusinessRuleError):
                self.svc.set_stock_quantity(self.f.actor(self.admin), variant.ProductVariantId,
                    StockQuantityUpdate(StockQuantity=5, ExpectedStockQuantity=3, IsSerialTracked=True,
                                        ExpectedIsSerialTracked=False, SerialNumbers=codes))
            self.assertEqual((variant.StockQuantity, variant.IsSerialTracked), (3, False))
            self.assertEqual(self.db.rows(ProductSerial), [])
        self.svc.variants.flush = Mock(side_effect=RuntimeError('write failure'))
        with self.assertRaises(RuntimeError):
            self.svc.set_stock_quantity(self.f.actor(self.admin), variant.ProductVariantId,
                StockQuantityUpdate(StockQuantity=4, ExpectedStockQuantity=3, IsSerialTracked=True,
                                    SerialNumbers=['NEW']))
        self.assertEqual((variant.StockQuantity, variant.IsSerialTracked), (3, False))
        self.assertEqual(self.db.rows(ProductSerial), [])

    def test_stale_tracking_setting_is_not_overwritten(self):
        variant = self.f.variant(stock=1, serial_tracked=True)
        with self.assertRaises(ConflictError) as error:
            self.svc.set_stock_quantity(self.f.actor(self.admin), variant.ProductVariantId,
                StockQuantityUpdate(StockQuantity=2, ExpectedStockQuantity=1, IsSerialTracked=True,
                                    ExpectedIsSerialTracked=False, SerialNumbers=['NEW']))
        self.assertEqual(error.exception.code, 'serial_tracking_changed')
        self.assertEqual(variant.StockQuantity, 1)

    def test_confirmed_legacy_units_are_not_counted_as_free_unnumbered_stock(self):
        variant = self.f.variant(stock=2, serial_tracked=True)
        self.f.order(self.customer, self.f.payment_method('COD'), lines=((variant, 5),), status='Processing')
        for i in range(2):
            self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId, SerialNumber=f'FREE-{i}', Status='Available'))
        self.edit(variant, 1)
        self.assertEqual(sum(s.Status == 'WrittenOff' for s in self.db.rows(ProductSerial)), 1)

    def test_serial_increase_and_reduction_are_rolled_back_on_persistence_failure(self):
        variant = self.f.variant(stock=1, serial_tracked=True)
        serial = self.db.add(ProductSerial(ProductVariantId=variant.ProductVariantId,
                  SerialNumber='FREE', Status='Available'))
        self.svc.variants.flush = Mock(side_effect=RuntimeError('save failed'))
        for quantity, codes in ((0, []), (2, ['NEW'])):
            with self.subTest(quantity=quantity), self.assertRaises(RuntimeError):
                self.edit(variant, quantity, serials=codes)
            self.assertEqual((variant.StockQuantity, serial.Status), (1, 'Available'))
            self.assertEqual(len(self.db.rows(ProductSerial)), 1)

    def test_failed_save_rolls_back_quantity(self):
        variant = self.f.variant(stock=3)
        self.svc.variants.flush = Mock(side_effect=RuntimeError("persistence failure"))
        with self.assertRaises(RuntimeError): self.edit(variant, 8)
        self.assertEqual(variant.StockQuantity, 3)

    def test_deleted_variant_cannot_be_edited(self):
        variant = self.f.variant(stock=3)
        variant.IsDeleted = True
        with self.assertRaises(NotFoundError): self.edit(variant, 8)


def test_http_stock_edit_role_validation_and_stale_state(flow):
    from app.main import app
    from app.routers.dependencies import get_inventory_service
    _, db, factory, as_user = flow
    app.dependency_overrides[get_inventory_service] = lambda: inventory_service(db, FakeSession(db))
    admin, staff = factory.user('Admin'), factory.user('Staff')
    variant = factory.variant(stock=3)
    path = f'/admin/variants/{variant.ProductVariantId}/stock'
    body = {'StockQuantity': 0, 'ExpectedStockQuantity': 3}
    assert as_user(staff).patch(path, json=body).status_code == 403
    assert as_user(admin).patch(path, json={**body, 'StockQuantity': -1}).status_code == 422
    response = as_user(admin).patch(path, json=body)
    assert response.status_code == 200 and response.json()['StockQuantity'] == 0
    assert db.rows(StockAdjustment) == []
    assert as_user(admin).patch(path, json={**body, 'StockQuantity': 10}).status_code == 409
    assert variant.StockQuantity == 0


def test_http_serial_stock_validation_and_atomic_registration(flow):
    from app.main import app
    from app.routers.dependencies import get_inventory_service
    _, db, factory, as_user = flow
    app.dependency_overrides[get_inventory_service] = lambda: inventory_service(db, FakeSession(db))
    admin = factory.user('Admin')
    variant = factory.variant(stock=10, serial_tracked=False)
    path = f'/admin/variants/{variant.ProductVariantId}/stock'
    client = as_user(admin)
    body = {'StockQuantity': 12, 'ExpectedStockQuantity': 10, 'IsSerialTracked': True, 'ExpectedIsSerialTracked': False}
    assert client.patch(path, json=body).status_code == 400
    for codes in ([''], ['x' * 101]):
        assert client.patch(path, json={**body, 'SerialNumbers': codes}).status_code == 422
    assert (variant.StockQuantity, variant.IsSerialTracked) == (10, False) and db.rows(ProductSerial) == []
    assert client.patch(path, json={**body, 'SerialNumbers': ['NEW-1', 'NEW-2']}).status_code == 200
    assert (variant.StockQuantity, variant.IsSerialTracked) == (12, True) and len(db.rows(ProductSerial)) == 2
    assert client.patch(path, json={'StockQuantity': 2, 'ExpectedStockQuantity': 12}).status_code == 200
    assert all(s.Status == 'Available' for s in db.rows(ProductSerial))
    assert client.patch(path, json={'StockQuantity': 0, 'ExpectedStockQuantity': 2}).status_code == 200
    assert variant.StockQuantity == 0
    assert all(s.Status == 'WrittenOff' for s in db.rows(ProductSerial))
    assert db.rows(StockAdjustment) == []
