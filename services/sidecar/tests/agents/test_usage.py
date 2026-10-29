"""用量去重、任务预算、嵌套模型和审批恢复；不调用付费服务。"""
import asyncio
from decimal import Decimal
import json
from uuid import uuid4

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, LLMResult

from src import config
from src.agents import agent
from src.harness.usage import UsageLedger, reported_usage, read_usage
from src.providers.llm.chat import ReasoningChatOpenAI
from src.providers.llm.schemas import ModelError, ModelSettings
from src.transport.handlers import AgentInput


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(config, 'AGENT_RUN_TOKEN_LIMIT', 0)
    monkeypatch.setattr(config, 'AGENT_RUN_COST_LIMIT', '0')
    monkeypatch.setattr(config, 'AGENT_MODEL_PRICES', '{}')
    monkeypatch.setattr(config, 'AGENT_COST_CURRENCY', 'CNY')


def message(text='done', **kwargs):
    return AIMessage(text, usage_metadata={'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120,
        'input_token_details': {'cache_read': 40}, 'output_token_details': {'reasoning': 5}}, **kwargs)


def result(msg):
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


class Model(FakeMessagesListChatModel):
    def bind_tools(self, *args, **kwargs):
        return self


def test_reported_usage_and_cost_do_not_double_count_cache_or_reasoning(monkeypatch):
    monkeypatch.setattr(config, 'AGENT_MODEL_PRICES', json.dumps({'fixture': {'input': 2, 'output': 10, 'cached_input': 1}}))
    async def case():
        ledger = UsageLedger(str(uuid4()), 'fixture')
        key = uuid4()
        await ledger.on_chat_model_start({}, [[]], run_id=key)
        await ledger.on_llm_end(result(message()), run_id=key)
        await ledger.on_llm_end(result(message()), run_id=key)
        usage = ledger.snapshot()
        assert usage['complete'] and len(usage['calls']) == 1
        assert usage['total_tokens'] == 120 and usage['cached_input_tokens'] == 40 and usage['reasoning_tokens'] == 5
        assert Decimal(usage['estimated_cost']) == Decimal('0.00036')
        restored = UsageLedger(ledger.run_id, 'fixture')
        assert restored.snapshot()['total_tokens'] == 120
    asyncio.run(case())


@pytest.mark.parametrize('mode', ['tokens', 'cost', 'missing'])
def test_budget_blocks_the_next_model_call(monkeypatch, mode):
    if mode == 'cost':
        monkeypatch.setattr(config, 'AGENT_MODEL_PRICES', '{"fixture":{"input":2,"output":10}}')
        monkeypatch.setattr(config, 'AGENT_RUN_COST_LIMIT', '.0001')
    else:
        monkeypatch.setattr(config, 'AGENT_RUN_TOKEN_LIMIT', 100)
    async def case():
        ledger = UsageLedger(str(uuid4()), 'fixture')
        key = uuid4()
        await ledger.on_chat_model_start({}, [[]], run_id=key)
        await ledger.on_llm_end(result(AIMessage('unreported') if mode == 'missing' else message()), run_id=key)
        with pytest.raises(ModelError) as caught:
            await ledger.on_chat_model_start({}, [[]], run_id=uuid4())
        expected = {'tokens': 'AGENT_TOKEN_BUDGET', 'cost': 'AGENT_COST_BUDGET', 'missing': 'AGENT_USAGE_UNAVAILABLE'}[mode]
        assert caught.value.code == expected
        assert len(ledger.snapshot()['calls']) == 1
    asyncio.run(case())


def test_missing_price_never_means_free_and_currency_budget_requires_price(monkeypatch):
    monkeypatch.setattr(config, 'AGENT_RUN_COST_LIMIT', '1')
    with pytest.raises(ModelError, match='单价'):
        UsageLedger(str(uuid4()), 'unpriced')


def test_graph_counts_tool_loop_and_blocks_further_calls(monkeypatch):
    monkeypatch.setattr(config, 'AGENT_RUN_TOKEN_LIMIT', 100)
    model = Model(responses=[message('', tool_calls=[{'id': 'ls1', 'name': 'ls', 'args': {'path': '/'}, 'type': 'tool_call'}]), message('not called')])
    monkeypatch.setattr(agent, 'create_model', lambda *_: model)
    async def case():
        events = [event async for event in agent.run_agent(AgentInput(thread_id='usage', messages=[{'role': 'user', 'content': 'inspect'}]), ModelSettings(model='fixture', timeout=10))]
        assert events[-1]['code'] == 'AGENT_TOKEN_BUDGET', events
        assert model.i == 1
        assert [event for event in events if event['type'] == 'usage'][-1]['usage']['total_tokens'] == 120
    asyncio.run(case())


def test_subagent_calls_count_in_the_parent_run(monkeypatch):
    model = Model(responses=[message('', tool_calls=[{'id': 'task1', 'name': 'task', 'args': {'description': 'answer', 'subagent_type': 'general-purpose'}, 'type': 'tool_call'}]), message('child'), message('parent')])
    monkeypatch.setattr(agent, 'create_model', lambda *_: model)
    async def case():
        events = [event async for event in agent.run_agent(AgentInput(thread_id='usage', messages=[{'role': 'user', 'content': 'delegate'}]), ModelSettings(model='fixture', timeout=10))]
        assert events[-1]['type'] == 'done', events
        usage = [event for event in events if event['type'] == 'usage'][-1]['usage']
        assert usage['reported_calls'] == 3 and usage['total_tokens'] == 360
    asyncio.run(case())


def test_approval_resume_preserves_usage(monkeypatch):
    monkeypatch.setattr(agent, 'create_model', lambda *_: Model(responses=[message('', tool_calls=[{'id': 'w1', 'name': 'write_file', 'args': {'file_path': '.env.demo', 'content': 'fixture'}, 'type': 'tool_call'}])]))
    async def case():
        body = AgentInput(run_id=str(uuid4()), thread_id='usage', messages=[{'role': 'user', 'content': 'write'}])
        initial = [event async for event in agent.run_agent(body, ModelSettings(model='fixture', timeout=10))]
        assert initial[-1]['type'] == 'approval', initial
        assert read_usage(body.run_id)['total_tokens'] == 120
        answers = {item['id']: {'decisions': [{'type': 'approve'}]} for item in initial[-1]['interrupts']}
        monkeypatch.setattr(agent, 'create_model', lambda *_: Model(responses=[message('approved')]))
        resumed = [event async for event in agent.run_agent(body.model_copy(update={'approval_resume': answers}), ModelSettings(model='fixture', timeout=10))]
        assert resumed[-1]['type'] == 'done', resumed
        assert [event for event in resumed if event['type'] == 'usage'][-1]['usage']['total_tokens'] == 240
    asyncio.run(case())


def test_real_sdk_requests_usage_and_receives_final_usage_chunk():
    chunks = [{'choices': [{'index': 0, 'delta': {'content': 'done'}, 'finish_reason': 'stop'}]},
              {'choices': [], 'usage': {'prompt_tokens': 11, 'completion_tokens': 7, 'total_tokens': 18}}]
    def serve(request):
        assert json.loads(request.content)['stream_options']['include_usage']
        data = ''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n'
        return httpx.Response(200, text=data, headers={'content-type': 'text/event-stream'})
    async def case():
        ledger = UsageLedger(str(uuid4()), 'fixture')
        async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
            model = ReasoningChatOpenAI(model='fixture', api_key='fixture', base_url='https://fixture.invalid/v1', http_async_client=client, stream_usage=True)
            async for _ in model.astream('test', config={'callbacks': [ledger]}):
                pass
        assert ledger.snapshot()['total_tokens'] == 18
        assert ledger.snapshot()['estimated_cost'] is None
    asyncio.run(case())
