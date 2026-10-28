"""Agent 业务接口，前端无需直接访问 Sidecar。"""
from typing import Annotated
from fastapi import APIRouter, Depends
from typing import Literal
from pydantic import BaseModel, Field
from src.infrastructure.sidecar.service import sidecar
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from src.core.responses import ApiResponse, ok
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from . import service
from .schemas import AgentRequest, TitleRequest
from .conversation_router import router as conversation_router
from .run_router import router as run_router
from .approval_router import router as approval_router
from .project_router import router as project_router

router = APIRouter(prefix="/api/agents", tags=["agents"])
router.include_router(conversation_router)
router.include_router(run_router)
router.include_router(approval_router)
router.include_router(project_router)
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/models", response_model=ApiResponse[dict], summary="查询 Agent 可用模型")
async def list_models(user: CurrentUser):
    """返回服务端配置的模型，隐藏凭证。"""
    return ok(await service.list_models(user.id))


@router.post("/chat", response_class=StreamingResponse, summary="临时运行 Agent（不保存历史）", deprecated=True)
async def chat(body: AgentRequest, user: CurrentUser):
    """兼容旧客户端；正式会话使用 /threads/{id}/chat 保存历史。"""
    stream = await service.open_chat(body, user.id)
    return StreamingResponse(stream.chunks(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                             background=BackgroundTask(stream.close))


@router.post("/title", response_model=ApiResponse[dict], summary="生成会话标题")
async def generate_title(body: TitleRequest, user: CurrentUser):
    """验证登录后调用 LLM 生成简短标题。"""
    return ok(await service.generate_title(body, user.id))


@router.get("/config", response_model=ApiResponse[dict], summary="读取当前设备 Agent 配置")
async def agent_config(user: CurrentUser, agent_code: Literal["general", "product"]):
    """返回当前 Agent 工作区的提示词。"""
    return ok(await sidecar("/agents/config", {"agent_code": agent_code}))


class AgentConfigUpdate(BaseModel):
    agent_code: Literal["general", "product"]
    prompt: str = Field(min_length=1, max_length=65536)
    expected_prompt: str = Field(min_length=1, max_length=65536)


@router.put("/config", response_model=ApiResponse[dict], summary="修改当前设备 Agent 配置")
async def update_agent_config(body: AgentConfigUpdate, user: CurrentUser):
    """将提示词保存到当前设备的 Agent 工作区。"""
    return ok(await sidecar("/agents/config/update", body.model_dump()))
