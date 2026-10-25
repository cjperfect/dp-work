"""knowledge_bases 表（最终结构基线，ORM 风格）。

依赖：users（owner_id 外键）。
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_knowledge_bases"
down_revision = "0003_transcript_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="knowledge_bases_pkey"),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name="knowledge_bases_name_nonempty_check"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"],
            ondelete="RESTRICT", name="knowledge_bases_owner_id_fkey",
        ),
    )
    op.create_index(
        "idx_knowledge_bases_owner_updated",
        "knowledge_bases",
        ["owner_id", "updated_at", "id"],
    )
    op.execute(
        """
        CREATE FUNCTION update_knowledge_timestamp() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
            BEGIN
                NEW.updated_at := clock_timestamp();
                RETURN NEW;
            END;
            $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_bases_set_updated_at BEFORE UPDATE ON knowledge_bases
        FOR EACH ROW WHEN ((old.* IS DISTINCT FROM new.*))
        EXECUTE FUNCTION update_knowledge_timestamp();
        """
    )


def downgrade() -> None:
    op.drop_table("knowledge_bases")
    op.execute("DROP FUNCTION IF EXISTS update_knowledge_timestamp()")
