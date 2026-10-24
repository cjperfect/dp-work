"""HTTP 用户守卫。放在 @router.get/post 等路由装饰器下方。"""

from collections.abc import Callable
from functools import wraps
from inspect import Parameter, iscoroutinefunction, signature
from typing import Annotated, get_type_hints

from fastapi import Depends

from app.modules.auth.dependencies import get_current_user, require_dept, require_role
from app.modules.users.models import User


def require_user(
    *, roles: tuple[str, ...] = (), departments: tuple[str, ...] = ()
) -> Callable:
    """校验有效用户；同类权限满足任意一个，角色与部门同时指定时须同时满足。

    当前用户由 get_current_user 写入 request.state.user；需要参数注入时仍可
    使用 Annotated[User, Depends(get_current_user)]，同请求会复用依赖结果。
    """
    role_guard = require_role(*roles) if roles else None
    dept_guard = require_dept(*departments) if departments else None

    async def authorize(user: Annotated[User, Depends(get_current_user)]) -> User:
        if role_guard:
            await role_guard(user)
        if dept_guard:
            await dept_guard(user)
        return user

    def decorate(endpoint: Callable) -> Callable:
        original = signature(endpoint)
        if any(
            parameter.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)
            for parameter in original.parameters.values()
        ):
            raise TypeError(
                "require_user 路由必须声明具体参数，不支持 *args / **kwargs"
            )
        # 在原函数所在模块解析延迟注解，避免包装后丢失请求体模型等类型。
        hints = get_type_hints(endpoint, include_extras=True)
        parameters = [
            parameter.replace(annotation=hints.get(name, parameter.annotation))
            for name, parameter in original.parameters.items()
        ]
        dependency_name = "_authenticated_user"
        while dependency_name in original.parameters:
            dependency_name += "_"
        parameters.append(
            Parameter(
                dependency_name,
                kind=Parameter.KEYWORD_ONLY,
                annotation=Annotated[User, Depends(authorize)],
            )
        )

        if iscoroutinefunction(endpoint):

            @wraps(endpoint)
            async def wrapped(*args, **kwargs):
                kwargs.pop(dependency_name, None)
                return await endpoint(*args, **kwargs)

        else:

            @wraps(endpoint)
            def wrapped(*args, **kwargs):
                kwargs.pop(dependency_name, None)
                return endpoint(*args, **kwargs)

        # FastAPI 通过签名识别依赖；内部守卫参数不会成为 HTTP 参数。
        wrapped.__signature__ = original.replace(
            parameters=parameters,
            return_annotation=hints.get("return", original.return_annotation),
        )
        return wrapped

    return decorate
