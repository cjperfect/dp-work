"""审批入口必须登录，决定仅允许一次批准或拒绝。"""
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock
import httpx
from src.main import create_app
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from src.modules.agents import approval_service


def test_approval_routes_validate_auth_and_decisions(monkeypatch):
    app = create_app()
    listing = AsyncMock(return_value=[])
    monkeypatch.setattr(approval_service, 'list_approvals', listing)
    async def case():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get('/api/agents/approvals?conversation_id=one')).status_code == 401
            path = '/api/agents/approvals/'+str(uuid4())+'/decide'
            assert (await client.post(path, json={'decision':'approve'})).status_code == 401
            app.dependency_overrides[get_current_user] = lambda: User(id=1, username='fixture', password_hash='none', role='admin', department='product', status=0)
            assert (await client.get('/api/agents/approvals?conversation_id=one')).status_code == 200
            listing.assert_awaited_once_with(1, 'one')
            assert (await client.post(path, json={'decision':'always'})).status_code == 422
            assert (await client.post(path, json={'decision':'approve', 'args':{'command':'alter'}})).status_code == 422
    asyncio.run(case())
