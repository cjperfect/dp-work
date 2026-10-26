"""独立临时 PostgreSQL 库中验证迁移升级、一致性与降级。"""
import asyncio
import os
import subprocess
import sys
import sqlite3
import pytest
from pathlib import Path
from uuid import uuid4
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from app.infrastructure.database.model_registry import Base
from scripts.import_sqlite import import_database
from app.infrastructure.database.session import async_database_url

API_ROOT = Path(__file__).resolve().parents[2]


def test_postgres_migration_roundtrip(migrated_test_database, tmp_path):
    name = f"dp_migrations_{uuid4().hex}"
    url = async_database_url(migrated_test_database)
    target = url.set(database=name).render_as_string(hide_password=False)

    async def database_command(sql):
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
        try:
            async with engine.connect() as connection:
                await connection.execute(text(sql))
        finally:
            await engine.dispose()

    def alembic(*args):
        subprocess.run([sys.executable, "-m", "alembic", "-c", str(API_ROOT / "alembic.ini"), *args],
                       check=True, env={**os.environ, "DATABASE_URL": target}, capture_output=True)

    async def tables():
        engine = create_async_engine(target)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(lambda conn: set(inspect(conn).get_table_names()))
        finally:
            await engine.dispose()

    asyncio.run(database_command(f'CREATE DATABASE "{name}"'))
    try:
        alembic("upgrade", "head")
        assert Base.metadata.tables.keys() <= asyncio.run(tables())
        alembic("check")
        source = tmp_path / "old.db"
        with sqlite3.connect(source) as db:
            db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, department TEXT, role TEXT, status INTEGER, created_at TEXT, updated_at TEXT)")
            db.execute("INSERT INTO users VALUES (99, '迁移账号', 'existing-hash', 'product', 'member', 0, '2026-10-26 01:00:00', '2026-10-26 01:00:00')")
        counts = asyncio.run(import_database(source, target))
        assert counts["users"] == 1
        with pytest.raises(ValueError, match="非空"):
            asyncio.run(import_database(source, target))

        async def verify_import():
            engine = create_async_engine(target)
            try:
                async with engine.begin() as connection:
                    restored = (await connection.execute(text("SELECT username, password_hash, created_at FROM users WHERE id=99"))).one()
                    assert restored.username == "迁移账号" and restored.password_hash == "existing-hash"
                    assert restored.created_at.tzinfo is not None
                    next_id = await connection.scalar(text("INSERT INTO users (username, password_hash, department) VALUES ('next-user', 'hash', 'product') RETURNING id"))
                    assert next_id > 99
            finally:
                await engine.dispose()
        asyncio.run(verify_import())
        alembic("downgrade", "base")
        assert not (Base.metadata.tables.keys() & asyncio.run(tables()))
    finally:
        asyncio.run(database_command(f'DROP DATABASE "{name}" WITH (FORCE)'))
