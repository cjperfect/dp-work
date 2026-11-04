"""PyCasbin 权限策略和管理员变更审计。"""
from alembic import op
import sqlalchemy as sa

revision = '0025_rbac_policies'
down_revision = '0024_local_agent_projects'
branch_labels = depends_on = None


def upgrade():
    policy = op.create_table('role_permissions',
        sa.Column('role', sa.String(32), primary_key=True),
        sa.Column('permission', sa.String(64), primary_key=True))
    op.create_table('access_audits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(32), nullable=False),
        sa.Column('target', sa.String(128), nullable=False),
        sa.Column('before', sa.JSON(), nullable=False),
        sa.Column('after', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.bulk_insert(policy, [{'role': 'admin', 'permission': 'knowledge:read'}, {'role': 'admin', 'permission': 'knowledge:write'}, {'role': 'admin', 'permission': 'knowledge:delete'}, {'role': 'admin', 'permission': 'knowledge:search'}, {'role': 'admin', 'permission': 'meeting:read'}, {'role': 'admin', 'permission': 'meeting:write'}, {'role': 'admin', 'permission': 'meeting:delete'}, {'role': 'admin', 'permission': 'meeting:generate'}, {'role': 'admin', 'permission': 'meeting:edit'}, {'role': 'admin', 'permission': 'meeting:share'}, {'role': 'admin', 'permission': 'meeting:restore'}, {'role': 'admin', 'permission': 'meeting:archive'}, {'role': 'admin', 'permission': 'device:connect'}, {'role': 'admin', 'permission': 'access:manage'}, {'role': 'member', 'permission': 'knowledge:read'}, {'role': 'member', 'permission': 'knowledge:write'}, {'role': 'member', 'permission': 'knowledge:delete'}, {'role': 'member', 'permission': 'knowledge:search'}, {'role': 'member', 'permission': 'meeting:read'}, {'role': 'member', 'permission': 'meeting:write'}, {'role': 'member', 'permission': 'meeting:delete'}, {'role': 'member', 'permission': 'meeting:generate'}, {'role': 'member', 'permission': 'meeting:edit'}, {'role': 'member', 'permission': 'meeting:share'}, {'role': 'member', 'permission': 'meeting:restore'}, {'role': 'member', 'permission': 'meeting:archive'}, {'role': 'member', 'permission': 'device:connect'}, {'role': 'viewer', 'permission': 'knowledge:read'}, {'role': 'viewer', 'permission': 'knowledge:search'}, {'role': 'viewer', 'permission': 'meeting:read'}, {'role': 'viewer', 'permission': 'device:connect'}])


def downgrade():
    op.drop_table('access_audits')
    op.drop_table('role_permissions')
