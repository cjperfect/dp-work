"""新增在线文档的 SQLite 持久化表。"""
import sqlalchemy as sa
from alembic import op

revision = "0003_knowledge_documents"
down_revision = "0002_knowledge_bases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("knowledge_base_id", sa.Integer(), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("blocks", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("idx_knowledge_documents_base_id", "knowledge_documents", ["knowledge_base_id"])


def downgrade() -> None:
    op.drop_table("knowledge_documents")
