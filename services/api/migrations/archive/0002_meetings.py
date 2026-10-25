"""meetings 表（最终结构基线，ORM 风格）。

依赖：users（owner_id 外键）。排在 transcript_segments/minutes 之前，
使这两张表的 meeting_id 外键在引用时表已存在。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_meetings"
down_revision = "0001_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("participants", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("elapsed_ms", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_sync_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="meetings_pkey"),
        sa.CheckConstraint(
            "status IN ('active','paused','ended','archived')",
            name="meetings_status_check",
        ),
        sa.CheckConstraint("elapsed_ms >= 0", name="meetings_elapsed_nonnegative_check"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"],
            ondelete="RESTRICT", name="meetings_owner_id_fkey",
        ),
    )
    op.create_index("idx_meetings_owner_updated", "meetings", ["owner_id", "updated_at", "id"])


def downgrade() -> None:
    op.drop_table("meetings")
