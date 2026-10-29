from contextlib import asynccontextmanager, suppress
import asyncio

from fastapi import FastAPI

from src.infrastructure.database import session
from src.core import config
from src.modules.knowledge.search_index import maintenance as search_maintenance
from src.task_dispatcher import worker as dispatch_worker
from src.modules.users.bootstrap import ensure_initial_admin
from src.infrastructure.sidecar.relay import maintenance as device_maintenance


@asynccontextmanager
async def lifespan(_: FastAPI):
    """管理服务启动和关闭。"""
    await session.init_db()
    tasks = []
    try:
        await ensure_initial_admin()
        tasks.append(asyncio.create_task(device_maintenance()))
        if config.MQ_DISPATCH_ENABLED:
            tasks.append(asyncio.create_task(dispatch_worker()))
        if config.ELASTICSEARCH_ENABLED:
            tasks.append(asyncio.create_task(search_maintenance()))
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        await session.close_db()
