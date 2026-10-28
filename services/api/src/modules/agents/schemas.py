"""Agent 输入协议，客户端只可提交普通对话消息。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=120000)


class AgentRequest(BaseModel):
    project_id: str | None = Field(default=None, pattern=r'^[a-fA-F0-9-]{36}$')
    model_config = ConfigDict(extra="forbid")
    agent_code: Literal["general", "product"] = "general"
    thread_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=128)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_messages(self):
        """限制上下文大小并要求末条为用户消息。"""
        if self.messages[-1].role != "user" or any(not row.content.strip() for row in self.messages):
            raise ValueError("最后一条必须是非空用户消息。")
        if sum(len(row.content) for row in self.messages) > 120000:
            raise ValueError("会话内容过长，请新建会话。")
        return self


class TitleRequest(BaseModel):
    """根据有限对话内容生成会话标题。"""
    model_config = ConfigDict(extra="forbid")
    thread_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    messages: list[ChatMessage] = Field(min_length=1, max_length=6)
    model: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_context(self):
        """限制标题输入大小并确保包含用户消息。"""
        if not any(row.role == "user" and row.content.strip() for row in self.messages):
            raise ValueError("标题生成需要用户消息。")
        if sum(len(row.content) for row in self.messages) > 16000:
            raise ValueError("标题输入过长。")
        return self
