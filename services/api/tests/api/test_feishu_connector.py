"""飞书 CLI 接口鉴权与敏感信息隔离。"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.modules.auth.dependencies import get_current_user
from src.modules.connectors import service


def test_feishu_routes_require_authentication_and_validate_action():
    async def case():
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for method, path in (("get", ""), ("post", "/verify"), ("post", "/disconnect"),
                                 ("post", "/authorization/login"), ("delete", "/authorization")):
                assert (await getattr(client, method)("/api/connectors/feishu" + path)).status_code == 401
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)
            assert (await client.post("/api/connectors/feishu/authorization/execute")).status_code == 422
    asyncio.run(case())


def test_status_uses_authenticated_owner_and_filters_private_fields(monkeypatch):
    fake = AsyncMock(return_value=dict(installed=True, configured=True, connected=True,
        verified=True, account="测试账号", flow=None, access_token="secret"))
    monkeypatch.setattr(service, "status", fake)
    async def case():
        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/connectors/feishu/verify")
            assert response.status_code == 200
            assert "secret" not in response.text
            assert response.json()["data"]["verified"] is True
        fake.assert_awaited_once_with(7, verify=True)
    asyncio.run(case())
