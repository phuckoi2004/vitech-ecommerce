"""Restrict user roles to Customer, Staff and Admin.

Revision ID: b5d3a7c912e4
Revises: 4ee28b0095ef
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b5d3a7c912e4"
down_revision: Union[str, Sequence[str], None] = "4ee28b0095ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep conversion and constraint replacement atomic, including concurrent writes.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute('LOCK TABLE public."Users" IN ACCESS EXCLUSIVE MODE')
    # Preserve identities, password hashes and every existing user reference.
    op.execute('UPDATE public."Users" SET "Role" = \'Admin\' WHERE "Role" = \'SuperAdmin\'')
    op.drop_constraint(op.f("CK_Users_Role_Valid"), "Users", schema="public", type_="check")
    op.create_check_constraint(
        op.f("CK_Users_Role_Valid"), "Users",
        '"Role" IN (\'Customer\', \'Staff\', \'Admin\')', schema="public",
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_constraint(op.f("CK_Users_Role_Valid"), "Users", schema="public", type_="check")
    op.create_check_constraint(
        op.f("CK_Users_Role_Valid"), "Users",
        '"Role" IN (\'Customer\', \'Staff\', \'Admin\', \'SuperAdmin\')', schema="public",
    )
    # Converted Admin accounts keep their role; their original role is not recoverable.
