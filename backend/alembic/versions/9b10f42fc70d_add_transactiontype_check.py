"""add TransactionType check

Revision ID: 9b10f42fc70d
Revises: dd773e03e503
Create Date: 2026-10-09 14:13:07.438045

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b10f42fc70d'
down_revision: Union[str, Sequence[str], None] = 'dd773e03e503'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = "CK_PaymentTransactions_TransactionType_Valid"
TRANSACTION_TYPES = ("Payment", "Refund")


def upgrade() -> None:
    """Upgrade schema."""
    # Không đổi dữ liệu: nếu có TransactionType ngoài Payment/Refund, lệnh lỗi và transaction rollback.
    allowed = ", ".join(f"'{value}'" for value in TRANSACTION_TYPES)
    op.create_check_constraint(op.f(CONSTRAINT_NAME), "PaymentTransactions", f'"TransactionType" IN ({allowed})')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f(CONSTRAINT_NAME), "PaymentTransactions", type_="check")
