"""会话执行适配。"""
from pydantic import BaseModel, ConfigDict, Field
from ...providers.settings import RuntimeConfig
from ..types import OperationError


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: int = Field(gt=0)
    thread_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,128}$")
    body: dict = Field(default_factory=dict)
    runtime: RuntimeConfig | None = None
    retrieval_token: str | None = Field(default=None, repr=False, max_length=4096)


async def session_operation(action, params, state):
    """执行本机会话方法并返回统一业务错误。"""
    from ...sessions import service
    from ...sessions.storage import SessionError
    params = SessionInput.model_validate(params).model_dump(mode="json", exclude_none=True)
    try:
        if action in ("chat", "approval.decide", "resume"):
            return await service.open_chat(params, state, resume="checkpoint" if action == "resume" else action.endswith("decide"))
        return await service.operation(action, params, state)
    except SessionError as cause:
        raise OperationError(cause.status, str(cause)) from cause

