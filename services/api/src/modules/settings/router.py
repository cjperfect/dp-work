"""个人设置接口。"""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Response
from src.core.responses import ApiResponse, ok
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from . import service
from .schemas import ServiceConfig

router = APIRouter(prefix="/api/settings", tags=["settings"])
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=ApiResponse[dict], summary="读取个人设置")
async def read(user: CurrentUser, response: Response):
    """读取当前用户设置。"""
    response.headers["Cache-Control"] = "no-store"
    return ok(await service.read(user.id))


@router.put("/{kind}", response_model=ApiResponse[dict], summary="保存个人服务配置")
async def save(kind: Literal["model", "asr"], body: ServiceConfig, user: CurrentUser):
    """保存当前用户模型或转写配置。"""
    return ok(await service.save(user.id, kind, body))


@router.post("/{kind}/test", response_model=ApiResponse[dict], summary="测试个人服务配置")
async def test(kind: Literal["model", "asr"], body: ServiceConfig, user: CurrentUser):
    """测试表单配置，不自动保存。"""
    return ok(await service.test(user.id, kind, body))


@router.post("/asr/session/{meeting_id}", response_model=ApiResponse[dict], summary="申请会议转写凭证")
async def asr_session(meeting_id: str, user: CurrentUser):
    """为当前用户的进行中会议申请转写连接凭证。"""
    return ok(await service.asr_session(user.id, meeting_id))


@router.get("/asr/configured", response_model=ApiResponse[dict], summary="检查个人语音配置状态")
async def asr_configured(user: CurrentUser):
    """查询实际生效的语音配置状态。"""
    personal = await service.runtime(user.id, "asr")
    if personal:
        return ok({"configured": True})
    defaults = await service.sidecar("/settings/defaults")
    return ok({"configured": defaults["asr"]["configured"]})
