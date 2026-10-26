"""父块保存完整上下文，子块保存检索向量。"""
from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.infrastructure.database.base import Base


class KnowledgeParentChunk(Base):
    """可供模型阅读和引用的父块。"""
    __tablename__ = "knowledge_parent_chunks"
    __table_args__ = (Index("idx_knowledge_parent_document", "document_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"))
    task_id: Mapped[str] = mapped_column(String(36))
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    chunk_metadata: Mapped[dict] = mapped_column(JSON)


class KnowledgeChildChunk(Base):
    """带父块关联的细粒度向量索引。"""
    __tablename__ = "knowledge_child_chunks"
    __table_args__ = (
        Index("idx_knowledge_child_parent", "parent_id"),
        Index("idx_knowledge_child_embedding", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_id: Mapped[str] = mapped_column(ForeignKey("knowledge_parent_chunks.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))
