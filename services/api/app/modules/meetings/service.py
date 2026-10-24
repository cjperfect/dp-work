import logging
from uuid import uuid4

from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.infrastructure.database import session

from .exceptions import MinutesNotReadyError
from .repository import MeetingRepository
from .schemas import MinutesUpdateIn, SegmentsBatch

log = logging.getLogger(__name__)


async def save_segments(batch: SegmentsBatch) -> dict:
    if not batch.segments:
        return {"written": 0, "ignored": 0}
    rows = [
        (
            segment.id or str(uuid4()),
            batch.meeting_id,
            segment.seq,
            segment.speaker,
            segment.text,
            segment.start_ms,
            segment.end_ms,
        )
        for segment in batch.segments
    ]
    try:
        async with session.transaction() as conn:
            written = await MeetingRepository(conn).insert_segments(rows)
    except Exception as exc:
        log.exception("Failed to save transcript segments")
        raise ApiError(ApiCode.INTERNAL_ERROR, "转写片段保存失败", 500) from exc
    return {"written": written, "ignored": len(rows) - written}


async def list_minutes() -> list[dict]:
    async with session.read_session() as conn:
        return await MeetingRepository(conn).list_minutes()


async def get_minutes(meeting_id: str) -> dict:
    async with session.read_session() as conn:
        minutes = await MeetingRepository(conn).get_minutes(meeting_id)
    if minutes is None:
        raise MinutesNotReadyError()
    return minutes


async def update_minutes(meeting_id: str, body: MinutesUpdateIn) -> dict:
    changes = body.model_dump(exclude_none=True)
    async with session.transaction() as conn:
        repository = MeetingRepository(conn)
        if await repository.get_minutes(meeting_id) is None:
            raise MinutesNotReadyError()
        if not changes:
            raise ApiError(ApiCode.PARAM_ERROR, "无更新字段", 400)
        updated = await repository.update_minutes(meeting_id, changes)
        if updated is None:
            raise MinutesNotReadyError()
        return updated


async def generate_minutes(meeting_id: str) -> dict:
    """保留现有占位行为；后续在这里接生成任务，Router 无需改变。"""
    return {"meeting_id": meeting_id, "status": 0}
