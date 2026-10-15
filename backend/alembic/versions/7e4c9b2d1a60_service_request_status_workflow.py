"""Status-only returns and direct warranty result publication (15/10/2026).

No tables/columns/data are added or deleted. Existing financial evidence is retained.
Refund workflows remain paused in code. Downgrade refuses incompatible new records.
"""
from alembic import op
import sqlalchemy as sa

revision = '7e4c9b2d1a60'
down_revision = '3d9f987f3c6f'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(op.f('CK_ReturnRequests_Completed_RequiresApproval'), 'ReturnRequests', type_='check')
    op.create_check_constraint(op.f('CK_ReturnRequests_Completed_RequiresTimestamp'), 'ReturnRequests',
        "\"Status\" <> 'Completed' OR \"CompletedAt\" IS NOT NULL")
    op.drop_constraint(op.f('CK_WarrantyRequests_Approval_NotByProposer'), 'WarrantyRequests', type_='check')


def downgrade():
    connection = op.get_bind()
    incompatible = connection.scalar(sa.text('''SELECT
      (SELECT count(*) FROM "ReturnRequests" WHERE "Status" = 'Completed' AND "CompensationApprovedAt" IS NULL)
      + (SELECT count(*) FROM "WarrantyRequests" WHERE "ResultApprovedByUserId" = "ResultProposedByUserId")'''))
    if incompatible:
        raise RuntimeError('Cannot restore old rules: status-only completions or self-confirmed warranty results exist')
    op.create_check_constraint(op.f('CK_WarrantyRequests_Approval_NotByProposer'), 'WarrantyRequests',
        '"ResultApprovedByUserId" IS NULL OR "ResultProposedByUserId" IS NULL OR "ResultApprovedByUserId" <> "ResultProposedByUserId"')
    op.drop_constraint(op.f('CK_ReturnRequests_Completed_RequiresTimestamp'), 'ReturnRequests', type_='check')
    op.create_check_constraint(op.f('CK_ReturnRequests_Completed_RequiresApproval'), 'ReturnRequests',
        "\"Status\" <> 'Completed' OR (\"CompletedAt\" IS NOT NULL AND \"CompensationApprovedAt\" IS NOT NULL)")
