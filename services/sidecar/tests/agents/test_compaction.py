"""真实压缩入口产生状态事件；摘要不混入用户回答。"""
import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from deepagents.middleware.summarization import SummarizationMiddleware

from src import config
from src.agents import agent
from src.harness import compaction


def test_actual_graph_reports_compaction_without_leaking_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'WORKSPACE_DIR', tmp_path / 'workspace')
    monkeypatch.setattr(FakeMessagesListChatModel, 'bind_tools', lambda self, *args, **kwargs: self, raising=False)
    monkeypatch.setattr(compaction, 'compute_summarization_defaults', lambda _: {
        'trigger': ('messages', 4), 'keep': ('messages', 1), 'truncate_args_settings': {}})
    request = agent.AgentRequest(thread_id='compact-test', messages=[
        {'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'消息{i}'} for i in range(7)])

    async def case():
        model = FakeMessagesListChatModel(responses=[AIMessage('内部摘要，不应展示'), AIMessage('正式回答')])
        events = [event async for event in agent.agent_events(request, model)]
        progress = [event for event in events if event['type'] == 'compaction']
        assert [event['status'] for event in progress] == ['running', 'complete']
        assert progress[0]['id'] == progress[1]['id']
        assert events[-1]['type'] == 'done' and events[-1]['content'] == '正式回答'
        assert ''.join(event['text'] for event in events if event['type'] == 'delta') == '正式回答'

        short = agent.AgentRequest(thread_id='short-test', messages=[{'role': 'user', 'content': '你好'}])
        events = [event async for event in agent.agent_events(short, model)]
        assert not any(event['type'] == 'compaction' for event in events)
    asyncio.run(case())


@pytest.mark.parametrize('error,status', [(RuntimeError, 'failed'), (asyncio.CancelledError, 'cancelled')])
def test_summary_error_and_cancellation_end_notice_without_swallowing(monkeypatch, error, status):
    events = []
    monkeypatch.setattr(compaction, 'get_stream_writer', lambda: events.append)
    async def fail(*args):
        raise error()
    monkeypatch.setattr(SummarizationMiddleware, '_acreate_summary', fail)
    middleware = compaction.compaction_middleware(FakeMessagesListChatModel(responses=[AIMessage('unused')]), None)
    async def case():
        with pytest.raises(error):
            await middleware._acreate_summary([HumanMessage('history')])
    asyncio.run(case())
    assert [event['status'] for event in events] == ['running', status]
