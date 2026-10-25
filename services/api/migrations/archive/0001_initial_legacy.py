"""现有 users / minutes / transcript_segments 表的初始基线。"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column(
            "role", sa.Text(), server_default=sa.text("'member'"), nullable=False
        ),
        sa.Column(
            "status", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
        sa.UniqueConstraint("username", name="users_username_key"),
    )
    op.create_table(
        "minutes",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("meeting_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "status", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="minutes_pkey"),
        sa.UniqueConstraint("meeting_id", name="minutes_meeting_id_key"),
    )
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("meeting_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="transcript_segments_pkey"),
        sa.UniqueConstraint(
            "meeting_id", "seq", name="transcript_segments_meeting_id_seq_key"
        ),
    )
    op.create_index(
        "idx_transcript_segments_meeting", "transcript_segments", ["meeting_id", "seq"]
    )


def downgrade() -> None:
    op.drop_index("idx_transcript_segments_meeting", table_name="transcript_segments")
    op.drop_table("transcript_segments")
    op.drop_table("minutes")
    op.drop_table("users")
    # vector 扩展可能被其他业务使用，不在回滚中删除。
