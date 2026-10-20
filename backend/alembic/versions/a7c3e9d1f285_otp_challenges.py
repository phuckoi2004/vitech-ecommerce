"""user: OtpChallenges — OTP băm, tách theo mục đích, giới hạn gửi/nhập sai

Revision ID: a7c3e9d1f285
Revises: e2b8c4f6a913
Create Date: 2026-10-10 16:00:00.000000

CHƯA ÁP DỤNG vào database. Bảng này phục vụ account service cũ của Stage 4;
Auth Giai đoạn 5 không dùng OtpChallenges: đăng ký dùng kho trạng thái, còn OTP
reset mật khẩu/đổi email tiếp tục lưu HMAC và hạn trong Users.OtpCode/OtpExpiredAt.
Migration SePay (b81569bc34b0) đặt sau migration này.

- OtpChallenges: mỗi lần gửi OTP (UserId, Purpose Registration/PasswordReset, CodeHash, ExpiresAt, FailedAttempts,
  LockedUntil, ConsumedAt, CreatedAt). Không lưu OTP dạng văn bản thuần.
- Xóa mọi giá trị đang có ở Users.OtpCode/OtpExpiredAt một lần khi upgrade, gồm cả HMAC
  của Auth Giai đoạn 5. Các cột được giữ nguyên để tiếp tục dùng. OTP reset mật khẩu/đổi
  email đang chờ lúc áp dụng migration mất hiệu lực và phải yêu cầu gửi lại.
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
DATA_API_ROLES = ("anon", "authenticated")


def revoke_from_data_api_roles(statement: str) -> None:
    """Chạy `{statement} FROM anon, authenticated` với các role trong DATA_API_ROLES đang tồn tại.

    Supabase luôn có cả hai role nên câu lệnh thực thi y như trước (bảo mật Data API không đổi). PostgreSQL thường
    (database local) không có các role này: không có quyền nào để thu hồi, nên bỏ qua thay vì lỗi; không tạo role.
    `statement` là SQL cố định trong file này (không có dấu nháy đơn).
    """
    names = ", ".join(f"'{role}'" for role in DATA_API_ROLES)
    op.execute(
        f"""
        DO $$
        DECLARE
            grantees text;
        BEGIN
            SELECT string_agg(quote_ident(rolname), ', ' ORDER BY rolname) INTO grantees
            FROM pg_catalog.pg_roles WHERE rolname IN ({names});
            IF grantees IS NOT NULL THEN
                EXECUTE '{statement} FROM ' || grantees;
            END IF;
        END
        $$
        """
    )


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
    revoke_from_data_api_roles(f'REVOKE ALL PRIVILEGES ON TABLE "{TABLE}"')
    # Dọn giá trị đang có một lần, gồm OTP legacy và HMAC Phase 5 đang chờ.
    # Cột vẫn dùng cho OTP reset/đổi email; người dùng cần gửi lại sau migration.
    op.execute('UPDATE "Users" SET "OtpCode" = NULL, "OtpExpiredAt" = NULL WHERE "OtpCode" IS NOT NULL OR "OtpExpiredAt" IS NOT NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("IX_OtpChallenges_UserId_Purpose_CreatedAt", table_name=TABLE)
    op.drop_table(TABLE)
