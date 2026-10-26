"""会议纪要生成的内部协议。"""
from datetime import datetime
from pydantic import BaseModel, Field


class TranscriptInput(BaseModel):
    id: str
    seq: int = Field(ge=0)
    speaker: str | None = None
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int | None = None


class MinutesInput(BaseModel):
    task_id: str
    meeting_id: str
    source_revision: int = Field(ge=1)
    title: str = Field(min_length=1)
    scheduled_at: datetime
    segments: list[TranscriptInput] = Field(min_length=1, max_length=20000)


class MinutesOutput(BaseModel):
    task_id: str
    source_revision: int
    content: str
    model: str
    prompt_version: str
