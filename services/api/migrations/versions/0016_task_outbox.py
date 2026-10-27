"""RabbitMQ 事务消息表。"""
import sqlalchemy as sa
from alembic import op
revision = '0016_task_outbox'
down_revision = '0015_knowledge_search_sync'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('task_outbox',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('target_id', sa.String(128), nullable=False),
        sa.Column('version', sa.String(128), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claim_token', sa.String(36), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('kind', 'target_id', 'version', name='uq_task_outbox_target_version'))
    op.create_index('idx_task_outbox_dispatch', 'task_outbox', ['completed_at', 'next_attempt_at', 'lease_until'])


def downgrade():
    op.drop_table('task_outbox')
