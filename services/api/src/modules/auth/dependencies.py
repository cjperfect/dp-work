"""登录和权限校验依赖。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from src.core.security import decode_token
from src.modules.users import service as users_service
from src.modules.users.models import User


bearer_auth = HTTPBearer(
    scheme_name="BearerAuth",
    bearerFormat="JWT",
    description="填写登录接口返回的 token，无需输入 Bearer 前缀。",
    auto_error=False,
)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_auth)],
) -> User:
    """验证登录凭证并获取当前用户。"""
    if credentials is None or not credentials.credentials.strip():
        raise ApiError(ApiCode.UNAUTHORIZED, "未登录或凭证无效", 401)
    payload = decode_token(credentials.credentials.strip())
    if payload is None:
        raise ApiError(ApiCode.TOKEN_EXPIRED, "登录已过期，请重新登录", 401)
    sub = payload.get("sub")
    if not sub:
        raise ApiError(ApiCode.UNAUTHORIZED, "未登录或凭证无效", 401)
    user = await users_service.find_by_subject(sub, payload.get("uidv"))
    if user is None or not user.is_active:
        raise ApiError(ApiCode.UNAUTHORIZED, "账号不存在或已停用", 401)
    request.state.user = user
    request.state.user_id = user.id
    return user


def require_role(*roles: str) -> Callable[..., Any]:
    """创建角色校验依赖。"""

    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        """校验当前用户权限。"""
        if user.role not in roles:
            raise ApiError(ApiCode.FORBIDDEN, "无权限执行该操作", 403)
        return user

    return _dep


def require_dept(*depts: str) -> Callable[..., Any]:
    """创建部门校验依赖。"""

    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        """校验当前用户权限。"""
        if user.department not in depts:
            raise ApiError(ApiCode.FORBIDDEN, "不属于该部门范围", 403)
        return user

    return _dep
