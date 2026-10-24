"""会议 ORM 查询；批量插入使用 PostgreSQL ON CONFLICT。"""

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Minutes, TranscriptSegment

_MINUTES_SUMMARY = (
    Minutes.id,
    Minutes.meeting_id,
    Minutes.title,
    Minutes.status,
    Minutes.created_at,
    Minutes.updated_at,
)


class MeetingRepository:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session

    async def insert_segments(self, rows: list[tuple[Any, ...]]) -> int:
        if not rows:
            return 0
        columns = ("id", "meeting_id", "seq", "speaker", "text", "start_ms", "end_ms")
        statement = (
            insert(TranscriptSegment)
            .values([dict(zip(columns, row, strict=True)) for row in rows])
            .on_conflict_do_nothing(index_elements=[TranscriptSegment.id])
            .returning(TranscriptSegment.id)
        )
        return len((await self.session.scalars(statement)).all())

    async def list_minutes(self) -> list[dict]:
        result = await self.session.execute(
            select(*_MINUTES_SUMMARY).order_by(Minutes.created_at.desc())
        )
        return [dict(row) for row in result.mappings()]

    async def get_minutes(self, meeting_id: str) -> dict | None:
        result = await self.session.execute(
            select(*_MINUTES_SUMMARY, Minutes.content).where(
                Minutes.meeting_id == meeting_id
            )
        )
        row = result.mappings().one_or_none()
        return dict(row) if row else None

    async def update_minutes(self, meeting_id: str, changes: dict) -> dict | None:
        values = {
            field: changes[field]
            for field in ("title", "content", "status")
            if field in changes
        }
        statement = (
            update(Minutes)
            .where(Minutes.meeting_id == meeting_id)
            .values(**values, updated_at=func.now())
            .returning(
                Minutes.id,
                Minutes.meeting_id,
                Minutes.title,
                Minutes.status,
                Minutes.updated_at,
            )
        )
        row = (await self.session.execute(statement)).mappings().one_or_none()
        return dict(row) if row else None
