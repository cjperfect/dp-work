from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert

from app.core.pagination import PageParams
from app.infrastructure.database.pagination import paginate

from .models import KnowledgeBase, KnowledgeDocument


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
            .values(
                name=name,
                description=description,
                # 应用层维护 updated_at：SQLite 无触发器且 CURRENT_TIMESTAMP 仅秒级，
                # 使用 Python 时间戳保证微秒精度，PG 下触发器会再覆盖为更精确值。
                updated_at=datetime.now(timezone.utc),
            )
            .returning(KnowledgeBase)
        )
        return await self.session.scalar(statement)

    async def delete(self, owner_id: int, base_id: int) -> bool:
        """删除用户的知识库。"""
        await self.session.execute(delete(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == base_id,
            KnowledgeDocument.knowledge_base_id.in_(select(KnowledgeBase.id).where(KnowledgeBase.owner_id == owner_id)),
        ))
        statement = (
            delete(KnowledgeBase)
            .where(KnowledgeBase.id == base_id, KnowledgeBase.owner_id == owner_id)
            .returning(KnowledgeBase.id)
        )
        return await self.session.scalar(statement) is not None


    async def owns_base(self, owner_id: int, base_id: int) -> bool:
        """检查知识库归属。"""
        return await self.session.scalar(select(KnowledgeBase.id).where(
            KnowledgeBase.id == base_id, KnowledgeBase.owner_id == owner_id
        )) is not None

    async def list_documents(self, base_id: int) -> list[KnowledgeDocument]:
        """查询知识库的在线文档。"""
        return list((await self.session.scalars(select(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == base_id
        ).order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id))).all())

    async def get_document(self, base_id: int, document_id: str) -> KnowledgeDocument | None:
        """读取知识库内的指定文档。"""
        return await self.session.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == base_id, KnowledgeDocument.id == document_id
        ))

    async def save_document(self, base_id: int, document_id: str, values: dict) -> KnowledgeDocument | None:
        """按文档 ID 幂等创建或更新，禁止跨知识库覆盖。"""
        now = datetime.now(timezone.utc)
        statement = insert(KnowledgeDocument).values(
            id=document_id, knowledge_base_id=base_id, **values, updated_at=now
        )
        statement = statement.on_conflict_do_update(
            index_elements=[KnowledgeDocument.id],
            set_={**values, "updated_at": now},
            where=(KnowledgeDocument.knowledge_base_id == base_id) & (KnowledgeDocument.source == "editor"),
        ).returning(KnowledgeDocument)
        record = await self.session.scalar(statement)
        if record is not None:
            await self.session.execute(update(KnowledgeBase).where(KnowledgeBase.id == base_id).values(updated_at=now))
        return record


    async def document_counts(self, base_ids: list[int]) -> dict[int, int]:
        """批量统计在线文档数量。"""
        if not base_ids:
            return {}
        rows = await self.session.execute(select(
            KnowledgeDocument.knowledge_base_id, func.count(KnowledgeDocument.id)
        ).where(KnowledgeDocument.knowledge_base_id.in_(base_ids)).group_by(KnowledgeDocument.knowledge_base_id))
        return dict(rows.all())


    async def delete_document(self, base_id: int, document_id: str) -> bool:
        """删除指定知识库中的文档。"""
        statement = delete(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == base_id,
            KnowledgeDocument.id == document_id,
        ).returning(KnowledgeDocument.id)
        removed = await self.session.scalar(statement) is not None
        if removed:
            await self.session.execute(update(KnowledgeBase).where(KnowledgeBase.id == base_id)
                                      .values(updated_at=datetime.now(timezone.utc)))
        return removed


    async def create_upload(self, base_id: int, values: dict) -> KnowledgeDocument:
        """新增上传文档记录并更新知识库时间。"""
        record = KnowledgeDocument(knowledge_base_id=base_id, **values)
        self.session.add(record)
        await self.session.flush()
        await self.session.execute(update(KnowledgeBase).where(KnowledgeBase.id == base_id)
                                   .values(updated_at=datetime.now(timezone.utc)))
        return record
