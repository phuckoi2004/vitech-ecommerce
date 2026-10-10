"""add AccountStatus check

Revision ID: dd773e03e503
Revises: b5d3a7c912e4
Create Date: 2026-10-09 00:18:27.631483

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd773e03e503'
down_revision: Union[str, Sequence[str], None] = 'b5d3a7c912e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = "CK_Users_AccountStatus_Valid"
ACCOUNT_STATUSES = ("Active", "Locked")


def upgrade() -> None:
    """Upgrade schema."""
    # Không đổi dữ liệu: nếu có AccountStatus ngoài Active/Locked, lệnh lỗi và transaction rollback.
    allowed = ", ".join(f"'{status}'" for status in ACCOUNT_STATUSES)
    op.create_check_constraint(op.f(CONSTRAINT_NAME), "Users", f'"AccountStatus" IN ({allowed})')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f(CONSTRAINT_NAME), "Users", type_="check")
