"""角色、权限和用户角色分配；不开放自行注册管理员。"""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field
from src.core.responses import ok
from src.modules.auth.dependencies import get_current_user, require_permission
from src.modules.users.models import User
from src.modules.users import service as users
from . import service
from .policy import PERMISSIONS

router = APIRouter(prefix='/api/access', tags=['access'])
CurrentUser = Annotated[User, Depends(get_current_user)]


Admin = Annotated[User, Depends(require_permission("access:manage"))]

class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['admin', 'manager', 'member', 'viewer']


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    permissions: list[str] = Field(max_length=len(PERMISSIONS))


@router.get('/me')
async def me(user: CurrentUser):
    return ok(await service.my_permissions(user))


@router.get('/roles')
async def roles(user: Admin):
    return ok({'roles': await service.list_roles(), 'permissions': PERMISSIONS})


@router.get('/users')
async def user_list(user: Admin):
    return ok(await users.list_users())


@router.put('/users/{user_id}/role')
async def assign_role(user_id: Annotated[int, Path(ge=1)], body: RoleUpdate, user: Admin):
    return ok(await service.set_role(user.id, user_id, body.role))


@router.put('/roles/{role}/permissions')
async def change_policy(role: str, body: PolicyUpdate, user: Admin):
    return ok(await service.set_permissions(user.id, role, body.permissions))
