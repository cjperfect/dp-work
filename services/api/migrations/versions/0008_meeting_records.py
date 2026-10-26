"""会议原文协作与历史版本。"""
import sqlalchemy as sa
from alembic import op
revision = '0008_meeting_records'
down_revision = '0007_minutes_generation'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('meeting_records',
        sa.Column('meeting_id', sa.String(128), sa.ForeignKey('meetings.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('state', sa.LargeBinary(), nullable=False),
        sa.Column('epoch', sa.String(36), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('share_token', sa.String(64), unique=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table('meeting_record_versions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('meeting_id', sa.String(128), sa.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('state', sa.LargeBinary(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('idx_meeting_record_versions_meeting_id', 'meeting_record_versions', ['meeting_id'])


def downgrade():
    op.drop_table('meeting_record_versions')
    op.drop_table('meeting_records')
