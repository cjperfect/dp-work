from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infrastructure.database import session
from app.modules.users.bootstrap import ensure_initial_admin


@asynccontextmanager
async def lifespan(_: FastAPI):
    await session.init_db()
    try:
        await ensure_initial_admin()
        yield
    finally:
        await session.close_db()
