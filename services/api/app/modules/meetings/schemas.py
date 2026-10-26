"""会议 API 数据结构。"""
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MeetingCreate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()), pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    title: str
    scheduled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """校验会议标题。"""
        value = value.strip()
        if not value:
            raise ValueError("请输入会议标题")
        return value


class MeetingState(MeetingCreate):
    model_config = ConfigDict(from_attributes=True)
    owner_id: int
    participants: list[str] = Field(default_factory=list)
    status: Literal["active", "paused", "ended", "archived"] = "active"
    elapsed_ms: int = Field(default=0, ge=0)
    resumed_at: datetime | None = None
    ended_at: datetime | None = None
    revision: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    minutes_status: int | None = None
    generation_status: Literal["idle", "generating", "ready", "failed"] = "idle"
    generation_error: str | None = None
    generation_ready_at: int | None = None
    generation_task_id: str | None = None
    generation_source_revision: int | None = None

    @field_validator("scheduled_at", "resumed_at", "ended_at", "created_at", "updated_at")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        """数据库中的无时区时间按 UTC 恢复。"""
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


class Segment(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str = Field(min_length=1, max_length=256)
    revision: int = Field(default=1, ge=1)
    seq: int = Field(ge=0)
    speaker: str | None = None
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_times(self):
        """校验片段结束时间。"""
        if self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("转写结束时间不能早于开始时间")
        return self


class Minutes(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    content: str = ""
    blocks: list[dict[str, Any]] | None = None
    status: Literal[0, 1, 2] = 1
    archived_document_id: str | int | None = None


class Workspace(BaseModel):
    meeting: MeetingState
    segments: list[Segment] = Field(default_factory=list, max_length=20000)
    minutes: Minutes | None = None

    @model_validator(mode="after")
    def validate_segments(self):
        """拒绝重复的片段 ID 或序号。"""
        if len({row.id for row in self.segments}) != len(self.segments) or len({row.seq for row in self.segments}) != len(self.segments):
            raise ValueError("转写片段 ID 和序号不能重复")
        return self


class MeetingSave(Workspace):
    expected_revision: int = Field(ge=1)


class GenerateMinutes(BaseModel):
    expected_revision: int = Field(ge=1)


class GenerationAccepted(BaseModel):
    task_id: str
    source_revision: int
    meeting: MeetingState
