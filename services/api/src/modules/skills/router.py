"""技能目录与本机 Agent 技能安装入口。"""
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from src.core.responses import ApiResponse, ok
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from src.infrastructure.sidecar.service import sidecar

router = APIRouter(prefix="/api/skills", tags=["skills"])
CurrentUser = Annotated[User, Depends(get_current_user)]
from .schemas import AgentCode, InstallInput, UninstallInput, DescriptionsInput


@router.get("/search", response_model=ApiResponse[dict])
async def search(user: CurrentUser, q: str = Query(default="", max_length=200)):
    """通过当前设备搜索 skills.sh 技能目录。"""
    return ok(await sidecar("/skills/search", {"query": q}))


@router.get("", response_model=ApiResponse[dict])
async def installed(user: CurrentUser, agent_code: AgentCode):
    """查询当前设备上指定 Agent 的实际安装状态。"""
    return ok(await sidecar("/skills/list", {"agent_code": agent_code}))


@router.post("/install", response_model=ApiResponse[dict])
async def install(body: InstallInput, user: CurrentUser):
    """下载并安装到当前设备的 Agent 独立目录。"""
    return ok(await sidecar("/skills/install", body.model_dump(), timeout=120))


@router.post("/uninstall", response_model=ApiResponse[dict])
async def uninstall(body: UninstallInput, user: CurrentUser):
    """卸载当前设备指定 Agent 的技能。"""
    return ok(await sidecar("/skills/uninstall", body.model_dump()))


@router.post("/descriptions", response_model=ApiResponse[dict])
async def descriptions(body: DescriptionsInput, user: CurrentUser):
    """批量补充技能卡片的简介。"""
    return ok(await sidecar("/skills/descriptions", body.model_dump()))
