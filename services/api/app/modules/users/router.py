from fastapi import APIRouter

from app.core.exceptions import ApiError
from app.core.responses import ApiCode, ApiResponse, ok
from app.decorators import require_user

from . import service
from .exceptions import UsernameExistsError
from .schemas import UserCreateIn

router = APIRouter(
    prefix="/api/v1/users",
    tags=["users"],
)


@router.get("", response_model=ApiResponse[list[dict]], summary="用户列表（admin）")
@require_user(roles=("admin",))
async def list_users() -> ApiResponse[list[dict]]:
    return ok(await service.list_users())


@router.post("", response_model=ApiResponse[dict], summary="创建用户（admin）")
@require_user(roles=("admin",))
async def create_user(body: UserCreateIn) -> ApiResponse[dict]:
    try:
        user = await service.create_user(**body.model_dump())
    except UsernameExistsError:
        raise ApiError(ApiCode.STATE_CONFLICT, "用户名已存在", 409) from None
    return ok(user.to_public(), message="创建成功")
