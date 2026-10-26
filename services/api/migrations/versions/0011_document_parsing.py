"""持久化文档解析任务及结果。"""
import sqlalchemy as sa
from alembic import op

revision = "0011_document_parsing"
down_revision = "0010_minutes_autosave"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("knowledge_documents", sa.Column("parse_status", sa.String(16), nullable=False, server_default="unparsed"))
    for name, kind in [
        ("parse_content", sa.Text()), ("parse_metadata", sa.JSON()),
        ("parse_error", sa.Text()), ("parsed_at", sa.DateTime(timezone=True)),
        ("parse_started_at", sa.DateTime(timezone=True)), ("parse_claim_token", sa.String(36)),
        ("parse_lease_until", sa.DateTime(timezone=True)),
    ]:
        op.add_column("knowledge_documents", sa.Column(name, kind, nullable=True))
    op.create_index("idx_knowledge_documents_parse_status", "knowledge_documents", ["parse_status"])


def downgrade():
    op.drop_index("idx_knowledge_documents_parse_status", table_name="knowledge_documents")
    for name in ("parse_lease_until", "parse_claim_token", "parse_started_at", "parsed_at", "parse_error",
                 "parse_metadata", "parse_content", "parse_status"):
        op.drop_column("knowledge_documents", name)
