from contextlib import asynccontextmanager, suppress
import asyncio

from fastapi import FastAPI

from app.infrastructure.database import session
from app.core import config
from app.modules.meetings.generation import worker
from app.modules.knowledge.parsing import worker as parse_worker
from app.modules.knowledge.rag import worker as vector_worker
from app.modules.users.bootstrap import ensure_initial_admin
from app.modules.connectors.service import shutdown as shutdown_connectors


@asynccontextmanager
async def lifespan(_: FastAPI):
    """管理服务启动和关闭。"""
    await session.init_db()
    tasks = []
    try:
        await ensure_initial_admin()
        if config.MINUTES_WORKER_ENABLED:
            tasks.append(asyncio.create_task(worker()))
        if config.DOCUMENT_PARSE_WORKER_ENABLED:
            tasks.append(asyncio.create_task(parse_worker()))
        if config.DOCUMENT_VECTOR_WORKER_ENABLED:
            tasks.append(asyncio.create_task(vector_worker()))
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        await shutdown_connectors()
        await session.close_db()
