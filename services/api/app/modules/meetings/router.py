"""会议接口。"""
from typing import Annotated
from fastapi import APIRouter, Depends, Path
from app.core.responses import ApiResponse, ok
from app.modules.auth.dependencies import get_current_user
from app.modules.users.models import User
from . import service, generation
from .schemas import MeetingCreate, MeetingState, MeetingSave, Workspace, GenerateMinutes, GenerationAccepted

from .events import router as events_router
from .record_router import router as record_router

router = APIRouter(prefix="/api/meetings", tags=["meetings"])
router.include_router(events_router)
router.include_router(record_router)
CurrentUser = Annotated[User, Depends(get_current_user)]
MeetingId = Annotated[str, Path(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]


@router.post("", response_model=ApiResponse[Workspace], summary="创建会议")
async def create_meeting(body: MeetingCreate, user: CurrentUser):
    """创建当前用户的会议。"""
    return ok(await service.create(user.id, body))


@router.get("", response_model=ApiResponse[list[MeetingState]], summary="查询会议列表")
async def list_meetings(user: CurrentUser):
    """查询当前用户的全部会议。"""
    return ok(await service.list_meetings(user.id))


@router.post("/import", response_model=ApiResponse[Workspace], summary="迁移旧会议")
async def import_meeting(body: Workspace, user: CurrentUser):
    """将浏览器旧会议迁入 PostgreSQL。"""
    return ok(await service.import_legacy(user.id, body))


@router.get("/{meeting_id}", response_model=ApiResponse[Workspace], summary="读取会议详情")
async def get_meeting(meeting_id: MeetingId, user: CurrentUser):
    """读取会议状态、转写与纪要。"""
    return ok(await service.get(user.id, meeting_id))


@router.put("/{meeting_id}", response_model=ApiResponse[Workspace], summary="保存会议")
async def save_meeting(meeting_id: MeetingId, body: MeetingSave, user: CurrentUser):
    """按版本保存会议数据。"""
    return ok(await service.save(user.id, meeting_id, body))


@router.delete("/{meeting_id}", response_model=ApiResponse[None], summary="删除会议")
async def delete_meeting(meeting_id: MeetingId, user: CurrentUser):
    """删除会议及关联数据。"""
    await service.remove(user.id, meeting_id)
    return ok(message="会议已删除")


@router.post("/{meeting_id}/minutes/generate", response_model=ApiResponse[GenerationAccepted], summary="生成会议纪要")
async def generate_minutes(meeting_id: MeetingId, body: GenerateMinutes, user: CurrentUser):
    """提交异步生成任务并返回当前状态。"""
    return ok(await generation.enqueue(user.id, meeting_id, body))
