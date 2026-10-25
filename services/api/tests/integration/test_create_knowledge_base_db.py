import asyncio
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.infrastructure.database import session
from app.main import create_app
from app.modules.knowledge.models import KnowledgeBase
from app.modules.users import service as users_service
from app.modules.users.models import User


def test_authenticated_creation_commits_to_sqlite():
    async def case():
        await session.init_db()
        owners = []
        try:
            for _ in range(2):
                owners.append(await users_service.create_user(f"knowledge-{uuid4().hex}", "test-password", "product"))
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
                for owner in owners:
                    token = create_access_token(owner.id, owner.role, owner.department)
                    response = await client.post("/api/knowledge-bases", headers={"Authorization": f"Bearer {token}"}, json={"name": " 项目资料 "})
                    assert response.status_code == 200
                    body = response.json()
                    assert body["code"] == 0
                    data = body["data"]
                    assert type(data["id"]) is int and data["id"] > 0
                    assert data["owner_id"] == owner.id
                    assert data["name"] == "项目资料"
                    assert data["description"] == ""
                    assert data["created_at"] and data["updated_at"]
                    async with session.read_session() as conn:
                        record = await conn.get(KnowledgeBase, data["id"])
                        assert record.owner_id == owner.id
                        assert record.name == "项目资料"
                        assert record.description == ""
                for owner in owners:
                    headers = {"Authorization": f"Bearer {create_access_token(owner.id, owner.role, owner.department)}"}
                    for query, count in (("", 1), (" 项目 ", 1), ("不存在", 0), ("%", 0), ("_", 0)):
                        response = await client.get("/api/knowledge-bases", headers=headers, params={"q": query})
                        assert response.status_code == 200
                        rows = response.json()["data"]["item"]
                        assert len(rows) == count
                        assert all(row["owner_id"] == owner.id for row in rows)
                async with session.read_session() as conn:
                    records = (await conn.scalars(select(KnowledgeBase).where(KnowledgeBase.owner_id.in_([owner.id for owner in owners])))).all()
                    assert len(records) == 2
                    assert records[0].id != records[1].id
        finally:
            async with session.transaction() as conn:
                ids = [owner.id for owner in owners]
                await conn.execute(delete(KnowledgeBase).where(KnowledgeBase.owner_id.in_(ids)))
                await conn.execute(delete(User).where(User.id.in_(ids)))
            await session.close_db()

    asyncio.run(case())
