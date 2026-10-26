"""个人模型与语音服务设置。"""
import sqlalchemy as sa
from alembic import op
revision = "0013_user_settings"
down_revision = "0012_parsed_document_edits"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("user_settings",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("model_config", sa.JSON(), nullable=False),
        sa.Column("asr_config", sa.JSON(), nullable=False),
        sa.Column("model_key", sa.Text(), nullable=True),
        sa.Column("asr_key", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade():
    op.drop_table("user_settings")
