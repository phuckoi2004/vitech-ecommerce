"""Keep the published list price independently from the SKU selling price.

Revision ID: 93e7a2b0c518
Revises: 82d6f1a9b407
"""
from alembic import op
import sqlalchemy as sa

revision = "93e7a2b0c518"
down_revision = "82d6f1a9b407"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ProductVariants", sa.Column("CompareAtPrice", sa.Numeric(15, 2), nullable=True))
    op.create_check_constraint("CompareAtPrice_Valid", "ProductVariants",
                               '"CompareAtPrice" IS NULL OR "CompareAtPrice" >= "Price"')


def downgrade():
    op.drop_constraint("CompareAtPrice_Valid", "ProductVariants", type_="check")
    op.drop_column("ProductVariants", "CompareAtPrice")
