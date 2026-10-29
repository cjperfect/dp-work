"""本机用量随会话保存，断流时从账本恢复。"""
import asyncio
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult, ChatGeneration

from src import config
from src.harness.usage import UsageLedger
from src.sessions import service
from src.sessions.storage import SessionStorage


def test_cancelled_usage_is_restored_to_message_and_run(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(service, 'storage', SessionStorage(tmp_path))
    run_id = str(uuid4())
    async def case():
        ledger = UsageLedger(run_id, 'fixture')
        first, pending = uuid4(), uuid4()
        await ledger.on_chat_model_start({}, [[]], run_id=first)
        msg = AIMessage('done', usage_metadata={'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120})
        await ledger.on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]), run_id=first)
        await ledger.on_chat_model_start({}, [[]], run_id=pending)
        await service.operation('create', {'owner_id': 7, 'body': {'id': 'usage-test', 'agent_id': 1}})
        def cancelled(state):
            state['nodes']['reply'] = {'id': 'reply', 'role': 'assistant', 'content': 'partial', 'status': 'cancelled', 'context': {}}
            state['active_path'] = ['reply']
            state['runs'][run_id] = {'id': run_id, 'status': 'cancelled', 'response_id': 'reply'}
        service.storage.mutate(7, 'usage-test', 'fixture', cancelled)
        detail = await service.operation('get', {'owner_id': 7, 'thread_id': 'usage-test'})
        usage = detail['messages'][0]['context']['usage']
        assert usage['total_tokens'] == 120 and usage['unreported_calls'] == 1 and not usage['complete']
        assert service.storage.get(7, 'usage-test')['runs'][run_id]['usage'] == usage
    asyncio.run(case())


def test_usage_event_is_durable_and_cannot_be_erased_by_late_message_save(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(service, 'storage', SessionStorage(tmp_path))
    run_id = str(uuid4())
    async def case():
        ledger = UsageLedger(run_id, 'fixture')
        call_id = uuid4()
        await ledger.on_chat_model_start({}, [[]], run_id=call_id)
        msg = AIMessage('done', usage_metadata={'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120})
        await ledger.on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]), run_id=call_id)
        await service.operation('create', {'owner_id': 7, 'body': {'id': 'usage-live', 'agent_id': 1}})
        def start(state):
            from src.sessions.storage import now
            state['nodes']['reply'] = {'id': 'reply', 'role': 'assistant', 'content': '', 'status': 'streaming', 'context': {}, 'created_at': now()}
            state['active_path'] = ['reply']
            state['runs'][run_id] = {'id': run_id, 'status': 'running', 'response_id': 'reply'}
            state['run_id'] = run_id
        service.storage.mutate(7, 'usage-live', 'fixture', start)
        async def events():
            yield {'type': 'usage', 'usage': ledger.snapshot()}
            yield {'type': 'done', 'content': 'answer'}
        delivered = [event async for event in service.persist_events(7, 'usage-live', run_id, events())]
        assert delivered[0]['usage']['total_tokens'] == 120
        saved = await service.operation('get', {'owner_id': 7, 'thread_id': 'usage-live'})
        saved['messages'][0]['context'].pop('usage')
        latest = await service.operation('messages', {'owner_id': 7, 'thread_id': 'usage-live', 'body': {
            'messages': saved['messages'], 'expected_revision': saved['thread']['draft_revision']}})
        assert latest['messages'][0]['context']['usage']['total_tokens'] == 120
        assert service.storage.get(7, 'usage-live')['runs'][run_id]['usage']['total_tokens'] == 120
    asyncio.run(case())
