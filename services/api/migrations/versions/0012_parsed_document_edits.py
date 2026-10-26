"""保存人工调整后的解析文档富文本。"""
import sqlalchemy as sa
from alembic import op
revision = "0012_parsed_document_edits"
down_revision = "0011_document_parsing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("knowledge_documents", sa.Column("parse_blocks", sa.JSON(), nullable=True))
    op.add_column("knowledge_documents", sa.Column("vectorized_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("knowledge_documents", "vectorized_at")
    op.drop_column("knowledge_documents", "parse_blocks")
