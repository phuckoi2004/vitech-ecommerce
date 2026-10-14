"""Purchase reader names are returned without exposing account-management data."""

from unittest.mock import patch

from pydantic import ValidationError

from app.models import PurchaseOrder
from app.schemas import PurchaseOrderCreate, PurchaseOrderUpdate
from app.services import PermissionDeniedError
from tests.test_purchasing import PurchaseOrderTestBase


class PurchaseCreatorNameTest(PurchaseOrderTestBase):
    def test_staff_reads_other_staff_and_admin_creator_names(self):
        staff_order = self.create_po()
        admin_order = self.create_po(self.admin)
        reader = self.f.user("Staff")
        with (
            patch.object(self.svc.purchase_orders, "list_purchase_orders", return_value=self.db.rows(PurchaseOrder), create=True),
            patch.object(self.svc.purchase_orders, "count_purchase_orders", return_value=2, create=True),
        ):
            page = self.svc.list_purchase_orders(self.f.actor(reader))
        names = {row.PurchaseOrderId: row.CreatedByName for row in page.Items}
        self.assertEqual(names[staff_order.PurchaseOrderId], self.staff.FullName)
        self.assertEqual(names[admin_order.PurchaseOrderId], self.admin.FullName)
        detail = self.svc.get_purchase_order(self.f.actor(reader), admin_order.PurchaseOrderId)
        self.assertEqual(detail.CreatedByName, self.admin.FullName)
        payload = detail.model_dump(mode="json")
        self.assertNotIn("PasswordHash", payload)
        self.assertNotIn("Email", payload)
        self.assertNotIn("PhoneNumber", payload)

    def test_create_and_write_responses_include_the_server_creator_name(self):
        po = self.create_po()
        self.assertEqual(po.CreatedByName, self.staff.FullName)
        updated = self.svc.update_purchase_order(self.f.actor(self.staff), po.PurchaseOrderId, PurchaseOrderUpdate(Note="Ghi chú"))
        self.assertEqual(updated.CreatedByName, self.staff.FullName)
        approved = self.approve(po.PurchaseOrderId)
        self.assertEqual(approved.CreatedByName, self.staff.FullName)

    def test_soft_deleted_creator_keeps_name_and_customer_still_cannot_read(self):
        po = self.create_po()
        self.staff.IsDeleted = True
        detail = self.svc.get_purchase_order(self.f.actor(self.admin), po.PurchaseOrderId)
        self.assertEqual(detail.CreatedByName, self.staff.FullName)
        with self.assertRaises(PermissionDeniedError):
            self.svc.list_purchase_orders(self.f.actor(self.customer))
        with self.assertRaises(PermissionDeniedError):
            self.svc.get_purchase_order(self.f.actor(self.customer), po.PurchaseOrderId)

    def test_client_cannot_supply_creator_name_when_creating_purchase(self):
        with self.assertRaises(ValidationError):
            PurchaseOrderCreate.model_validate({
                "SupplierId": self.supplier.SupplierId,
                "CreatedByName": "Tên giả từ client",
                "Items": [{"ProductVariantId": self.v1.ProductVariantId, "OrderedQuantity": 1, "UnitPrice": "1.00"}],
            })
