"""认证守卫依赖：Bearer JWT → 当前用户装载 + 角色 / 部门鉴权。

用法（docs/api-architecture.md §4.3）：
- 路由级：router = APIRouter(dependencies=[Depends(get_current_user)])
- 单个：def f(user: Annotated[User, Depends(get_current_user)]) -> ...
- 角色：def f(_: User = Depends(require_role("admin"))) -> ...
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Header, Request

from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.core.security import decode_token
from app.modules.users import service as users_service
from app.modules.users.models import User


def _bearer_token(auth: str | None) -> str:
    if not auth or not auth.lower().startswith("bearer "):
        raise ApiError(ApiCode.UNAUTHORIZED, "未登录或凭证无效", 401)
    token = auth.split(" ", 1)[1].strip()
    if not token:
        raise ApiError(ApiCode.UNAUTHORIZED, "未登录或凭证无效", 401)
    return token


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> User:
    """认证守卫：解析 Bearer → 校验 JWT → 查库 → 注入 request.state。"""
    payload = decode_token(_bearer_token(authorization))
    if payload is None:
        raise ApiError(ApiCode.TOKEN_EXPIRED, "登录已过期，请重新登录", 401)
    sub = payload.get("sub")
    if not sub:
        raise ApiError(ApiCode.UNAUTHORIZED, "未登录或凭证无效", 401)
    user = await users_service.find_by_id(str(sub))
    if user is None or not user.is_active:
        raise ApiError(ApiCode.UNAUTHORIZED, "账号不存在或已停用", 401)
    request.state.user = user
    request.state.user_id = user.id
    return user


def require_role(*roles: str) -> Callable[..., Any]:
    """角色守卫：当前用户 role ∈ roles，否则 403。"""

    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise ApiError(ApiCode.FORBIDDEN, "无权限执行该操作", 403)
        return user

    return _dep


def require_dept(*depts: str) -> Callable[..., Any]:
    """部门守卫：部门专业范畴隔离（数据可见性），否则 403。"""

    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.department not in depts:
            raise ApiError(ApiCode.FORBIDDEN, "不属于该部门范围", 403)
        return user

    return _dep
