"""会议纪要协作文档和不可变版本快照。"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.database.base import Base


class MeetingRecord(Base):
    __tablename__ = 'meeting_records'
    meeting_id: Mapped[str] = mapped_column(String(128), ForeignKey('meetings.id', ondelete='CASCADE'), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), server_default="original")
    state: Mapped[bytes] = mapped_column(LargeBinary)
    epoch: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    saved_revision: Mapped[int] = mapped_column(Integer, server_default="1")
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MeetingRecordVersion(Base):
    __tablename__ = 'meeting_record_versions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(String(128), ForeignKey('meetings.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(16), server_default="original")
    state: Mapped[bytes] = mapped_column(LargeBinary)
    revision: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
