"""当前用户的工具审批查询与一次性决定。"""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, ConfigDict
from src.core.responses import ApiResponse, ok
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from . import approval_service

router = APIRouter(prefix='/approvals')
CurrentUser = Annotated[User, Depends(get_current_user)]


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['approve', 'reject']


@router.get('', response_model=ApiResponse[list], summary='查询会话审批')
async def list_approvals(user: CurrentUser, conversation_id: str = Query(min_length=1, max_length=128)):
    """读取会话的待审批操作与历史决定。"""
    return ok(await approval_service.list_approvals(user.id, conversation_id))


@router.post('/{approval_id}/decide', response_class=StreamingResponse, summary='允许一次或拒绝工具执行')
async def decide(approval_id: Annotated[str, Path(pattern=r'^[a-fA-F0-9-]{36}$')], body: DecisionInput, user: CurrentUser):
    """保存审批决定后继续同一 Agent 执行。"""
    stream = await approval_service.decide(user.id, approval_id, body.decision)
    return StreamingResponse(stream.chunks(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}, background=BackgroundTask(stream.close))
