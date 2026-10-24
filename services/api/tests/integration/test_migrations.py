"""在独立临时 schema 中验证迁移，不触碰其他测试/应用表。"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.core import config
from app.infrastructure.database.baseline import adopt_existing_schema
from app.infrastructure.database.session import async_database_url
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

API_ROOT = Path(__file__).resolve().parents[2]
LEGACY_SQL = API_ROOT.parents[1] / "infra/postgres/init/01-init.sql"


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
            "INSERT INTO users (id, username, password_hash, display_name, department) VALUES ('legacy-id', 'legacy', 'original-hash', 'Original', 'product')"
        )
    )


def test_empty_database_upgrade_downgrade_and_metadata_match():
    async def case():
        async with isolated_schema() as conn:

            def exercise(connection):
                cfg = migration_config(connection)
                command.upgrade(cfg, "head")
                assert {"users", "minutes", "transcript_segments"}.issubset(
                    inspect(connection).get_table_names()
                )
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
                == "0001_initial"
            )
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
