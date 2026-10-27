"""设备出站执行通道入口。"""
from typing import Annotated
from fastapi import APIRouter,WebSocket,Request,Depends
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from . import service,events
router=APIRouter(prefix='/api/devices',tags=['devices'])


@router.get('/calls/{call_id}/input',include_in_schema=False)
async def input_data(call_id:str,request:Request,user:Annotated[User,Depends(get_current_user)]):
    """读取本次设备调用输入。"""
    return await service.input_data(call_id,request.headers.get('X-Device-ID'),user.id)


@router.websocket('/connect')
async def connect(ws:WebSocket):
    """由 Electron 主动建立登录后的执行连接。"""
    await events.connect(ws)
