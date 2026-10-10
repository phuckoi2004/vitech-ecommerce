"""remove SuperAdmin role

Revision ID: b5d3a7c912e4
Revises: 4ee28b0095ef
Create Date: 2026-10-08 23:50:51.091720

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d3a7c912e4'
down_revision: Union[str, Sequence[str], None] = '4ee28b0095ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Dựng lại theo trạng thái database: revision này đã được apply nhưng file gốc không có trong repo.
# Database (đã đối chiếu read-only) chỉ khác 4ee28b0095ef ở CHECK của Users.Role.
CONSTRAINT_NAME = "CK_Users_Role_Valid"
NEW_ROLES = ("Customer", "Staff", "Admin")
OLD_ROLES = ("Customer", "Staff", "Admin", "SuperAdmin")


def _role_check(roles: tuple[str, ...]) -> str:
    return '"Role" IN (' + ", ".join(f"'{role}'" for role in roles) + ")"


def upgrade() -> None:
    """Upgrade schema."""
    # Không đổi dữ liệu: nếu còn user Role='SuperAdmin', lệnh tạo CHECK sẽ lỗi và transaction rollback.
    op.drop_constraint(op.f(CONSTRAINT_NAME), "Users", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT_NAME), "Users", _role_check(NEW_ROLES))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f(CONSTRAINT_NAME), "Users", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT_NAME), "Users", _role_check(OLD_ROLES))
