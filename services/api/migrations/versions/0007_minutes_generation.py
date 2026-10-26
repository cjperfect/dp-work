"""持久化纪要生成任务与原始内容快照。"""
import sqlalchemy as sa
from alembic import op

revision = "0007_minutes_generation"
down_revision = "0006_meeting_timestamp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("generation_task_id", sa.String(36), nullable=True))
    op.add_column("meetings", sa.Column("generation_source_revision", sa.Integer(), nullable=True))
    op.create_table("meeting_generation_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(128), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_minutes_jobs_claim", "meeting_generation_jobs", ["status", "lease_until", "created_at"])
    op.create_index("uq_minutes_jobs_active", "meeting_generation_jobs", ["meeting_id"], unique=True,
                    postgresql_where=sa.text("status IN ('queued', 'running')"))
    op.execute("UPDATE meetings SET generation_status='failed', generation_error='旧版占位任务未实际执行，请重新生成。' WHERE generation_status='generating'")


def downgrade() -> None:
    op.drop_table("meeting_generation_jobs")
    op.drop_column("meetings", "generation_source_revision")
    op.drop_column("meetings", "generation_task_id")
