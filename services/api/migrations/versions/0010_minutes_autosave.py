"""区分协作增量持久化与纪要正文自动保存。"""
import sqlalchemy as sa
from alembic import op
revision = '0010_minutes_autosave'
down_revision = '0009_minutes_collaboration'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('meeting_records', sa.Column('saved_revision', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('meeting_records', sa.Column('saved_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.execute('UPDATE meeting_records SET saved_revision = revision, saved_at = updated_at')


def downgrade():
    op.drop_column('meeting_records', 'saved_at')
    op.drop_column('meeting_records', 'saved_revision')
