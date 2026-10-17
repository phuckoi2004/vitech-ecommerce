"""Purchase reader names are returned without exposing account-management data."""

from unittest.mock import patch

from pydantic import ValidationError

from app.models import PurchaseOrder
from app.schemas import PurchaseOrderCreate, PurchaseOrderUpdate
from app.services import PermissionDeniedError
from tests.test_purchasing import PurchaseOrderTestBase


class PurchaseCreatorNameTest(PurchaseOrderTestBase):
    def test_decision_name_is_returned_to_staff_from_detail_and_decision_response(self):
        po = self.create_po()
        approved = self.approve(po.PurchaseOrderId, by=self.admin2)
        self.assertEqual(approved.DecidedByName, self.admin2.FullName)
        self.admin2.IsDeleted = True  # historical account still has a display name
        detail = self.svc.get_purchase_order(self.f.actor(self.staff), po.PurchaseOrderId)
        self.assertEqual(detail.DecidedByName, self.admin2.FullName)
        self.assertEqual(detail.DecidedByUserId, self.admin2.UserId)
        for private_field in ("PasswordHash", "Email", "PhoneNumber"):
            self.assertNotIn(private_field, detail.model_dump())
        with self.assertRaises(PermissionDeniedError):
            self.svc.get_purchase_order(self.f.actor(self.customer), po.PurchaseOrderId)

    def test_rejected_decision_name_clears_when_resubmitted(self):
        po = self.create_po()
        rejected = self.reject(po.PurchaseOrderId, by=self.admin)
        self.assertEqual(rejected.DecidedByName, self.admin.FullName)
        resubmitted = self.svc.resubmit_purchase_order(self.f.actor(self.staff), po.PurchaseOrderId)
        self.assertIsNone(resubmitted.DecidedByName)
        self.assertIsNone(resubmitted.DecidedByUserId)

    def test_pending_and_automatic_approval_do_not_invent_a_separate_decision(self):
        pending = self.create_po()
        automatic = self.create_po(self.admin)
        self.assertIsNone(pending.DecidedByName)
        self.assertIsNone(automatic.DecidedByName)
        self.assertIsNone(automatic.DecidedByUserId)
        self.assertEqual(automatic.Status, "Approved")
        self.assertEqual(automatic.CreatedByName, self.admin.FullName)

    def test_client_cannot_write_decision_display_name(self):
        with self.assertRaises(ValidationError):
            PurchaseOrderUpdate.model_validate({"DecidedByName": "Forged approver"})

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
