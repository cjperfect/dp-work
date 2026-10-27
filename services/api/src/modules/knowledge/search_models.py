"""关键词索引同步任务，保留删除后的清理请求。"""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.database.base import Base


class KnowledgeSearchSync(Base):
    """PG 为事实来源，ES 作为可重建的搜索索引。"""
    __tablename__ = "knowledge_search_sync"
    __table_args__ = (Index("idx_knowledge_search_sync_pending", "next_run_at", "lease_until"),)
    document_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    synced_revision: Mapped[int] = mapped_column(BigInteger, server_default=text("0"))
    desired_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    index_generation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
