"""inventory: StockAdjustments (Opening/điều chỉnh kho) và ProductVariants.IsSerialTracked

Revision ID: 763f153af842
Revises: 213feab4a632
Create Date: 2026-10-09 18:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy migration này TRƯỚC khi triển khai code có model StockAdjustment
và cột ProductVariants.IsSerialTracked (ORM sẽ lỗi khi truy vấn cột chưa tồn tại).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '763f153af842'
down_revision: Union[str, Sequence[str], None] = '213feab4a632'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "StockAdjustments"
DATA_API_ROLES = ("anon", "authenticated")
APPEND_ONLY_FUNCTION = "public.prevent_stock_adjustment_change()"
APPEND_ONLY_TRIGGER = "TR_StockAdjustments_AppendOnly"


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
    # Biến thể hiện có mặc định không quản lý serial (giữ nguyên hành vi bán hàng hiện tại).
    op.add_column(
        "ProductVariants",
        sa.Column("IsSerialTracked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    op.create_table(
        TABLE,
        sa.Column("StockAdjustmentId", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("ProductVariantId", sa.UUID(), nullable=False),
        sa.Column("AdjustedByUserId", sa.UUID(), nullable=False),
        sa.Column("AdjustmentType", sa.String(length=20), nullable=False),
        sa.Column("QuantityBefore", sa.Integer(), nullable=False),
        sa.Column("QuantityChange", sa.Integer(), nullable=False),
        sa.Column("QuantityAfter", sa.Integer(), nullable=False),
        sa.Column("CostPriceBefore", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("CostPriceAfter", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("Reason", sa.Text(), nullable=False),
        sa.Column("CreatedAt", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "\"AdjustmentType\" IN ('Opening', 'Increase', 'Decrease')", name=op.f("CK_StockAdjustments_AdjustmentType_Valid")
        ),
        sa.CheckConstraint('"QuantityBefore" >= 0', name=op.f("CK_StockAdjustments_QuantityBefore_NonNegative")),
        sa.CheckConstraint('"QuantityAfter" >= 0', name=op.f("CK_StockAdjustments_QuantityAfter_NonNegative")),
        sa.CheckConstraint(
            '"QuantityChange" = "QuantityAfter" - "QuantityBefore"', name=op.f("CK_StockAdjustments_QuantityChange_Consistent")
        ),
        sa.CheckConstraint(
            "\"AdjustmentType\" <> 'Increase' OR \"QuantityChange\" > 0", name=op.f("CK_StockAdjustments_Increase_Positive")
        ),
        sa.CheckConstraint(
            "\"AdjustmentType\" <> 'Decrease' OR \"QuantityChange\" < 0", name=op.f("CK_StockAdjustments_Decrease_Negative")
        ),
        sa.CheckConstraint('"CostPriceBefore" >= 0', name=op.f("CK_StockAdjustments_CostPriceBefore_NonNegative")),
        sa.CheckConstraint('"CostPriceAfter" >= 0', name=op.f("CK_StockAdjustments_CostPriceAfter_NonNegative")),
        sa.CheckConstraint(
            "\"AdjustmentType\" = 'Opening' OR \"CostPriceAfter\" = \"CostPriceBefore\"",
            name=op.f("CK_StockAdjustments_CostPrice_OnlyOpening"),
        ),
        sa.CheckConstraint('length(btrim("Reason")) > 0', name=op.f("CK_StockAdjustments_Reason_NotBlank")),
        sa.ForeignKeyConstraint(
            ["ProductVariantId"], ["ProductVariants.ProductVariantId"],
            name=op.f("FK_StockAdjustments_ProductVariantId"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["AdjustedByUserId"], ["Users.UserId"], name=op.f("FK_StockAdjustments_AdjustedByUserId"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("StockAdjustmentId", name=op.f("PK_StockAdjustments")),
    )
    op.create_index(
        "IX_StockAdjustments_ProductVariantId_CreatedAt", TABLE, ["ProductVariantId", "CreatedAt"], unique=False
    )
    # Mỗi biến thể chỉ có một lần khai báo tồn đầu kỳ.
    op.create_index(
        "UX_StockAdjustments_Opening_ProductVariantId",
        TABLE,
        ["ProductVariantId"],
        unique=True,
        postgresql_where=sa.text("\"AdjustmentType\" = 'Opening'"),
    )

    # Viết thủ công: lịch sử chỉ được ghi thêm, không sửa/xóa.
    op.execute(
        f"""
        CREATE FUNCTION {APPEND_ONLY_FUNCTION}
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = ''
        AS $$
        BEGIN
            RAISE EXCEPTION 'StockAdjustments chỉ được ghi thêm, không được sửa hoặc xóa';
        END;
        $$
        """
    )
    op.execute(f"REVOKE EXECUTE ON FUNCTION {APPEND_ONLY_FUNCTION} FROM PUBLIC")
    revoke_from_data_api_roles(f"REVOKE EXECUTE ON FUNCTION {APPEND_ONLY_FUNCTION}")
    op.execute(
        f'CREATE TRIGGER "{APPEND_ONLY_TRIGGER}" BEFORE UPDATE OR DELETE ON "{TABLE}" '
        f"FOR EACH ROW EXECUTE FUNCTION {APPEND_ONLY_FUNCTION}"
    )

    # Viết thủ công: security hardening cho Supabase Data API (giống các bảng khác).
    op.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY')
    revoke_from_data_api_roles(f'REVOKE ALL PRIVILEGES ON TABLE "{TABLE}"')


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f'DROP TRIGGER "{APPEND_ONLY_TRIGGER}" ON "{TABLE}"')
    op.execute(f"DROP FUNCTION {APPEND_ONLY_FUNCTION}")
    op.drop_index("UX_StockAdjustments_Opening_ProductVariantId", table_name=TABLE)
    op.drop_index("IX_StockAdjustments_ProductVariantId_CreatedAt", table_name=TABLE)
    op.drop_table(TABLE)
    op.drop_column("ProductVariants", "IsSerialTracked")
