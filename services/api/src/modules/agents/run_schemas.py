"""运行查询的响应结构。"""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class RunOut(BaseModel):
    """不包含正文、密钥或内部租约的运行元数据。"""
    id: str
    conversation_id: str
    agent_id: int
    response_id: str
    status: Literal["running", "completed", "failed", "cancelled", "interrupted"]
    model: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    deadline_at: datetime
    finished_at: datetime | None
