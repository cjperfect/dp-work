from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infrastructure.database import session
from app.modules.users.bootstrap import ensure_initial_admin
from app.modules.connectors.service import shutdown as shutdown_connectors


@asynccontextmanager
async def lifespan(_: FastAPI):
    """管理服务启动和关闭。"""
    await session.init_db()
    try:
        await ensure_initial_admin()
        yield
    finally:
        await shutdown_connectors()
        await session.close_db()
