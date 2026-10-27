from datetime import datetime
from typing import Any, Literal

from src.core.pagination import Page

from pydantic import BaseModel, ConfigDict, field_validator


class KnowledgeBaseCreate(BaseModel):
    """新增知识库请求参数。"""
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """校验知识库名称。"""
        value = value.strip()
        if not value:
            raise ValueError("请输入知识库名称")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        """清理描述首尾空白。"""
        return value.strip()


class KnowledgeBaseUpdate(KnowledgeBaseCreate):
    """修改知识库请求参数。"""


class KnowledgeBaseOut(BaseModel):
    """知识库响应数据。"""
    # 允许接收数据库对象
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    description: str
    document_count: int = 0
    created_at: datetime
    updated_at: datetime


class KnowledgeBasePage(Page[KnowledgeBaseOut]):
    """知识库分页数据。"""


class KnowledgeDocumentContent(BaseModel):
    """在线文档自动保存参数。"""
    model_config = ConfigDict(extra="forbid")

    title: str = "未命名文档"
    content: str = ""
    blocks: list[dict[str, Any]] | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """清理标题，空标题使用默认名称。"""
        return value.strip() or "未命名文档"


class KnowledgeDocumentSave(KnowledgeDocumentContent):
    """保存正文时可保留服务端的最新标题。"""
    preserve_title: bool = False


class KnowledgeDocumentRename(BaseModel):
    """只修改文档标题。"""
    model_config = ConfigDict(extra="forbid")
    title: str


class KnowledgeDocumentOut(KnowledgeDocumentContent):
    """在线文档响应数据。"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    knowledge_base_id: int
    source: Literal["editor", "upload"] = "editor"
    file_type: Literal["txt", "md", "pdf", "doc", "docx"] = "md"
    original_name: str | None = None
    byte_size: int = 0
    created_at: datetime
    updated_at: datetime

    parse_status: Literal["unparsed", "queued", "parsing", "parsed", "failed"] = "unparsed"
    parse_content: str | None = None
    parse_error: str | None = None
    parsed_at: datetime | None = None
    parse_blocks: list[dict[str, Any]] | None = None
    vectorized_at: datetime | None = None
    vector_status: Literal["unindexed", "queued", "indexing", "indexed", "failed"] = "unindexed"
    vector_error: str | None = None
    vector_task_id: str | None = None
    vector_done: int = 0
    vector_total: int = 0


class ParsedDocumentSave(BaseModel):
    """保存人工修订的解析正文。"""
    model_config = ConfigDict(extra="forbid")
    content: str
    blocks: list[dict[str, Any]] | None = None
    expected_parsed_at: datetime


class VectorizeDocument(BaseModel):
    """固定已保存的解析正文版本。"""
    model_config = ConfigDict(extra="forbid")
    expected_parsed_at: datetime
