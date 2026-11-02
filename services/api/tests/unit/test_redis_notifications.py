"""通知必须提交后发布，回滚不能向 Redis 泄露事件。"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from src.infrastructure.database import session, notifications


def test_publish_only_after_successful_commit(monkeypatch):
    async def case():
        state = {'committed': False}
        db = SimpleNamespace(info={}, execute=AsyncMock())
        @asynccontextmanager
        async def begin():
            yield db
            state['committed'] = True
        monkeypatch.setattr(session, '_session_factory', lambda: SimpleNamespace(begin=begin))
        async def publish(messages):
            assert state['committed']
            assert messages[0][0] == 'meeting_record'
        publisher = AsyncMock(side_effect=publish)
        monkeypatch.setattr(notifications, 'publish_committed', publisher)
        async with session.transaction() as current:
            await notifications.notify(current, 'meeting_record', {'id': 'fixture'})
            publisher.assert_not_awaited()
        publisher.assert_awaited_once()
    asyncio.run(case())


def test_rollback_does_not_publish(monkeypatch):
    async def case():
        db = SimpleNamespace(info={}, execute=AsyncMock())
        @asynccontextmanager
        async def begin():
            yield db
        monkeypatch.setattr(session, '_session_factory', lambda: SimpleNamespace(begin=begin))
        publisher = AsyncMock()
        monkeypatch.setattr(notifications, 'publish_committed', publisher)
        with pytest.raises(ValueError):
            async with session.transaction() as current:
                await notifications.notify(current, 'meeting_record', {'id': 'fixture'})
                raise ValueError('rollback')
        publisher.assert_not_awaited()
    asyncio.run(case())
