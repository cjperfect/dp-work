"""异步 Alembic 环境，亦支持传入现有同步 Connection。"""

import asyncio

from alembic import context
from src.core import config as app_config
from src.infrastructure.database.model_registry import Base
from src.infrastructure.database.session import async_database_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

config = context.config


def configure_connection(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async():
    engine = create_async_engine(
        async_database_url(app_config.DATABASE_URL),
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(configure_connection)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=async_database_url(app_config.DATABASE_URL).render_as_string(
            hide_password=False
        ),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    configure_connection(config.attributes["connection"])
else:
    asyncio.run(run_async())
