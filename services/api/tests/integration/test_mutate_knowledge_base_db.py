import asyncio
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.infrastructure.database import session
from app.main import create_app
from app.modules.knowledge.models import KnowledgeBase
from app.modules.users import service as users_service
from app.modules.users.models import User


def test_mutations_persist_enforce_ownership_and_update_list():
    async def case():
        await session.init_db()
        owners = []
        try:
            for _ in range(2):
                owners.append(await users_service.create_user(f"mutation-{uuid4().hex}", "test", "product"))
            headers = [{"Authorization": f"Bearer {create_access_token(owner.id, owner.role, owner.department)}"} for owner in owners]
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
                record = (await client.post("/api/knowledge-bases", headers=headers[0], json={"name": "原名称", "description": "原描述"})).json()["data"]
                path = f'/api/knowledge-bases/{record["id"]}'
                for auth in (headers[1],):
                    assert (await client.put(path, headers=auth, json={"name": "越权"})).status_code == 404
                    assert (await client.delete(path, headers=auth)).status_code == 404
                async with session.read_session() as db:
                    assert (await db.get(KnowledgeBase, record["id"])).name == "原名称"
                response = await client.put(path, headers=headers[0], json={"name": " 更新名称 ", "description": " 新描述 "})
                assert response.status_code == 200
                updated = response.json()["data"]
                assert updated["id"] == record["id"] and updated["owner_id"] == owners[0].id
                assert updated["created_at"] == record["created_at"]
                assert updated["updated_at"] > record["updated_at"]
                async with session.read_session() as db:
                    persisted = await db.get(KnowledgeBase, record["id"])
                    assert (persisted.name, persisted.description) == ("更新名称", "新描述")
                invalid = await client.put(path, headers=headers[0], json={"name": " "})
                assert invalid.status_code == 422
                listing = (await client.get("/api/knowledge-bases", headers=headers[0], params={"q": "新描述"})).json()["data"]
                assert listing["total"] == 1 and listing["item"][0]["name"] == "更新名称"
                assert (await client.delete(path, headers=headers[0])).status_code == 200
                assert (await client.delete(path, headers=headers[0])).status_code == 404
                assert (await client.put(path, headers=headers[0], json={"name": "已删除"})).status_code == 404
                async with session.read_session() as db:
                    assert await db.get(KnowledgeBase, record["id"]) is None
                listing = (await client.get("/api/knowledge-bases", headers=headers[0])).json()["data"]
                assert listing["total"] == 0 and listing["item"] == []
        finally:
            async with session.transaction() as db:
                ids = [owner.id for owner in owners]
                await db.execute(delete(KnowledgeBase).where(KnowledgeBase.owner_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))
            await session.close_db()

    asyncio.run(case())
