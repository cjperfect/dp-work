"""云端仅公开账号、会议、知识库和必要的设备传输接口。"""
import asyncio
from unittest.mock import AsyncMock
from httpx import ASGITransport,AsyncClient
from src.main import create_app
from src.modules.auth.dependencies import get_current_user
from src.modules.users.models import User


def test_local_business_is_not_exposed_by_cloud_api():
    async def case():
        app=create_app()
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            for method,path in [('GET','/api/agents/models'),('POST','/api/agents/chat'),('GET','/api/agents/threads'),
                ('GET','/api/agents/projects'),('GET','/api/settings'),('GET','/api/skills'),('POST','/api/skills/install'),
                ('GET','/api/connectors/feishu')]:
                assert (await client.request(method,path,json={} if method=='POST' else None)).status_code==404
            schema=(await client.get('/api/openapi.json')).json()
            for path in schema['paths']:
                assert not path.startswith(('/api/agents','/api/settings','/api/connectors','/api/skills'))
            for path in ('/api/auth/login','/api/auth/register','/api/meetings','/api/knowledge-bases'):
                assert path in schema['paths']
    asyncio.run(case())


def test_retrieval_capability_requires_auth_and_owned_bases(monkeypatch):
    from src.modules.knowledge import rag,rag_access
    authorize=AsyncMock()
    monkeypatch.setattr(rag,'authorize_bases',authorize)
    monkeypatch.setattr(rag_access,'issue_capability',lambda owner,bases:'scoped-fixture')
    async def case():
        app=create_app()
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            path='/api/knowledge-bases/retrieval-capability'
            assert (await client.post(path,json={'knowledge_base_ids':[1]})).status_code==401
            app.dependency_overrides[get_current_user]=lambda:User(id=7,username='fixture',password_hash='unused',role='member',department='product',status=0)
            response=await client.post(path,json={'knowledge_base_ids':[1,2]})
            assert response.status_code==200 and response.json()['data']['capability']=='scoped-fixture'
            authorize.assert_awaited_once_with(7,[1,2])
            assert (await client.post(path,json={'knowledge_base_ids':[1],'owner_id':8})).status_code==422
    asyncio.run(case())
