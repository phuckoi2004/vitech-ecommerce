"""Distinguish automatic product discounts from coupon promotions.

Revision ID: 82d6f1a9b407
Revises: 71a4d9c8e620
"""
from alembic import op
import sqlalchemy as sa

revision = "82d6f1a9b407"
down_revision = "71a4d9c8e620"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("Promotions", sa.Column("ApplyMode", sa.String(20), nullable=False, server_default="Coupon"))
    op.create_check_constraint("ApplyMode_Valid", "Promotions", '"ApplyMode" IN (\'Coupon\', \'Automatic\')')


def downgrade():
    op.drop_constraint("ApplyMode_Valid", "Promotions", type_="check")
    op.drop_column("Promotions", "ApplyMode")
