import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.modules.auth.dependencies import get_current_user
from src.modules.knowledge import service
from src.modules.knowledge.schemas import KnowledgeBaseOut
from src.modules.users.models import User


def test_update_and_delete_use_authenticated_owner(monkeypatch):
    now = datetime.now(timezone.utc)
    update = AsyncMock(return_value=KnowledgeBaseOut(id=7, owner_id=42, name="修改后", description="描述", created_at=now, updated_at=now))
    deletion = AsyncMock()
    monkeypatch.setattr(service, "update_knowledge_base", update)
    monkeypatch.setattr(service, "delete_knowledge_base", deletion)
    application = create_app()
    application.dependency_overrides[get_current_user] = lambda: User(id=42, username="tester")

    async def case():
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            response = await client.put("/api/knowledge-bases/7", json={"name": " 修改后 ", "description": " 描述 "})
            assert response.status_code == 200
            assert response.json()["data"]["name"] == "修改后"
            owner, base_id, body = update.await_args.args
            assert (owner, base_id, body.name, body.description) == (42, 7, "修改后", "描述")
            response = await client.delete("/api/knowledge-bases/7")
            assert response.status_code == 200
            assert response.json() == {"code": 0, "message": "知识库删除成功", "data": None}
            deletion.assert_awaited_once_with(42, 7)
            for payload in ({"name": " "}, {"name": "名称", "owner_id": 99}, {"name": "名称", "id": 8}):
                assert (await client.put("/api/knowledge-bases/7", json=payload)).status_code == 422
            for base_id in ("0", "-1", "invalid", "9223372036854775808"):
                assert (await client.put(f"/api/knowledge-bases/{base_id}", json={"name": "名称"})).status_code == 422
                assert (await client.delete(f"/api/knowledge-bases/{base_id}")).status_code == 422
            assert update.await_count == 1 and deletion.await_count == 1

    asyncio.run(case())


def test_update_and_delete_require_login():
    async def case():
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
            assert (await client.put("/api/knowledge-bases/1", json={"name": "名称"})).status_code == 401
            assert (await client.delete("/api/knowledge-bases/1")).status_code == 401

    asyncio.run(case())
