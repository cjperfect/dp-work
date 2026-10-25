"""核对旧 SQL 初始化的表结构后，登记 Alembic 初始版本，不重建业务表。"""

import asyncio
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core import config

from .legacy_schema import legacy_schema_metadata
from .session import async_database_url

BASELINE_REVISION = "0001_users"


def adopt_existing_schema(connection: Connection) -> None:
    """核对旧库结构并登记迁移基线。"""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    metadata = legacy_schema_metadata()
    managed_tables = set(metadata.tables)
    if "alembic_version" in tables:
        raise RuntimeError(
            "数据库已有 Alembic 版本，请使用 alembic current / upgrade head"
        )
    if not managed_tables.issubset(tables):
        raise RuntimeError(
            "缺少业务表；空库请使用 alembic upgrade head，部分建表需先核对"
        )

    def include_name(name, type_, parent_names):
        """筛选需要核对的表。"""
        return type_ != "table" or name in managed_tables

    migration_context = MigrationContext.configure(
        connection,
        opts={
            "compare_type": True,
            "compare_server_default": True,
            "include_name": include_name,
        },
    )
    differences = compare_metadata(migration_context, metadata)
    if differences:
        raise RuntimeError(
            f"现有表结构与 ORM 基线不一致，不能登记版本：{differences!r}"
        )
    alembic_config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    alembic_config.attributes["connection"] = connection
    command.stamp(alembic_config, BASELINE_REVISION)


async def adopt() -> None:
    """执行旧库基线登记。"""
    engine = create_async_engine(
        async_database_url(config.DATABASE_URL),
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(adopt_existing_schema)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(adopt())
    print("旧库表结构核对通过，已登记 0001_users；请继续执行 alembic upgrade head。")
