import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.modules.auth.dependencies import get_current_user
from src.modules.knowledge import service
from src.modules.knowledge.schemas import KnowledgeBaseOut
from src.modules.users.models import User


def test_create_uses_authenticated_owner_and_rejects_client_owned_fields(monkeypatch):
    now = datetime.now(timezone.utc)
    create = AsyncMock(return_value=KnowledgeBaseOut(id=1, owner_id=42, name="项目资料", description="规范", created_at=now, updated_at=now))
    monkeypatch.setattr(service, "create_knowledge_base", create)
    application = create_app()
    application.dependency_overrides[get_current_user] = lambda: User(id=42, username="tester")

    async def case():
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            response = await client.post("/api/knowledge-bases", json={"name": " 项目资料 ", "description": " 规范 "})
            assert response.status_code == 200
            assert response.json()["data"]["owner_id"] == 42
            owner, body = create.await_args.args
            assert owner == 42
            assert body.name == "项目资料"
            assert body.description == "规范"
            for payload in ({"name": " "}, {"name": "资料", "owner_id": 99}, {"name": "资料", "id": 10}):
                assert (await client.post("/api/knowledge-bases", json=payload)).status_code == 422
            assert create.await_count == 1

    asyncio.run(case())


def test_create_requires_authentication():
    async def case():
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
            response = await client.post("/api/knowledge-bases", json={"name": "资料"})
            assert response.status_code == 401
            assert response.json()["data"] is None

    asyncio.run(case())
