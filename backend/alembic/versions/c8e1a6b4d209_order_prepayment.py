"""Snapshot mandatory 20% prepayment on new high-value COD orders.

Revision ID: c8e1a6b4d209
Revises: f4b8c1d2e930
"""
from alembic import op
import sqlalchemy as sa

revision = "c8e1a6b4d209"
down_revision = "f4b8c1d2e930"
branch_labels = None
depends_on = None

STATUSES = "'Pending', 'PartiallyPaid', 'Paid', 'Failed', 'Refunded', 'Cancelled'"


def upgrade():
    if not op.get_context().as_sql:
        inspector = sa.inspect(op.get_bind())
        column = next((c for c in inspector.get_columns("Orders") if c["name"] == "PrepaymentAmount"), None)
        if column:
            checks = {c["name"]: c["sqltext"] for c in inspector.get_check_constraints("Orders")}
            if (column["nullable"] or not isinstance(column["type"], sa.Numeric)
                    or column["type"].precision != 15 or column["type"].scale != 2
                    or column["default"] is None or "0" not in str(column["default"])
                    or "CK_Orders_PrepaymentAmount_Valid" not in checks
                    or "PartiallyPaid" not in checks.get("CK_Orders_PaymentStatus_Valid", "")):
                raise RuntimeError("Unexpected prepayment schema; manual inspection required")
            return
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("Orders", sa.Column("PrepaymentAmount", sa.Numeric(15, 2), server_default="0", nullable=False))
    op.create_check_constraint(op.f("CK_Orders_PrepaymentAmount_Valid"), "Orders",
                               '"PrepaymentAmount" >= 0 AND "PrepaymentAmount" <= "TotalAmount"')
    op.drop_constraint(op.f("CK_Orders_PaymentStatus_Valid"), "Orders", type_="check")
    op.create_check_constraint(op.f("CK_Orders_PaymentStatus_Valid"), "Orders", f'"PaymentStatus" IN ({STATUSES})')


def downgrade():
    op.drop_constraint(op.f("CK_Orders_PaymentStatus_Valid"), "Orders", type_="check")
    op.create_check_constraint(op.f("CK_Orders_PaymentStatus_Valid"), "Orders",
                               '"PaymentStatus" IN (\'Pending\', \'Paid\', \'Failed\', \'Refunded\', \'Cancelled\')')
    op.drop_constraint(op.f("CK_Orders_PrepaymentAmount_Valid"), "Orders", type_="check")
    op.drop_column("Orders", "PrepaymentAmount")
