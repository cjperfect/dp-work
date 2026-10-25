"""chat_threads 表（最终结构基线，ORM 风格）。

依赖：agents（agent_id 外键）。建表后补上 agents.active_thread_id 的
循环外键（模型侧 use_alter=True）。
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_chat_threads"
down_revision = "0008_agent_knowledge_bases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), server_default=sa.text("'新会话'"), nullable=False),
        sa.Column("draft", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("draft_revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="chat_threads_pkey"),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"],
            ondelete="CASCADE", name="chat_threads_agent_id_fkey",
        ),
    )
    op.create_index(
        "idx_chat_threads_agent_updated",
        "chat_threads",
        ["agent_id", "updated_at", "id"],
    )
    # agents 与 chat_threads 的循环外键：chat_threads 已建，此时补上
    op.execute(
        """
        ALTER TABLE agents
        ADD CONSTRAINT agents_active_thread_id_fkey FOREIGN KEY (active_thread_id)
        REFERENCES chat_threads(id) ON DELETE SET NULL;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE agents DROP CONSTRAINT IF EXISTS agents_active_thread_id_fkey")
    op.drop_table("chat_threads")
