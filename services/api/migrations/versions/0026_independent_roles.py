"""将部门负责人继承的权限固化为独立授权，保留原有有效权限。"""
from alembic import op

revision = '0026_independent_roles'
down_revision = '0025_rbac_policies'
branch_labels = depends_on = None


def upgrade():
    op.execute('SELECT pg_advisory_xact_lock(24702501)')
    op.execute("""INSERT INTO role_permissions (role, permission)
        SELECT 'manager', permission FROM role_permissions WHERE role = 'member'
        ON CONFLICT (role, permission) DO NOTHING""")


def downgrade():
    # 无法区分历史继承与后续人工授权，回退不删除已有授权数据。
    pass
