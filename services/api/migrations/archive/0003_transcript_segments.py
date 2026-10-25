"""transcript_segments 表（最终结构基线，ORM 风格）。

依赖：users -> meetings（meeting_id 外键）。
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_transcript_segments"
down_revision = "0002_meetings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("meeting_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="transcript_segments_pkey"),
        sa.UniqueConstraint("meeting_id", "seq", name="transcript_segments_meeting_id_seq_key"),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meetings.id"],
            ondelete="CASCADE", name="transcript_segments_meeting_id_fkey",
        ),
    )
    op.create_index(
        "idx_transcript_segments_meeting",
        "transcript_segments",
        ["meeting_id", "seq"],
    )


def downgrade() -> None:
    op.drop_table("transcript_segments")
