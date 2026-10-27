from datetime import datetime

from sqlalchemy import (
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base


class KnowledgeBase(Base):
    """知识库表模型。"""
    __tablename__ = "knowledge_bases"
    __table_args__ = (Index("idx_knowledge_bases_owner_id", "owner_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=FetchedValue(),
    )


class KnowledgeDocument(Base):
    """在线文档，保存富文本块与 Markdown 正文。"""
    __tablename__ = "knowledge_documents"
    __table_args__ = (Index("idx_knowledge_documents_base_id", "knowledge_base_id"), Index("idx_knowledge_vector_status", "vector_status"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("knowledge_bases.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, server_default=text("''"))
    blocks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(16), server_default=text("'editor'"))
    file_type: Mapped[str] = mapped_column(String(16), server_default=text("'md'"))
    original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer, server_default=text("'0'"))
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parse_status: Mapped[str] = mapped_column(String(16), server_default=text("'unparsed'"), index=True)
    parse_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_metadata: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parse_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parse_claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    parse_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parse_blocks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    vectorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    vector_status: Mapped[str] = mapped_column(String(16), server_default=text("'unindexed'"))
    vector_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    vector_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    vector_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vector_claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    vector_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vector_profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vector_done: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    vector_total: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    vector_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
