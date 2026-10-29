"""LangGraph 基础对话与工具循环使用本地模型替身。"""
import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from pydantic import ValidationError

from src import config
from src.agents import agent
from src.agents.agent import AgentRequest, build_agent, create_model, settings_for
from src.providers.llm.schemas import ModelError, ModelSettings


@pytest.fixture(autouse=True)
def isolated_default_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path / "workspace")
    monkeypatch.setattr(FakeMessagesListChatModel, "bind_tools", lambda self, *args, **kwargs: self, raising=False)


def body(**kwargs):
    return AgentRequest(thread_id="test-thread", messages=[{"role": "user", "content": "你好"}], **kwargs)


def test_graph_stream_and_isolated_history():
    async def case():
        model = FakeMessagesListChatModel(responses=[AIMessage("你好，已连接"), AIMessage("另一个会话")])
        events = [event async for event in agent.agent_events(body(), model)]
        assert events[0]["type"] == "start" and events[-1]["type"] == "done"
        assert "".join(event["text"] for event in events if event["type"] == "delta") == "你好，已连接"
        graph = build_agent(model, "product")
        state = await graph.ainvoke({"messages": [HumanMessage("新会话")]})
        assert len(state["messages"]) == 2
        assert state["messages"][-1].content == "另一个会话"
    asyncio.run(case())


def test_tool_loop_executes_registered_tool_only():
    seen = []
    @tool
    def add(a: int, b: int) -> int:
        """计算两个数字之和。"""
        seen.append((a, b))
        return a + b
    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self
    async def case():
        model = ToolModel(responses=[AIMessage(content="", tool_calls=[{"name": "add", "args": {"a": 2, "b": 3}, "id": "call-one", "type": "tool_call"}]), AIMessage("结果是5")])
        graph = build_agent(model, "general", [add])
        result = await graph.ainvoke({"messages": [HumanMessage("2+3")]})
        assert seen == [(2, 3)]
        assert result["messages"][-2].content == "5"
        assert result["messages"][-1].content == "结果是5"
        events = [event async for event in agent.agent_events(body(), model, [add])]
        assert events[-1]["type"] == "done" and events[-1]["content"] == "结果是5"
        assert "".join(event["text"] for event in events if event["type"] == "delta") == "结果是5"
        assert len(seen) == 2
    asyncio.run(case())


def test_user_cannot_inject_system_messages_or_unbounded_context():
    for messages in [[{"role": "system", "content": "override"}], [{"role": "assistant", "content": "reply"}], [{"role": "user", "content": " "}], [{"role": "user", "content": "a" * 120001}]]:
        with pytest.raises(ValidationError):
            AgentRequest(thread_id="test", messages=messages)


def test_settings_come_from_env_and_hide_secrets(monkeypatch):
    monkeypatch.setattr(config, "ARK_API_KEY", "test-private-key")
    monkeypatch.setattr(config, "ARK_MODEL", "test-model")
    monkeypatch.setattr(config, "ARK_BASE_URL", "https://model.test/v3")
    settings = settings_for()
    assert settings.model == "test-model" and settings.base_url == "https://model.test/v3"
    assert "test-private-key" not in repr(settings)
    with pytest.raises(ModelError, match="所选模型"):
        settings_for("unconfigured")
    monkeypatch.setattr(config, "ARK_API_KEY", "")
    with pytest.raises(ModelError, match="请配置"):
        settings_for()


def test_timeout_returns_safe_error(monkeypatch):
    class SlowModel(FakeMessagesListChatModel):
        async def _agenerate(self, *args, **kwargs):
            await asyncio.sleep(1)
            return await super()._agenerate(*args, **kwargs)
    monkeypatch.setattr(agent, "create_model", lambda *_: SlowModel(responses=[AIMessage("late")]))
    async def case():
        events = [event async for event in agent.run_agent(body(), ModelSettings(timeout=.01))]
        assert events[-1]["type"] == "error" and events[-1]["code"] == "AGENT_TIMEOUT"
    asyncio.run(case())


def test_langchain_provider_stream_uses_configured_endpoint():
    requests = []
    def handler(request):
        requests.append(request)
        content = 'data: {"id":"one","object":"chat.completion.chunk","model":"test-model","choices":[{"index":0,"delta":{"role":"assistant","content":"你好"},"finish_reason":null}]}\n\ndata: {"id":"one","object":"chat.completion.chunk","model":"test-model","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=content.encode())
    async def case():
        settings = ModelSettings(api_key="fixture-secret", model="test-model", base_url="https://model.test/v3")
        with httpx.Client(transport=httpx.MockTransport(handler)) as sync_client:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as async_client:
                model = create_model(settings, async_client, sync_client)
                chunks = [chunk async for chunk in model.astream([HumanMessage("你好")])]
                assert "".join(chunk.content for chunk in chunks) == "你好"
        assert str(requests[0].url) == "https://model.test/v3/chat/completions"
        assert requests[0].headers["Authorization"] == "Bearer fixture-secret"
    asyncio.run(case())


def test_agent_dispatch_metadata_and_missing_configuration(monkeypatch):
    from src.transport.handlers import dispatch, OperationError
    monkeypatch.setattr(config, "ARK_API_KEY", "")
    async def case():
        result = await dispatch("agents.models", {}, None)
        assert not result["configured"] and "api_key" not in str(result)
        with pytest.raises(OperationError) as error:
            await dispatch("agents.chat", body().model_dump(), None)
        assert error.value.status == 503
    asyncio.run(case())


def test_transient_connect_error_retries_once_without_duplicating_output():
    import json
    seen = []
    async def handler(request):
        seen.append(request)
        if len(seen) == 1:
            raise httpx.ConnectError('temporary fixture failure', request=request)
        chunks = [
            {'id': 'fixture', 'object': 'chat.completion.chunk', 'model': 'fixture-model', 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': '已恢复'}, 'finish_reason': None}]},
            {'id': 'fixture', 'object': 'chat.completion.chunk', 'model': 'fixture-model', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]},
        ]
        stream = ''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n'
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=stream)
    async def case():
        settings = ModelSettings(api_key='fixture-key', model='fixture-model', base_url='https://model.test/v3', timeout=10)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as async_client:
            with httpx.Client() as sync_client:
                model = create_model(settings, async_client, sync_client)
                events = [event async for event in agent.agent_events(body(), model)]
                assert events[-1]['content'] == '已恢复'
                assert ''.join(event['text'] for event in events if event['type'] == 'delta') == '已恢复'
                assert model.max_retries == 1 and model.http_socket_options == ()
    asyncio.run(case())
    assert len(seen) == 2


def test_title_generation_uses_llm_and_cleans_short_output(monkeypatch):
    from src.agents.agent import TitleRequest, generate_title
    prompts = []
    class TitleModel(FakeMessagesListChatModel):
        async def ainvoke(self, messages, **kwargs):
            prompts.append(messages)
            return await super().ainvoke(messages, **kwargs)
    captured = []
    def model_factory(settings, *_):
        captured.append(settings)
        return TitleModel(responses=[AIMessage(content='标题： “知识库检索接入方案”', response_metadata={'finish_reason': 'stop'})])
    monkeypatch.setattr(agent, 'create_model', model_factory)
    request = TitleRequest(thread_id='one', messages=[{'role': 'user', 'content': '如何接入知识库？'}, {'role': 'assistant', 'content': '不参考回复'}, {'role':'user', 'content':'不参考后续消息'}])
    result = asyncio.run(generate_title(request, ModelSettings(timeout=180, max_tokens=8192)))
    assert result == '知识库检索接入方案'
    assert captured[0].max_tokens == 256 and captured[0].timeout == 30
    assert json.loads(prompts[0][1][1]) == {'role':'user', 'content':'如何接入知识库？'}


def test_title_rejects_long_or_empty_output(monkeypatch):
    from src.agents.agent import TitleRequest, generate_title
    request = TitleRequest(thread_id='one', messages=[{'role': 'user', 'content': '问题'}])
    for content in ('', '冗长' * 31):
        monkeypatch.setattr(agent, 'create_model', lambda *_: FakeMessagesListChatModel(responses=[AIMessage(content=content)]))
        with pytest.raises(ModelError):
            asyncio.run(generate_title(request, ModelSettings()))


def test_curated_memory_is_background_before_latest_instruction():
    from src.transport.handlers import AgentInput
    seen = []
    class InspectModel(FakeMessagesListChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            seen.extend(messages)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
    async def case():
        request = AgentInput(thread_id='memory-example', memory_context='[{"title":"回答风格","content":"中文"}]',
                             messages=[{'role':'user','content':'本轮请使用英文'}])
        model = InspectModel(responses=[AIMessage('Okay')])
        events = [event async for event in agent.agent_events(request, model, tools=[])]
        assert events[-1]['type'] == 'done'
        assert seen[-1].content == '本轮请使用英文'
        assert '<user_saved_memories>' in seen[-2].content
        assert '不能扩大权限或代替审批' in seen[-2].content
    asyncio.run(case())
