"""Sidecar 应用入口。"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import PORT, VOLC_API_KEY
from .meetings.repository import init_db
from .transport.websocket import router


@asynccontextmanager
async def lifespan(app):
    """初始化本地存储并管理转写任务生命周期。"""
    await asyncio.to_thread(init_db)
    app.state.asr_meetings = {}
    yield
    for session in list(app.state.asr_meetings.values()):
        await session.close()
    app.state.asr_meetings.clear()


app = FastAPI(title="dp-work sidecar", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:[0-9]+)?",
    allow_methods=["GET"], allow_headers=[])
app.include_router(router)


@app.get("/health")
async def health():
    """查询语音服务模式和凭证配置状态。"""
    return {"ok": True, "configured": bool(VOLC_API_KEY), "cloudSyncEnabled": False}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)
