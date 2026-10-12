"""payment webhook events (SePay) và đối soát UnmatchedPayment

Revision ID: b81569bc34b0
Revises: a9f4c2e7b513
Create Date: 2026-10-09 23:00:00.000000

CHƯA ÁP DỤNG vào database. Migration SePay luôn đứng CUỐI chuỗi (sau các migration Service Layer:
763f153af842, d3326a8fbc5c, 4c2d9e7a1f53, 8b7e3d1c5a29, 5d1f9a3c7e64,
e2b8c4f6a913, a7c3e9d1f285, c8d2f4a6b1e3, d4f7b2e9a6c1, f3b8d1a5c7e2, e6a2d9c4b8f1, a9f4c2e7b513), TRƯỚC khi triển khai code webhook SePay (PaymentWebhookService)
và PaymentReconciliation có cột PaymentWebhookEventId.

- Tạo PaymentWebhookEvents: lưu bền vững giao dịch ngân hàng từ webhook trước khi xử lý; UNIQUE
  (Provider, AccountNumber, ProviderTransactionId) chống xử lý trùng khi SePay gửi lại.
- PaymentReconciliations: thêm loại UnmatchedPayment (tiền vào không xác định được đơn) nên OrderId,
  PaymentTransactionId, ExpectedAmount được NULL chỉ với loại này; thêm PaymentWebhookEventId.
Downgrade thất bại nếu đã có bản ghi UnmatchedPayment (cột NOT NULL không khôi phục được) — có chủ đích,
để không xóa dữ liệu đối soát.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b81569bc34b0'
down_revision: Union[str, Sequence[str], None] = 'a9f4c2e7b513'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EVENTS = "PaymentWebhookEvents"
RECONCILIATIONS = "PaymentReconciliations"
DATA_API_ROLES = "anon, authenticated"
OLD_ISSUE_TYPES = ("AmountMismatch", "DuplicatePayment", "PaymentAfterCancellation")
NEW_ISSUE_TYPES = OLD_ISSUE_TYPES + ("UnmatchedPayment",)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f'"{column}" IN (' + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        EVENTS,
        sa.Column("PaymentWebhookEventId", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("Provider", sa.String(length=30), nullable=False),
        sa.Column("ProviderTransactionId", sa.String(length=100), nullable=False),
        sa.Column("AccountNumber", sa.String(length=50), nullable=False),
        sa.Column("TransferType", sa.String(length=10), nullable=False),
        sa.Column("TransferAmount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("PaymentCode", sa.String(length=100), nullable=True),
        sa.Column("ReferenceCode", sa.String(length=100), nullable=True),
        sa.Column("TransactionDate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("Payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("Status", sa.String(length=20), nullable=False),
        sa.Column("ProcessingNote", sa.Text(), nullable=True),
        sa.Column("PaymentTransactionId", sa.UUID(), nullable=True),
        sa.Column("ReceivedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ProcessedAt", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_in("Provider", ("SePay",)), name=op.f("CK_PaymentWebhookEvents_Provider_Valid")),
        sa.CheckConstraint(
            _in("Status", ("Received", "Processed", "Ignored")), name=op.f("CK_PaymentWebhookEvents_Status_Valid")
        ),
        sa.CheckConstraint(_in("TransferType", ("in", "out")), name=op.f("CK_PaymentWebhookEvents_TransferType_Valid")),
        sa.CheckConstraint('"TransferAmount" >= 0', name=op.f("CK_PaymentWebhookEvents_TransferAmount_NonNegative")),
        sa.CheckConstraint(
            "(\"Status\" = 'Received' AND \"ProcessedAt\" IS NULL) OR (\"Status\" <> 'Received' AND \"ProcessedAt\" IS NOT NULL)",
            name=op.f("CK_PaymentWebhookEvents_Processing_Consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["PaymentTransactionId"], ["PaymentTransactions.PaymentTransactionId"],
            name=op.f("FK_PaymentWebhookEvents_PaymentTransactionId"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("PaymentWebhookEventId", name=op.f("PK_PaymentWebhookEvents")),
        sa.UniqueConstraint(
            "Provider", "AccountNumber", "ProviderTransactionId", name=op.f("UQ_PaymentWebhookEvents_ProviderTxn")
        ),
    )
    op.create_index("IX_PaymentWebhookEvents_Status_ReceivedAt", EVENTS, ["Status", "ReceivedAt"], unique=False)
    op.create_index("IX_PaymentWebhookEvents_PaymentCode", EVENTS, ["PaymentCode"], unique=False)
    op.execute(f'ALTER TABLE "{EVENTS}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{EVENTS}" FROM {DATA_API_ROLES}')

    # PaymentReconciliations: UnmatchedPayment không có đơn/giao dịch/số tiền kỳ vọng.
    op.alter_column(RECONCILIATIONS, "OrderId", existing_type=sa.UUID(), nullable=True)
    op.alter_column(RECONCILIATIONS, "PaymentTransactionId", existing_type=sa.UUID(), nullable=True)
    op.alter_column(RECONCILIATIONS, "ExpectedAmount", existing_type=sa.Numeric(precision=15, scale=2), nullable=True)
    op.add_column(RECONCILIATIONS, sa.Column("PaymentWebhookEventId", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("FK_PaymentReconciliations_PaymentWebhookEventId"), RECONCILIATIONS, EVENTS,
        ["PaymentWebhookEventId"], ["PaymentWebhookEventId"], ondelete="RESTRICT",
    )
    op.drop_constraint(op.f("CK_PaymentReconciliations_IssueType_Valid"), RECONCILIATIONS, type_="check")
    op.create_check_constraint(
        op.f("CK_PaymentReconciliations_IssueType_Valid"), RECONCILIATIONS, _in("IssueType", NEW_ISSUE_TYPES)
    )
    op.create_check_constraint(
        op.f("CK_PaymentReconciliations_Matched_References_Required"),
        RECONCILIATIONS,
        "\"IssueType\" = 'UnmatchedPayment' OR (\"OrderId\" IS NOT NULL AND \"PaymentTransactionId\" IS NOT NULL "
        "AND \"ExpectedAmount\" IS NOT NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("CK_PaymentReconciliations_Matched_References_Required"), RECONCILIATIONS, type_="check")
    op.drop_constraint(op.f("CK_PaymentReconciliations_IssueType_Valid"), RECONCILIATIONS, type_="check")
    op.create_check_constraint(
        op.f("CK_PaymentReconciliations_IssueType_Valid"), RECONCILIATIONS, _in("IssueType", OLD_ISSUE_TYPES)
    )
    op.drop_constraint(op.f("FK_PaymentReconciliations_PaymentWebhookEventId"), RECONCILIATIONS, type_="foreignkey")
    op.drop_column(RECONCILIATIONS, "PaymentWebhookEventId")
    op.alter_column(RECONCILIATIONS, "ExpectedAmount", existing_type=sa.Numeric(precision=15, scale=2), nullable=False)
    op.alter_column(RECONCILIATIONS, "PaymentTransactionId", existing_type=sa.UUID(), nullable=False)
    op.alter_column(RECONCILIATIONS, "OrderId", existing_type=sa.UUID(), nullable=False)
    op.drop_index("IX_PaymentWebhookEvents_PaymentCode", table_name=EVENTS)
    op.drop_index("IX_PaymentWebhookEvents_Status_ReceivedAt", table_name=EVENTS)
    op.drop_table(EVENTS)
