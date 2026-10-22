"""Link a replacement order to its return request; snapshot applied exchange credit.

Revision ID: e6a2c9d4b810
Revises: c3a9f5e7d206
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e6a2c9d4b810"
down_revision = "c3a9f5e7d206"
branch_labels = None
depends_on = None


def installed(connection):
    """Allow adoption after the same narrowly scoped DDL was applied on a shared DB with external history."""
    inspector = sa.inspect(connection)
    columns = {c["name"]: c for c in inspector.get_columns("Orders")}
    present = set(columns) & {"SourceReturnRequestId", "ExchangeCreditAmount"}
    if not present:
        return False
    if len(present) != 2:
        raise RuntimeError("Partial exchange schema; refusing to guess missing changes")
    credit, source = columns["ExchangeCreditAmount"], columns["SourceReturnRequestId"]
    if (credit["nullable"] or not source["nullable"] or not isinstance(credit["type"], sa.Numeric)
            or credit["type"].precision != 15 or credit["type"].scale != 2
            or not isinstance(source["type"], sa.Uuid)
            or credit["default"] is None or "0" not in str(credit["default"])):
        raise RuntimeError("Unexpected exchange column definitions")
    fk = next((f for f in inspector.get_foreign_keys("Orders") if f["constrained_columns"] == ["SourceReturnRequestId"]), None)
    index = next((i for i in inspector.get_indexes("Orders") if i["name"] == "UX_Orders_SourceReturn_Active"), None)
    checks = {c["name"]: c["sqltext"] for c in inspector.get_check_constraints("Orders")}
    if (not fk or fk["referred_table"] != "ReturnRequests" or fk["referred_columns"] != ["ReturnRequestId"]
            or fk.get("options", {}).get("ondelete") != "RESTRICT"
            or not index or not index["unique"] or index["column_names"] != ["SourceReturnRequestId"]
            or "Cancelled" not in str(index.get("dialect_options", {}).get("postgresql_where", ""))
            or not all(name in checks for name in ("CK_Orders_ExchangeCredit_Valid", "CK_Orders_ExchangeCredit_Source"))):
        raise RuntimeError("Exchange schema constraints differ; manual inspection required")
    return True


def upgrade():
    if not op.get_context().as_sql and installed(op.get_bind()):
        return
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("Orders", sa.Column("SourceReturnRequestId", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("Orders", sa.Column("ExchangeCreditAmount", sa.Numeric(15, 2), server_default="0", nullable=False))
    op.create_foreign_key("FK_Orders_SourceReturnRequestId", "Orders", "ReturnRequests",
                          ["SourceReturnRequestId"], ["ReturnRequestId"], ondelete="RESTRICT")
    op.create_check_constraint(op.f("CK_Orders_ExchangeCredit_Valid"), "Orders", '"ExchangeCreditAmount" >= 0 AND "ExchangeCreditAmount" <= "DiscountAmount"')
    op.create_check_constraint(op.f("CK_Orders_ExchangeCredit_Source"), "Orders", '"SourceReturnRequestId" IS NOT NULL OR "ExchangeCreditAmount" = 0')
    op.create_index("UX_Orders_SourceReturn_Active", "Orders", ["SourceReturnRequestId"], unique=True,
                    postgresql_where=sa.text('"SourceReturnRequestId" IS NOT NULL AND "OrderStatus" <> \'Cancelled\''))


def downgrade():
    op.drop_index("UX_Orders_SourceReturn_Active", table_name="Orders")
    op.drop_constraint(op.f("CK_Orders_ExchangeCredit_Source"), "Orders", type_="check")
    op.drop_constraint(op.f("CK_Orders_ExchangeCredit_Valid"), "Orders", type_="check")
    op.drop_constraint("FK_Orders_SourceReturnRequestId", "Orders", type_="foreignkey")
    op.drop_column("Orders", "ExchangeCreditAmount")
    op.drop_column("Orders", "SourceReturnRequestId")
