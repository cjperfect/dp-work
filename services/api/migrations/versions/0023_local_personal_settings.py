"""个人模型及 ASR 配置迁入设备，移除云端设置表。"""
import importlib.util
from pathlib import Path
from alembic import op
revision = '0023_local_personal_settings'
down_revision = '0022_local_agent_history'
branch_labels = depends_on = None


def upgrade():
    op.drop_table('user_settings')


def downgrade():
    """只恢复表结构，配置需从备份恢复。"""
    spec = importlib.util.spec_from_file_location('old_settings', Path(__file__).with_name('0013_user_settings.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.upgrade()
