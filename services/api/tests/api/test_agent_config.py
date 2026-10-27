"""Agent 配置通过鉴权后的设备通道读取。"""
import asyncio
from unittest.mock import AsyncMock
import httpx
from src.main import create_app
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User
from src.modules.agents import router as agents_router


def test_agent_config_requires_auth_and_valid_agent(monkeypatch):
    app = create_app()
    operation = AsyncMock(return_value={'agent_code': 'product', 'prompt': '产品规范', 'prompt_file': 'AGENT.md'})
    monkeypatch.setattr(agents_router, 'sidecar', operation)
    async def case():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get('/api/agents/config?agent_code=product')).status_code == 401
            assert (await client.put('/api/agents/config', json={'agent_code': 'product', 'prompt': '更新', 'expected_prompt': '原始'})).status_code == 401
            operation.assert_not_awaited()
            app.dependency_overrides[get_current_user] = lambda: User(id=1, username='fixture', password_hash='none', role='admin', department='product', status=0)
            response = await client.get('/api/agents/config?agent_code=product')
            assert response.status_code == 200 and response.json()['data']['prompt'] == '产品规范'
            operation.assert_awaited_once_with('/agents/config', {'agent_code': 'product'})
            assert (await client.get('/api/agents/config?agent_code=../general')).status_code == 422
            updated = await client.put('/api/agents/config', json={'agent_code': 'product', 'prompt': '更新', 'expected_prompt': '原始'})
            assert updated.status_code == 200
            operation.assert_awaited_with('/agents/config/update', {'agent_code': 'product', 'prompt': '更新', 'expected_prompt': '原始'})
    asyncio.run(case())
