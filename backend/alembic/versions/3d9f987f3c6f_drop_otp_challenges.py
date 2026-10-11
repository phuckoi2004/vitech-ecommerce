"""user: bỏ bảng OtpChallenges (thiết kế OTP cũ của giai đoạn 4, Auth giai đoạn 5 không dùng)

Revision ID: 3d9f987f3c6f
Revises: c6a4e2b8d901
Create Date: 2026-10-11 20:00:00.000000

Quyết định 11/10/2026: giữ cơ chế OTP của Auth giai đoạn 5 (kho trạng thái + Users.OtpCode/OtpExpiredAt).
OtpChallenges cần UserId nên không phục vụ được luồng "chỉ tạo tài khoản sau khi xác minh OTP"; không còn code
đọc/ghi bảng. Bảng chỉ chứa bản băm OTP tạm thời có hạn vài phút, nên xóa không mất dữ liệu nghiệp vụ.

Downgrade tạo lại bảng rỗng đúng cấu trúc của a7c3e9d1f285 (kèm RLS/REVOKE), không đụng tới Users.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d9f987f3c6f'
down_revision: Union[str, Sequence[str], None] = 'c6a4e2b8d901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "OtpChallenges"
INDEX = "IX_OtpChallenges_UserId_Purpose_CreatedAt"
DATA_API_ROLES = "anon, authenticated"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        TABLE,
        sa.Column("OtpChallengeId", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("UserId", sa.UUID(), nullable=False),
        sa.Column("Purpose", sa.String(length=20), nullable=False),
        sa.Column("CodeHash", sa.String(length=255), nullable=False),
        sa.Column("ExpiresAt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("FailedAttempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("LockedUntil", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ConsumedAt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("CreatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("\"Purpose\" IN ('Registration', 'PasswordReset')", name=op.f("CK_OtpChallenges_Purpose_Valid")),
        sa.CheckConstraint('"FailedAttempts" >= 0', name=op.f("CK_OtpChallenges_FailedAttempts_NonNegative")),
        sa.ForeignKeyConstraint(["UserId"], ["Users.UserId"], name=op.f("FK_OtpChallenges_UserId"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("OtpChallengeId", name=op.f("PK_OtpChallenges")),
    )
    op.create_index(INDEX, TABLE, ["UserId", "Purpose", "CreatedAt"], unique=False)
    # Security hardening cho Supabase Data API (giống các bảng khác).
    op.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{TABLE}" FROM {DATA_API_ROLES}')
