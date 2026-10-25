"""新增知识库表（SQLite 方言）。"""

import sqlalchemy as sa
from alembic import op

revision = "0002_knowledge_bases"
down_revision = "0001_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="knowledge_bases_pkey"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name="knowledge_bases_owner_id_fkey",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("idx_knowledge_bases_owner_id", "knowledge_bases", ["owner_id"])


def downgrade() -> None:
    op.drop_table("knowledge_bases")
