"""项目名称、目录及设备关联已迁入本机。"""
import sqlalchemy as sa
from alembic import op
revision = '0024_local_agent_projects'
down_revision = '0023_local_personal_settings'
branch_labels = depends_on = None


def upgrade():
    op.drop_table('agent_projects')


def downgrade():
    """只恢复旧项目表结构，数据需要从备份恢复。"""
    op.create_table('agent_projects',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('device_id',sa.String(36),nullable=False),
        sa.Column('name',sa.String(256),nullable=False),
        sa.Column('path',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index('idx_agent_projects_owner_updated','agent_projects',['owner_id','updated_at'])
