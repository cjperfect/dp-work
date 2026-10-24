from fastapi import APIRouter

from app.core.responses import ApiResponse, ok
from app.decorators import require_user

from . import service
from .schemas import MinutesUpdateIn, SegmentsBatch

router = APIRouter(prefix="/api/v1", tags=["meetings"])


@router.post("/segments", response_model=ApiResponse[dict])
@require_user()
async def save_segments(body: SegmentsBatch) -> ApiResponse[dict]:
    return ok(await service.save_segments(body))


@router.get("/minutes", response_model=ApiResponse[list[dict]], summary="纪要列表")
@require_user()
async def list_minutes() -> ApiResponse[list[dict]]:
    return ok(await service.list_minutes())


@router.get(
    "/meetings/{meeting_id}/minutes",
    response_model=ApiResponse[dict],
    summary="按会议读取纪要",
)
@require_user()
async def get_minutes(meeting_id: str) -> ApiResponse[dict]:
    return ok(await service.get_minutes(meeting_id))


@router.put(
    "/meetings/{meeting_id}/minutes",
    response_model=ApiResponse[dict],
    summary="更新纪要（编辑 / 状态流转）",
)
@require_user()
async def update_minutes(meeting_id: str, body: MinutesUpdateIn) -> ApiResponse[dict]:
    return ok(await service.update_minutes(meeting_id, body), message="更新成功")


# 兼容现有前端的公开占位入口；它目前不执行数据库或模型操作。
placeholder_router = APIRouter(prefix="/api/v1", tags=["meetings"])


@placeholder_router.post(
    "/meetings/{meeting_id}/minutes/generate",
    response_model=ApiResponse[dict],
    summary="生成会议纪要（占位）",
)
async def generate_minutes(meeting_id: str) -> ApiResponse[dict]:
    return ok(await service.generate_minutes(meeting_id), message="已开始生成")
