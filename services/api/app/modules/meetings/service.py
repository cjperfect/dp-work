"""会议业务与事务管理。"""
from datetime import datetime, timezone
from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.infrastructure.database import session
from .repository import MeetingsRepository
from .schemas import MeetingCreate, MeetingState, MeetingSave, Workspace, Segment, Minutes


async def _workspace(repository: MeetingsRepository, record) -> Workspace:
    """组装会议、确认转写与富文本纪要。"""
    minutes = await repository.minutes(record.id)
    return Workspace(meeting=MeetingState.model_validate(record),
        segments=[Segment.model_validate(row) for row in await repository.segments(record.id)],
        minutes=Minutes.model_validate(minutes) if minutes else None)


def _values(meeting: MeetingState, allow_generation: bool = False) -> dict:
    """提取允许修改的会议状态。"""
    values = meeting.model_dump(exclude={"id", "owner_id", "revision", "created_at", "updated_at"})
    if not allow_generation:
        for key in ("generation_status", "generation_error", "generation_ready_at", "generation_task_id", "generation_source_revision", "minutes_status"):
            values.pop(key, None)
    if meeting.status != "active":
        values["resumed_at"] = None
    if meeting.status in ("ended", "archived") and not meeting.ended_at:
        values["ended_at"] = datetime.now(timezone.utc)
    return values


async def create(owner_id: int, body: MeetingCreate) -> Workspace:
    """创建会议，同一用户重复提交相同 ID 返回原记录。"""
    async with session.transaction() as conn:
        repository = MeetingsRepository(conn)
        record = await repository.get(owner_id, body.id)
        if record:
            return await _workspace(repository, record)
        if await repository.id_exists(body.id):
            raise ApiError(ApiCode.STATE_CONFLICT, "会议标识已存在", 409)
        record = await repository.create(owner_id, body.id, {
            "title": body.title, "scheduled_at": body.scheduled_at, "participants": [],
            "resumed_at": datetime.now(timezone.utc),
        })
        return await _workspace(repository, record)


async def list_meetings(owner_id: int) -> list[MeetingState]:
    """查询当前用户的会议列表。"""
    async with session.read_session() as conn:
        return [MeetingState.model_validate(row) for row in await MeetingsRepository(conn).list(owner_id)]


async def get(owner_id: int, meeting_id: str) -> Workspace:
    """读取当前用户的会议详情。"""
    async with session.read_session() as conn:
        repository = MeetingsRepository(conn)
        record = await repository.get(owner_id, meeting_id)
        if record is None:
            raise ApiError(ApiCode.NOT_FOUND, "会议不存在", 404)
        return await _workspace(repository, record)


async def save(owner_id: int, meeting_id: str, body: MeetingSave) -> Workspace:
    """在同一事务中保存会议状态、转写与纪要。"""
    if body.meeting.id != meeting_id:
        raise ApiError(ApiCode.STATE_CONFLICT, "会议标识不匹配", 409)
    async with session.transaction() as conn:
        repository = MeetingsRepository(conn)
        previous = await repository.get(owner_id, meeting_id, lock=True)
        if previous is None:
            raise ApiError(ApiCode.NOT_FOUND, "会议不存在", 404)
        if previous.generation_status == "generating":
            raise ApiError(ApiCode.STATE_CONFLICT, "会议纪要生成中，暂不能修改会议内容。", 409)
        record = await repository.update(owner_id, meeting_id, body.expected_revision, _values(body.meeting))
        if record is None:
            raise ApiError(ApiCode.STATE_CONFLICT, "会议已被其他页面修改，请重新加载后重试。", 409)
        from .record_models import MeetingRecord
        from . import records
        collaboration = await conn.get(MeetingRecord, meeting_id)
        if collaboration and collaboration.kind == 'minutes':
            stored = await repository.minutes(meeting_id)
            if (Minutes.model_validate(stored).model_dump() if stored else None) != (body.minutes.model_dump() if body.minutes else None):
                raise ApiError(ApiCode.STATE_CONFLICT, '纪要已启用协作，请在协作编辑器中修改。', 409)
        if previous.status == 'ended':
            saved_segments = {row.id: row for row in await repository.segments(meeting_id)}
            for segment in body.segments:
                old = saved_segments.get(segment.id)
                if old and old.text != segment.text:
                    if previous.generation_status == 'ready':
                        raise ApiError(ApiCode.STATE_CONFLICT, '纪要已生成，原始转写已锁定。', 409)
                    if old.original_text is None:
                        old.original_text = old.text
        await repository.save_contents(meeting_id, body)
        if collaboration and collaboration.kind == 'minutes':
            await records.notify(conn, meeting_id)
        return await _workspace(repository, record)


async def import_legacy(owner_id: int, body: Workspace) -> Workspace:
    """迁移浏览器旧会议，已有 PostgreSQL 记录始终优先。"""
    if body.meeting.owner_id != owner_id:
        raise ApiError(ApiCode.NOT_FOUND, "会议不存在", 404)
    async with session.transaction() as conn:
        repository = MeetingsRepository(conn)
        record = await repository.get(owner_id, body.meeting.id)
        if record:
            return await _workspace(repository, record)
        if await repository.id_exists(body.meeting.id):
            raise ApiError(ApiCode.NOT_FOUND, "会议不存在", 404)
        values = _values(body.meeting, allow_generation=True)
        record = await repository.create(owner_id, body.meeting.id, values)
        await repository.save_contents(record.id, body)
        return await _workspace(repository, record)


async def remove(owner_id: int, meeting_id: str) -> None:
    """删除会议及关联的转写、纪要。"""
    async with session.transaction() as conn:
        repository = MeetingsRepository(conn)
        if not await repository.delete(owner_id, meeting_id):
            raise ApiError(ApiCode.NOT_FOUND, "会议不存在", 404)
        await repository.notify_generation(owner_id, meeting_id)
