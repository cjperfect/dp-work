"""用户项目的目录元信息，实际访问授权保存在本机。"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.database.base import Base


class AgentProject(Base):
    __tablename__ = 'agent_projects'
    __table_args__ = (Index('idx_agent_projects_owner_updated', 'owner_id', 'updated_at'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    device_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(256))
    path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
