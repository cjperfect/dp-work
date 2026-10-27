"""Agent 运行管理。"""
import sqlalchemy as sa
from alembic import op

revision = "0018_agent_runs"
down_revision = "0017_conversations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.String(128), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("response_id", sa.String(256), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(300), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('running','completed','failed','cancelled','interrupted')", name="ck_agent_runs_status"))
    op.create_index("idx_agent_runs_owner_started", "agent_runs", ["owner_id", "started_at"])
    op.create_index("idx_agent_runs_thread_started", "agent_runs", ["conversation_id", "started_at"])
    op.create_index("idx_agent_runs_active_thread", "agent_runs", ["conversation_id"], unique=True,
                    postgresql_where=sa.text("status = 'running'"))


def downgrade():
    op.drop_table("agent_runs")
