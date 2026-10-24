"""PostgreSQL 连接池（asyncpg）。DSN 默认对齐根目录 docker-compose.yml。"""
from __future__ import annotations

import os

import asyncpg

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://dp:dp_dev_password@localhost:5432/dp_work",
)

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)


async def get_pool() -> asyncpg.Pool:
    assert _pool is not None, "db pool 未初始化"
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
