"""SQLite 迁移冒烟：空库 upgrade head 建表 → 与模型 metadata 一致 → downgrade 清库。"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.infrastructure.database.model_registry import Base

API_ROOT = Path(__file__).resolve().parents[2]


def _alembic(db_path: Path, *args: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(API_ROOT / "alembic.ini"),
            *args,
        ],
        check=True,
        env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
    )


@pytest.fixture(scope="module", autouse=True)
def migrated_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("migrations") / "smoke.db"
    _alembic(db_path, "upgrade", "head")
    return db_path


def _table_names(db_path: Path) -> set[str]:
    async def _collect() -> set[str]:
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(
                    lambda c: set(inspect(c).get_table_names())
                )
        finally:
            await engine.dispose()

    return asyncio.run(_collect())


def test_upgrade_creates_all_model_tables(migrated_db):
    tables = _table_names(migrated_db)
    assert "alembic_version" in tables
    assert Base.metadata.tables.keys() <= tables


def test_downgrade_to_base_drops_all_business_tables(migrated_db):
    _alembic(migrated_db, "downgrade", "base")
    tables = _table_names(migrated_db)
    assert "users" not in tables
    assert "knowledge_bases" not in tables
