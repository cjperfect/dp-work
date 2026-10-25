import asyncio
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from app.core.pagination import PageParams
from app.modules.knowledge.schemas import KnowledgeBasePage
from app.main import create_app
from app.modules.auth.dependencies import get_current_user
from app.modules.knowledge import service
from app.modules.users.models import User


def test_list_uses_authenticated_owner_and_query(monkeypatch):
    listing = AsyncMock(return_value=KnowledgeBasePage(item=[], total=0, page=2, page_size=10))
    monkeypatch.setattr(service, "list_knowledge_bases", listing)
    application = create_app()
    application.dependency_overrides[get_current_user] = lambda: User(id=42, username="tester")

    async def case():
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            response = await client.get("/api/knowledge-bases", params={"q": "产品", "owner_id": 99, "page": 2, "page_size": 10})
            assert response.status_code == 200
            assert response.json()["data"] == {"item": [], "total": 0, "page": 2, "page_size": 10}
            listing.assert_awaited_once_with(42, PageParams(page=2, page_size=10), "产品")

    asyncio.run(case())


def test_list_requires_login():
    async def case():
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
            assert (await client.get("/api/knowledge-bases")).status_code == 401

    asyncio.run(case())


def test_invalid_pagination_is_rejected():
    application = create_app()
    application.dependency_overrides[get_current_user] = lambda: User(id=42, username="tester")

    async def case():
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            for query in ({"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 101}, {"page": "bad"}):
                assert (await client.get("/api/knowledge-bases", params=query)).status_code == 422

    asyncio.run(case())
