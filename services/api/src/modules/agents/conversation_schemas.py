"""会话 CRUD、分支快照及迁移协议。"""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .schemas import AgentRequest


class MessageIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=256)
    seq: int = Field(default=0, ge=0)
    role: Literal['user', 'assistant']
    content: str = Field(max_length=120000)
    status: Literal['streaming', 'waiting_approval', 'complete', 'failed', 'cancelled'] = 'complete'
    created_at: datetime
    context: dict = Field(default_factory=dict)


class BranchIn(BaseModel):
    parentId: str | None = Field(default=None, max_length=256)
    message: MessageIn


class ThreadCreate(BaseModel):
    project_id: str | None = Field(default=None, pattern=r'^[a-fA-F0-9-]{36}$')
    model_config = ConfigDict(extra='forbid')
    id: str = Field(default_factory=lambda: str(uuid4()), pattern=r'^[a-zA-Z0-9_-]{1,128}$')
    agent_id: Literal[1, 2]
    knowledge_base_ids: list[int | str] = Field(default_factory=list, max_length=20)


class DraftSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=0)
    draft: str = Field(max_length=120000)
    knowledge_base_ids: list[int | str] = Field(default_factory=list, max_length=20)


class GraphSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=0)
    messages: list[MessageIn] = Field(default_factory=list, max_length=5000)
    message_branches: list[BranchIn] = Field(default_factory=list, max_length=5000)

    @model_validator(mode='after')
    def validate_graph(self):
        """拒绝重复 ID、父节点冲突、循环和过大的历史。"""
        nodes = {entry.message.id: entry for entry in self.message_branches}
        if len(nodes) != len(self.message_branches) or len({row.id for row in self.messages}) != len(self.messages):
            raise ValueError('消息 ID 重复。')
        for index, message in enumerate(self.messages):
            parent = self.messages[index - 1].id if index else None
            if message.id in nodes and nodes[message.id].parentId != parent:
                raise ValueError('消息父节点冲突。')
            nodes[message.id] = BranchIn(parentId=parent, message=message)
        if len(nodes) > 5000 or sum(len(entry.message.content) + len(str(entry.message.context)) for entry in nodes.values()) > 4000000:
            raise ValueError('会话过大，请新建会话。')
        completed = set()
        for key in nodes:
            path, current = set(), key
            while current is not None and current not in completed:
                if current in path or current not in nodes:
                    raise ValueError('消息分支存在循环或缺失父节点。')
                path.add(current)
                current = nodes[current].parentId
            completed.update(path)
        return self


class RenameThread(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    title_source: Literal['manual', 'generated'] = 'manual'
    first_message_id: str | None = Field(default=None, max_length=256)


class LegacyThread(BaseModel):
    model_config = ConfigDict(extra='ignore')
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,128}$')
    agent_id: Literal[1, 2]
    title: str = Field(default='新会话', max_length=200)
    title_source: Literal['pending', 'manual', 'generated'] = 'pending'
    draft: str = Field(default='', max_length=120000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ImportThread(GraphSave):
    expected_revision: int = 0
    thread: LegacyThread
    knowledge_base_ids: list[int | str] = Field(default_factory=list, max_length=20)


class StoredChat(AgentRequest):
    response_id: str = Field(min_length=1, max_length=256)
    expected_revision: int = Field(ge=0)
