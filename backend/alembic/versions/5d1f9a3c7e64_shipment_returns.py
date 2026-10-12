"""order: ShipmentReturns / ShipmentReturnItems — hàng của đơn hủy khi đang giao chờ quay về kho

Revision ID: 5d1f9a3c7e64
Revises: 8b7e3d1c5a29
Create Date: 2026-10-10 11:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy TRƯỚC khi triển khai OrderService đợt 5.1 (hủy đơn đang giao không hoàn
tồn ngay; nhận lại và kiểm tra hàng). Migration SePay (b81569bc34b0) đặt sau migration này.

- ShipmentReturns: một hồ sơ mỗi đơn (UNIQUE OrderId); AwaitingReturn → Received (một lần, ReceivedAt bắt buộc).
- ShipmentReturnItems: một dòng mỗi serial (ExpectedQuantity = 1) hoặc mỗi dòng đơn không quản lý serial;
  RestockedQuantity + DamagedQuantity = ExpectedQuantity khi đã nhận.
Downgrade dừng nếu đã có hồ sơ (không xóa lịch sử hàng hoàn kho).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d1f9a3c7e64'
down_revision: Union[str, Sequence[str], None] = '8b7e3d1c5a29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RETURNS = "ShipmentReturns"
ITEMS = "ShipmentReturnItems"
DATA_API_ROLES = "anon, authenticated"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        RETURNS,
        sa.Column("ShipmentReturnId", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("OrderId", sa.UUID(), nullable=False),
        sa.Column("Status", sa.String(length=20), nullable=False),
        sa.Column("CreatedByUserId", sa.UUID(), nullable=True),
        sa.Column("CreatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ReceivedByUserId", sa.UUID(), nullable=True),
        sa.Column("ReceivedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("Note", sa.Text(), nullable=True),
        sa.CheckConstraint("\"Status\" IN ('AwaitingReturn', 'Received')", name=op.f("CK_ShipmentReturns_Status_Valid")),
        sa.CheckConstraint(
            "(\"Status\" = 'AwaitingReturn' AND \"ReceivedAt\" IS NULL) OR "
            "(\"Status\" = 'Received' AND \"ReceivedAt\" IS NOT NULL)",
            name=op.f("CK_ShipmentReturns_Receipt_Consistent"),
        ),
        sa.ForeignKeyConstraint(["OrderId"], ["Orders.OrderId"], name=op.f("FK_ShipmentReturns_OrderId"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["CreatedByUserId"], ["Users.UserId"], name=op.f("FK_ShipmentReturns_CreatedByUserId"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["ReceivedByUserId"], ["Users.UserId"], name=op.f("FK_ShipmentReturns_ReceivedByUserId"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("ShipmentReturnId", name=op.f("PK_ShipmentReturns")),
        sa.UniqueConstraint("OrderId", name=op.f("UQ_ShipmentReturns_OrderId")),
    )
    op.create_index("IX_ShipmentReturns_Status_CreatedAt", RETURNS, ["Status", "CreatedAt"], unique=False)

    op.create_table(
        ITEMS,
        sa.Column("ShipmentReturnItemId", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("ShipmentReturnId", sa.UUID(), nullable=False),
        sa.Column("OrderItemId", sa.UUID(), nullable=False),
        sa.Column("ProductSerialId", sa.UUID(), nullable=True),
        sa.Column("ExpectedQuantity", sa.Integer(), nullable=False),
        sa.Column("RestockedQuantity", sa.Integer(), nullable=True),
        sa.Column("DamagedQuantity", sa.Integer(), nullable=True),
        sa.CheckConstraint('"ExpectedQuantity" > 0', name=op.f("CK_ShipmentReturnItems_ExpectedQuantity_Positive")),
        sa.CheckConstraint(
            '"ProductSerialId" IS NULL OR "ExpectedQuantity" = 1', name=op.f("CK_ShipmentReturnItems_Serial_SingleUnit")
        ),
        sa.CheckConstraint(
            '("RestockedQuantity" IS NULL AND "DamagedQuantity" IS NULL) OR '
            '("RestockedQuantity" >= 0 AND "DamagedQuantity" >= 0 '
            'AND "RestockedQuantity" + "DamagedQuantity" = "ExpectedQuantity")',
            name=op.f("CK_ShipmentReturnItems_Outcome_Consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["ShipmentReturnId"], ["ShipmentReturns.ShipmentReturnId"],
            name=op.f("FK_ShipmentReturnItems_ShipmentReturnId"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["OrderItemId"], ["OrderItems.OrderItemId"], name=op.f("FK_ShipmentReturnItems_OrderItemId"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ProductSerialId"], ["ProductSerials.ProductSerialId"],
            name=op.f("FK_ShipmentReturnItems_ProductSerialId"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ShipmentReturnItemId", name=op.f("PK_ShipmentReturnItems")),
    )
    op.create_index(
        "UX_ShipmentReturnItems_Return_OrderItem_NoSerial", ITEMS, ["ShipmentReturnId", "OrderItemId"], unique=True,
        postgresql_where=sa.text('"ProductSerialId" IS NULL'),
    )
    op.create_index(
        "UX_ShipmentReturnItems_Return_Serial", ITEMS, ["ShipmentReturnId", "ProductSerialId"], unique=True,
        postgresql_where=sa.text('"ProductSerialId" IS NOT NULL'),
    )
    op.create_index("IX_ShipmentReturnItems_ProductSerialId", ITEMS, ["ProductSerialId"], unique=False)

    # Viết thủ công: security hardening cho Supabase Data API (giống các bảng khác).
    for table in (RETURNS, ITEMS):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM {DATA_API_ROLES}')


def downgrade() -> None:
    """Downgrade schema. Thất bại có chủ đích nếu đã có hồ sơ hàng hoàn kho."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{RETURNS}") THEN
                RAISE EXCEPTION 'Da co ho so hang hoan kho (ShipmentReturns); khong ha cap';
            END IF;
        END
        $$
        """
    )
    op.drop_index("IX_ShipmentReturnItems_ProductSerialId", table_name=ITEMS)
    op.drop_index("UX_ShipmentReturnItems_Return_Serial", table_name=ITEMS)
    op.drop_index("UX_ShipmentReturnItems_Return_OrderItem_NoSerial", table_name=ITEMS)
    op.drop_table(ITEMS)
    op.drop_index("IX_ShipmentReturns_Status_CreatedAt", table_name=RETURNS)
    op.drop_table(RETURNS)
