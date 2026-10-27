"""用户会话与带父节点的消息历史。"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.database.base import Base


class Conversation(Base):
    """当前路径和草稿独立保存，删除后保留 ID 防止旧客户端复活。"""
    __tablename__ = 'conversations'
    __table_args__ = (Index('idx_conversations_owner_updated', 'owner_id', 'updated_at'),)
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    agent_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), server_default='新会话')
    title_source: Mapped[str] = mapped_column(String(16), server_default='pending')
    draft: Mapped[str] = mapped_column(Text, server_default='')
    draft_revision: Mapped[int] = mapped_column(Integer, server_default=text('0'))
    knowledge_base_ids: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    active_path: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    run_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    run_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationMessage(Base):
    """同一会话内消息 ID 唯一，父 ID 组成编辑后的分支树。"""
    __tablename__ = 'conversation_messages'
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), primary_key=True)
    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default='complete')
    context: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
