"""minutes 表（最终结构基线，ORM 风格）。

依赖：users -> meetings（meeting_id 外键）、knowledge_documents
（archived_document_id 外键）。
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_minutes"
down_revision = "0005_knowledge_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "minutes",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("meeting_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("status", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("archived_document_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="minutes_pkey"),
        sa.UniqueConstraint("meeting_id", name="minutes_meeting_id_key"),
        sa.UniqueConstraint("archived_document_id", name="minutes_archived_document_id_key"),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meetings.id"],
            ondelete="CASCADE", name="minutes_meeting_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["archived_document_id"], ["knowledge_documents.id"],
            ondelete="SET NULL", name="minutes_archived_document_id_fkey",
        ),
    )


def downgrade() -> None:
    op.drop_table("minutes")
