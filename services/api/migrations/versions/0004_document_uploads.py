"""文档上传的文件元数据。"""
import sqlalchemy as sa
from alembic import op

revision = "0004_document_uploads"
down_revision = "0003_knowledge_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("source", sa.String(16), server_default=sa.text("'editor'"), nullable=False))
    op.add_column("knowledge_documents", sa.Column("file_type", sa.String(16), server_default=sa.text("'md'"), nullable=False))
    op.add_column("knowledge_documents", sa.Column("original_name", sa.Text(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("byte_size", sa.Integer(), server_default=sa.text("'0'"), nullable=False))
    op.add_column("knowledge_documents", sa.Column("storage_key", sa.Text(), nullable=True))


def downgrade() -> None:
    for column in ("storage_key", "byte_size", "original_name", "file_type", "source"):
        op.drop_column("knowledge_documents", column)
