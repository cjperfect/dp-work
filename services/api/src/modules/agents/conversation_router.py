"""会话历史的业务接口，全部要求登录。"""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from src.core.responses import ApiResponse, ok
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from . import conversation_service as service
from .conversation_schemas import ThreadCreate, DraftSave, GraphSave, RenameThread, ImportThread, StoredChat

router = APIRouter(prefix='/threads')
CurrentUser = Annotated[User, Depends(get_current_user)]
ThreadId = Annotated[str, Path(pattern=r'^[a-zA-Z0-9_-]{1,128}$')]


@router.get('', response_model=ApiResponse[list[dict]], summary='查询全部会话')
async def list_threads(user: CurrentUser, q: str = Query(default='', max_length=200), agent_id: Literal[1, 2] | None = None):
    """返回本人全部 Agent 会话，支持标题搜索与 Agent 筛选。"""
    return ok(await service.list_threads(user.id, q, agent_id))


@router.post('', response_model=ApiResponse[dict], summary='创建会话')
async def create_thread(body: ThreadCreate, user: CurrentUser):
    """幂等创建当前用户的会话。"""
    return ok(await service.create(user.id, body))


@router.post('/import', response_model=ApiResponse[dict | None], summary='迁移本地会话')
async def import_thread(body: ImportThread, user: CurrentUser):
    """只迁入不存在的会话，不覆盖服务端记录。"""
    return ok(await service.import_thread(user.id, body))


@router.get('/{thread_id}', response_model=ApiResponse[dict], summary='查询会话消息和分支')
async def get_thread(thread_id: ThreadId, user: CurrentUser):
    """读取当前路径和全部消息分支。"""
    return ok(await service.get(user.id, thread_id))


@router.patch('/{thread_id}/draft', response_model=ApiResponse[dict], summary='保存会话草稿')
async def save_draft(thread_id: ThreadId, body: DraftSave, user: CurrentUser):
    """按版本保存草稿与上下文选择。"""
    return ok(await service.save_draft(user.id, thread_id, body))


@router.put('/{thread_id}/messages', response_model=ApiResponse[dict], summary='保存会话消息与编辑分支')
async def save_messages(thread_id: ThreadId, body: GraphSave, user: CurrentUser):
    """保存当前消息路径，保留历史分支。"""
    return ok(await service.save_graph(user.id, thread_id, body))


@router.patch('/{thread_id}', response_model=ApiResponse[dict], summary='重命名会话')
async def rename(thread_id: ThreadId, body: RenameThread, user: CurrentUser):
    """人工标题优先于自动生成标题。"""
    return ok(await service.rename(user.id, thread_id, body))


@router.delete('/{thread_id}', response_model=ApiResponse[None], summary='删除会话')
async def remove(thread_id: ThreadId, user: CurrentUser):
    """删除消息，旧页面无法重新写回。"""
    await service.remove(user.id, thread_id)
    return ok()


@router.post('/{thread_id}/chat', response_class=StreamingResponse, summary='流式对话并保存历史')
async def chat(thread_id: ThreadId, body: StoredChat, user: CurrentUser):
    """使用 PG 历史执行 Agent，并保存回答和状态。"""
    stream = await service.open_chat(user.id, thread_id, body)
    return StreamingResponse(stream.chunks(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}, background=BackgroundTask(stream.close))
