"""dp-work API 入口。"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .routes.segments import router as segments_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title="dp-work api", version="0.1.0")

# 本地开发：允许 web 前端（localhost:3000）与 sidecar 跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(segments_router)


@app.on_event("startup")
async def startup() -> None:
    await db.init_pool()


@app.on_event("shutdown")
async def shutdown() -> None:
    await db.close_pool()


@app.get("/health")
async def health() -> dict:
    try:
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"ok": True, "db": "up"}
    except Exception:  # noqa: BLE001
        return {"ok": False, "db": "down"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
