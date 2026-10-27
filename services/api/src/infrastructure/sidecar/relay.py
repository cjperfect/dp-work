"""通过 PG 持久化跨 API / Worker 进程的设备 RPC。"""
import asyncio
import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from cryptography.fernet import Fernet
from sqlalchemy import delete, func, select, text, update
from src.core import config
from src.infrastructure.database import session
from src.modules.devices.models import Device, DeviceCall, DeviceChunk
from .context import scope

log=logging.getLogger(__name__)

from .requests import ROUTES



class DeviceOffline(Exception):
    """设备离线，后台任务应保留并稍后重试。"""


def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256((config.JWT_SECRET + ':device-rpc-v1').encode()).digest()))


async def notify(db, channel, value):
    await db.execute(text('SELECT pg_notify(:channel, :payload)'), {'channel': channel, 'payload': json.dumps(value)})


async def online_device(owner, target=None):
    async with session.read_session() as db:
        rows = list((await db.scalars(select(Device).where(Device.owner_id == owner, Device.lease_until > func.now(),
            *([Device.id == target] if target else [])))).all())
    if len(rows) != 1:
        raise DeviceOffline('执行设备未连接，或存在多个设备，请从桌面端发起操作。')
    return rows[0]


async def create_call(request, timeout):
    owner, target = scope.get()
    if owner is None: raise DeviceOffline('缺少执行任务的用户身份。')
    if (request.method, request.url.path) not in ROUTES:
        raise ValueError('不支持的本地执行接口。')
    data = await request.aread()
    if len(data) > 21 * 1024 * 1024: raise ValueError('执行输入过大。')
    device = await online_device(owner, target)
    key = str(uuid4())
    async with session.transaction() as db:
        db.add(DeviceCall(id=key, owner_id=owner, device_id=device.id, session_id=device.session_id,
            method=request.method, path=request.url.path, query=request.url.query.decode(),
            content_type=request.headers.get('content-type','application/octet-stream'),
            encrypted_input=cipher().encrypt(data), state='queued',
            deadline_at=datetime.now(timezone.utc) + timedelta(seconds=timeout)))
        await notify(db, 'device_requests', {'session_id':device.session_id})
    return key


async def snapshot(key, seq=None):
    async with session.read_session() as db:
        row = await db.get(DeviceCall, key)
        if row and row.state in ('queued','running'):
            device=await db.get(Device,row.device_id)
            if not device or device.session_id!=row.session_id or device.lease_until<=datetime.now(timezone.utc):
                raise DeviceOffline('执行设备已经离线。')
        chunks = [] if seq is None else list((await db.scalars(select(DeviceChunk).where(
            DeviceChunk.call_id == key, DeviceChunk.seq >= seq).order_by(DeviceChunk.seq).limit(64))).all())
        return row, chunks


async def cancel(key):
    async with session.transaction() as db:
        row = await db.get(DeviceCall, key, with_for_update=True)
        if row:
            if row.state in ('queued','running'):
                row.state='cancelled'
                await notify(db,'device_requests',{'session_id':row.session_id})
            row.encrypted_input=b''
            await db.execute(delete(DeviceChunk).where(DeviceChunk.call_id == key))


async def wait_signal(queue, key, deadline):
    remaining=(deadline-datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0: raise DeviceOffline('本地执行超时，请重试。')
    try:
        while True:
            value=json.loads(await asyncio.wait_for(queue.get(),timeout=min(2,remaining)))
            if value.get('call_id') == key: return
            remaining=(deadline-datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0: raise DeviceOffline('本地执行超时，请重试。')
    except TimeoutError:
        return


async def maintenance():
    while True:
        try:
            async with session.transaction() as db:
                expired=list((await db.scalars(select(DeviceCall).where(DeviceCall.state.in_(['queued','running']),
                    DeviceCall.deadline_at <= func.now()).with_for_update(skip_locked=True).limit(100))).all())
                for row in expired:
                    row.state='failed';row.error='本地执行超时。';row.encrypted_input=b''
                    await notify(db,'device_requests',{'session_id':row.session_id})
                    await notify(db,'device_responses',{'call_id':row.id})
                await db.execute(delete(DeviceCall).where(DeviceCall.created_at < func.now()-timedelta(hours=1),
                    DeviceCall.state.in_(['completed','failed','cancelled'])))
        except Exception:
            log.warning("设备执行临时数据清理失败，将稍后重试。")
        await asyncio.sleep(15)
