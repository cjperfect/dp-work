"""Sidecar 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import PORT, VOLC_API_KEY
from .transport.websocket import router
from .transport.internal import router as internal_router


@asynccontextmanager
async def lifespan(app):
    """管理转写任务生命周期。"""
    app.state.asr_meetings = {}
    app.state.asr_tickets = {}
    yield
    for session in list(app.state.asr_meetings.values()):
        await session.close()
    app.state.asr_meetings.clear()
    app.state.asr_tickets.clear()


app = FastAPI(title="dp-work sidecar", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:[0-9]+)?",
    allow_methods=["GET"], allow_headers=[])
app.include_router(router)
app.include_router(internal_router)


@app.get("/health")
async def health():
    """查询语音服务模式和凭证配置状态。"""
    return {"ok": True, "configured": bool(VOLC_API_KEY)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)
