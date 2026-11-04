"""项目管理适配。"""
import asyncio
from pydantic import BaseModel, ConfigDict, Field
from ..types import OperationError


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: int = Field(gt=0)
    device_id: str = Field(pattern=r"^[a-fA-F0-9-]{36}$")
    body: dict = Field(default_factory=dict)


async def project_operation(action, params, state):
    """项目列表与元数据只在当前执行设备存储。"""
    from ...sessions.projects import operation
    from ...sessions.storage import SessionError
    from ...providers.llm.schemas import ModelError
    body = ProjectInput.model_validate(params)
    try:
        return await asyncio.to_thread(operation, action, body.owner_id, body.body, body.device_id)
    except (SessionError, ModelError, ValueError) as cause:
        raise OperationError(getattr(cause, "status", 409), str(cause)) from cause

