from contextlib import asynccontextmanager, suppress
import asyncio

from fastapi import FastAPI

from app.infrastructure.database import session
from app.core import config
from app.modules.meetings.generation import worker
from app.modules.users.bootstrap import ensure_initial_admin
from app.modules.connectors.service import shutdown as shutdown_connectors


@asynccontextmanager
async def lifespan(_: FastAPI):
    """管理服务启动和关闭。"""
    await session.init_db()
    task = None
    try:
        await ensure_initial_admin()
        if config.MINUTES_WORKER_ENABLED:
            task = asyncio.create_task(worker())
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await shutdown_connectors()
        await session.close_db()
