"""记忆管理和作用范围协议。"""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Kind = Literal['preference', 'fact', 'experience']
Scope = Literal['user', 'agent', 'project']
AgentCode = Literal['general', 'product', 'ui']


class MemoryWrite(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=2000)
    kind: Kind = 'preference'
    scope: Scope = 'user'
    agent_code: AgentCode | None = None
    project_id: UUID | None = None
    enabled: bool = True
    expires_at: datetime | None = None

    @field_validator('title', 'content')
    @classmethod
    def meaningful_text(cls, value):
        """拒绝空白标题和正文。"""
        value = value.strip()
        if not value or '\x00' in value:
            raise ValueError('请输入有效的记忆标题和关键信息。')
        return value

    @model_validator(mode='after')
    def valid_scope(self):
        """范围必须与目标 Agent 或项目一致。"""
        if self.scope == 'user' and (self.agent_code or self.project_id):
            raise ValueError('用户记忆不能指定 Agent 或项目。')
        if self.scope == 'agent' and (not self.agent_code or self.project_id):
            raise ValueError('请选择 Agent，且不要指定项目。')
        if self.scope == 'project' and (not self.project_id or self.agent_code):
            raise ValueError('请选择项目，且不要指定 Agent。')
        if self.expires_at:
            if self.expires_at.tzinfo is None:
                raise ValueError('过期时间必须包含时区。')
            self.expires_at = self.expires_at.astimezone(timezone.utc)
        return self


class MemoryUpdate(MemoryWrite):
    expected_revision: int = Field(ge=1)


class MemoryDelete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)


class MemoryQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    q: str = Field(default='', max_length=120)
    scope: Scope | None = None
    kind: Kind | None = None
    agent_code: AgentCode | None = None
    project_id: UUID | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=8, ge=1, le=100)


class MemoryPreference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool | None = None
    auto_generate: bool | None = None
    expected_revision: int = Field(ge=1)

    @model_validator(mode='after')
    def has_change(self):
        """读取和生成分别控制，至少修改一项。"""
        if self.enabled is None and self.auto_generate is None:
            raise ValueError('请选择需要修改的记忆设置。')
        return self
