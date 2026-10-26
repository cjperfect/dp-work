"""用户检索与服务端检索回调入口。"""
import secrets
from typing import Annotated
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core import config
from app.core.exceptions import ApiError
from app.core.responses import ApiCode, ApiResponse, ok
from app.modules.auth.dependencies import get_current_user
from app.modules.users.models import User
from . import rag, rag_access

router = APIRouter()


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_base_ids: list[int] = Field(min_length=1, max_length=20)
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=4, ge=1, le=8)

    @field_validator("query")
    @classmethod
    def query_required(cls, value):
        """排除空白查询。"""
        if not value.strip():
            raise ValueError("请输入检索内容。")
        return value.strip()


class InternalSearch(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    capability: str = Field(min_length=1, max_length=4096, repr=False)
    vector: list[float] = Field(min_length=1024, max_length=1024)
    profile: str = Field(pattern=r"^[0-9a-f]{64}$")
    top_k: int = Field(default=4, ge=1, le=8)


@router.post("/api/knowledge-bases/search", response_model=ApiResponse[list[dict]], summary="父子分块语义检索")
async def search(body: SearchInput, user: Annotated[User, Depends(get_current_user)]):
    """检索当前用户可访问的知识库，返回去重后的父块及引用。"""
    return ok(await rag.search(user.id, body.knowledge_base_ids, body.query, body.top_k))


@router.post("/api/internal/knowledge/search", response_model=ApiResponse[dict], include_in_schema=False)
async def internal_search(body: InternalSearch, x_internal_token: Annotated[str | None, Header()] = None):
    """仅接受 Sidecar 的服务凭证和固定范围的短时授权。"""
    if not config.SIDECAR_INTERNAL_TOKEN or not x_internal_token or not secrets.compare_digest(x_internal_token, config.SIDECAR_INTERNAL_TOKEN):
        raise ApiError(ApiCode.UNAUTHORIZED, "无效的内部服务凭证。", 401)
    return ok(await rag_access.retrieve_with_status(body.capability, body.vector, body.profile, body.top_k))
