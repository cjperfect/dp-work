"""用户本机主动连接云端的执行通道。"""
import base64
from datetime import datetime,timezone
from sqlalchemy import select
from src.core.exceptions import ApiError
from src.core.responses import ApiCode,ok
from src.infrastructure.database import session
from src.infrastructure.sidecar.relay import cipher,notify
from src.infrastructure.sidecar.requests import rpc_input
from .models import Device,DeviceCall,DeviceChunk




async def fail_calls(db,session_id):
    rows=list((await db.scalars(select(DeviceCall).where(DeviceCall.session_id==session_id,
        DeviceCall.state.in_(['queued','running'])).with_for_update())).all())
    for row in rows:
        row.state='failed';row.error='用户设备已离线。';row.encrypted_input=b''
        await notify(db,'device_responses',{'call_id':row.id})


async def input_data(call_id:str,device_id:str|None,owner_id:int):
    """仅当前用户的目标设备可读取本次执行输入。"""
    async with session.read_session() as db:
        row=await db.get(DeviceCall,call_id)
        if not row or row.owner_id!=owner_id or row.device_id!=device_id or (row.state!='running' or not row.encrypted_input):
            raise ApiError(ApiCode.NOT_FOUND,'执行任务不存在。',404)
        device=await db.get(Device,row.device_id)
        if not device or device.session_id!=row.session_id or device.lease_until<=datetime.now(timezone.utc):
            raise ApiError(ApiCode.NOT_FOUND,'设备连接已失效。',404)
        try:
            job = rpc_input(row.method, row.path, row.query, cipher().decrypt(row.encrypted_input))
        except (ValueError, UnicodeError) as cause:
            raise ApiError(ApiCode.NOT_FOUND, '执行任务输入无效。', 404) from cause
        return ok({'id': row.id, **job,
            'timeout_seconds': max(1, (row.deadline_at-datetime.now(timezone.utc)).total_seconds())})



async def accept_result(owner,device_id,sid,message):
    if message.get('type') not in ('head','chunk','end','error'):raise ValueError('invalid frame')
    key=message.get('id')
    if not isinstance(key,str) or len(key)!=36:raise ValueError('invalid id')
    async with session.transaction() as db:
        device=await db.get(Device,device_id)
        if not device or device.session_id!=sid:raise ValueError('stale connection')
        row=await db.get(DeviceCall,key,with_for_update=True)
        if not row or row.owner_id!=owner or row.session_id!=sid:raise ValueError('invalid scope')
        if row.state not in ('queued','running'):return
        kind=message['type']
        if kind=='head':
            code=message.get('status');ct=message.get('content_type','application/octet-stream')
            if row.status_code is not None or type(code) is not int or not 200<=code<=599 or not isinstance(ct,str) or len(ct)>128:raise ValueError('invalid response head')
            row.status_code,row.response_type=code,ct;row.encrypted_input=b''
        elif kind=='chunk':
            encoded=message.get('data');seq=message.get('seq')
            if row.status_code is None or type(seq) is not int or seq!=row.next_seq or not isinstance(encoded,str) or len(encoded)>65536:raise ValueError('invalid chunk')
            data=base64.b64decode(encoded,validate=True)
            if len(data)>49152 or row.response_bytes+len(data)>32*1024*1024 or seq>=10000:raise ValueError('response too large')
            db.add(DeviceChunk(call_id=row.id,seq=seq,data=data));row.next_seq+=1;row.response_bytes+=len(data)
        elif kind=='end':
            if row.status_code is None:raise ValueError('missing response head')
            row.state='completed';row.encrypted_input=b''
        else:
            row.state='failed';row.error='本机 Sidecar 执行失败或连接中断。';row.encrypted_input=b''
        await notify(db,'device_responses',{'call_id':key})


