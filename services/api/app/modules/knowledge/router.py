from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.core.pagination import PageParams
from app.core.responses import ApiResponse, ok
from app.modules.auth.dependencies import get_current_user
from app.modules.users.models import User

from . import service
from .schemas import KnowledgeBaseCreate, KnowledgeBaseOut, KnowledgeBasePage, KnowledgeBaseUpdate

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge"])


@router.post(
    "",
    response_model=ApiResponse[KnowledgeBaseOut],
    status_code=200,
    summary="新增知识库",
)
async def create_knowledge_base(
    body: KnowledgeBaseCreate,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KnowledgeBaseOut]:
    """处理新增知识库请求。"""
    return ok(await service.create_knowledge_base(user.id, body), message="知识库创建成功")


@router.get(
    "",
    response_model=ApiResponse[KnowledgeBasePage],
    summary="查询知识库列表",
)
async def list_knowledge_bases(
    user: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[PageParams, Depends()],
    q: Annotated[str, Query(description="按名称或描述搜索")] = "",
) -> ApiResponse[KnowledgeBasePage]:
    """查询当前用户的知识库。"""
    return ok(await service.list_knowledge_bases(user.id, pagination, q))


@router.put(
    "/{base_id}",
    response_model=ApiResponse[KnowledgeBaseOut],
    summary="修改知识库",
)
async def update_knowledge_base(
    base_id: Annotated[int, Path(ge=1, le=9_223_372_036_854_775_807)],
    body: KnowledgeBaseUpdate,
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[KnowledgeBaseOut]:
    """处理修改知识库请求。"""
    return ok(await service.update_knowledge_base(user.id, base_id, body), message="知识库修改成功")


@router.delete(
    "/{base_id}",
    response_model=ApiResponse[None],
    summary="删除知识库",
)
async def delete_knowledge_base(
    base_id: Annotated[int, Path(ge=1, le=9_223_372_036_854_775_807)],
    user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    """处理删除知识库请求。"""
    await service.delete_knowledge_base(user.id, base_id)
    return ok(message="知识库删除成功")
