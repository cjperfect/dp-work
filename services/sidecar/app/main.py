"""Sidecar 入口：WebSocket JSON-RPC（前端转写通道）+ 后台批量上行循环。

当前阶段：
- /ws 已可连接、收发 JSON 消息（asr.start / audio / asr.stop 协议已定义）
- SQLite 实时保存与定时上行循环已实现（同步队列可直接跑）
- 模拟 ASR 分句流默认开启（MOCK_ASR=1），用于打通 Web ⇄ Sidecar 消息链路
- 豆包 ASR 实际流接入：安装 volcengine SDK 后在 app/asr.py 接入（见 README），
  接入后设 MOCK_ASR=0 切真实流
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from . import asr as asr_mod
from . import mock as mock_mod
from . import store, sync
from .config import MOCK_ASR, PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("sidecar")

app = FastAPI(title="dp-work sidecar", version="0.1.0")

# 活跃会议（sync_loop 遍历的集合）
_active_meetings: set[str] = set()
# 每个 ws 连接的 ASR mock 任务（asr.stop / 断开时取消）
_ws_tasks: dict[WebSocket, asyncio.Task | None] = {}


@app.on_event("startup")
async def startup() -> None:
    store.init_db()
    asyncio.create_task(sync.sync_loop(lambda: list(_active_meetings)))


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "sdk": asr_mod.sdk_available(), "mock_asr": _mock_enabled()}


def _mock_enabled() -> bool:
    return MOCK_ASR


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    meeting_id: str | None = None
    task: asyncio.Task | None = None
    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")
            if mtype == "asr.start":
                # 兼容 camelCase（TS contracts）与 snake_case（Python 文档示例）
                meeting_id = msg.get("meeting_id") or msg.get("meetingId")
                _active_meetings.add(meeting_id)
                await websocket.send_json({"type": "ready", "meeting_id": meeting_id})
                if _mock_enabled():
                    task = asyncio.create_task(
                        mock_mod.mock_asr(websocket, meeting_id, asyncio.Event(), 0)
                    )
                    _ws_tasks[websocket] = task
            elif mtype == "audio":
                # 音频块 → 真实 ASR 流（app/asr.py 接入后此处调用；mock 模式忽略）
                if not _mock_enabled():
                    await asr_mod.ingest_audio_chunk(
                        meeting_id, msg.get("payload", "").encode(), None, {}
                    )
                await websocket.send_json({"type": "audio.ack", "bytes": len(msg.get("payload", ""))})
            elif mtype == "asr.stop":
                if meeting_id is None:
                    meeting_id = msg.get("meeting_id") or msg.get("meetingId")
                if meeting_id:
                    await sync.flush(meeting_id)
                    _active_meetings.discard(meeting_id)
                if task:
                    task.cancel()
                    _ws_tasks.pop(websocket, None)
                await websocket.send_json({"type": "stopped", "meeting_id": meeting_id})
    except WebSocketDisconnect:
        log.info("ws 断开 meeting=%s", meeting_id)
    except asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001
        log.exception("ws 异常")
    finally:
        if task:
            task.cancel()
        _ws_tasks.pop(websocket, None)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
