"""区分旧原文协作与会议纪要协作。"""
import sqlalchemy as sa
from alembic import op
revision = '0009_minutes_collaboration'
down_revision = '0008_meeting_records'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('meeting_records', sa.Column('kind', sa.String(16), nullable=False, server_default='original'))
    op.add_column('meeting_record_versions', sa.Column('kind', sa.String(16), nullable=False, server_default='original'))
    op.execute('UPDATE meeting_records SET share_token = NULL')
    op.add_column('meeting_segments', sa.Column('original_text', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('meeting_segments', 'original_text')
    op.drop_column('meeting_record_versions', 'kind')
    op.drop_column('meeting_records', 'kind')
