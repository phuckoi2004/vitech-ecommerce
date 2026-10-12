"""payment 5.11: người tạo giao dịch Refund, kết quả xác nhận (Gateway/Manual) và bằng chứng xác nhận thủ công

Revision ID: a9f4c2e7b513
Revises: e6a2d9c4b8f1
Create Date: 2026-10-11 15:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy TRƯỚC khi dùng PaymentService/ReturnService bản 5.11 (ORM đọc các cột mới).
Migration SePay (b81569bc34b0) đặt sau migration này.

PaymentTransactions (phương án D2):
- CreatedByUserId, ResolvedByUserId (FK → Users, RESTRICT: giữ dấu vết người tạo/xác nhận hoàn tiền), ResolvedAt,
  ResolutionSource (Gateway | Manual), EvidenceReference varchar(255), ResolutionNote text. Tất cả NULL được.
- CHECK: ResolutionSource hợp lệ; chưa có kết quả thì mọi trường xác nhận NULL, có kết quả thì chỉ với Refund
  Success/Failed và có ResolvedAt; kết quả từ cổng không có người xác nhận/bằng chứng thủ công; xác nhận thủ công bắt
  buộc người xác nhận, mã bằng chứng và ghi chú không rỗng; người xác nhận khác người tạo (bỏ qua khi chưa có người tạo).
Dữ liệu cũ: không suy diễn người tạo/người xác nhận — các cột mới để NULL, mọi CHECK đều thỏa với dòng cũ nên không
cần dừng nâng cấp. Refund cũ (Pending/Success/Failed) giữ nguyên.
Downgrade dừng nếu đã có dữ liệu người tạo/kết quả xác nhận (không xóa bằng chứng hoàn tiền).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9f4c2e7b513'
down_revision: Union[str, Sequence[str], None] = 'e6a2d9c4b8f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "PaymentTransactions"
RESOLUTION_SOURCE_SQL = "\"ResolutionSource\" IN ('Gateway', 'Manual')"
RESOLUTION_CONSISTENT_SQL = (
    "(\"ResolutionSource\" IS NULL AND \"ResolvedByUserId\" IS NULL AND \"ResolvedAt\" IS NULL "
    "AND \"EvidenceReference\" IS NULL AND \"ResolutionNote\" IS NULL) OR "
    "(\"ResolutionSource\" IS NOT NULL AND \"ResolvedAt\" IS NOT NULL AND \"TransactionType\" = 'Refund' "
    "AND \"Status\" IN ('Success', 'Failed'))"
)
GATEWAY_RESOLUTION_SQL = (
    "\"ResolutionSource\" <> 'Gateway' OR (\"ResolvedByUserId\" IS NULL AND \"EvidenceReference\" IS NULL "
    "AND \"ResolutionNote\" IS NULL)"
)
MANUAL_RESOLUTION_SQL = (
    "\"ResolutionSource\" <> 'Manual' OR (\"ResolvedByUserId\" IS NOT NULL "
    "AND \"EvidenceReference\" IS NOT NULL AND length(btrim(\"EvidenceReference\")) > 0 "
    "AND \"ResolutionNote\" IS NOT NULL AND length(btrim(\"ResolutionNote\")) > 0)"
)
MANUAL_NOT_BY_CREATOR_SQL = (
    "\"ResolutionSource\" <> 'Manual' OR \"CreatedByUserId\" IS NULL "
    "OR \"ResolvedByUserId\" <> \"CreatedByUserId\""
)
CHECKS = (
    ("ResolutionSource_Valid", RESOLUTION_SOURCE_SQL),
    ("Resolution_Consistent", RESOLUTION_CONSISTENT_SQL),
    ("GatewayResolution_NoManualFields", GATEWAY_RESOLUTION_SQL),
    ("ManualResolution_Complete", MANUAL_RESOLUTION_SQL),
    ("ManualResolution_NotByCreator", MANUAL_NOT_BY_CREATOR_SQL),
)
NEW_COLUMNS = ("CreatedByUserId", "ResolvedByUserId", "ResolvedAt", "ResolutionSource", "EvidenceReference",
               "ResolutionNote")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(TABLE, sa.Column("CreatedByUserId", sa.UUID(), nullable=True))
    op.add_column(TABLE, sa.Column("ResolvedByUserId", sa.UUID(), nullable=True))
    op.add_column(TABLE, sa.Column("ResolvedAt", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("ResolutionSource", sa.String(length=20), nullable=True))
    op.add_column(TABLE, sa.Column("EvidenceReference", sa.String(length=255), nullable=True))
    op.add_column(TABLE, sa.Column("ResolutionNote", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("FK_PaymentTransactions_CreatedByUserId"), TABLE, "Users",
        ["CreatedByUserId"], ["UserId"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("FK_PaymentTransactions_ResolvedByUserId"), TABLE, "Users",
        ["ResolvedByUserId"], ["UserId"], ondelete="RESTRICT",
    )
    for name, sql in CHECKS:
        op.create_check_constraint(op.f(f"CK_PaymentTransactions_{name}"), TABLE, sql)


def downgrade() -> None:
    """Downgrade schema. Thất bại có chủ đích nếu đã có dữ liệu người tạo hoặc kết quả xác nhận Refund."""
    filled = " OR ".join(f'"{column}" IS NOT NULL' for column in NEW_COLUMNS)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{TABLE}" WHERE {filled}) THEN
                RAISE EXCEPTION 'Da co du lieu nguoi tao/ket qua xac nhan hoan tien; khong ha cap de tranh mat bang chung';
            END IF;
        END
        $$
        """
    )
    for name, _ in reversed(CHECKS):
        op.drop_constraint(op.f(f"CK_PaymentTransactions_{name}"), TABLE, type_="check")
    op.drop_constraint(op.f("FK_PaymentTransactions_ResolvedByUserId"), TABLE, type_="foreignkey")
    op.drop_constraint(op.f("FK_PaymentTransactions_CreatedByUserId"), TABLE, type_="foreignkey")
    for column in reversed(NEW_COLUMNS):
        op.drop_column(TABLE, column)
