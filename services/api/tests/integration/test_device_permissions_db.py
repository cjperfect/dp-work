"""设备输入和执行回执始终绑定当前用户及连接会话。"""
import asyncio
import base64
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from sqlalchemy import delete
from src.core.exceptions import ApiError
from src.infrastructure.database import session
from src.infrastructure.sidecar.relay import cipher
from src.modules.devices.models import Device,DeviceCall
from src.modules.devices import service
from src.modules.users import service as users
from src.modules.users.models import User


def test_device_owner_session_and_input_cleanup():
    async def case():
        await session.init_db()
        owners=[await users.create_user('device-scope-'+uuid4().hex,'fixture','product') for _ in range(2)]
        device_id,call_id,sid=[str(uuid4()) for _ in range(3)]
        try:
            async with session.transaction() as db:
                db.add(Device(id=device_id,owner_id=owners[0].id,session_id=sid,lease_until=datetime.now(timezone.utc)+timedelta(minutes=1)))
                await db.flush()
                db.add(DeviceCall(id=call_id,owner_id=owners[0].id,device_id=device_id,session_id=sid,method='POST',
                    path='/internal/agents/chat',query='',content_type='application/json',encrypted_input=cipher().encrypt(b'{"fixture":"private-fixture"}'),
                    state='running',deadline_at=datetime.now(timezone.utc)+timedelta(minutes=1)))
            for owner,device in [(owners[1].id,device_id),(owners[0].id,str(uuid4()))]:
                with pytest.raises(ApiError) as error:await service.input_data(call_id,device,owner)
                assert error.value.status_code==404
            visible=await service.input_data(call_id,device_id,owners[0].id)
            assert visible.data['method']=='agents.chat' and visible.data['params']=={'fixture':'private-fixture'}
            async with session.read_session() as db:
                row=await db.get(DeviceCall,call_id)
                assert b'private-fixture' not in row.encrypted_input
            for owner,connection in [(owners[1].id,sid),(owners[0].id,str(uuid4()))]:
                with pytest.raises(ValueError):await service.accept_result(owner,device_id,connection,{'type':'head','id':call_id,'status':200})
            await service.accept_result(owners[0].id,device_id,sid,{'type':'head','id':call_id,'status':200})
            with pytest.raises(ApiError):await service.input_data(call_id,device_id,owners[0].id)
            with pytest.raises(ValueError):await service.accept_result(owners[0].id,device_id,sid,
                {'type':'chunk','id':call_id,'seq':1,'data':base64.b64encode(b'text').decode()})
            await service.accept_result(owners[0].id,device_id,sid,{'type':'chunk','id':call_id,'seq':0,'data':base64.b64encode(b'text').decode()})
            await service.accept_result(owners[0].id,device_id,sid,{'type':'end','id':call_id})
            # 终态后忽略同一会话迟到回执，不把完成覆盖成失败。
            await service.accept_result(owners[0].id,device_id,sid,{'type':'error','id':call_id})
            async with session.read_session() as db:
                row=await db.get(DeviceCall,call_id)
                assert row.state=='completed' and row.next_seq==1 and row.encrypted_input==b''
        finally:
            async with session.transaction() as db:await db.execute(delete(User).where(User.id.in_([owner.id for owner in owners])))
            await session.close_db()
    asyncio.run(case())
