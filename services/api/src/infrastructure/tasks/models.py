"""与业务数据同事务提交的可靠任务消息。"""
from datetime import datetime
from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.database.base import Base


class TaskOutbox(Base):
    """消息可重复投递，完成状态由业务处理器确认。"""
    __tablename__ = 'task_outbox'
    __table_args__ = (
        UniqueConstraint('kind', 'target_id', 'version', name='uq_task_outbox_target_version'),
        Index('idx_task_outbox_dispatch', 'completed_at', 'next_attempt_at', 'lease_until'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(128))
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text('0'))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
