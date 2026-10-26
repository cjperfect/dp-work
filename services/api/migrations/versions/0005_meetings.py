"""会议、确认转写与富文本纪要。"""
import sqlalchemy as sa
from alembic import op

revision = "0005_meetings"
down_revision = "0004_document_uploads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("meetings",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'active'"), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("'1'"), nullable=False),
        sa.Column("minutes_status", sa.Integer(), nullable=True),
        sa.Column("generation_status", sa.String(16), server_default=sa.text("'idle'"), nullable=False),
        sa.Column("generation_error", sa.Text(), nullable=True),
        sa.Column("generation_ready_at", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("idx_meetings_owner_updated", "meetings", ["owner_id", "updated_at"])
    op.create_table("meeting_segments",
        sa.Column("meeting_id", sa.String(128), sa.ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.String(256), primary_key=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("'1'"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.UniqueConstraint("meeting_id", "seq", name="uq_meeting_segments_seq"))
    op.create_table("meeting_minutes",
        sa.Column("meeting_id", sa.String(128), sa.ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("blocks", sa.JSON(), nullable=True),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("archived_document_id", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_table("meeting_minutes")
    op.drop_table("meeting_segments")
    op.drop_index("idx_meetings_owner_updated", table_name="meetings")
    op.drop_table("meetings")
