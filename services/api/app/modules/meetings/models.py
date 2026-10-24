"""转写和纪要 ORM 映射，保留原有列、约束与索引。"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("meeting_id", "seq"),
        Index("idx_transcript_segments_meeting", "meeting_id", "seq"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    meeting_id: Mapped[str] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    start_ms: Mapped[int | None] = mapped_column(Integer)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[int] = mapped_column(SmallInteger, server_default=sql_text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Minutes(Base):
    __tablename__ = "minutes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    meeting_id: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, server_default=sql_text("''"))
    status: Mapped[int] = mapped_column(SmallInteger, server_default=sql_text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
