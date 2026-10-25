"""agent_knowledge_bases 表（最终结构基线，ORM 风格）。

依赖：agents、knowledge_bases（均为已建表）。
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_agent_knowledge_bases"
down_revision = "0007_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_knowledge_bases",
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "agent_id", "knowledge_base_id",
            name="agent_knowledge_bases_pkey",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"],
            ondelete="CASCADE", name="agent_knowledge_bases_agent_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"],
            ondelete="CASCADE", name="agent_knowledge_bases_knowledge_base_id_fkey",
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_knowledge_bases")
