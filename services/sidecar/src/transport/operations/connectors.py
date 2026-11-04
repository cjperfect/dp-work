"""连接器授权适配。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from ..types import OperationError


class ConnectorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: int = Field(gt=0)
    action: Literal["configure", "login"] = "login"


async def connector_operation(operation, params, state):
    """CLI 授权与凭证只在当前用户设备执行。"""
    from ...connectors import service
    from ...connectors.errors import ConnectorError
    body = ConnectorInput.model_validate(params)
    try:
        if operation in ("status", "verify"):
            return await service.status(body.owner_id, verify=operation == "verify")
        if operation == "start":
            return await service.start(body.owner_id, body.action)
        if operation == "cancel":
            await service.cancel(body.owner_id)
        else:
            await service.logout(body.owner_id)
        return None
    except ConnectorError as cause:
        raise OperationError(cause.status_code, cause.message) from cause

