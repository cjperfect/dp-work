"""传输层共用的结果、错误与配置输入。"""
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable, Literal
from pydantic import BaseModel, ConfigDict, Field


class OperationError(Exception):
    """可安全展示的业务错误，状态用于现有 API 兼容适配。"""
    def __init__(self, status, message, code=None):
        super().__init__(message)
        self.status = status
        self.detail = {"message": message, **({"code": code} if code else {})}


@dataclass
class EventStream:
    events: AsyncIterator[dict]
    on_close: Callable[[], Awaitable[None]] | None = None

    async def aclose(self):
        """即使还没读到第一条事件，也执行运行所属的清理。"""
        try:
            await self.events.aclose()
        finally:
            if self.on_close is not None:
                callback, self.on_close = self.on_close, None
                await callback()


class LocalSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: int = Field(gt=0)
    kind: Literal["model", "asr"] = "model"
    body: dict = Field(default_factory=dict)

