"""Agent 每次执行的持久化记录。"""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.database.base import Base


class AgentRun(Base):
    """运行只保存执行元数据，正文仍由会话消息保存。"""
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running','completed','failed','cancelled','interrupted')", name="ck_agent_runs_status"),
        Index("idx_agent_runs_owner_started", "owner_id", "started_at"),
        Index("idx_agent_runs_thread_started", "conversation_id", "started_at"),
        Index("idx_agent_runs_active_thread", "conversation_id", unique=True,
              postgresql_where=text("status = 'running'")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_id: Mapped[int] = mapped_column(Integer)
    response_id: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), server_default="running")
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
