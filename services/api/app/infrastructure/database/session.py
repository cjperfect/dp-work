"""SQLAlchemy 异步会话；Service 决定事务边界，每次调用独立 Session。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import URL, event, make_url, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core import config

_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


def async_database_url(value: str) -> URL:
    """转换为异步数据库连接地址（SQLite）。"""
    url = make_url(value)
    if url.drivername not in ("sqlite", "sqlite+aiosqlite"):
        raise ValueError("DATABASE_URL 必须使用 SQLite（sqlite+aiosqlite:///）")
    return url.set(drivername="sqlite+aiosqlite")


async def init_db() -> None:
    """初始化数据库连接池。"""
    global _engine, _sessions
    if _engine is None:
        # SQLite：单文件、无连接池语义，需允许跨线程访问
        _engine = create_async_engine(
            async_database_url(config.DATABASE_URL),
            connect_args={"check_same_thread": False},
            hide_parameters=True,
        )
        event.listen(_engine.sync_engine, "connect", _enable_foreign_keys)
        _sessions = async_sessionmaker(_engine, expire_on_commit=False)


def _enable_foreign_keys(connection, _record) -> None:
    """为每个 SQLite 连接启用外键约束。"""
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


async def close_db() -> None:
    """关闭数据库连接池。"""
    global _engine, _sessions
    engine, _engine, _sessions = _engine, None, None
    if engine is not None:
        await engine.dispose()


def _session_factory() -> async_sessionmaker[AsyncSession]:
    """获取数据库会话工厂。"""
    if _sessions is None:
        raise RuntimeError("数据库尚未初始化")
    return _sessions


@asynccontextmanager
async def read_session() -> AsyncIterator[AsyncSession]:
    """提供数据库查询会话。"""
    async with _session_factory()() as db_session:
        yield db_session


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncSession]:
    """管理数据库事务。"""
    async with _session_factory().begin() as db_session:
        yield db_session


async def is_healthy() -> bool:
    """检查数据库连接。"""
    async with read_session() as db_session:
        return await db_session.scalar(text("SELECT 1")) == 1
