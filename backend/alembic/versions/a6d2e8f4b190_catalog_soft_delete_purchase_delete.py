"""Separate catalog hide/delete and allow deletion of complete purchase documents.

Revision ID: a6d2e8f4b190
Revises: 7e4c9b2d1a60
"""
from alembic import op
import sqlalchemy as sa

revision = "a6d2e8f4b190"
down_revision = "7e4c9b2d1a60"
branch_labels = None
depends_on = None


def _receipt_guard(allow_document_delete: bool) -> None:
    condition = """
        IF TG_OP = 'DELETE' THEN
            IF TG_TABLE_NAME = 'PurchaseReceipts' THEN
                IF NOT EXISTS (SELECT 1 FROM public."PurchaseOrders"
                               WHERE "PurchaseOrderId" = OLD."PurchaseOrderId") THEN
                    RETURN OLD;
                END IF;
            ELSIF TG_TABLE_NAME = 'PurchaseReceiptItems' THEN
                IF NOT EXISTS (
                    SELECT 1 FROM public."PurchaseReceipts" r
                    JOIN public."PurchaseOrders" p ON p."PurchaseOrderId" = r."PurchaseOrderId"
                    WHERE r."PurchaseReceiptId" = OLD."PurchaseReceiptId"
                ) THEN
                    RETURN OLD;
                END IF;
            END IF;
        END IF;
    """ if allow_document_delete else ""
    op.execute(f"""
        CREATE OR REPLACE FUNCTION public.prevent_purchase_receipt_change()
        RETURNS trigger LANGUAGE plpgsql SET search_path = '' AS $$
        BEGIN
            {condition}
            RAISE EXCEPTION 'Lich su nhan hang chi duoc xoa cung toan bo phieu nhap, khong duoc sua rieng';
        END;
        $$
    """)


def _receipt_fks(ondelete: str) -> None:
    for table, column, parent, pk in (
        ("PurchaseReceipts", "PurchaseOrderId", "PurchaseOrders", "PurchaseOrderId"),
        ("PurchaseReceiptItems", "PurchaseOrderItemId", "PurchaseOrderItems", "PurchaseOrderItemId"),
    ):
        name = op.f(f"FK_{table}_{column}")
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, parent, [column], [pk], ondelete=ondelete)


def upgrade() -> None:
    for table in ("Categories", "Brands"):
        op.add_column(table, sa.Column("IsDeleted", sa.Boolean(), nullable=False, server_default=sa.text("false")), if_not_exists=True)
    _receipt_fks("CASCADE")
    _receipt_guard(True)


def downgrade() -> None:
    # Do not silently resurrect soft-deleted catalog entries.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM "Categories" WHERE "IsDeleted")
           OR EXISTS (SELECT 1 FROM "Brands" WHERE "IsDeleted") THEN
            RAISE EXCEPTION 'Cannot downgrade while soft-deleted catalog entries exist';
        END IF;
    END $$""")
    _receipt_guard(False)
    _receipt_fks("RESTRICT")
    for table in ("Categories", "Brands"):
        op.drop_column(table, "IsDeleted")
