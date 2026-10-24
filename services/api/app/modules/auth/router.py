from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.responses import ApiResponse, ok
from app.modules.users.models import User

from . import service
from .dependencies import get_current_user
from .schemas import LoginIn, RefreshIn, RegisterIn

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=ApiResponse[dict],
    status_code=201,
    summary="用户名密码注册",
)
async def register(body: RegisterIn) -> ApiResponse[dict]:
    return ok(await service.register(body.username, body.password), message="注册成功")


@router.post("/login", response_model=ApiResponse[dict], summary="登录签发 JWT")
async def login(body: LoginIn) -> ApiResponse[dict]:
    return ok(await service.login(body.username, body.password), message="登录成功")


@router.post("/refresh", response_model=ApiResponse[dict], summary="刷新令牌")
async def refresh(body: RefreshIn) -> ApiResponse[dict]:
    return ok(await service.refresh(body.token), message="刷新成功")


@router.get("/users/me", response_model=ApiResponse[dict], summary="当前用户信息")
async def me(user: Annotated[User, Depends(get_current_user)]) -> ApiResponse[dict]:
    return ok(user.to_public())
