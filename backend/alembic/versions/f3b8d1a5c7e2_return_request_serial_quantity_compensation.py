"""returns: serial/số lượng trả, kết quả kiểm tra, căn cứ và duyệt số tiền, liên kết giao dịch hoàn tiền

Revision ID: f3b8d1a5c7e2
Revises: d4f7b2e9a6c1
Create Date: 2026-10-10 22:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy TRƯỚC khi triển khai ReturnService (đợt 5.4).
Migration SePay (b81569bc34b0) đặt sau migration này.

- ReturnRequests: ProductSerialId (RESTRICT), Quantity NOT NULL, RestockedQuantity/DamagedQuantity (kết quả kiểm tra),
  CompensationBasis jsonb (căn cứ tính tiền), CompensationApprovedAt/ByUserId (SET NULL) — Admin duyệt số tiền,
  RefundPaymentTransactionId (RESTRICT, UNIQUE) — giao dịch Refund tạo cho yêu cầu trả hàng.
- CHECK RequestType IN (Exchange, Return); Quantity > 0; serial = 1 đơn vị; nhập lại + hỏng = số lượng, chỉ sau khi
  nhận hàng; duyệt cần kết quả kiểm tra và số tiền; hoàn tiền chỉ cho Return đã duyệt; Completed cần đã duyệt.
- UNIQUE INDEX một yêu cầu đổi/trả đang xử lý (Pending/Approved/Receiving/Processing) cho mỗi serial.
Không suy diễn dữ liệu cũ: đã có dòng ReturnRequests (không xác định được serial/số lượng) → DỪNG nâng cấp.
Downgrade dừng nếu đã có dòng ReturnRequests (không xóa serial/số lượng/căn cứ tiền đã ghi).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3b8d1a5c7e2'
down_revision: Union[str, Sequence[str], None] = 'd4f7b2e9a6c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "ReturnRequests"
OPEN_SQL = "\"Status\" IN ('Pending', 'Approved', 'Receiving', 'Processing')"
CHECKS = (
    ("CK_ReturnRequests_RequestType_Valid", "\"RequestType\" IN ('Exchange', 'Return')"),
    ("CK_ReturnRequests_Quantity_Positive", '"Quantity" > 0'),
    ("CK_ReturnRequests_Serial_SingleUnit", '"ProductSerialId" IS NULL OR "Quantity" = 1'),
    (
        "CK_ReturnRequests_Inspection_Consistent",
        '("RestockedQuantity" IS NULL AND "DamagedQuantity" IS NULL) OR ("RestockedQuantity" >= 0 '
        'AND "DamagedQuantity" >= 0 AND "RestockedQuantity" + "DamagedQuantity" = "Quantity")',
    ),
    ("CK_ReturnRequests_Inspection_RequiresReceipt", '"RestockedQuantity" IS NULL OR "ReceivedAt" IS NOT NULL'),
    (
        "CK_ReturnRequests_Approval_RequiresAssessment",
        '"CompensationApprovedAt" IS NULL OR ("CompensationAmount" IS NOT NULL AND "RestockedQuantity" IS NOT NULL)',
    ),
    (
        "CK_ReturnRequests_Refund_RequiresApprovedReturn",
        "\"RefundPaymentTransactionId\" IS NULL OR (\"RequestType\" = 'Return' AND \"CompensationApprovedAt\" IS NOT NULL)",
    ),
    (
        "CK_ReturnRequests_Completed_RequiresApproval",
        "\"Status\" <> 'Completed' OR (\"CompletedAt\" IS NOT NULL AND \"CompensationApprovedAt\" IS NOT NULL)",
    ),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{TABLE}") THEN
                RAISE EXCEPTION 'Da co ReturnRequests cu (khong xac dinh duoc serial/so luong tra); can bo sung thu cong';
            END IF;
        END
        $$
        """
    )
    op.add_column(TABLE, sa.Column("ProductSerialId", sa.UUID(), nullable=True))
    op.add_column(TABLE, sa.Column("Quantity", sa.Integer(), nullable=False))
    op.add_column(TABLE, sa.Column("RestockedQuantity", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("DamagedQuantity", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("CompensationBasis", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(TABLE, sa.Column("CompensationApprovedAt", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("CompensationApprovedByUserId", sa.UUID(), nullable=True))
    op.add_column(TABLE, sa.Column("RefundPaymentTransactionId", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("FK_ReturnRequests_ProductSerialId"), TABLE, "ProductSerials",
        ["ProductSerialId"], ["ProductSerialId"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("FK_ReturnRequests_CompensationApprovedByUserId"), TABLE, "Users",
        ["CompensationApprovedByUserId"], ["UserId"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("FK_ReturnRequests_RefundPaymentTransactionId"), TABLE, "PaymentTransactions",
        ["RefundPaymentTransactionId"], ["PaymentTransactionId"], ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        op.f("UQ_ReturnRequests_RefundPaymentTransactionId"), TABLE, ["RefundPaymentTransactionId"]
    )
    for name, condition in CHECKS:
        op.create_check_constraint(op.f(name), TABLE, condition)
    op.create_index(
        "UX_ReturnRequests_Serial_Open", TABLE, ["ProductSerialId"], unique=True,
        postgresql_where=sa.text('"ProductSerialId" IS NOT NULL AND ' + OPEN_SQL),
    )


def downgrade() -> None:
    """Downgrade schema. Thất bại có chủ đích nếu đã có dòng ReturnRequests."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM "{TABLE}") THEN
                RAISE EXCEPTION 'Da co ReturnRequests (serial/so luong/can cu tien); khong ha cap';
            END IF;
        END
        $$
        """
    )
    op.drop_index("UX_ReturnRequests_Serial_Open", table_name=TABLE)
    for name, _ in reversed(CHECKS):
        op.drop_constraint(op.f(name), TABLE, type_="check")
    op.drop_constraint(op.f("UQ_ReturnRequests_RefundPaymentTransactionId"), TABLE, type_="unique")
    op.drop_constraint(op.f("FK_ReturnRequests_RefundPaymentTransactionId"), TABLE, type_="foreignkey")
    op.drop_constraint(op.f("FK_ReturnRequests_CompensationApprovedByUserId"), TABLE, type_="foreignkey")
    op.drop_constraint(op.f("FK_ReturnRequests_ProductSerialId"), TABLE, type_="foreignkey")
    op.drop_column(TABLE, "RefundPaymentTransactionId")
    op.drop_column(TABLE, "CompensationApprovedByUserId")
    op.drop_column(TABLE, "CompensationApprovedAt")
    op.drop_column(TABLE, "CompensationBasis")
    op.drop_column(TABLE, "DamagedQuantity")
    op.drop_column(TABLE, "RestockedQuantity")
    op.drop_column(TABLE, "Quantity")
    op.drop_column(TABLE, "ProductSerialId")
