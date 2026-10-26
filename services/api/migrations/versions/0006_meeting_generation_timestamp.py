"""会议生成时间使用毫秒时间戳，避免 PostgreSQL INTEGER 溢出。"""
import sqlalchemy as sa
from alembic import op

revision = "0006_meeting_timestamp"
down_revision = "0005_meetings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("meetings") as batch:
        batch.alter_column("generation_ready_at", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True)


def downgrade() -> None:
    # 毫秒时间戳不能安全缩回 int32，保留可空字段并清除旧版模拟计时值。
    op.execute("UPDATE meetings SET generation_ready_at = NULL")
    with op.batch_alter_table("meetings") as batch:
        batch.alter_column("generation_ready_at", existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=True)
