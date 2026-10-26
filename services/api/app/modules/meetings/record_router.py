"""会议纪要协作、分享和版本接口。"""
import asyncio
import base64
import json
import time
from contextlib import suppress
from typing import Annotated
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from app.core import config
from app.core.exceptions import ApiError
from app.core.responses import ok
from app.core.security import decode_token
from app.infrastructure.database.notifications import listen
from app.modules.auth.dependencies import get_current_user
from app.modules.users import service as users_service
from app.modules.users.models import User
from . import records

router = APIRouter()
CurrentUser = Annotated[User, Depends(get_current_user)]


class VersionCreate(BaseModel):
    label: str = Field(default='手动版本', max_length=100)


class VersionRestore(BaseModel):
    expected_revision: int = Field(ge=1)


@router.get('/shared/records/{token}')
async def resolve(token: str, user: CurrentUser):
    """读取登录用户持链接访问的纪要。"""
    return ok(await records.resolve_share(token, user.id))


@router.get('/{meeting_id}/record')
async def document(meeting_id: str, user: CurrentUser, share_token: str | None = None):
    """读取会议协作纪要。"""
    return ok(await records.get_document(meeting_id, user.id, share_token))


@router.post('/{meeting_id}/record/share')
async def share(meeting_id: str, user: CurrentUser):
    """创建或获取协作分享链接。"""
    return ok(await records.share_document(meeting_id, user.id))


@router.get('/{meeting_id}/record/versions')
async def versions(meeting_id: str, user: CurrentUser, share_token: str | None = None):
    """查询最近一百个历史版本。"""
    return ok(await records.list_versions(meeting_id, user.id, share_token))


@router.post('/{meeting_id}/record/versions')
async def checkpoint(meeting_id: str, body: VersionCreate, user: CurrentUser):
    """手动保存命名版本。"""
    await records.checkpoint(meeting_id, user.id, body.label)
    return ok()


@router.get('/{meeting_id}/record/versions/{version_id}')
async def version(meeting_id: str, version_id: str, user: CurrentUser, share_token: str | None = None):
    """预览历史版本。"""
    return ok(await records.version_state(meeting_id, user.id, version_id, share_token))


@router.post('/{meeting_id}/record/versions/{version_id}/restore')
async def restore(meeting_id: str, version_id: str, body: VersionRestore, user: CurrentUser):
    """创建者恢复历史版本。"""
    return ok(await records.restore(meeting_id, user.id, version_id, body.expected_revision))


@router.websocket('/{meeting_id}/record/events')
async def events(websocket: WebSocket, meeting_id: str):
    """鉴权后双向同步 CRDT 增量，入库后确认接收。"""
    origin = websocket.headers.get('origin')
    if origin and origin not in config.CORS_ORIGINS:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    reader = pending = None
    user = None
    share = None
    try:
        async with asyncio.timeout(5):
            auth = await websocket.receive_json()
            payload = decode_token(auth.get('token', ''))
            if not payload:
                raise ValueError('invalid auth')
            user = await users_service.find_by_subject(payload.get('sub'), payload.get('uidv'))
            if user is None or not user.is_active:
                raise ValueError('invalid auth')
        share = auth.get('share_token')
        async with listen('meeting_record') as queue:
            await websocket.send_json({'type': 'state', **await records.get_document(meeting_id, user.id, share)})
            reader = asyncio.create_task(websocket.receive_text())
            while payload.get('exp', 0) > time.time():
                if pending is None:
                    pending = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait((reader, pending), timeout=20, return_when=asyncio.FIRST_COMPLETED)
                if reader in done:
                    raw = reader.result()
                    if len(raw) > 6 * 1024 * 1024:
                        raise ValueError('message too large')
                    message = json.loads(raw)
                    if message.get('type') == 'awareness':
                        if len(message.get('update', '')) <= 4096:
                            from app.infrastructure.database import session
                            from sqlalchemy import text
                            async with session.transaction() as db:
                                await records.access(db, meeting_id, user.id, share)
                                await db.execute(text("SELECT pg_notify('meeting_record', :payload)"), {'payload': json.dumps({'id': meeting_id, 'awareness': message['update']})})
                        reader = asyncio.create_task(websocket.receive_text())
                    elif message.get('type') == 'save':
                        try:
                            state = await records.save_document(meeting_id, user.id, message.get('epoch'), share)
                            await websocket.send_json({'type': 'saved', 'save_seq': message.get('save_seq'), **state})
                        except ApiError as cause:
                            await websocket.send_json({'type': 'save.error', 'message': cause.message})
                        except Exception:
                            await websocket.send_json({'type': 'save.error', 'message': '自动保存失败，请稍后重试。'})
                        reader = asyncio.create_task(websocket.receive_text())
                    else:
                        try:
                            update = base64.b64decode(message['update'], validate=True)
                            state = await records.update_document(meeting_id, user.id, message['epoch'], update, share)
                            await websocket.send_json({'type': 'ack', 'seq': message['seq'], **state})
                        except ApiError as cause:
                            await websocket.send_json({'type': 'error', 'message': cause.message})
                        reader = asyncio.create_task(websocket.receive_text())
                if pending in done:
                    event = json.loads(pending.result())
                    if event.get('id') == meeting_id:
                        if 'awareness' in event:
                            await websocket.send_json({'type': 'awareness', 'update': event['awareness']})
                        else:
                            await websocket.send_json({'type': 'state', **await records.get_document(meeting_id, user.id, share)})
                    pending = None
                if not done:
                    await websocket.send_json({'type': 'ping'})
            await websocket.close(code=4401)
    except (WebSocketDisconnect, RuntimeError):
        pass
    except ApiError as cause:
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.send_json({'type': 'error', 'message': cause.message})
            await websocket.close(code=4403)
    except (ValueError, TypeError):
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=4401)
    except Exception:
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=1011)
    finally:
        if user is not None:
            with suppress(Exception):
                await records.save_document(meeting_id, user.id, share=share)
        for task in (reader, pending):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await task


class ArchiveMinutes(BaseModel):
    knowledge_base_id: int = Field(ge=1)


@router.post('/{meeting_id}/minutes/archive')
async def archive(meeting_id: str, body: ArchiveMinutes, user: CurrentUser):
    """将最新纪要原子归档到知识库。"""
    return ok(await records.archive_minutes(meeting_id, user.id, body.knowledge_base_id))
