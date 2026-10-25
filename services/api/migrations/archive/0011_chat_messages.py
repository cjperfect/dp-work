"""chat_messages 表（最终结构基线，ORM 风格）。

依赖：chat_threads（thread_id 外键）。迁移链最后一个 revision（head）。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_chat_messages"
down_revision = "0010_chat_thread_knowledge_bases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), server_default=sa.text("'user'"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="chat_messages_pkey"),
        sa.UniqueConstraint("thread_id", "seq", name="chat_messages_thread_id_seq_key"),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["chat_threads.id"],
            ondelete="CASCADE", name="chat_messages_thread_id_fkey",
        ),
    )


def downgrade() -> None:
    op.drop_table("chat_messages")
