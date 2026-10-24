"""认证业务；不依赖 FastAPI 或其他模块的 Router/Repository。"""

from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.core.security import create_access_token, decode_token, verify_password
from app.modules.users import service as users_service
from app.modules.users.exceptions import UsernameExistsError
from app.modules.users.models import User


def _session(user: User) -> dict:
    return {
        "token": create_access_token(user.id, user.role, user.department),
        "user": user.to_public(),
    }


async def register(username: str, password: str) -> dict:
    try:
        user = await users_service.create_user(
            username=username,
            password=password,
            display_name=username,
            department="unassigned",
            role="member",
            allow_existing=False,
        )
    except UsernameExistsError:
        raise ApiError(
            ApiCode.STATE_CONFLICT, "用户名已存在，请换一个用户名或直接登录", 409
        ) from None
    return _session(user)


async def login(username: str, password: str) -> dict:
    user = await users_service.find_by_username(username)
    if user is None or not verify_password(password, user.password_hash):
        raise ApiError(ApiCode.BAD_CREDENTIALS, "用户名或密码错误", 401)
    if not user.is_active:
        raise ApiError(ApiCode.UNAUTHORIZED, "账号已停用", 403)
    return _session(user)


async def refresh(token: str) -> dict:
    payload = decode_token(token)
    if payload is None or not payload.get("sub"):
        raise ApiError(ApiCode.TOKEN_EXPIRED, "登录已过期，请重新登录", 401)
    user = await users_service.find_by_id(str(payload["sub"]))
    if user is None or not user.is_active:
        raise ApiError(ApiCode.UNAUTHORIZED, "账号不存在或已停用", 401)
    return {"token": create_access_token(user.id, user.role, user.department)}
