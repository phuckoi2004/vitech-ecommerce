"""Compile the scoped migration using the PostgreSQL dialect without connecting to a database."""
import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_upgrade_is_limited_to_catalog_flags_and_purchase_receipt_deletion():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/a6d2e8f4b190_catalog_soft_delete_purchase_delete.py"
    spec = importlib.util.spec_from_file_location("catalog_purchase_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        module.upgrade()
    sql = output.getvalue()
    assert 'ALTER TABLE "Categories" ADD COLUMN IF NOT EXISTS "IsDeleted" BOOLEAN DEFAULT false NOT NULL' in sql
    assert 'ALTER TABLE "Brands" ADD COLUMN IF NOT EXISTS "IsDeleted" BOOLEAN DEFAULT false NOT NULL' in sql
    assert sql.count("ON DELETE CASCADE") == 2
    assert "IF TG_OP = 'DELETE'" in sql
    assert 'JOIN public."PurchaseOrders"' in sql
    assert "UPDATE \"ProductVariants\"" not in sql
    assert "ProductSerials" not in sql
