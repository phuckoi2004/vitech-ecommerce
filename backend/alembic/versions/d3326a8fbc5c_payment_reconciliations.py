"""payment reconciliations: bản ghi đối soát thanh toán bất thường

Revision ID: d3326a8fbc5c
Revises: 763f153af842
Create Date: 2026-10-09 21:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy cùng/sau 763f153af842 và TRƯỚC khi triển khai code PaymentService có
PaymentReconciliationRepository (callback thanh toán sẽ lỗi nếu bảng chưa tồn tại).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd3326a8fbc5c'
down_revision: Union[str, Sequence[str], None] = '763f153af842'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "PaymentReconciliations"
DATA_API_ROLES = "anon, authenticated"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        TABLE,
        sa.Column("PaymentReconciliationId", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("OrderId", sa.UUID(), nullable=False),
        sa.Column("PaymentTransactionId", sa.UUID(), nullable=False),
        sa.Column("IssueType", sa.String(length=30), nullable=False),
        sa.Column("GatewayTransactionCode", sa.String(length=100), nullable=False),
        sa.Column("ExpectedAmount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("ReceivedAmount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("ResponseData", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("Status", sa.String(length=20), nullable=False),
        sa.Column("ResolutionNote", sa.Text(), nullable=True),
        sa.Column("ResolvedByUserId", sa.UUID(), nullable=True),
        sa.Column("ResolvedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("CreatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "\"IssueType\" IN ('AmountMismatch', 'DuplicatePayment', 'PaymentAfterCancellation')",
            name=op.f("CK_PaymentReconciliations_IssueType_Valid"),
        ),
        sa.CheckConstraint("\"Status\" IN ('Open', 'Resolved')", name=op.f("CK_PaymentReconciliations_Status_Valid")),
        sa.CheckConstraint('"ExpectedAmount" >= 0', name=op.f("CK_PaymentReconciliations_ExpectedAmount_NonNegative")),
        sa.CheckConstraint('"ReceivedAmount" >= 0', name=op.f("CK_PaymentReconciliations_ReceivedAmount_NonNegative")),
        sa.CheckConstraint(
            "(\"Status\" = 'Open' AND \"ResolvedAt\" IS NULL) OR (\"Status\" = 'Resolved' AND \"ResolvedAt\" IS NOT NULL)",
            name=op.f("CK_PaymentReconciliations_Resolution_Consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["OrderId"], ["Orders.OrderId"], name=op.f("FK_PaymentReconciliations_OrderId"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["PaymentTransactionId"], ["PaymentTransactions.PaymentTransactionId"],
            name=op.f("FK_PaymentReconciliations_PaymentTransactionId"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ResolvedByUserId"], ["Users.UserId"], name=op.f("FK_PaymentReconciliations_ResolvedByUserId"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("PaymentReconciliationId", name=op.f("PK_PaymentReconciliations")),
        # Khóa idempotency: callback gửi lặp không tạo bản ghi đối soát trùng.
        sa.UniqueConstraint(
            "GatewayTransactionCode", "IssueType", name=op.f("UQ_PaymentReconciliations_GatewayTransactionCode_IssueType")
        ),
    )
    op.create_index("IX_PaymentReconciliations_Status_CreatedAt", TABLE, ["Status", "CreatedAt"], unique=False)
    op.create_index("IX_PaymentReconciliations_OrderId", TABLE, ["OrderId"], unique=False)

    # Viết thủ công: security hardening cho Supabase Data API (giống các bảng khác).
    op.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{TABLE}" FROM {DATA_API_ROLES}')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("IX_PaymentReconciliations_OrderId", table_name=TABLE)
    op.drop_index("IX_PaymentReconciliations_Status_CreatedAt", table_name=TABLE)
    op.drop_table(TABLE)
