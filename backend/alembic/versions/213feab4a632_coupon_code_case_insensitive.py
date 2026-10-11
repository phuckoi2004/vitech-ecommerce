"""Make coupon codes unique regardless of letter case.

Revision ID: 213feab4a632
Revises: b5d3a7c912e4

This revision was applied to the database before its file was added to the
repository; it is reconstructed from the live schema so the chain resolves again.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "213feab4a632"
down_revision: Union[str, Sequence[str], None] = "b5d3a7c912e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # "SALE10" and "sale10" are the same coupon, like Users.Email.
    op.drop_constraint(op.f("UQ_Coupons_Code"), "Coupons", schema="public", type_="unique")
    op.create_index(
        "UX_Coupons_Code_Lower", "Coupons", [sa.literal_column('lower("Code")')],
        unique=True, schema="public",
    )


def downgrade() -> None:
    op.drop_index("UX_Coupons_Code_Lower", table_name="Coupons", schema="public")
    op.create_unique_constraint(op.f("UQ_Coupons_Code"), "Coupons", ["Code"], schema="public")
