"""会话、消息、运行及审批已迁至设备，移除废弃 PG 表。"""
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = '0022_local_agent_history'
down_revision = '0021_agent_projects'
branch_labels = depends_on = None


def upgrade():
    """依外键顺序移除旧表，不使用 CASCADE 影响其他业务。"""
    op.drop_table('agent_approvals')
    op.drop_table('agent_runs')
    op.drop_table('conversation_messages')
    op.drop_table('conversations')


def historical(name):
    file = Path(__file__).with_name(name + '.py')
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.upgrade()


def downgrade():
    """恢复旧结构；已删除正文需要从独立备份恢复。"""
    historical('0017_conversations')
    historical('0018_agent_runs')
    op.add_column('agent_runs', sa.Column('device_id', sa.String(36), nullable=True))
    historical('0020_agent_approvals')
    op.add_column('conversations', sa.Column('project_id', sa.String(36), nullable=True))
    op.create_foreign_key('fk_conversations_project', 'conversations', 'agent_projects',
                          ['project_id'], ['id'], ondelete='SET NULL')
    op.create_index('idx_conversations_project', 'conversations', ['project_id'])
