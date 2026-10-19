"""Add an optional category image without changing existing category data."""

from alembic import op
import sqlalchemy as sa

revision = "6f8a2c4d9b10"
down_revision = "7e4c9b2d1a60"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("Categories", sa.Column("ImageUrl", sa.String(length=500), nullable=True))


def downgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_column("Categories", "ImageUrl")
