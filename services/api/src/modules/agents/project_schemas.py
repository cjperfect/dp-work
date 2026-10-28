"""项目目录与会话关联参数。"""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[a-fA-F0-9-]{36}$')
    device_id: str = Field(pattern=r'^[a-fA-F0-9-]{36}$')
    name: str = Field(min_length=1, max_length=256)
    path: str = Field(min_length=1, max_length=4096)

    @field_validator('name', 'path')
    @classmethod
    def nonblank(cls, value):
        """拒绝空白目录元信息。"""
        if not value.strip() or '\x00' in value: raise ValueError('项目名称和目录不能为空。')
        return value.strip()


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class ThreadProject(BaseModel):
    project_id: str | None = Field(default=None, pattern=r'^[a-fA-F0-9-]{36}$')
    expected_revision: int = Field(ge=0)
