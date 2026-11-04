"""长期记忆管理适配。"""
import asyncio
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from ..types import OperationError


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    owner_id: int = Field(gt=0)
    key: str | None = Field(default=None, pattern=r'^[a-fA-F0-9-]{36}$')
    body: dict = Field(default_factory=dict)


async def memory_operation(action, params, state):
    """记忆只在本机按账号处理，不接受网页指定存储路径。"""
    import sqlite3
    from ...memory.service import operation
    from ...memory.repository import MemoryError
    from ...sessions.storage import SessionError
    from ...providers.llm.schemas import ModelError
    data = MemoryInput.model_validate(params)
    try:
        return await asyncio.to_thread(operation, action, data.owner_id, data.body, data.key)
    except ValidationError as cause:
        raise OperationError(400, cause.errors()[0]['msg']) from cause
    except (MemoryError, SessionError, ModelError) as cause:
        raise OperationError(getattr(cause, 'status', 409), str(cause)) from cause
    except (ValueError, TypeError) as cause:
        raise OperationError(400, '记忆参数无效。') from cause
    except (sqlite3.DatabaseError, OSError) as cause:
        raise OperationError(500, '记忆存储不可用，请检查本机数据文件。') from cause

