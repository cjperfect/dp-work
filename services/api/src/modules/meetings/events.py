"""会议生成状态的登录用户订阅。"""
import asyncio
import json
import time
from contextlib import suppress
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.core import config
from src.core.security import decode_token
from src.infrastructure.database.notifications import listen
from src.modules.users import service as users_service
from . import service

router = APIRouter()


@router.websocket("/events")
async def meeting_events(websocket: WebSocket):
    """先验证首帧 JWT，再发送本人的会议状态。"""
    origin = websocket.headers.get("origin")
    if origin and origin not in config.CORS_ORIGINS:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    reader = None
    pending = None
    try:
        async with asyncio.timeout(5):
            message = await websocket.receive_text()
            if len(message) > 8192:
                raise ValueError("invalid auth")
            auth = json.loads(message)
            if not isinstance(auth, dict) or not isinstance(auth.get("token"), str):
                raise ValueError("invalid auth")
            payload = decode_token(auth["token"])
            if not payload:
                raise ValueError("invalid auth")
            user = await users_service.find_by_subject(payload.get("sub"), payload.get("uidv"))
            if user is None or not user.is_active:
                raise ValueError("invalid auth")
        async with listen("meeting_generation") as queue:
            # 先订阅后读快照，覆盖任务在建立连接前已完成的情况。
            meetings = await service.list_meetings(user.id)
            await websocket.send_json({"type": "meetings.snapshot", "meetings": [row.model_dump(mode="json") for row in meetings]})
            reader = asyncio.create_task(websocket.receive_text())
            while True:
                if payload.get("exp", 0) <= time.time():
                    await websocket.close(code=4401)
                    break
                pending = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait((reader, pending), timeout=20, return_when=asyncio.FIRST_COMPLETED)
                if reader in done:
                    reader.result()
                    break
                if pending in done:
                    event = json.loads(pending.result())
                    pending = None
                    if event.get("owner_id") != user.id:
                        continue
                    # 更新只含列表元数据，正文由详情页按需读取。
                    meetings = await service.list_meetings(user.id)
                    row = next((row for row in meetings if row.id == event.get("meeting_id")), None)
                    if row:
                        await websocket.send_json({"type": "meeting.updated", "meeting": row.model_dump(mode="json")})
                    else:
                        await websocket.send_json({"type": "meeting.removed", "meeting_id": event["meeting_id"]})
                else:
                    pending.cancel()
                    with suppress(asyncio.CancelledError):
                        await pending
                    pending = None
                    await websocket.send_json({"type": "ping"})
    except (ValueError, TypeError, TimeoutError):
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=4401)
    except WebSocketDisconnect:
        pass
    except Exception:
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=1011)
    finally:
        for task in (reader, pending):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect):
                    await task

        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close()
