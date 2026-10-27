"""Harness 统一执行身份、终态和资源释放。"""
import asyncio
from unittest.mock import patch
from src.harness.runtime import run_events
from src.transport.handlers import dispatch


def test_run_id_single_terminal_and_generator_cleanup():
    closed = []
    async def producer():
        try:
            yield {'type': 'start', 'run_id': 'old-id'}
            yield {'type': 'delta', 'text': '内容'}
            yield {'type': 'done', 'content': '内容'}
            yield {'type': 'error', 'message': '不得发布'}
        finally:
            closed.append(True)
    async def case():
        events = [item async for item in run_events(producer(), 'api-run-id', 'fixture-model')]
        assert [item['type'] for item in events] == ['start', 'delta', 'done']
        assert all(item['run_id'] == 'api-run-id' for item in events)
        assert events[0]['status'] == 'running' and events[-1]['status'] == 'completed'
        assert events[-1]['duration_ms'] >= 0 and closed
    asyncio.run(case())


def test_early_eof_and_disconnect_close_producer():
    async def empty():
        if False:
            yield
    async def case():
        events = [item async for item in run_events(empty(), 'id')]
        assert events[-1]['code'] == 'AGENT_DISCONNECTED' and events[-1]['status'] == 'interrupted'
        closed = asyncio.Event()
        async def pending():
            try:
                yield {'type': 'delta', 'text': '部分'}
                await asyncio.Event().wait()
            finally:
                closed.set()
        iterator = run_events(pending(), 'id')
        await anext(iterator); await anext(iterator)
        waiting = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0)
        waiting.cancel()
        try:
            await waiting
        except asyncio.CancelledError:
            pass
        assert closed.is_set()
    asyncio.run(case())


def test_rpc_dispatch_uses_api_run_id():
    async def producer(*args):
        yield {'type': 'start', 'run_id': 'sidecar-generated'}
        yield {'type': 'done', 'content': 'fixture'}
    from src.providers.llm.schemas import ModelSettings
    run_id = 'a' * 8 + '-1111-2222-3333-' + 'b' * 12
    async def case():
        with patch('src.transport.handlers.settings_for', return_value=ModelSettings(model='fixture-model')), \
             patch('src.transport.handlers.run_agent', producer):
            body = {'run_id': run_id, 'thread_id': 'thread', 'messages': [{'role': 'user', 'content': '你好'}]}
            result = await dispatch('agents.chat', body, None)
            events = [event async for event in result.events]
            assert all(item['run_id'] == run_id for item in events)
            assert events[0]['model'] == 'fixture-model' and events[-1]['status'] == 'completed'
    asyncio.run(case())
