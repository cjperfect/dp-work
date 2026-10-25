"""chat_thread_knowledge_bases 表（最终结构基线，ORM 风格）。

依赖：chat_threads、knowledge_bases（均为已建表）。
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_chat_thread_knowledge_bases"
down_revision = "0009_chat_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_thread_knowledge_bases",
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "thread_id", "knowledge_base_id",
            name="chat_thread_knowledge_bases_pkey",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["chat_threads.id"],
            ondelete="CASCADE", name="chat_thread_knowledge_bases_thread_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"],
            ondelete="CASCADE", name="chat_thread_knowledge_bases_knowledge_base_id_fkey",
        ),
    )


def downgrade() -> None:
    op.drop_table("chat_thread_knowledge_bases")
