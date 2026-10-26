"""Agent 业务接口，前端无需直接访问 Sidecar。"""
from typing import Annotated
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from app.core.responses import ApiResponse, ok
from app.modules.auth.dependencies import get_current_user
from app.modules.users.models import User
from . import service
from .schemas import AgentRequest

router = APIRouter(prefix="/api/agents", tags=["agents"])
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/models", response_model=ApiResponse[dict], summary="查询 Agent 可用模型")
async def list_models(user: CurrentUser):
    """返回服务端配置的模型，隐藏凭证。"""
    return ok(await service.list_models(user.id))


@router.post("/chat", response_class=StreamingResponse, summary="流式运行 Agent")
async def chat(body: AgentRequest, user: CurrentUser):
    """验证登录后转发 Agent 事件流，历史消息暂不入库。"""
    stream = await service.open_chat(body, user.id)
    return StreamingResponse(stream.chunks(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                             background=BackgroundTask(stream.close))
