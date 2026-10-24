from pydantic import BaseModel, Field


class SegmentIn(BaseModel):
    id: str | None = Field(default=None, description="分句 id = 幂等键；缺省则生成")
    seq: int
    speaker: str | None = None
    text: str
    start_ms: int | None = None
    end_ms: int | None = None


class SegmentsBatch(BaseModel):
    meeting_id: str
    segments: list[SegmentIn] = Field(max_length=200)


class MinutesUpdateIn(BaseModel):
    title: str | None = None
    content: str | None = None
    status: int | None = None  # 0 生成中 / 1 已生成 / 2 已发布到知识库
