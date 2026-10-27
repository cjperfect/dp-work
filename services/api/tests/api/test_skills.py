"""技能接口鉴权、参数与本机执行服务对接。"""
import asyncio
from unittest.mock import AsyncMock
import httpx
from src.main import create_app
from src.core.exceptions import ApiError
from src.core.responses import ApiCode
from src.modules.auth.dependencies import get_current_user
from src.modules.skills import router as skills_router
from src.modules.users.models import User


def test_skill_routes_require_auth_and_dispatch_validated_parameters(monkeypatch):
    app = create_app()
    operation = AsyncMock(return_value={"items": []})
    monkeypatch.setattr(skills_router, 'sidecar', operation)
    async def case():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get('/api/skills?agent_code=general')).status_code == 401
            assert (await client.post('/api/skills/install', json={'agent_code': 'general', 'source': 'a/b@skill'})).status_code == 401
            app.dependency_overrides[get_current_user] = lambda: User(id=1, username='fixture', password_hash='none', role='admin', department='product', status=0)
            assert (await client.get('/api/skills?agent_code=general')).status_code == 200
            operation.assert_awaited_with('/skills/list', {'agent_code': 'general'})
            assert (await client.get('/api/skills/search?q=react')).status_code == 200
            operation.assert_awaited_with('/skills/search', {'query': 'react'})
            assert (await client.post('/api/skills/descriptions', json={'skill_ids': ['a/b@skill']})).status_code == 200
            operation.assert_awaited_with('/skills/descriptions', {'skill_ids': ['a/b@skill']})
            assert (await client.post('/api/skills/install', json={'agent_code': 'product', 'source': 'a/b@skill'})).status_code == 200
            operation.assert_awaited_with('/skills/install', {'agent_code': 'product', 'source': 'a/b@skill'}, timeout=120)
            assert (await client.post('/api/skills/uninstall', json={'agent_code': 'general', 'skill_id': 'a/b@skill'})).status_code == 200
            operation.assert_awaited_with('/skills/uninstall', {'agent_code': 'general', 'skill_id': 'a/b@skill'})
            assert (await client.get('/api/skills?agent_code=../other')).status_code == 422
            operation.side_effect = ApiError(ApiCode.PARAM_ERROR, '同名技能已存在。', 409)
            response = await client.post('/api/skills/install', json={'agent_code': 'general', 'source': 'a/b@skill'})
            assert response.status_code == 409 and response.json()['message'] == '同名技能已存在。'
    asyncio.run(case())
