"""knowledge_documents 表（最终结构基线，ORM 风格）。

依赖：users -> knowledge_bases（knowledge_base_id 外键）。
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_knowledge_documents"
down_revision = "0004_knowledge_bases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), server_default=sa.text("'upload'"), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="knowledge_documents_pkey"),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name="knowledge_documents_name_nonempty_check"
        ),
        sa.CheckConstraint(
            "file_type = ANY (ARRAY['md'::text, 'pdf'::text])",
            name="knowledge_documents_file_type_check",
        ),
        sa.CheckConstraint(
            "source = ANY (ARRAY['upload'::text, 'editor'::text])",
            name="knowledge_documents_source_check",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="knowledge_documents_size_nonnegative_check"),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"],
            ondelete="CASCADE", name="knowledge_documents_knowledge_base_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            ondelete="RESTRICT", name="knowledge_documents_created_by_fkey",
        ),
    )
    op.create_index(
        "idx_knowledge_documents_base_updated",
        "knowledge_documents",
        ["knowledge_base_id", "updated_at", "id"],
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_documents_set_updated_at BEFORE UPDATE ON knowledge_documents
        FOR EACH ROW WHEN ((old.* IS DISTINCT FROM new.*))
        EXECUTE FUNCTION update_knowledge_timestamp();
        """
    )


def downgrade() -> None:
    op.drop_table("knowledge_documents")
