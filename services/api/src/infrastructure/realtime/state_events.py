"""带首帧鉴权、权限校验和心跳的业务状态订阅。"""
import asyncio
import json
import time
from contextlib import suppress
from collections.abc import Awaitable, Callable
from fastapi import WebSocket, WebSocketDisconnect
from src.core import config
from src.core.exceptions import ApiError
from src.core.security import decode_token
from src.infrastructure.database.notifications import listen
from src.modules.users import service as users_service
from src.modules.access.service import authorize_id


async def state_events(
    websocket: WebSocket, *, permission: str, channel: str,
    snapshot: Callable[[int], Awaitable[dict]],
    update: Callable[[int, dict], Awaitable[list[dict]]],
):
    """共享状态订阅生命周期；业务模块只负责快照和增量消息。"""
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
        await authorize_id(user.id, permission)
        async with listen(channel) as queue:
            # 先订阅后读快照，避免建连期间漏掉完成事件。
            await websocket.send_json(await snapshot(user.id))
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
                    await authorize_id(user.id, permission)
                    event = json.loads(pending.result())
                    pending = None
                    if event.get("owner_id") != user.id:
                        continue
                    for message in await update(user.id, event):
                        await websocket.send_json(message)
                else:
                    pending.cancel()
                    with suppress(asyncio.CancelledError):
                        await pending
                    pending = None
                    await websocket.send_json({"type": "ping"})
    except (ValueError, TypeError, TimeoutError):
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=4401)
    except ApiError:
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=4403)
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
