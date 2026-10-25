"""agents 表（最终结构基线，ORM 风格）。

依赖：users（owner_id 外键）。active_thread_id 与 chat_threads 形成循环引用，
该外键在 0009_chat_threads 建表后以 ALTER 补上（见 use_alter）。
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_agents"
down_revision = "0006_minutes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("skill_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("active_thread_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="agents_pkey"),
        sa.UniqueConstraint("owner_id", "code", name="agents_owner_id_code_key"),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"],
            ondelete="RESTRICT", name="agents_owner_id_fkey",
        ),
    )


def downgrade() -> None:
    op.drop_table("agents")
