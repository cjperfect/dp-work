from datetime import datetime

from app.core.pagination import Page

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
    created_at: datetime
    updated_at: datetime


class KnowledgeBasePage(Page[KnowledgeBaseOut]):
    """知识库分页数据。"""
