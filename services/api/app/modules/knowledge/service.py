from app.core.exceptions import ApiError
from app.core.responses import ApiCode
from app.core.pagination import PageParams
from app.infrastructure.database import session

from .repository import KnowledgeRepository
from .schemas import KnowledgeBaseCreate, KnowledgeBaseOut, KnowledgeBasePage, KnowledgeBaseUpdate


async def create_knowledge_base(
    owner_id: int, body: KnowledgeBaseCreate
) -> KnowledgeBaseOut:
    """创建知识库并返回结果。"""
    async with session.transaction() as conn:
        record = await KnowledgeRepository(conn).create(owner_id, body.name, body.description)
        # 把数据库对象转换为接口响应数据
        return KnowledgeBaseOut.model_validate(record)


async def list_knowledge_bases(
    owner_id: int, params: PageParams, q: str = ""
) -> KnowledgeBasePage:
    """查询知识库分页。"""
    async with session.read_session() as conn:
        records, total = await KnowledgeRepository(conn).list_by_owner(
            owner_id, params, q.strip()
        )
        return KnowledgeBasePage(
            item=[KnowledgeBaseOut.model_validate(record) for record in records],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )


async def update_knowledge_base(
    owner_id: int, base_id: int, body: KnowledgeBaseUpdate
) -> KnowledgeBaseOut:
    """修改知识库。"""
    async with session.transaction() as conn:
        record = await KnowledgeRepository(conn).update(owner_id, base_id, body.name, body.description)
        if record is None:
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
        return KnowledgeBaseOut.model_validate(record)


async def delete_knowledge_base(owner_id: int, base_id: int) -> None:
    """删除知识库。"""
    async with session.transaction() as conn:
        if not await KnowledgeRepository(conn).delete(owner_id, base_id):
            raise ApiError(ApiCode.NOT_FOUND, "知识库不存在", 404)
