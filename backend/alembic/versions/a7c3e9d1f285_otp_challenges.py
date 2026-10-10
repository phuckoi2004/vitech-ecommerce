"""user: OtpChallenges — OTP băm, tách theo mục đích, giới hạn gửi/nhập sai

Revision ID: a7c3e9d1f285
Revises: e2b8c4f6a913
Create Date: 2026-10-10 16:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy TRƯỚC khi triển khai UserService đợt 5.1.
Migration SePay (b81569bc34b0) đặt sau migration này.

- OtpChallenges: mỗi lần gửi OTP (UserId, Purpose Registration/PasswordReset, CodeHash, ExpiresAt, FailedAttempts,
  LockedUntil, ConsumedAt, CreatedAt). Không lưu OTP dạng văn bản thuần.
- Xóa OTP văn bản thuần còn lưu ở Users.OtpCode/OtpExpiredAt (cột giữ nguyên theo thiết kế, không còn được dùng).
  Người dùng đang chờ xác minh cần yêu cầu gửi lại OTP (OTP cũ chỉ có hạn 5 phút).
Downgrade: xóa bảng OtpChallenges (dữ liệu OTP tạm thời; OTP đang chờ phải gửi lại).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e9d1f285'
down_revision: Union[str, Sequence[str], None] = 'e2b8c4f6a913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "OtpChallenges"
DATA_API_ROLES = "anon, authenticated"


def upgrade() -> None:
    """Upgrade schema."""
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
    op.create_index(
        "IX_OtpChallenges_UserId_Purpose_CreatedAt", TABLE, ["UserId", "Purpose", "CreatedAt"], unique=False
    )
    # Viết thủ công: security hardening cho Supabase Data API (giống các bảng khác).
    op.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{TABLE}" FROM {DATA_API_ROLES}')
    # Không giữ OTP văn bản thuần (cơ chế cũ).
    op.execute('UPDATE "Users" SET "OtpCode" = NULL, "OtpExpiredAt" = NULL WHERE "OtpCode" IS NOT NULL OR "OtpExpiredAt" IS NOT NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("IX_OtpChallenges_UserId_Purpose_CreatedAt", table_name=TABLE)
    op.drop_table(TABLE)
