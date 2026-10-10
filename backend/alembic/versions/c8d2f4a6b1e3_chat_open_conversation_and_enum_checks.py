"""chat: mỗi Customer tối đa một hội thoại Open; CHECK cho Mode/SenderType/MessageType

Revision ID: c8d2f4a6b1e3
Revises: a7c3e9d1f285
Create Date: 2026-10-10 18:00:00.000000

CHƯA ÁP DỤNG vào database. Phải chạy TRƯỚC khi triển khai ChatService (đợt 5.3).
Migration SePay (b81569bc34b0) đặt sau migration này.

- UNIQUE INDEX "UX_Conversations_CustomerId_Open" ON Conversations(CustomerId) WHERE Status = 'Open':
  chặn hai yêu cầu mở hội thoại đồng thời tạo hai hội thoại Open cho cùng Customer.
- CHECK Conversations.Mode IN (AI, Staff); Messages.SenderType IN (Customer, Staff, AI);
  Messages.MessageType IN (Text, Image, Product); tin nhắn AI không gắn SenderUserId.
- Không tự sửa/xóa dữ liệu cũ: nếu đã có Customer nhiều hội thoại Open hoặc giá trị ngoài danh sách thì DỪNG
  nâng cấp với thông báo rõ; cần xử lý thủ công (ví dụ đóng hội thoại thừa) rồi chạy lại.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8d2f4a6b1e3'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9d1f285'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONVERSATIONS = "Conversations"
MESSAGES = "Messages"
OPEN_INDEX = "UX_Conversations_CustomerId_Open"
AI_SENDER_SQL = "\"SenderType\" <> 'AI' OR \"SenderUserId\" IS NULL"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f'"{column}" IN (' + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM "{CONVERSATIONS}" WHERE "Status" = 'Open'
                GROUP BY "CustomerId" HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'Co Customer co nhieu hoi thoai Open; dong thu cong hoi thoai thua truoc khi nang cap';
            END IF;
            IF EXISTS (SELECT 1 FROM "{CONVERSATIONS}" WHERE NOT ({_in("Mode", ("AI", "Staff"))})) THEN
                RAISE EXCEPTION 'Conversations.Mode co gia tri ngoai (AI, Staff); can chuan hoa thu cong';
            END IF;
            IF EXISTS (
                SELECT 1 FROM "{MESSAGES}"
                WHERE NOT ({_in("SenderType", ("Customer", "Staff", "AI"))})
                   OR NOT ({_in("MessageType", ("Text", "Image", "Product"))})
                   OR NOT ({AI_SENDER_SQL})
            ) THEN
                RAISE EXCEPTION 'Messages co SenderType/MessageType ngoai danh sach hoac tin AI gan nguoi dung; can xu ly thu cong';
            END IF;
        END
        $$
        """
    )
    op.create_index(
        OPEN_INDEX, CONVERSATIONS, ["CustomerId"], unique=True, postgresql_where=sa.text("\"Status\" = 'Open'")
    )
    op.create_check_constraint(op.f("CK_Conversations_Mode_Valid"), CONVERSATIONS, _in("Mode", ("AI", "Staff")))
    op.create_check_constraint(
        op.f("CK_Messages_SenderType_Valid"), MESSAGES, _in("SenderType", ("Customer", "Staff", "AI"))
    )
    op.create_check_constraint(
        op.f("CK_Messages_MessageType_Valid"), MESSAGES, _in("MessageType", ("Text", "Image", "Product"))
    )
    op.create_check_constraint(op.f("CK_Messages_AiSender_NoUser"), MESSAGES, AI_SENDER_SQL)


def downgrade() -> None:
    """Downgrade schema (chỉ bỏ ràng buộc, không đổi dữ liệu)."""
    op.drop_constraint(op.f("CK_Messages_AiSender_NoUser"), MESSAGES, type_="check")
    op.drop_constraint(op.f("CK_Messages_MessageType_Valid"), MESSAGES, type_="check")
    op.drop_constraint(op.f("CK_Messages_SenderType_Valid"), MESSAGES, type_="check")
    op.drop_constraint(op.f("CK_Conversations_Mode_Valid"), CONVERSATIONS, type_="check")
    op.drop_index(OPEN_INDEX, table_name=CONVERSATIONS)
