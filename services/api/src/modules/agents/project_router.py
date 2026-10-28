"""项目目录元信息与会话归属接口。"""
from typing import Annotated
from fastapi import APIRouter, Depends, Path
from src.core.responses import ApiResponse, ok
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from . import project_service as service
from .project_schemas import ProjectCreate, ProjectRename, ThreadProject
router = APIRouter()
CurrentUser = Annotated[User, Depends(get_current_user)]
ProjectId = Annotated[str, Path(pattern=r'^[a-fA-F0-9-]{36}$')]


@router.get('/projects', response_model=ApiResponse[list], summary='查询项目')
async def list_projects(user: CurrentUser):
    return ok(await service.list_projects(user.id))


@router.post('/projects', response_model=ApiResponse[dict], summary='添加本机文件夹项目')
async def create(body: ProjectCreate, user: CurrentUser):
    return ok(await service.create(user.id, body))


@router.patch('/projects/{project_id}', response_model=ApiResponse[dict], summary='重命名项目')
async def rename(project_id: ProjectId, body: ProjectRename, user: CurrentUser):
    return ok(await service.rename(user.id, project_id, body.name))


@router.delete('/projects/{project_id}', response_model=ApiResponse[None], summary='移除项目，保留文件与会话')
async def remove(project_id: ProjectId, user: CurrentUser):
    await service.remove(user.id, project_id)
    return ok()


@router.patch('/threads/{thread_id}/project', response_model=ApiResponse[dict], summary='选择会话工作目录')
async def set_project(thread_id: str, body: ThreadProject, user: CurrentUser):
    return ok(await service.set_thread_project(user.id, thread_id, body))
