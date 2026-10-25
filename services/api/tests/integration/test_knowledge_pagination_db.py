import asyncio
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.pagination import PageParams
from app.core.security import create_access_token
from app.infrastructure.database import session
from app.infrastructure.database.pagination import paginate
from app.main import create_app
from app.modules.knowledge.models import KnowledgeBase
from app.modules.users import service as users_service
from app.modules.users.models import User


def test_knowledge_pages_statistics_and_ownership():
    async def case():
        await session.init_db()
        owners = []
        try:
            for _ in range(2):
                owners.append(await users_service.create_user(f"pages-{uuid4().hex}", "test", "product"))
            async with session.transaction() as db:
                records = [KnowledgeBase(owner_id=owners[0].id, name=f"产品-{i}", description="API 文档" if i < 3 else "规范") for i in range(5)]
                db.add_all(records + [KnowledgeBase(owner_id=owners[1].id, name="其他用户", description="API 文档")])
                await db.flush()
                ids = [record.id for record in records]
            headers = {"Authorization": f"Bearer {create_access_token(owners[0].id, owners[0].role, owners[0].department)}"}
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
                first = (await client.get("/api/knowledge-bases", headers=headers, params={"page_size": 2})).json()["data"]
                second = (await client.get("/api/knowledge-bases", headers=headers, params={"page_size": 2, "page": 2})).json()["data"]
                assert first["total"] == 5
                assert set(first) == {"item", "total", "page", "page_size"}
                assert [row["id"] for row in first["item"] + second["item"]] == list(reversed(ids))[:4]
                matched = (await client.get("/api/knowledge-bases", headers=headers, params={"q": " api ", "page_size": 2})).json()["data"]
                assert matched["total"] == 3
                empty = (await client.get("/api/knowledge-bases", headers=headers, params={"page": 99})).json()["data"]
                assert empty["item"] == [] and empty["total"] == 5
                absent = (await client.get("/api/knowledge-bases", headers=headers, params={"q": "未匹配"})).json()["data"]
                assert absent["total"] == 0 and absent["item"] == []
                assert all(row["owner_id"] == owners[0].id for row in first["item"])
            async with session.read_session() as db:
                rows, total = await paginate(db, select(KnowledgeBase).where(KnowledgeBase.owner_id == owners[0].id).order_by(KnowledgeBase.id), PageParams(page=3, page_size=2))
                assert total == 5 and [row.id for row in rows] == [ids[-1]]
        finally:
            async with session.transaction() as db:
                owner_ids = [owner.id for owner in owners]
                await db.execute(delete(KnowledgeBase).where(KnowledgeBase.owner_id.in_(owner_ids)))
                await db.execute(delete(User).where(User.id.in_(owner_ids)))
            await session.close_db()

    asyncio.run(case())
