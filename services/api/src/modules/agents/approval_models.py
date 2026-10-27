"""工具审批记录与一次性决定。"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, String, func, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.database.base import Base


class AgentApproval(Base):
    __tablename__ = 'agent_approvals'
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name='ck_agent_approvals_status'),
        Index('idx_agent_approvals_run_created', 'run_id', 'created_at'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.id', ondelete='CASCADE'))
    interrupts: Mapped[list] = mapped_column(JSONB)
    knowledge_base_ids: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
