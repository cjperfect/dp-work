from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.infrastructure.database.pagination import paginate

from .models import KnowledgeBase


class KnowledgeRepository:
    """知识库数据访问。"""
    def __init__(self, db_session: AsyncSession):
        """接收数据库会话。"""
        self.session = db_session

    async def create(self, owner_id: int, name: str, description: str) -> KnowledgeBase:
        """新增知识库记录。"""
        record = KnowledgeBase(owner_id=owner_id, name=name, description=description)
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_by_owner(
        self, owner_id: int, params: PageParams, q: str = ""
    ) -> tuple[list[KnowledgeBase], int]:
        """分页查询用户知识库并统计数量。"""
        match = or_(
            KnowledgeBase.name.icontains(q, autoescape=True),
            KnowledgeBase.description.icontains(q, autoescape=True),
        )
        scope = KnowledgeBase.owner_id == owner_id
        statement = (
            select(KnowledgeBase).where(scope, match)
            .order_by(KnowledgeBase.updated_at.desc(), KnowledgeBase.id.desc())
        )
        return await paginate(self.session, statement, params)

    async def update(
        self, owner_id: int, base_id: int, name: str, description: str
    ) -> KnowledgeBase | None:
        """修改用户的知识库。"""
        statement = (
            update(KnowledgeBase)
            .where(KnowledgeBase.id == base_id, KnowledgeBase.owner_id == owner_id)
            .values(name=name, description=description)
            .returning(KnowledgeBase)
        )
        return await self.session.scalar(statement)

    async def delete(self, owner_id: int, base_id: int) -> bool:
        """删除用户的知识库。"""
        statement = (
            delete(KnowledgeBase)
            .where(KnowledgeBase.id == base_id, KnowledgeBase.owner_id == owner_id)
            .returning(KnowledgeBase.id)
        )
        return await self.session.scalar(statement) is not None
