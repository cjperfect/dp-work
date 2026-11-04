"""共享状态订阅在权限撤回时不发送增量，并清理等待客户端的任务。"""
import asyncio
import json
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from src.core.exceptions import ApiError
from src.infrastructure.realtime import state_events as transport


@pytest.mark.parametrize('permission', ['meeting:read', 'knowledge:read'])
def test_revoked_permission_closes_stream_and_cancels_reader(monkeypatch, permission):
    async def run():
        cancelled = asyncio.Event()
        reader_started = asyncio.Event()
        queue = asyncio.Queue()
        queue.put_nowait(json.dumps({'owner_id': 7}))
        calls = 0

        async def receive():
            nonlocal calls
            calls += 1
            if calls == 1:
                return json.dumps({'token': 'fixture'})
            reader_started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

        @asynccontextmanager
        async def listen(channel):
            assert channel == 'test_states'
            yield queue

        async def authorize(owner, required):
            assert (owner, required) == (7, permission)
            # 第一次允许读取快照，下一次推送前已被撤回权限。
            if reader_started.is_set():
                raise ApiError(4030, '无权限', 403)

        websocket = SimpleNamespace(
            headers={}, accept=AsyncMock(), receive_text=receive,
            send_json=AsyncMock(), close=AsyncMock(),
        )
        snapshot = AsyncMock(return_value={'type': 'snapshot'})
        update = AsyncMock()
        monkeypatch.setattr(transport, 'decode_token', lambda _: {'sub': '7', 'exp': time.time() + 60})
        monkeypatch.setattr(transport.users_service, 'find_by_subject', AsyncMock(return_value=SimpleNamespace(id=7, is_active=True)))
        monkeypatch.setattr(transport, 'authorize_id', authorize)
        monkeypatch.setattr(transport, 'listen', listen)
        await asyncio.wait_for(transport.state_events(
            websocket, permission=permission, channel='test_states', snapshot=snapshot, update=update,
        ), timeout=2)
        snapshot.assert_awaited_once_with(7)
        update.assert_not_awaited()
        websocket.send_json.assert_awaited_once_with({'type': 'snapshot'})
        assert any(call.kwargs.get('code') == 4403 for call in websocket.close.await_args_list)
        assert cancelled.is_set()

    asyncio.run(run())
