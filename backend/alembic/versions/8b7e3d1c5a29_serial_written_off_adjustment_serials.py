"""inventory: trạng thái serial WrittenOff và StockAdjustmentSerials (serial thuộc phiếu điều chỉnh In/Out)

Revision ID: 8b7e3d1c5a29
Revises: 4c2d9e7a1f53
Create Date: 2026-10-10 09:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy TRƯỚC khi triển khai InventoryService/ProductSerialService đợt 5.1
(ORM sẽ lỗi khi truy vấn bảng chưa tồn tại). Migration SePay (b81569bc34b0) đặt sau migration này.

- ProductSerials.Status thêm WrittenOff: serial đã loại khỏi tồn kho qua phiếu điều chỉnh giảm.
- StockAdjustmentSerials: serial nhập bởi Opening/Increase (In) hoặc loại khỏi kho bởi Decrease (Out).
  UNIQUE (ProductSerialId, Direction): một serial không bị nhập hai lần hoặc loại khỏi kho hai lần.
  Trigger: hướng khớp loại phiếu, serial cùng biến thể với phiếu; chỉ ghi thêm (chặn UPDATE/DELETE).
Downgrade dừng nếu đã có serial WrittenOff hoặc liên kết serial (không xóa lịch sử kho).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b7e3d1c5a29'
down_revision: Union[str, Sequence[str], None] = '4c2d9e7a1f53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "StockAdjustmentSerials"
SERIALS = "ProductSerials"
DATA_API_ROLES = "anon, authenticated"
GUARD_FUNCTION = "public.guard_stock_adjustment_serial()"
GUARD_TRIGGER = "TR_StockAdjustmentSerials_Guard"
OLD_SERIAL_STATUSES = ("Available", "Reserved", "Sold", "Warranty", "Returned")
NEW_SERIAL_STATUSES = OLD_SERIAL_STATUSES + ("WrittenOff",)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f'"{column}" IN (' + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f("CK_ProductSerials_Status_Valid"), SERIALS, type_="check")
    op.create_check_constraint(op.f("CK_ProductSerials_Status_Valid"), SERIALS, _in("Status", NEW_SERIAL_STATUSES))

    op.create_table(
        TABLE,
        sa.Column("StockAdjustmentId", sa.UUID(), nullable=False),
        sa.Column("ProductSerialId", sa.UUID(), nullable=False),
        sa.Column("Direction", sa.String(length=10), nullable=False),
        sa.CheckConstraint(_in("Direction", ("In", "Out")), name=op.f("CK_StockAdjustmentSerials_Direction_Valid")),
        sa.ForeignKeyConstraint(
            ["StockAdjustmentId"], ["StockAdjustments.StockAdjustmentId"],
            name=op.f("FK_StockAdjustmentSerials_StockAdjustmentId"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ProductSerialId"], ["ProductSerials.ProductSerialId"],
            name=op.f("FK_StockAdjustmentSerials_ProductSerialId"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("StockAdjustmentId", "ProductSerialId", name=op.f("PK_StockAdjustmentSerials")),
        sa.UniqueConstraint(
            "ProductSerialId", "Direction", name=op.f("UQ_StockAdjustmentSerials_ProductSerialId_Direction")
        ),
    )

    # Viết thủ công: ràng buộc liên bảng + chỉ ghi thêm.
    op.execute(
        f"""
        CREATE FUNCTION {GUARD_FUNCTION}
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = ''
        AS $$
        DECLARE
            adjustment_type varchar;
            adjustment_variant uuid;
            serial_variant uuid;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'StockAdjustmentSerials chi duoc ghi them, khong duoc sua hoac xoa';
            END IF;
            SELECT a."AdjustmentType", a."ProductVariantId" INTO adjustment_type, adjustment_variant
            FROM public."StockAdjustments" a WHERE a."StockAdjustmentId" = NEW."StockAdjustmentId";
            SELECT s."ProductVariantId" INTO serial_variant
            FROM public."{SERIALS}" s WHERE s."ProductSerialId" = NEW."ProductSerialId";
            IF serial_variant IS DISTINCT FROM adjustment_variant THEN
                RAISE EXCEPTION 'Serial khong cung bien the voi phieu dieu chinh';
            END IF;
            IF (adjustment_type IN ('Opening', 'Increase') AND NEW."Direction" <> 'In')
                OR (adjustment_type = 'Decrease' AND NEW."Direction" <> 'Out') THEN
                RAISE EXCEPTION 'Huong serial khong khop loai phieu dieu chinh';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(f"REVOKE EXECUTE ON FUNCTION {GUARD_FUNCTION} FROM PUBLIC")
    op.execute(f"REVOKE EXECUTE ON FUNCTION {GUARD_FUNCTION} FROM {DATA_API_ROLES}")
    op.execute(
        f'CREATE TRIGGER "{GUARD_TRIGGER}" BEFORE INSERT OR UPDATE OR DELETE ON "{TABLE}" '
        f"FOR EACH ROW EXECUTE FUNCTION {GUARD_FUNCTION}"
    )

    # Viết thủ công: security hardening cho Supabase Data API (giống các bảng khác).
    op.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'REVOKE ALL PRIVILEGES ON TABLE "{TABLE}" FROM {DATA_API_ROLES}')


def downgrade() -> None:
    """Downgrade schema. Thất bại có chủ đích nếu đã có lịch sử serial/WrittenOff (không xóa lịch sử kho)."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{TABLE}") OR EXISTS (SELECT 1 FROM "{SERIALS}" WHERE "Status" = 'WrittenOff') THEN
                RAISE EXCEPTION 'Da co lich su serial dieu chinh kho hoac serial WrittenOff; khong ha cap';
            END IF;
        END
        $$
        """
    )
    op.execute(f'DROP TRIGGER "{GUARD_TRIGGER}" ON "{TABLE}"')
    op.execute(f"DROP FUNCTION {GUARD_FUNCTION}")
    op.drop_table(TABLE)
    op.drop_constraint(op.f("CK_ProductSerials_Status_Valid"), SERIALS, type_="check")
    op.create_check_constraint(op.f("CK_ProductSerials_Status_Valid"), SERIALS, _in("Status", OLD_SERIAL_STATUSES))
