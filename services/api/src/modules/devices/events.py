"""用户本机主动连接云端的执行通道。"""
import asyncio
import hashlib
import json
import time
from contextlib import suppress
from datetime import datetime,timedelta,timezone
from uuid import UUID,uuid4
from fastapi import WebSocket,WebSocketDisconnect
from sqlalchemy import func,select,update
from sqlalchemy.dialects.postgresql import insert
from src.core.security import decode_token
from src.infrastructure.database import session
from src.infrastructure.database.notifications import listen
from src.modules.users import service as users
from .models import Device,DeviceCall




from .service import fail_calls,accept_result


async def connect(ws:WebSocket):
    """首帧鉴权，连接主动来自 Electron，不接受任意本地 URL。"""
    await ws.accept()
    sid=str(uuid4());device_id=None;reader=None;pending=None
    try:
        async with asyncio.timeout(5):
            raw=await ws.receive_text()
            if len(raw)>8192:raise ValueError('auth too large')
            auth=json.loads(raw);token=auth.get('token')
            payload=decode_token(token) if isinstance(token,str) else None
            if not payload:raise ValueError('invalid auth')
            user=await users.find_by_subject(payload.get('sub'),payload.get('uidv'))
            if not user or not user.is_active:raise ValueError('invalid user')
            installation=str(UUID(auth.get('installation_id')))
            device_id=str(UUID(hashlib.sha256(f'{user.id}:{installation}'.encode()).hexdigest()[:32]))
        async with listen('device_requests') as queue:
            async with session.transaction() as db:
                previous=await db.get(Device,device_id,with_for_update=True)
                if previous:await fail_calls(db,previous.session_id)
                statement=insert(Device).values(id=device_id,owner_id=user.id,session_id=sid,
                    lease_until=datetime.now(timezone.utc)+timedelta(seconds=30))
                await db.execute(statement.on_conflict_do_update(index_elements=[Device.id],set_={
                    'session_id':sid,'lease_until':statement.excluded.lease_until}))
            await ws.send_json({'type':'connected','device_id':device_id})
            reader=asyncio.create_task(ws.receive_text());sent=set();last_check=0
            while True:
                if payload.get('exp',0)<=time.time():raise ValueError('expired auth')
                if time.monotonic()-last_check>10:
                    fresh=await users.find_by_id(user.id)
                    if not fresh or not fresh.is_active:raise ValueError('inactive user')
                    async with session.transaction() as db:
                        current=await db.get(Device,device_id,with_for_update=True)
                        if not current or current.session_id!=sid:raise ValueError('replaced device session')
                        current.lease_until=datetime.now(timezone.utc)+timedelta(seconds=30)
                    last_check=time.monotonic()
                cancellations=[]
                async with session.transaction() as db:
                    for key in list(sent):
                        call=await db.get(DeviceCall,key)
                        if not call or call.state in ('cancelled','failed'):
                            cancellations.append(key);sent.discard(key)
                        elif call.state=='completed':sent.discard(key)
                    calls=list((await db.scalars(select(DeviceCall).where(DeviceCall.session_id==sid,DeviceCall.state=='queued')
                        .order_by(DeviceCall.created_at).with_for_update(skip_locked=True).limit(max(0,4-len(sent))))).all()) if len(sent)<4 else []
                    for call in calls:
                        call.state='running';sent.add(call.id)
                for key in cancellations:await ws.send_json({'type':'cancel','id':key})
                for call in calls:await ws.send_json({'type':'call','id':call.id})
                pending=asyncio.create_task(queue.get())
                done,_=await asyncio.wait((reader,pending),timeout=2,return_when=asyncio.FIRST_COMPLETED)
                if reader in done:
                    raw=reader.result()
                    if len(raw)>100000:raise ValueError('frame too large')
                    message=json.loads(raw)
                    if message.get('type')!='ping':await accept_result(user.id,device_id,sid,message)
                    reader=asyncio.create_task(ws.receive_text())
                if pending not in done:
                    pending.cancel()
                    with suppress(asyncio.CancelledError):await pending
                pending=None
    except (ValueError,TypeError,AttributeError,TimeoutError,WebSocketDisconnect):
        pass
    except Exception:
        pass
    finally:
        for task in (reader,pending):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError,WebSocketDisconnect):await task
        if device_id:
            async with session.transaction() as db:
                await fail_calls(db,sid)
                await db.execute(update(Device).where(Device.id==device_id,Device.session_id==sid).values(lease_until=func.now()))
        with suppress(RuntimeError,WebSocketDisconnect):await ws.close(code=1008)
