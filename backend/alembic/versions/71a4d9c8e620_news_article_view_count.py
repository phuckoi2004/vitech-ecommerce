"""Persist public article view totals without changing news publishing permissions."""
from alembic import op
import sqlalchemy as sa

revision = "71a4d9c8e620"
down_revision = "6f8a2c4d9b10"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("NewsArticles", sa.Column("ViewCount", sa.BigInteger(), nullable=False, server_default=sa.text("0")))
    op.create_check_constraint(op.f("CK_NewsArticles_ViewCount_NonNegative"), "NewsArticles", '"ViewCount" >= 0')


def downgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_constraint(op.f("CK_NewsArticles_ViewCount_NonNegative"), "NewsArticles", type_="check")
    op.drop_column("NewsArticles", "ViewCount")
