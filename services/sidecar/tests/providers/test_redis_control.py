"""用独立 Redis key 验证实际模型限流和向量缓存隔离。"""
import asyncio
import os
from uuid import uuid4
from unittest.mock import AsyncMock, patch
import pytest
from src import config
from src.providers.llm import redis_control as control
from src.providers.llm.schemas import ModelError
from src.usage.ledger import scope

URL = os.environ.get('TEST_REDIS_URL')
pytestmark = pytest.mark.skipif(not URL, reason='需要 TEST_REDIS_URL')


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(config, 'REDIS_URL', URL or '')
    monkeypatch.setattr(config, 'REDIS_PREFIX', 'test:' + str(uuid4()))
    monkeypatch.setattr(config, 'REDIS_MODEL_RPM', 3)
    monkeypatch.setattr(config, 'REDIS_MODEL_USER_RPM', 2)
    monkeypatch.setattr(config, 'REDIS_CACHE_TTL_SECONDS', 1)


def test_model_user_and_provider_quotas():
    async def case():
        with scope(1):
            await control.permit('model', 'https://test', 'key')
            await control.permit('model', 'https://test', 'key')
            with pytest.raises(ModelError, match='频繁'):
                await control.permit('model', 'https://test', 'key')
        with scope(2):
            await control.permit('model', 'https://test', 'key')
            with pytest.raises(ModelError, match='频繁'):
                await control.permit('model', 'https://test', 'key')
            await control.permit('other-model', 'https://test', 'key')
    asyncio.run(case())


def test_cache_owner_profile_credential_isolation_and_expiry(monkeypatch):
    async def case():
        vector = [1.0] * 1024
        with scope(1):
            await control.cache_vector('question', 'profile', vector)
            assert await control.cached_vector('question', 'profile') == vector
            assert await control.cached_vector('question', 'other-profile') is None
            key = control.query_key('question', 'profile')
            assert 'question' not in key
        with scope(2):
            assert await control.cached_vector('question', 'profile') is None
        with scope(1):
            await asyncio.sleep(1.1)
            assert await control.cached_vector('question', 'profile') is None
            await control.cache_vector('question', 'profile', vector)
            monkeypatch.setattr(config, 'EMBEDDING_API_KEY', 'different')
            assert await control.cached_vector('question', 'profile') is None
    asyncio.run(case())


def test_unavailable_cache_falls_back_but_model_limit_fails_closed(monkeypatch):
    async def case():
        monkeypatch.setattr(config, 'REDIS_URL', 'redis://127.0.0.1:1/0')
        assert await control.cached_vector('question', 'profile') is None
        await control.cache_vector('question', 'profile', [1.0] * 1024)
        monkeypatch.setattr(config, 'REDIS_LIMIT_FAIL_OPEN', False)
        with pytest.raises(ModelError, match='限流服务'):
            await control.permit('model', 'https://test', 'key')
        monkeypatch.setattr(config, 'REDIS_LIMIT_FAIL_OPEN', True)
        await control.permit('model', 'https://test', 'key')
    asyncio.run(case())


def test_cache_hit_skips_embedding_provider(monkeypatch):
    from src.knowledge.rag.embedding import ArkEmbeddings
    async def case():
        monkeypatch.setattr(config, 'EMBEDDING_API_KEY', 'test-key')
        monkeypatch.setattr(config, 'EMBEDDING_BASE_URL', 'https://test')
        vector = [1.0] * 1024
        with patch('src.knowledge.rag.embedding.cached_vector', AsyncMock(return_value=vector)), \
             patch('httpx.AsyncClient.post', AsyncMock(side_effect=AssertionError('缓存命中不调用上游'))):
            assert await ArkEmbeddings().aembed_query('question') == vector
    asyncio.run(case())


def test_invalid_cached_vector_fetches_and_replaces_provider_result(monkeypatch):
    from src.knowledge.rag.embedding import ArkEmbeddings
    import httpx
    async def case():
        monkeypatch.setattr(config, 'EMBEDDING_API_KEY', 'test-key')
        monkeypatch.setattr(config, 'EMBEDDING_BASE_URL', 'https://test')
        vector = [1.0] * 1024
        post = AsyncMock(return_value=httpx.Response(200, json={'data': {'embedding': vector}}))
        cache = AsyncMock()
        with patch('src.knowledge.rag.embedding.cached_vector', AsyncMock(return_value=[0])), \
             patch('src.knowledge.rag.embedding.permit', AsyncMock()), \
             patch('src.knowledge.rag.embedding.cache_vector', cache), \
             patch('src.knowledge.rag.embedding.write', lambda *args, **kwargs: None), \
             patch('httpx.AsyncClient.post', post):
            assert await ArkEmbeddings().aembed_query('question') == vector
        post.assert_awaited_once()
        cache.assert_awaited_once()
    asyncio.run(case())
