"""users 表（最终结构基线，ORM 风格）。

压缩自原 0001~0007 演进链：主键升级为 bigint identity、删除 display_name
与 legacy_id、updated_at 触发器等字段变更已直接体现在最终建表语句里。
演进历史保留在 migrations/archive/ 仅供审计。
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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="users_pkey"),
        sa.UniqueConstraint("username", name="users_username_key"),
    )
    # updated_at 触发器函数与触发器（触发器不属于 ORM 表结构，用数据库对象创建）
    op.execute(
        """
        CREATE FUNCTION update_users_timestamp() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
            BEGIN
                NEW.updated_at := clock_timestamp();
                RETURN NEW;
            END;
            $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users
        FOR EACH ROW WHEN ((old.* IS DISTINCT FROM new.*))
        EXECUTE FUNCTION update_users_timestamp();
        """
    )


def downgrade() -> None:
    op.drop_table("users")
    op.execute("DROP FUNCTION IF EXISTS update_users_timestamp()")
