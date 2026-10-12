"""payment: liên kết giao dịch Refund với khoản Payment gốc (RefundOfPaymentTransactionId)

Revision ID: 4c2d9e7a1f53
Revises: d3326a8fbc5c
Create Date: 2026-10-09 23:30:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy TRƯỚC khi triển khai PaymentService có RefundOfPaymentTransactionId
(ORM sẽ lỗi khi truy vấn cột chưa tồn tại). Chạy sau 763f153af842, d3326a8fbc5c; migration SePay (b81569bc34b0)
được đặt sau migration này.

- Mỗi giao dịch Refund trỏ tới đúng một giao dịch Payment gốc (FK tự tham chiếu, RESTRICT); Payment không có nguồn.
- Trigger: nguồn phải là Payment cùng đơn; liên kết không đổi sau khi tạo; Payment đã có Refund không đổi
  loại/đơn (giữ lịch sử hoàn tiền).
- Không suy đoán dữ liệu cũ: nếu đã có giao dịch Refund (chưa có liên kết) thì DỪNG nâng cấp, cần gán
  RefundOfPaymentTransactionId thủ công rồi chạy lại.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c2d9e7a1f53'
down_revision: Union[str, Sequence[str], None] = 'd3326a8fbc5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "PaymentTransactions"
COLUMN = "RefundOfPaymentTransactionId"
DATA_API_ROLES = "anon, authenticated"
SOURCE_FUNCTION = "public.check_payment_refund_source()"
SOURCE_TRIGGER = "TR_PaymentTransactions_RefundSource"
REFUND_SOURCE_CONSISTENT_SQL = (
    "(\"TransactionType\" = 'Refund' AND \"RefundOfPaymentTransactionId\" IS NOT NULL) OR "
    "(\"TransactionType\" <> 'Refund' AND \"RefundOfPaymentTransactionId\" IS NULL)"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{TABLE}" WHERE "TransactionType" = 'Refund') THEN
                RAISE EXCEPTION 'PaymentTransactions co giao dich Refund chua lien ket khoan Payment goc; '
                    'gan {COLUMN} thu cong truoc khi nang cap';
            END IF;
        END
        $$
        """
    )
    op.add_column(TABLE, sa.Column(COLUMN, sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("FK_PaymentTransactions_RefundOfPaymentTransactionId"), TABLE, TABLE,
        [COLUMN], ["PaymentTransactionId"], ondelete="RESTRICT",
    )
    op.create_index("IX_PaymentTransactions_RefundOfPaymentTransactionId", TABLE, [COLUMN], unique=False)
    op.create_check_constraint(
        op.f("CK_PaymentTransactions_RefundSource_Consistent"), TABLE, REFUND_SOURCE_CONSISTENT_SQL
    )

    # Viết thủ công: ràng buộc liên dòng mà CHECK không diễn đạt được.
    op.execute(
        f"""
        CREATE FUNCTION {SOURCE_FUNCTION}
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = ''
        AS $$
        DECLARE
            source_type varchar;
            source_order uuid;
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF OLD."{COLUMN}" IS DISTINCT FROM NEW."{COLUMN}" THEN
                    RAISE EXCEPTION 'Khong duoc doi khoan Payment goc cua giao dich Refund';
                END IF;
                IF (OLD."TransactionType" IS DISTINCT FROM NEW."TransactionType"
                        OR OLD."OrderId" IS DISTINCT FROM NEW."OrderId")
                    AND EXISTS (SELECT 1 FROM public."{TABLE}" r WHERE r."{COLUMN}" = OLD."PaymentTransactionId") THEN
                    RAISE EXCEPTION 'Payment da co giao dich Refund: khong duoc doi loai giao dich hoac don hang';
                END IF;
            END IF;
            IF NEW."{COLUMN}" IS NOT NULL THEN
                SELECT p."TransactionType", p."OrderId" INTO source_type, source_order
                FROM public."{TABLE}" p
                WHERE p."PaymentTransactionId" = NEW."{COLUMN}";
                IF source_type IS DISTINCT FROM 'Payment' OR source_order IS DISTINCT FROM NEW."OrderId" THEN
                    RAISE EXCEPTION 'Nguon hoan tien phai la giao dich Payment cua cung don hang';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(f"REVOKE EXECUTE ON FUNCTION {SOURCE_FUNCTION} FROM PUBLIC")
    op.execute(f"REVOKE EXECUTE ON FUNCTION {SOURCE_FUNCTION} FROM {DATA_API_ROLES}")
    op.execute(
        f'CREATE TRIGGER "{SOURCE_TRIGGER}" BEFORE INSERT OR UPDATE ON "{TABLE}" '
        f"FOR EACH ROW EXECUTE FUNCTION {SOURCE_FUNCTION}"
    )


def downgrade() -> None:
    """Downgrade schema. Thất bại có chủ đích nếu đã có Refund (không xóa liên kết hoàn tiền đã ghi)."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{TABLE}" WHERE "{COLUMN}" IS NOT NULL) THEN
                RAISE EXCEPTION 'Da co giao dich Refund lien ket khoan Payment goc; khong ha cap de tranh mat lich su';
            END IF;
        END
        $$
        """
    )
    op.execute(f'DROP TRIGGER "{SOURCE_TRIGGER}" ON "{TABLE}"')
    op.execute(f"DROP FUNCTION {SOURCE_FUNCTION}")
    op.drop_constraint(op.f("CK_PaymentTransactions_RefundSource_Consistent"), TABLE, type_="check")
    op.drop_index("IX_PaymentTransactions_RefundOfPaymentTransactionId", table_name=TABLE)
    op.drop_constraint(op.f("FK_PaymentTransactions_RefundOfPaymentTransactionId"), TABLE, type_="foreignkey")
    op.drop_column(TABLE, COLUMN)
