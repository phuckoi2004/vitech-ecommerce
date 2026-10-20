"""Join promotional pricing and catalog/purchasing migration histories.

Both published branches keep their existing revision identifiers and ancestry.
This merge revision does not change schema or data.
"""

revision = "c3a9f5e7d206"
down_revision = ("93e7a2b0c518", "b2f8c6d4e901")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
