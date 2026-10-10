"""warranty/returns 5.4.1: người đề xuất kết quả bảo hành, ghi chú nội bộ trong lịch sử yêu cầu

Revision ID: e6a2d9c4b8f1
Revises: f3b8d1a5c7e2
Create Date: 2026-10-11 09:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy TRƯỚC khi dùng WarrantyService/ReturnService bản 5.4.1.
Migration SePay (b81569bc34b0) đặt sau migration này.

- WarrantyRequests: ResultProposedByUserId (SET NULL), ResultProposedAt — người/thời điểm đề xuất kết quả; CHECK kết quả
  phải có thời điểm đề xuất; CHECK người duyệt khác người đề xuất (bỏ qua khi một trong hai đã bị SET NULL).
- ServiceRequestHistories: InternalNote (chỉ Staff/Admin xem), IsInternal NOT NULL DEFAULT false (cả dòng chỉ
  Staff/Admin xem); CHECK dòng nội bộ không có Note dành cho khách. Dòng cũ giữ nguyên, mặc định công khai.
Không suy diễn dữ liệu cũ: đã có yêu cầu bảo hành mang ResultType (không xác định được người đề xuất) → DỪNG nâng cấp.
Downgrade dừng nếu đã có dữ liệu đề xuất / ghi chú nội bộ (không xóa lịch sử).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6a2d9c4b8f1'
down_revision: Union[str, Sequence[str], None] = 'f3b8d1a5c7e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WARRANTY = "WarrantyRequests"
HISTORY = "ServiceRequestHistories"
PROPOSAL_SQL = '"ResultType" IS NULL OR "ResultProposedAt" IS NOT NULL'
NOT_BY_PROPOSER_SQL = (
    '"ResultApprovedByUserId" IS NULL OR "ResultProposedByUserId" IS NULL '
    'OR "ResultApprovedByUserId" <> "ResultProposedByUserId"'
)
INTERNAL_SQL = 'NOT "IsInternal" OR "Note" IS NULL'


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{WARRANTY}" WHERE "ResultType" IS NOT NULL) THEN
                RAISE EXCEPTION 'Da co yeu cau bao hanh mang ResultType nhung khong xac dinh duoc nguoi de xuat; can xu ly thu cong';
            END IF;
        END
        $$
        """
    )
    op.add_column(WARRANTY, sa.Column("ResultProposedByUserId", sa.UUID(), nullable=True))
    op.add_column(WARRANTY, sa.Column("ResultProposedAt", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f("FK_WarrantyRequests_ResultProposedByUserId"), WARRANTY, "Users",
        ["ResultProposedByUserId"], ["UserId"], ondelete="SET NULL",
    )
    op.create_check_constraint(op.f("CK_WarrantyRequests_Proposal_Recorded"), WARRANTY, PROPOSAL_SQL)
    op.create_check_constraint(op.f("CK_WarrantyRequests_Approval_NotByProposer"), WARRANTY, NOT_BY_PROPOSER_SQL)
    op.add_column(HISTORY, sa.Column("InternalNote", sa.Text(), nullable=True))
    op.add_column(HISTORY, sa.Column("IsInternal", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.create_check_constraint(op.f("CK_ServiceRequestHistories_Internal_NoPublicNote"), HISTORY, INTERNAL_SQL)


def downgrade() -> None:
    """Downgrade schema. Thất bại có chủ đích nếu đã có dữ liệu đề xuất hoặc ghi chú nội bộ."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{WARRANTY}" WHERE "ResultProposedAt" IS NOT NULL OR "ResultProposedByUserId" IS NOT NULL)
               OR EXISTS (SELECT 1 FROM "{HISTORY}" WHERE "IsInternal" OR "InternalNote" IS NOT NULL) THEN
                RAISE EXCEPTION 'Da co du lieu de xuat ket qua/ghi chu noi bo; khong ha cap';
            END IF;
        END
        $$
        """
    )
    op.drop_constraint(op.f("CK_ServiceRequestHistories_Internal_NoPublicNote"), HISTORY, type_="check")
    op.drop_column(HISTORY, "IsInternal")
    op.drop_column(HISTORY, "InternalNote")
    op.drop_constraint(op.f("CK_WarrantyRequests_Approval_NotByProposer"), WARRANTY, type_="check")
    op.drop_constraint(op.f("CK_WarrantyRequests_Proposal_Recorded"), WARRANTY, type_="check")
    op.drop_constraint(op.f("FK_WarrantyRequests_ResultProposedByUserId"), WARRANTY, type_="foreignkey")
    op.drop_column(WARRANTY, "ResultProposedAt")
    op.drop_column(WARRANTY, "ResultProposedByUserId")
