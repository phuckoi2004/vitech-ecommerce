"""Join catalog soft-delete/purchase deletion and category image/news view branches.

This revision only joins migration history. It contains no schema or data changes.
"""

revision = "b2f8c6d4e901"
down_revision = ("a6d2e8f4b190", "71a4d9c8e620")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
