"""在独立临时 schema 中验证迁移，不触碰其他测试/应用表。

Squash 后迁移体系为单一最终结构基线 0001_users：
- 空库 upgrade head = 一键建出 users 表；
- 旧库（无 Alembic 版本、结构与最终一致）经基线核对后 stamp；
- 业务演进链（原 0002~0011）已归档到 migrations/archive/，不再参与执行。
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core import config
from app.infrastructure.database.baseline import adopt_existing_schema
from app.infrastructure.database.session import async_database_url

API_ROOT = Path(__file__).resolve().parents[2]
LEGACY_SQL = API_ROOT / "tests/fixtures/legacy_schema.sql"

FINAL_TABLES = {"users", "knowledge_bases"}


def migration_config(connection):
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.attributes["connection"] = connection
    return cfg


@asynccontextmanager
async def isolated_schema():
    name = "migration_test_" + uuid4().hex
    url = async_database_url(config.DATABASE_URL)
    admin_engine = create_async_engine(url, poolclass=NullPool)
    async with admin_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{name}"'))
    engine = create_async_engine(
        url, poolclass=NullPool, connect_args={"server_settings": {"search_path": name}}
    )
    try:
        async with engine.begin() as conn:
            yield conn
    finally:
        await engine.dispose()
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
        await admin_engine.dispose()


async def create_legacy_tables(conn):
    """按最终结构建"旧库"（无 Alembic 版本号），并插入一个 legacy 用户。"""
    script = "\n".join(
        line
        for line in LEGACY_SQL.read_text().splitlines()
        if not line.lstrip().startswith("--")
    )
    for statement in script.split(";"):
        if statement.strip():
            await conn.execute(text(statement))
    await conn.execute(
        text(
            "INSERT INTO users (username, password_hash, department) "
            "VALUES ('legacy', 'original-hash', 'product')"
        )
    )


def test_empty_database_upgrade_downgrade_and_metadata_match():
    async def case():
        async with isolated_schema() as conn:

            def exercise(connection):
                cfg = migration_config(connection)
                command.upgrade(cfg, "head")
                tables = set(inspect(connection).get_table_names())
                assert FINAL_TABLES.issubset(tables)
                row = connection.execute(
                    text("SELECT * FROM users LIMIT 0")
                ).keys()
                assert "display_name" not in row
                assert "updated_at" in row
                identity = connection.scalar(
                    text(
                        "SELECT identity_generation FROM information_schema.columns "
                        "WHERE table_schema=current_schema() AND table_name='users' "
                        "AND column_name='id'"
                    )
                )
                assert identity == "ALWAYS"
                command.check(cfg)
                command.downgrade(cfg, "base")
                assert "users" not in inspect(connection).get_table_names()
                command.upgrade(cfg, "head")
                command.check(cfg)

            await conn.run_sync(exercise)

    asyncio.run(case())


def test_adopt_legacy_schema_preserves_existing_records():
    async def case():
        async with isolated_schema() as conn:
            await create_legacy_tables(conn)
            await conn.run_sync(adopt_existing_schema)
            assert (
                await conn.scalar(
                    text("SELECT password_hash FROM users WHERE username = 'legacy'")
                )
                == "original-hash"
            )
            assert (
                await conn.scalar(text("SELECT version_num FROM alembic_version"))
                == "0001_users"
            )
            await conn.run_sync(
                lambda connection: command.upgrade(migration_config(connection), "head")
            )
            row = (
                await conn.execute(
                    text("SELECT id, password_hash FROM users WHERE username='legacy'")
                )
            ).one()
            assert isinstance(row.id, int)
            assert row.password_hash == "original-hash"
            await conn.run_sync(
                lambda connection: command.check(migration_config(connection))
            )

    asyncio.run(case())


def test_schema_drift_prevents_baseline_stamp():
    async def case():
        async with isolated_schema() as conn:
            await create_legacy_tables(conn)
            await conn.execute(text("ALTER TABLE users ADD COLUMN unexpected text"))
            with pytest.raises(RuntimeError, match="不一致"):
                await conn.run_sync(adopt_existing_schema)
            assert not await conn.run_sync(
                lambda connection: inspect(connection).has_table("alembic_version")
            )
            assert (
                await conn.scalar(
                    text("SELECT password_hash FROM users WHERE username = 'legacy'")
                )
                == "original-hash"
            )

    asyncio.run(case())
