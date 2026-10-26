"""会议、确认转写与纪要的 PostgreSQL 模型。"""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.infrastructure.database.base import Base


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (Index("idx_meetings_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    participants: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'active'"))
    elapsed_ms: Mapped[int] = mapped_column(Integer, server_default=text("'0'"))
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("'1'"))
    minutes_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_status: Mapped[str] = mapped_column(String(16), server_default=text("'idle'"))
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    generation_source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_ready_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MeetingSegment(Base):
    __tablename__ = "meeting_segments"
    __table_args__ = (UniqueConstraint("meeting_id", "seq", name="uq_meeting_segments_seq"),)

    meeting_id: Mapped[str] = mapped_column(String(128), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("'1'"))
    seq: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MeetingMinutes(Base):
    __tablename__ = "meeting_minutes"

    meeting_id: Mapped[str] = mapped_column(String(128), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    blocks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[int] = mapped_column(Integer)
    archived_document_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class MeetingGenerationJob(Base):
    __tablename__ = "meeting_generation_jobs"
    __table_args__ = (
        Index("idx_minutes_jobs_claim", "status", "lease_until", "created_at"),
        Index("uq_minutes_jobs_active", "meeting_id", unique=True,
              postgresql_where=text("status IN ('queued', 'running')")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(String(128), ForeignKey("meetings.id", ondelete="CASCADE"))
    source_revision: Mapped[int] = mapped_column(Integer)
    input: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("'0'"))
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
