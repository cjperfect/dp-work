"""独立命名空间的真实 Redis 测试；不清空已有数据，不需要业务数据库。"""
import asyncio
import json
import os
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient
from src.core import config
from src.infrastructure.redis import client
from src.infrastructure.database import notifications
from src.middleware.rate_limit import RateLimitMiddleware

URL = os.environ.get('TEST_REDIS_URL')
pytestmark = pytest.mark.skipif(not URL, reason='需要 TEST_REDIS_URL')


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(config, 'REDIS_URL', URL or '')
    monkeypatch.setattr(config, 'REDIS_PREFIX', 'test:' + str(uuid4()))
    monkeypatch.setattr(config, 'REDIS_PUBSUB_ENABLED', True)


def test_atomic_limit_across_concurrent_clients_and_expiry():
    async def case():
        results = await asyncio.gather(*[client.check_limit('test', 'same', 5, 1) for _ in range(20)])
        assert results.count(0) == 5
        assert await client.check_limit('test', 'other', 5, 1) == 0
        await asyncio.sleep(1.1)
        assert await client.check_limit('test', 'same', 5, 1) == 0
    asyncio.run(case())


def test_http_429_and_retry_after(monkeypatch):
    async def case():
        monkeypatch.setattr(config, 'REDIS_IP_RPM', 1)
        async def app(scope, receive, send):
            from starlette.responses import JSONResponse
            await JSONResponse({'ok': True})(scope, receive, send)
        async with AsyncClient(transport=ASGITransport(app=RateLimitMiddleware(app)), base_url='http://test') as http:
            assert (await http.get('/api/test')).status_code == 200
            blocked = await http.get('/api/test')
            assert blocked.status_code == 429
            assert int(blocked.headers['Retry-After']) > 0
            assert (await http.get('/health')).status_code == 200
    asyncio.run(case())


def test_redis_delivery_and_pg_duplicate_fallback(monkeypatch):
    async def case():
        callbacks = {}
        pg = SimpleNamespace(close=AsyncMock())
        async def add(channel, callback):
            callbacks[channel] = callback
        pg.add_listener = add
        monkeypatch.setattr(notifications.asyncpg, 'connect', AsyncMock(return_value=pg))
        payload = json.dumps({'id': 'fixture', '_event_id': str(uuid4())})
        async with notifications.listen('meeting_record') as queue:
            await client.publish('meeting_record', payload)
            assert json.loads(await asyncio.wait_for(queue.get(), 1)) == {'id': 'fixture'}
            callbacks['meeting_record'](None, 0, 'meeting_record', payload)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(queue.get(), 0.25)
            # 无 Redis 消息时仍由 PG 通道交付。
            callbacks['meeting_record'](None, 0, 'meeting_record', json.dumps({'id': 'fallback', '_event_id': str(uuid4())}))
            assert json.loads(await asyncio.wait_for(queue.get(), 1))['id'] == 'fallback'
        pg.close.assert_awaited_once()
    asyncio.run(case())


def test_redis_failure_rejects_or_allows_by_policy(monkeypatch):
    async def case():
        monkeypatch.setattr(config, 'REDIS_URL', 'redis://127.0.0.1:1/0')
        async def app(scope, receive, send):
            from starlette.responses import Response
            await Response(status_code=204)(scope, receive, send)
        async with AsyncClient(transport=ASGITransport(app=RateLimitMiddleware(app)), base_url='http://test') as http:
            monkeypatch.setattr(config, 'REDIS_LIMIT_FAIL_OPEN', False)
            assert (await http.get('/api/test')).status_code == 503
            monkeypatch.setattr(config, 'REDIS_LIMIT_FAIL_OPEN', True)
            assert (await http.get('/api/test')).status_code == 204
    asyncio.run(case())


def test_real_postgres_commit_and_rollback(monkeypatch):
    """独立频道测试真实 SQLAlchemy 提交/回滚，不写业务表。"""
    database_url = os.environ.get('TEST_NOTIFY_DATABASE_URL')
    if not database_url:
        pytest.skip('需要 TEST_NOTIFY_DATABASE_URL')
    async def case():
        from src.infrastructure.database import session
        monkeypatch.setattr(config, 'DATABASE_URL', database_url)
        await session.init_db()
        channel = 'test_' + uuid4().hex
        try:
            async with notifications.listen(channel) as queue:
                async with session.transaction() as db:
                    await notifications.notify(db, channel, {'state': 'committed'})
                    assert queue.empty()
                assert json.loads(await asyncio.wait_for(queue.get(), 1)) == {'state': 'committed'}
                with pytest.raises(ValueError):
                    async with session.transaction() as db:
                        await notifications.notify(db, channel, {'state': 'rolled-back'})
                        raise ValueError('rollback')
                with pytest.raises(TimeoutError):
                    await asyncio.wait_for(queue.get(), 0.3)
        finally:
            await session.close_db()
    asyncio.run(case())


def test_authenticated_user_limit_keeps_retry_header(monkeypatch):
    async def case():
        from fastapi import Depends, FastAPI
        from src.modules.auth import dependencies
        from src.core.exceptions import register_exception_handlers
        app = FastAPI()
        register_exception_handlers(app)
        monkeypatch.setattr(config, 'REDIS_USER_RPM', 1)
        monkeypatch.setattr(dependencies, 'decode_token', lambda _: {'sub': '7', 'uidv': 2})
        monkeypatch.setattr(dependencies.users_service, 'find_by_subject', AsyncMock(return_value=SimpleNamespace(id=7, is_active=True)))
        @app.get('/test')
        async def endpoint(user=Depends(dependencies.get_current_user)):
            return {'id': user.id}
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test', headers={'Authorization': 'Bearer fixture'}) as http:
            assert (await http.get('/test')).status_code == 200
            blocked = await http.get('/test')
            assert blocked.status_code == 429
            assert blocked.json()['code'] == 4290
            assert int(blocked.headers['Retry-After']) > 0
    asyncio.run(case())


def test_limited_responses_keep_cors_headers(monkeypatch):
    async def case():
        from src.main import create_app
        monkeypatch.setattr(config, 'REDIS_IP_RPM', 1)
        origin = config.CORS_ORIGINS[0]
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url='http://test', headers={'Origin': origin}) as http:
            assert (await http.get('/api/docs')).status_code == 200
            blocked = await http.get('/api/docs')
            assert blocked.status_code == 429
            assert blocked.headers['access-control-allow-origin'] == origin
            assert 'Retry-After' in blocked.headers['access-control-expose-headers']
    asyncio.run(case())
