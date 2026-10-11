"""coupon code case-insensitive unique

Revision ID: 213feab4a632
Revises: 9b10f42fc70d
Create Date: 2026-10-09 14:41:27.516794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '213feab4a632'
down_revision: Union[str, Sequence[str], None] = '9b10f42fc70d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UNIQUE_CONSTRAINT = "UQ_Coupons_Code"
UNIQUE_INDEX = "UX_Coupons_Code_Lower"


def upgrade() -> None:
    """Upgrade schema."""
    # Tạo index mới trước rồi mới bỏ UNIQUE cũ (trong cùng transaction) để không có lúc thiếu ràng buộc.
    # Nếu dữ liệu có mã chỉ khác nhau về hoa thường, tạo index lỗi và transaction rollback.
    op.create_index(UNIQUE_INDEX, "Coupons", [sa.literal_column('lower("Code")')], unique=True)
    op.drop_constraint(op.f(UNIQUE_CONSTRAINT), "Coupons", type_="unique")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_unique_constraint(op.f(UNIQUE_CONSTRAINT), "Coupons", ["Code"])
    op.drop_index(UNIQUE_INDEX, table_name="Coupons")
