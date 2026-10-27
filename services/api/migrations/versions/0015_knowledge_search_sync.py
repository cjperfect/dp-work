"""Elasticsearch 持久化同步与删除补偿。"""
import sqlalchemy as sa
from alembic import op
revision = "0015_knowledge_search_sync"
down_revision = "0014_knowledge_rag"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("knowledge_search_sync",
        sa.Column("document_id", sa.String(128), primary_key=True),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("synced_revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("desired_task_id", sa.String(36), nullable=True),
        sa.Column("index_generation", sa.String(64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("idx_knowledge_search_sync_pending", "knowledge_search_sync", ["next_run_at", "lease_until"])


def downgrade():
    op.drop_table("knowledge_search_sync")
