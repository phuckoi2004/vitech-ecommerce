"""AI request/reply idempotency and one pending turn per conversation.

Revision ID: d7a1e5c9b304
Revises: c3a9f5e7d206
"""

from alembic import op
import sqlalchemy as sa

revision = "d7a1e5c9b304"
down_revision = "c3a9f5e7d206"
branch_labels = None
depends_on = None


def upgrade():
    # Existing duplicates stop CREATE UNIQUE INDEX; never delete/rewrite chat history.
    op.create_index("UX_Messages_AiRequest", "Messages", ["ConversationId", sa.text('(\"Metadata\" ->> \'ClientRequestId\')')],
                    unique=True, postgresql_where=sa.text(
                        '\"SenderType\" = \'Customer\' AND \"Metadata\" ->> \'ClientRequestId\' IS NOT NULL'))
    op.create_index("UX_Messages_AiReply", "Messages", ["ConversationId", sa.text('(\"Metadata\" ->> \'ReplyToMessageId\')')],
                    unique=True, postgresql_where=sa.text(
                        '\"SenderType\" = \'AI\' AND \"Metadata\" ->> \'ReplyToMessageId\' IS NOT NULL'))
    op.create_index("UX_Messages_AiPending", "Messages", ["ConversationId"], unique=True,
                    postgresql_where=sa.text(
                        '\"SenderType\" = \'Customer\' AND \"Metadata\" ->> \'AiProcessingStatus\' = \'Pending\''))


def downgrade():
    for name in ("UX_Messages_AiPending", "UX_Messages_AiReply", "UX_Messages_AiRequest"):
        op.drop_index(name, table_name="Messages")
