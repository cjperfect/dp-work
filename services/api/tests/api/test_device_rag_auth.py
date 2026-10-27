"""设备模式的 RAG 回调不能用普通登录令牌替代范围授权。"""
import asyncio
from httpx import ASGITransport,AsyncClient
from src.core import config
from src.core.security import create_access_token
from src.main import create_app


def test_device_rag_rejects_invalid_and_login_tokens(monkeypatch):
    monkeypatch.setattr(config,'SIDECAR_TRANSPORT','device')
    async def case():
        async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://test') as client:
            for token in ('invalid',create_access_token(123,'member','product')):
                response=await client.post('/api/internal/knowledge/search',json={'capability':token,'profile':'a'*64,'query':'query'})
                assert response.status_code==401
    asyncio.run(case())
