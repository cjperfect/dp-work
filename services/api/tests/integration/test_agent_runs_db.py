"""运行状态持久化、取消通知、过期恢复与用户隔离。"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from src.core.exceptions import ApiError
from src.core.security import create_access_token
from src.infrastructure.database import session
from src.main import create_app
from src.modules.agents import conversation_service as conversations, run_service, service as agents
from src.modules.agents.conversation_schemas import ThreadCreate, GraphSave, StoredChat
from src.modules.agents.run_models import AgentRun
from src.modules.agents.conversation_models import Conversation
from src.modules.users import service as users
from src.modules.users.models import User


def frame(event):
    return ('data: ' + json.dumps(event) + '\n\n').encode()


@asynccontextmanager
async def prepared():
    await session.init_db()
    owner = await users.create_user('runs-' + uuid4().hex, 'fixture', 'product')
    key = 'thread-' + uuid4().hex
    try:
        await conversations.create(owner.id, ThreadCreate(id=key, agent_id=1))
        now = datetime.now(timezone.utc).isoformat()
        detail = await conversations.save_graph(owner.id, key, GraphSave(expected_revision=0, messages=[
            {'id': 'u', 'role': 'user', 'content': '问题', 'created_at': now},
            {'id': 'a', 'role': 'assistant', 'content': '', 'status': 'streaming', 'created_at': now}]))
        body = StoredChat(thread_id=key, response_id='a', expected_revision=detail['thread']['draft_revision'],
                          messages=[{'role': 'user', 'content': '问题'}])
        yield owner, key, body
    finally:
        async with session.transaction() as db:
            await db.execute(delete(User).where(User.id == owner.id))
        await session.close_db()


class Stream:
    def __init__(self, events):
        self.events, self.closed = events, False
    async def close(self):
        self.closed = True
    async def chunks(self):
        for event in self.events:
            yield frame(event)


def test_completed_run_and_query_api_permissions(monkeypatch):
    upstream = Stream([{'type': 'start', 'run_id': 'untrusted-upstream-id', 'model': 'fixture-model'},
                       {'type': 'done', 'content': '答案', 'model': 'fixture-model'}])
    model = AsyncMock(return_value=upstream)
    monkeypatch.setattr(agents, 'open_chat', model)
    async def case():
        async with prepared() as (owner, key, body):
            stream = await conversations.open_chat(owner.id, key, body)
            run_id = stream.token
            assert model.call_args.kwargs['run_id'] == run_id
            assert (await run_service.get(owner.id, run_id))['status'] == 'running'
            with pytest.raises(ApiError):
                await conversations.open_chat(owner.id, key, body)
            async for chunk in stream.chunks():
                event = json.loads(chunk.decode().removeprefix('data: '))
                assert event['run_id'] == run_id
                if event['type'] == 'done':
                    assert (await run_service.get(owner.id, run_id))['status'] == 'completed'
            assert upstream.closed
            result = await run_service.cancel(owner.id, run_id)
            assert result['status'] == 'completed' and result['model'] == 'fixture-model'
            assert result['finished_at'] >= result['started_at'] and not result['error_code']
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url='http://test') as client:
                path = '/api/agents/runs/' + run_id
                headers = {'Authorization': 'Bearer ' + create_access_token(owner.id, owner.role, owner.department)}
                assert (await client.get(path)).status_code == 401
                assert (await client.get(path, headers=headers)).json()['data']['status'] == 'completed'
                listing = (await client.get('/api/agents/runs', headers=headers,
                    params={'conversation_id': key, 'status': 'completed', 'page_size': 1})).json()['data']
                assert listing['total'] == 1 and listing['page_size'] == 1 and len(listing['item']) == 1
                assert (await client.post(path + '/cancel', headers=headers)).status_code == 200
            with pytest.raises(ApiError):
                await run_service.get(owner.id + 999999, run_id)
            with pytest.raises(ApiError):
                await run_service.cancel(owner.id + 999999, run_id)
            # 连接池重建后依然能读取终态。
            await session.close_db(); await session.init_db()
            assert (await run_service.get(owner.id, run_id))['status'] == 'completed'
    asyncio.run(case())


def test_cancel_notifies_idle_stream_and_rejects_late_completion(monkeypatch):
    class Idle(Stream):
        async def chunks(self):
            yield frame({'type': 'delta', 'text': '部分内容'})
            await asyncio.Event().wait()
    upstream = Idle([])
    monkeypatch.setattr(agents, 'open_chat', AsyncMock(return_value=upstream))
    async def case():
        async with prepared() as (owner, key, body):
            stream = await conversations.open_chat(owner.id, key, body)
            iterator = stream.chunks()
            await anext(iterator)
            await stream.persist('streaming')
            waiting = asyncio.create_task(anext(iterator))
            result = await run_service.cancel(owner.id, stream.token)
            assert result['status'] == 'cancelled'
            event = await asyncio.wait_for(waiting, timeout=2)
            assert b'RUN_STOPPED' in event
            await iterator.aclose()
            assert upstream.closed
            assert not await conversations.save_reply(owner.id, key, 'a', stream.token, '迟到的答案', 'complete')
            saved = await conversations.get(owner.id, key)
            assert saved['messages'][-1]['status'] == 'cancelled' and saved['messages'][-1]['content'] == '部分内容'
            again = await run_service.cancel(owner.id, stream.token)
            assert again['finished_at'] == result['finished_at']
    asyncio.run(case())


def test_cancel_during_upstream_connection(monkeypatch):
    async def case():
        async with prepared() as (owner, key, body):
            entered, cancelled = asyncio.Event(), asyncio.Event()
            ids = []
            async def connecting(*args, **kwargs):
                ids.append(kwargs['run_id']); entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            monkeypatch.setattr(agents, 'open_chat', connecting)
            opening = asyncio.create_task(conversations.open_chat(owner.id, key, body))
            await asyncio.wait_for(entered.wait(), 2)
            await run_service.cancel(owner.id, ids[0])
            with pytest.raises(ApiError) as error:
                await asyncio.wait_for(opening, 2)
            assert error.value.status_code == 409
            assert cancelled.is_set() and (await run_service.get(owner.id, ids[0]))['status'] == 'cancelled'
    asyncio.run(case())


def test_expired_run_is_interrupted_without_resurrection():
    async def case():
        async with prepared() as (owner, key, body):
            run_id, _ = await conversations.begin_chat(owner.id, key, body)
            async with session.transaction() as db:
                (await db.get(AgentRun, run_id)).deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await run_service.recover()
            result = await run_service.get(owner.id, run_id)
            assert result['status'] == 'interrupted' and result['error_code'] == 'RUN_EXPIRED'
            assert not await conversations.save_reply(owner.id, key, 'a', run_id, '迟到结果', 'complete')
            saved = await conversations.get(owner.id, key)
            assert saved['messages'][-1]['status'] == 'failed'
            async with session.read_session() as db:
                assert (await db.get(Conversation, key)).run_token is None
            await conversations.remove(owner.id, key)
            with pytest.raises(ApiError):
                await run_service.get(owner.id, run_id)
    asyncio.run(case())


@pytest.mark.parametrize('events,code', [([{'type': 'error', 'code': 'AGENT_TIMEOUT', 'message': '回答超时'}], 'AGENT_TIMEOUT'),
    ([{'type': 'delta', 'text': '不完整'}], 'AGENT_DISCONNECTED'),
    ([{'type': 'done', 'content': ''}], 'INVALID_AGENT_EVENT')])
def test_failed_stream_records_safe_error(monkeypatch, events, code):
    monkeypatch.setattr(agents, 'open_chat', AsyncMock(return_value=Stream(events)))
    async def case():
        async with prepared() as (owner, key, body):
            stream = await conversations.open_chat(owner.id, key, body)
            _ = [chunk async for chunk in stream.chunks()]
            result = await run_service.get(owner.id, stream.token)
            assert result['status'] == 'failed' and result['error_code'] == code and result['finished_at']
    asyncio.run(case())


def test_connect_failure_and_client_disconnect(monkeypatch):
    async def case():
        async with prepared() as (owner, key, body):
            monkeypatch.setattr(agents, 'open_chat', AsyncMock(side_effect=RuntimeError('private-upstream')))
            with pytest.raises(RuntimeError):
                await conversations.open_chat(owner.id, key, body)
            async with session.read_session() as db:
                run = await db.scalar(select(AgentRun).where(AgentRun.conversation_id == key))
                assert run.status == 'failed' and run.error_code == 'AGENT_CONNECT_FAILED'
                assert 'private-upstream' not in run.error_message
        async with prepared() as (owner, key, body):
            upstream = Stream([{'type': 'delta', 'text': '保留部分回答'}])
            monkeypatch.setattr(agents, 'open_chat', AsyncMock(return_value=upstream))
            stream = await conversations.open_chat(owner.id, key, body)
            iterator = stream.chunks(); await anext(iterator); await iterator.aclose()
            result = await run_service.get(owner.id, stream.token)
            assert result['status'] == 'cancelled' and result['error_code'] == 'CLIENT_DISCONNECTED'
            assert (await conversations.get(owner.id, key))['messages'][-1]['content'] == '保留部分回答'
    asyncio.run(case())


def test_delete_active_conversation_stops_upstream(monkeypatch):
    class Idle(Stream):
        async def chunks(self):
            yield frame({'type': 'delta', 'text': '进行中'})
            await asyncio.Event().wait()
    upstream = Idle([])
    monkeypatch.setattr(agents, 'open_chat', AsyncMock(return_value=upstream))
    async def case():
        async with prepared() as (owner, key, body):
            stream = await conversations.open_chat(owner.id, key, body)
            iterator = stream.chunks(); await anext(iterator)
            waiting = asyncio.create_task(anext(iterator))
            await conversations.remove(owner.id, key)
            assert b'RUN_STOPPED' in await asyncio.wait_for(waiting, 2)
            await iterator.aclose()
            assert upstream.closed
            async with session.read_session() as db:
                run = await db.get(AgentRun, stream.token)
                assert run.status == 'cancelled' and run.error_code == 'CONVERSATION_DELETED'
            with pytest.raises(ApiError):
                await run_service.get(owner.id, stream.token)
    asyncio.run(case())
