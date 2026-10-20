"""secure alembic_version

Revision ID: 4ee28b0095ef
Revises: 2cb2e7418b06
Create Date: 2026-10-07 23:32:58.662391

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ee28b0095ef'
down_revision: Union[str, Sequence[str], None] = '2cb2e7418b06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Alembic tạo alembic_version trước khi chạy upgrade() của initial migration,
# nên bảng này nhận default privileges cũ (anon/authenticated = arwdDxtm) và RLS tắt.
VERSION_TABLE = "public.alembic_version"
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
    op.execute(f"ALTER TABLE {VERSION_TABLE} ENABLE ROW LEVEL SECURITY")
    revoke_from_data_api_roles(f"REVOKE ALL PRIVILEGES ON TABLE {VERSION_TABLE}")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"ALTER TABLE {VERSION_TABLE} DISABLE ROW LEVEL SECURITY")
    # Không khôi phục quyền cũ của anon/authenticated (arwdDxtm):
    # làm vậy sẽ mở lại quyền ghi alembic_version qua Supabase Data API.
