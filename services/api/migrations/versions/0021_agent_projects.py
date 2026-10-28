"""项目目录元信息与会话归属。"""
import sqlalchemy as sa
from alembic import op
revision = '0021_agent_projects'
down_revision = '0020_agent_approvals'
branch_labels = depends_on = None


def upgrade():
    op.create_table('agent_projects',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('device_id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(256), nullable=False), sa.Column('path', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('idx_agent_projects_owner_updated', 'agent_projects', ['owner_id','updated_at'])
    op.add_column('conversations', sa.Column('project_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_conversations_project', 'conversations','agent_projects',['project_id'],['id'],ondelete='SET NULL')
    op.create_index('idx_conversations_project', 'conversations', ['project_id'])


def downgrade():
    op.drop_index('idx_conversations_project', table_name='conversations')
    op.drop_constraint('fk_conversations_project', 'conversations', type_='foreignkey')
    op.drop_column('conversations','project_id')
    op.drop_table('agent_projects')
