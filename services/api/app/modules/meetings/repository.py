"""会议数据访问。"""
from sqlalchemy import delete, select, update, func, or_, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from .models import Meeting, MeetingSegment, MeetingMinutes, MeetingGenerationJob
from .schemas import Workspace


class MeetingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, owner_id: int, meeting_id: str, lock: bool = False) -> Meeting | None:
        """按用户读取会议。"""
        statement = select(Meeting).where(Meeting.id == meeting_id, Meeting.owner_id == owner_id)
        return await self.session.scalar(statement.with_for_update() if lock else statement)

    async def list(self, owner_id: int) -> list[Meeting]:
        """查询当前用户的全部会议。"""
        return list((await self.session.scalars(select(Meeting).where(Meeting.owner_id == owner_id)
                    .order_by(Meeting.updated_at.desc(), Meeting.id))).all())

    async def id_exists(self, meeting_id: str) -> bool:
        """检查会议标识是否已存在。"""
        return await self.session.scalar(select(Meeting.id).where(Meeting.id == meeting_id)) is not None

    async def create(self, owner_id: int, meeting_id: str, values: dict) -> Meeting:
        """插入会议记录。"""
        record = Meeting(id=meeting_id, owner_id=owner_id, **values)
        self.session.add(record)
        await self.session.flush()
        return record

    async def update(self, owner_id: int, meeting_id: str, revision: int, values: dict) -> Meeting | None:
        """按版本更新，避免旧页面覆盖新数据。"""
        return await self.session.scalar(update(Meeting).where(Meeting.id == meeting_id,
            Meeting.owner_id == owner_id, Meeting.revision == revision)
            .values(**values, revision=Meeting.revision + 1, updated_at=func.clock_timestamp())
            .returning(Meeting).execution_options(populate_existing=True))

    async def segments(self, meeting_id: str) -> list[MeetingSegment]:
        """按时间序号读取确认转写。"""
        return list((await self.session.scalars(select(MeetingSegment).where(MeetingSegment.meeting_id == meeting_id)
                    .order_by(MeetingSegment.seq))).all())

    async def minutes(self, meeting_id: str) -> MeetingMinutes | None:
        """读取会议纪要及富文本结构。"""
        return await self.session.get(MeetingMinutes, meeting_id)

    async def save_contents(self, meeting_id: str, workspace: Workspace) -> None:
        """合并确认转写，并保存纪要。"""
        existing = {row.id: row for row in await self.segments(meeting_id)}
        by_seq = {row.seq: row.id for row in existing.values()}
        for segment in workspace.segments:
            if segment.seq in by_seq and by_seq[segment.seq] != segment.id:
                raise ApiError(ApiCode.STATE_CONFLICT, "转写序号已被其他片段使用，请刷新后重试。", 409)
            old = existing.get(segment.id)
            if old and old.revision > segment.revision:
                continue
            values = segment.model_dump()
            if old:
                for field, value in values.items():
                    setattr(old, field, value)
            else:
                self.session.add(MeetingSegment(meeting_id=meeting_id, **values))
        minutes = await self.minutes(meeting_id)
        if workspace.minutes is None:
            if minutes:
                await self.session.delete(minutes)
        else:
            values = workspace.minutes.model_dump()
            if values["archived_document_id"] is not None:
                values["archived_document_id"] = str(values["archived_document_id"])
            if minutes:
                for field, value in values.items():
                    setattr(minutes, field, value)
            else:
                self.session.add(MeetingMinutes(meeting_id=meeting_id, **values))
        await self.session.flush()

    async def delete(self, owner_id: int, meeting_id: str) -> bool:
        """删除会议，关联记录由外键级联删除。"""
        return await self.session.scalar(delete(Meeting).where(Meeting.id == meeting_id,
            Meeting.owner_id == owner_id).returning(Meeting.id)) is not None


    async def active_job(self, meeting_id: str) -> MeetingGenerationJob | None:
        """读取会议尚未完成的生成任务。"""
        return await self.session.scalar(select(MeetingGenerationJob).where(
            MeetingGenerationJob.meeting_id == meeting_id,
            MeetingGenerationJob.status.in_(("queued", "running"))))

    async def create_job(self, task_id: str, meeting_id: str, revision: int, payload: dict) -> MeetingGenerationJob:
        """保存不可变的生成输入快照。"""
        job = MeetingGenerationJob(id=task_id, meeting_id=meeting_id, source_revision=revision, input=payload)
        self.session.add(job)
        await self.session.flush()
        return job

    async def claim_job(self, lease_seconds: float) -> MeetingGenerationJob | None:
        """使用行锁领取排队任务或租约过期的任务。"""
        from datetime import timedelta
        from uuid import uuid4
        job = await self.session.scalar(select(MeetingGenerationJob).where(or_(
            MeetingGenerationJob.status == "queued",
            and_(MeetingGenerationJob.status == "running", MeetingGenerationJob.lease_until < func.now())
        )).order_by(MeetingGenerationJob.created_at).limit(1).with_for_update(skip_locked=True))
        if job:
            job.status = "running"
            job.claim_token = str(uuid4())
            job.attempts += 1
            job.lease_until = func.now() + timedelta(seconds=lease_seconds)
            await self.session.flush()
        return job

    async def claimed_job(self, task_id: str, claim_token: str) -> MeetingGenerationJob | None:
        """锁定当前执行批次，拒绝过期执行器覆盖结果。"""
        return await self.session.scalar(select(MeetingGenerationJob).where(
            MeetingGenerationJob.id == task_id, MeetingGenerationJob.claim_token == claim_token,
            MeetingGenerationJob.status == "running").with_for_update())

    async def job_meeting(self, meeting_id: str) -> Meeting | None:
        """供内部任务执行器锁定对应会议。"""
        return await self.session.scalar(select(Meeting).where(Meeting.id == meeting_id).with_for_update())

    async def notify_generation(self, owner_id: int, meeting_id: str) -> None:
        """事务提交时通知所有 API 实例的生成状态订阅者。"""
        import json
        await self.session.execute(text("SELECT pg_notify('meeting_generation', :payload)"),
            {"payload": json.dumps({"owner_id": owner_id, "meeting_id": meeting_id})})
