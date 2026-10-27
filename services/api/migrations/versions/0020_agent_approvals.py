"""工具审批的持久化记录。"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op
revision = '0020_agent_approvals'
down_revision = '0019_device_bridge'
branch_labels = depends_on = None


def upgrade():
    op.create_table('agent_approvals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('run_id', sa.String(36), sa.ForeignKey('agent_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('interrupts', postgresql.JSONB(), nullable=False),
        sa.Column('knowledge_base_ids', postgresql.JSONB(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp(), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name='ck_agent_approvals_status'))
    op.create_index('idx_agent_approvals_run_created', 'agent_approvals', ['run_id', 'created_at'])


def downgrade():
    op.drop_table('agent_approvals')
