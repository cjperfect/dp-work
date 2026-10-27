"""用户设备反向执行通道。"""
import sqlalchemy as sa
from alembic import op
revision='0019_device_bridge'
down_revision='0018_agent_runs'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('devices',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('session_id',sa.String(36),nullable=False),sa.Column('lease_until',sa.DateTime(timezone=True),nullable=False))
    op.create_index('idx_devices_owner_id','devices',['owner_id'])
    op.create_table('device_calls',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('device_id',sa.String(36),sa.ForeignKey('devices.id',ondelete='CASCADE'),nullable=False),
        sa.Column('session_id',sa.String(36),nullable=False),sa.Column('method',sa.String(8),nullable=False),
        sa.Column('path',sa.String(256),nullable=False),sa.Column('query',sa.String(2000),nullable=False),
        sa.Column('content_type',sa.String(128),nullable=False),sa.Column('encrypted_input',sa.LargeBinary(),nullable=False),
        sa.Column('state',sa.String(16),nullable=False,server_default='queued'),
        sa.Column('status_code',sa.Integer(),nullable=True),sa.Column('response_type',sa.String(128),nullable=True),
        sa.Column('next_seq',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('response_bytes',sa.Integer(),nullable=False,server_default='0'),sa.Column('error',sa.Text(),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('deadline_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('idx_device_calls_session_state','device_calls',['session_id','state'])
    op.create_table('device_call_chunks',sa.Column('call_id',sa.String(36),sa.ForeignKey('device_calls.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('seq',sa.Integer(),primary_key=True),sa.Column('data',sa.LargeBinary(),nullable=False))
    op.add_column('task_outbox',sa.Column('device_id',sa.String(36),nullable=True))
    op.add_column('agent_runs',sa.Column('device_id',sa.String(36),nullable=True))


def downgrade():
    op.drop_column('agent_runs','device_id');op.drop_column('task_outbox','device_id')
    op.drop_table('device_call_chunks');op.drop_table('device_calls');op.drop_table('devices')
