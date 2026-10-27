"""用户会话和消息分支持久化。"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op
revision = '0017_conversations'
down_revision = '0016_task_outbox'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('conversations',
        sa.Column('id', sa.String(128), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False, server_default='新会话'),
        sa.Column('title_source', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('draft', sa.Text(), nullable=False, server_default=''),
        sa.Column('draft_revision', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('knowledge_base_ids', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('active_path', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('run_token', sa.String(36), nullable=True),
        sa.Column('run_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('idx_conversations_owner_updated', 'conversations', ['owner_id', 'updated_at'])
    op.create_table('conversation_messages',
        sa.Column('conversation_id', sa.String(128), sa.ForeignKey('conversations.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('id', sa.String(256), primary_key=True),
        sa.Column('parent_id', sa.String(256), nullable=True),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='complete'),
        sa.Column('context', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('conversation_messages')
    op.drop_table('conversations')
