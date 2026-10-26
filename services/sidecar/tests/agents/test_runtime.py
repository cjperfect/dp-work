"""LangGraph 基础对话与工具循环使用本地模型替身。"""
import asyncio
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
from src.main import app


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


def test_internal_agent_auth_and_metadata(monkeypatch):
    monkeypatch.setattr(config, "SIDECAR_INTERNAL_TOKEN", "test-internal")
    monkeypatch.setattr(config, "ARK_API_KEY", "")
    async def case():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sidecar") as client:
            assert (await client.get("/internal/agents/models")).status_code == 401
            result = await client.get("/internal/agents/models", headers={"X-Internal-Token": "test-internal"})
            assert result.status_code == 200 and not result.json()["configured"]
            assert "api_key" not in result.text
            response = await client.post("/internal/agents/chat", headers={"X-Internal-Token": "test-internal"}, json=body().model_dump())
            assert response.status_code == 503
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
