"""purchasing: lịch sử nhận hàng (PurchaseReceipts/Items) và trạng thái Closed cho phiếu giao thiếu

Revision ID: e2b8c4f6a913
Revises: 5d1f9a3c7e64
Create Date: 2026-10-10 14:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy TRƯỚC khi triển khai PurchaseOrderService đợt 5.1.
Migration SePay (b81569bc34b0) đặt sau migration này.

- PurchaseOrders.Status thêm Closed (Admin đóng phiếu còn thiếu, bắt buộc lý do); thêm ClosedByUserId (SET NULL),
  ClosedAt, CloseReason; CHECK Closed_Consistent. Số đặt/đã nhận giữ nguyên; số thiếu = Ordered − Received.
- PurchaseReceipts / PurchaseReceiptItems: mỗi lần nhận hàng thực tế (người nhận, thời điểm, số lượng, đơn giá).
  Chỉ ghi thêm (trigger chặn UPDATE/DELETE).
- Không tự tạo lịch sử cho các lần nhận trước migration (không suy đoán người nhận/thời điểm).
Downgrade dừng nếu đã có phiếu Closed hoặc lịch sử nhận hàng.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b8c4f6a913'
down_revision: Union[str, Sequence[str], None] = '5d1f9a3c7e64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ORDERS = "PurchaseOrders"
RECEIPTS = "PurchaseReceipts"
ITEMS = "PurchaseReceiptItems"
DATA_API_ROLES = "anon, authenticated"
APPEND_ONLY_FUNCTION = "public.prevent_purchase_receipt_change()"
OLD_STATUSES = ("Pending", "Approved", "Rejected", "Receiving", "Completed", "Cancelled")
NEW_STATUSES = OLD_STATUSES + ("Closed",)
CLOSED_CONSISTENT_SQL = (
    "(\"Status\" = 'Closed' AND \"ClosedAt\" IS NOT NULL AND \"CloseReason\" IS NOT NULL "
    "AND length(btrim(\"CloseReason\")) > 0) OR "
    "(\"Status\" <> 'Closed' AND \"ClosedAt\" IS NULL AND \"CloseReason\" IS NULL)"
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f'"{column}" IN (' + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f("CK_PurchaseOrders_Status_Valid"), ORDERS, type_="check")
    op.create_check_constraint(op.f("CK_PurchaseOrders_Status_Valid"), ORDERS, _in("Status", NEW_STATUSES))
    op.add_column(ORDERS, sa.Column("ClosedByUserId", sa.UUID(), nullable=True))
    op.add_column(ORDERS, sa.Column("ClosedAt", sa.DateTime(timezone=True), nullable=True))
    op.add_column(ORDERS, sa.Column("CloseReason", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("FK_PurchaseOrders_ClosedByUserId"), ORDERS, "Users", ["ClosedByUserId"], ["UserId"], ondelete="SET NULL"
    )
    op.create_check_constraint(op.f("CK_PurchaseOrders_Closed_Consistent"), ORDERS, CLOSED_CONSISTENT_SQL)

    op.create_table(
        RECEIPTS,
        sa.Column("PurchaseReceiptId", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("PurchaseOrderId", sa.UUID(), nullable=False),
        sa.Column("ReceivedByUserId", sa.UUID(), nullable=False),
        sa.Column("ReceivedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("Note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["PurchaseOrderId"], ["PurchaseOrders.PurchaseOrderId"],
            name=op.f("FK_PurchaseReceipts_PurchaseOrderId"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ReceivedByUserId"], ["Users.UserId"], name=op.f("FK_PurchaseReceipts_ReceivedByUserId"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("PurchaseReceiptId", name=op.f("PK_PurchaseReceipts")),
    )
    op.create_index("IX_PurchaseReceipts_PurchaseOrderId_ReceivedAt", RECEIPTS, ["PurchaseOrderId", "ReceivedAt"], unique=False)

    op.create_table(
        ITEMS,
        sa.Column("PurchaseReceiptId", sa.UUID(), nullable=False),
        sa.Column("PurchaseOrderItemId", sa.UUID(), nullable=False),
        sa.Column("Quantity", sa.Integer(), nullable=False),
        sa.Column("UnitPrice", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.CheckConstraint('"Quantity" > 0', name=op.f("CK_PurchaseReceiptItems_Quantity_Positive")),
        sa.CheckConstraint('"UnitPrice" >= 0', name=op.f("CK_PurchaseReceiptItems_UnitPrice_NonNegative")),
        sa.ForeignKeyConstraint(
            ["PurchaseReceiptId"], ["PurchaseReceipts.PurchaseReceiptId"],
            name=op.f("FK_PurchaseReceiptItems_PurchaseReceiptId"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["PurchaseOrderItemId"], ["PurchaseOrderItems.PurchaseOrderItemId"],
            name=op.f("FK_PurchaseReceiptItems_PurchaseOrderItemId"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("PurchaseReceiptId", "PurchaseOrderItemId", name=op.f("PK_PurchaseReceiptItems")),
    )
    op.create_index("IX_PurchaseReceiptItems_PurchaseOrderItemId", ITEMS, ["PurchaseOrderItemId"], unique=False)

    # Viết thủ công: lịch sử nhận hàng chỉ được ghi thêm.
    op.execute(
        f"""
        CREATE FUNCTION {APPEND_ONLY_FUNCTION}
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = ''
        AS $$
        BEGIN
            RAISE EXCEPTION 'Lich su nhan hang chi duoc ghi them, khong duoc sua hoac xoa';
        END;
        $$
        """
    )
    op.execute(f"REVOKE EXECUTE ON FUNCTION {APPEND_ONLY_FUNCTION} FROM PUBLIC")
    op.execute(f"REVOKE EXECUTE ON FUNCTION {APPEND_ONLY_FUNCTION} FROM {DATA_API_ROLES}")
    for table in (RECEIPTS, ITEMS):
        op.execute(
            f'CREATE TRIGGER "TR_{table}_AppendOnly" BEFORE UPDATE OR DELETE ON "{table}" '
            f"FOR EACH ROW EXECUTE FUNCTION {APPEND_ONLY_FUNCTION}"
        )
        # Viết thủ công: security hardening cho Supabase Data API (giống các bảng khác).
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM {DATA_API_ROLES}')


def downgrade() -> None:
    """Downgrade schema. Thất bại có chủ đích nếu đã có phiếu Closed hoặc lịch sử nhận hàng."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{RECEIPTS}") OR EXISTS (SELECT 1 FROM "{ORDERS}" WHERE "Status" = 'Closed') THEN
                RAISE EXCEPTION 'Da co lich su nhan hang hoac phieu nhap Closed; khong ha cap';
            END IF;
        END
        $$
        """
    )
    for table in (ITEMS, RECEIPTS):
        op.execute(f'DROP TRIGGER "TR_{table}_AppendOnly" ON "{table}"')
    op.execute(f"DROP FUNCTION {APPEND_ONLY_FUNCTION}")
    op.drop_index("IX_PurchaseReceiptItems_PurchaseOrderItemId", table_name=ITEMS)
    op.drop_table(ITEMS)
    op.drop_index("IX_PurchaseReceipts_PurchaseOrderId_ReceivedAt", table_name=RECEIPTS)
    op.drop_table(RECEIPTS)
    op.drop_constraint(op.f("CK_PurchaseOrders_Closed_Consistent"), ORDERS, type_="check")
    op.drop_constraint(op.f("FK_PurchaseOrders_ClosedByUserId"), ORDERS, type_="foreignkey")
    op.drop_column(ORDERS, "CloseReason")
    op.drop_column(ORDERS, "ClosedAt")
    op.drop_column(ORDERS, "ClosedByUserId")
    op.drop_constraint(op.f("CK_PurchaseOrders_Status_Valid"), ORDERS, type_="check")
    op.create_check_constraint(op.f("CK_PurchaseOrders_Status_Valid"), ORDERS, _in("Status", OLD_STATUSES))
