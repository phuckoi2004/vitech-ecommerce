"""warranty: máy thay thế, Admin duyệt kết quả, CHECK ResultType/FileType, mỗi serial một yêu cầu đang xử lý

Revision ID: d4f7b2e9a6c1
Revises: c8d2f4a6b1e3
Create Date: 2026-10-10 20:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy TRƯỚC khi triển khai WarrantyService (đợt 5.4).
Migration SePay (b81569bc34b0) đặt sau migration này.

- WarrantyRequests: ResultApprovedByUserId (SET NULL), ResultApprovedAt — Admin duyệt kết quả nhân viên đề xuất;
  ReplacementProductSerialId (RESTRICT), ReplacementHandedOverAt, ReplacementHandedOverByUserId (SET NULL) — máy
  thay thế giao cho khách (serial cũ giữ nguyên lịch sử).
- CHECK ResultType IN (Repaired, ProductReplaced, PartReplaced, NotRepairable); thông tin máy thay thế chỉ khi
  ProductReplaced; duyệt cần có kết quả; Completed cần kết quả đã duyệt (+ đã bàn giao máy thay thế nếu đổi máy).
- CHECK ServiceRequestAttachments.FileType IN (Image, Video).
- UNIQUE INDEX một yêu cầu đang xử lý (New/HandedOver/Processing) cho mỗi serial, và cho mỗi dòng đơn không serial.
Không tự sửa dữ liệu cũ: dữ liệu vi phạm → DỪNG nâng cấp với thông báo rõ.
Downgrade dừng nếu đã có dữ liệu duyệt/máy thay thế (không xóa lịch sử bảo hành).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f7b2e9a6c1'
down_revision: Union[str, Sequence[str], None] = 'c8d2f4a6b1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "WarrantyRequests"
ATTACHMENTS = "ServiceRequestAttachments"
OPEN_SQL = "\"Status\" IN ('New', 'HandedOver', 'Processing')"
RESULT_TYPES_SQL = "\"ResultType\" IN ('Repaired', 'ProductReplaced', 'PartReplaced', 'NotRepairable')"
FILE_TYPES_SQL = "\"FileType\" IN ('Image', 'Video')"
REPLACEMENT_SQL = (
    '("ReplacementProductSerialId" IS NULL AND "ReplacementHandedOverAt" IS NULL) '
    "OR \"ResultType\" = 'ProductReplaced'"
)
APPROVAL_SQL = '"ResultApprovedAt" IS NULL OR "ResultType" IS NOT NULL'
COMPLETED_SQL = (
    "\"Status\" <> 'Completed' OR (\"CompletedAt\" IS NOT NULL AND \"ResultType\" IS NOT NULL "
    "AND \"ResultApprovedAt\" IS NOT NULL "
    "AND (\"ResultType\" <> 'ProductReplaced' OR \"ReplacementHandedOverAt\" IS NOT NULL))"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{TABLE}" WHERE "ResultType" IS NOT NULL AND NOT ({RESULT_TYPES_SQL})) THEN
                RAISE EXCEPTION 'WarrantyRequests.ResultType co gia tri ngoai danh sach; can chuan hoa thu cong';
            END IF;
            IF EXISTS (SELECT 1 FROM "{TABLE}" WHERE "Status" = 'Completed') THEN
                RAISE EXCEPTION 'Da co yeu cau bao hanh Completed chua co thong tin duyet ket qua; can xu ly thu cong';
            END IF;
            IF EXISTS (SELECT 1 FROM "{ATTACHMENTS}" WHERE NOT ({FILE_TYPES_SQL})) THEN
                RAISE EXCEPTION 'ServiceRequestAttachments.FileType co gia tri ngoai (Image, Video); can chuan hoa thu cong';
            END IF;
            IF EXISTS (
                SELECT 1 FROM "{TABLE}" WHERE "ProductSerialId" IS NOT NULL AND {OPEN_SQL}
                GROUP BY "ProductSerialId" HAVING count(*) > 1
            ) OR EXISTS (
                SELECT 1 FROM "{TABLE}" WHERE "ProductSerialId" IS NULL AND {OPEN_SQL}
                GROUP BY "OrderItemId" HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'Co nhieu yeu cau bao hanh dang xu ly cho cung serial/dong don; can xu ly thu cong';
            END IF;
        END
        $$
        """
    )
    op.add_column(TABLE, sa.Column("ResultApprovedByUserId", sa.UUID(), nullable=True))
    op.add_column(TABLE, sa.Column("ResultApprovedAt", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("ReplacementProductSerialId", sa.UUID(), nullable=True))
    op.add_column(TABLE, sa.Column("ReplacementHandedOverAt", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("ReplacementHandedOverByUserId", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("FK_WarrantyRequests_ResultApprovedByUserId"), TABLE, "Users",
        ["ResultApprovedByUserId"], ["UserId"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("FK_WarrantyRequests_ReplacementProductSerialId"), TABLE, "ProductSerials",
        ["ReplacementProductSerialId"], ["ProductSerialId"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("FK_WarrantyRequests_ReplacementHandedOverByUserId"), TABLE, "Users",
        ["ReplacementHandedOverByUserId"], ["UserId"], ondelete="SET NULL",
    )
    op.create_check_constraint(op.f("CK_WarrantyRequests_ResultType_Valid"), TABLE, RESULT_TYPES_SQL)
    op.create_check_constraint(op.f("CK_WarrantyRequests_Replacement_OnlyProductReplaced"), TABLE, REPLACEMENT_SQL)
    op.create_check_constraint(op.f("CK_WarrantyRequests_Approval_RequiresResult"), TABLE, APPROVAL_SQL)
    op.create_check_constraint(op.f("CK_WarrantyRequests_Completed_RequiresApprovedResult"), TABLE, COMPLETED_SQL)
    op.create_check_constraint(op.f("CK_ServiceRequestAttachments_FileType_Valid"), ATTACHMENTS, FILE_TYPES_SQL)
    op.create_index(
        "UX_WarrantyRequests_Serial_Open", TABLE, ["ProductSerialId"], unique=True,
        postgresql_where=sa.text('"ProductSerialId" IS NOT NULL AND ' + OPEN_SQL),
    )
    op.create_index(
        "UX_WarrantyRequests_OrderItem_Open_NoSerial", TABLE, ["OrderItemId"], unique=True,
        postgresql_where=sa.text('"ProductSerialId" IS NULL AND ' + OPEN_SQL),
    )


def downgrade() -> None:
    """Downgrade schema. Thất bại có chủ đích nếu đã có dữ liệu duyệt kết quả / máy thay thế."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM "{TABLE}"
                WHERE "ResultApprovedAt" IS NOT NULL OR "ReplacementProductSerialId" IS NOT NULL
                   OR "ReplacementHandedOverAt" IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Da co du lieu duyet ket qua/may thay the bao hanh; khong ha cap';
            END IF;
        END
        $$
        """
    )
    op.drop_index("UX_WarrantyRequests_OrderItem_Open_NoSerial", table_name=TABLE)
    op.drop_index("UX_WarrantyRequests_Serial_Open", table_name=TABLE)
    op.drop_constraint(op.f("CK_ServiceRequestAttachments_FileType_Valid"), ATTACHMENTS, type_="check")
    op.drop_constraint(op.f("CK_WarrantyRequests_Completed_RequiresApprovedResult"), TABLE, type_="check")
    op.drop_constraint(op.f("CK_WarrantyRequests_Approval_RequiresResult"), TABLE, type_="check")
    op.drop_constraint(op.f("CK_WarrantyRequests_Replacement_OnlyProductReplaced"), TABLE, type_="check")
    op.drop_constraint(op.f("CK_WarrantyRequests_ResultType_Valid"), TABLE, type_="check")
    op.drop_constraint(op.f("FK_WarrantyRequests_ReplacementHandedOverByUserId"), TABLE, type_="foreignkey")
    op.drop_constraint(op.f("FK_WarrantyRequests_ReplacementProductSerialId"), TABLE, type_="foreignkey")
    op.drop_constraint(op.f("FK_WarrantyRequests_ResultApprovedByUserId"), TABLE, type_="foreignkey")
    op.drop_column(TABLE, "ReplacementHandedOverByUserId")
    op.drop_column(TABLE, "ReplacementHandedOverAt")
    op.drop_column(TABLE, "ReplacementProductSerialId")
    op.drop_column(TABLE, "ResultApprovedAt")
    op.drop_column(TABLE, "ResultApprovedByUserId")
