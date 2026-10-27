"""飞书 CLI 自助授权接口。"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.core.responses import ApiResponse, ok
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from . import service

router = APIRouter(prefix="/api/connectors/feishu", tags=["connectors"])
CurrentUser = Annotated[User, Depends(get_current_user)]


class AuthorizationOut(BaseModel):
    """授权页面信息，不包含设备密钥和 Token。"""
    action: str
    state: str
    url: str | None = None
    qr_code: str | None = None
    message: str | None = None
    expires_at: str


class FeishuStatus(BaseModel):
    """当前用户的飞书 CLI 状态。"""
    installed: bool
    configured: bool
    connected: bool
    verified: bool
    account: str | None = None
    last_verified_at: str | None = None
    flow: AuthorizationOut | None = None


@router.get("", response_model=ApiResponse[FeishuStatus], summary="查询飞书连接状态")
async def status(user: CurrentUser):
    """读取真实 CLI 配置与用户身份状态。"""
    return ok(await service.status(user.id))


@router.post("/authorization/{action}", response_model=ApiResponse[AuthorizationOut], summary="启动飞书网页配置或授权")
async def start(action: Literal["configure", "login"], user: CurrentUser):
    """由用户发起配置或最小权限的身份授权。"""
    return ok(await service.start(user.id, action))


@router.delete("/authorization", response_model=ApiResponse[None], summary="取消飞书授权流程")
async def cancel(user: CurrentUser):
    """终止当前用户的待完成授权进程。"""
    await service.cancel(user.id)
    return ok(message="授权已取消")


@router.post("/verify", response_model=ApiResponse[FeishuStatus], summary="验证飞书用户登录状态")
async def verify(user: CurrentUser):
    """向飞书验证用户 Token 是否有效。"""
    return ok(await service.status(user.id, verify=True))


@router.post("/disconnect", response_model=ApiResponse[None], summary="断开本机飞书登录")
async def disconnect(user: CurrentUser):
    """清理本机用户登录态，不撤销飞书服务端全部授权。"""
    await service.logout(user.id)
    return ok(message="本机飞书登录已断开")
