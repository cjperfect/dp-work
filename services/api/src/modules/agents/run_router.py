"""运行查询与取消接口。"""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Path, Query
from src.core.pagination import PageParams, Page
from src.core.responses import ApiResponse, ok
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from . import run_service
from .run_schemas import RunOut

router = APIRouter(prefix="/runs")
CurrentUser = Annotated[User, Depends(get_current_user)]
RunId = Annotated[str, Path(pattern=r"^[a-fA-F0-9-]{36}$")]


@router.get("", response_model=ApiResponse[Page[RunOut]], summary="分页查询 Agent 运行")
async def list_runs(user: CurrentUser, params: Annotated[PageParams, Depends()],
                    conversation_id: str | None = Query(default=None, max_length=128),
                    status: Literal["running", "completed", "failed", "cancelled", "interrupted"] | None = None):
    """查询当前用户的执行记录。"""
    return ok(await run_service.list_runs(user.id, params, conversation_id, status))


@router.get("/{run_id}", response_model=ApiResponse[RunOut], summary="查询 Agent 运行详情")
async def get_run(run_id: RunId, user: CurrentUser):
    """读取状态、时间、回复 ID 和安全错误信息。"""
    return ok(await run_service.get(user.id, run_id))


@router.post("/{run_id}/cancel", response_model=ApiResponse[RunOut], summary="停止 Agent 运行")
async def cancel_run(run_id: RunId, user: CurrentUser):
    """幂等停止运行，保留已经生成的内容。"""
    return ok(await run_service.cancel(user.id, run_id))
