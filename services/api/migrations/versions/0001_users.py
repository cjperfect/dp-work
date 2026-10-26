"""users 表（最终结构基线，ORM 风格，兼容 PostgreSQL）。

压缩自原 0001~0007 演进链：删除 display_name 与 legacy_id、
updated_at 等字段变更已直接体现在最终建表语句里。
演进历史保留在 migrations/archive/ 仅供审计。

Integer 自增主键、CURRENT_TIMESTAMP 默认值；
updated_at 由应用层维护（无数据库触发器）。
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_users"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), server_default=sa.text("'member'"), nullable=False),
        sa.Column("status", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
        sa.UniqueConstraint("username", name="users_username_key"),
    )


def downgrade() -> None:
    op.drop_table("users")
