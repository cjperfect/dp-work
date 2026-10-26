"""父子分块与 pgvector 索引。"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
revision = "0014_knowledge_rag"
down_revision = "0013_user_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for column in [
        sa.Column("vector_status", sa.String(16), nullable=False, server_default="unindexed"),
        sa.Column("vector_error", sa.Text(), nullable=True),
        sa.Column("vector_task_id", sa.String(36), nullable=True),
        sa.Column("vector_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vector_claim_token", sa.String(36), nullable=True),
        sa.Column("vector_lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vector_profile", sa.String(64), nullable=True),
        sa.Column("vector_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vector_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vector_attempts", sa.Integer(), nullable=False, server_default="0"),
    ]:
        op.add_column("knowledge_documents", column)
    op.create_index("idx_knowledge_vector_status", "knowledge_documents", ["vector_status"])
    op.create_table("knowledge_parent_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(128), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_metadata", sa.JSON(), nullable=False))
    op.create_index("idx_knowledge_parent_document", "knowledge_parent_chunks", ["document_id"])
    op.create_table("knowledge_child_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("knowledge_parent_chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False))
    op.create_index("idx_knowledge_child_parent", "knowledge_child_chunks", ["parent_id"])
    op.create_index("idx_knowledge_child_embedding", "knowledge_child_chunks", ["embedding"], postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})


def downgrade():
    op.drop_table("knowledge_child_chunks")
    op.drop_table("knowledge_parent_chunks")
    op.drop_index("idx_knowledge_vector_status", table_name="knowledge_documents")
    for name in ("vector_status", "vector_error", "vector_task_id", "vector_started_at", "vector_claim_token", "vector_lease_until", "vector_profile", "vector_done", "vector_total", "vector_attempts"):
        op.drop_column("knowledge_documents", name)
