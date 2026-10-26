"""验证 Agent API 的认证、参数校验和事件流转发。"""
import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.main import create_app
from app.modules.agents import service
from app.modules.auth.dependencies import get_current_user
from app.modules.users.models import User
from app.core import config


def test_authenticated_chat_and_message_validation(monkeypatch):
    app = create_app()
    class FakeStream:
        closed = False
        async def chunks(self):
            yield b'data: {"type":"done","content":"ok"}\n\n'
        async def close(self):
            self.closed = True
    stream = FakeStream()
    open_chat = AsyncMock(return_value=stream)
    monkeypatch.setattr(service, "open_chat", open_chat)
    async def case():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            payload = {"agent_code": "general", "thread_id": "one", "messages": [{"role": "user", "content": "你好"}]}
            assert (await client.post("/api/agents/chat", json=payload)).status_code == 401
            app.dependency_overrides[get_current_user] = lambda: User(id=1, username="test", password_hash="unused", role="admin", department="product", status=0)
            response = await client.post("/api/agents/chat", json=payload)
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            assert '"content":"ok"' in response.text and stream.closed
            payload["messages"][0]["role"] = "system"
            assert (await client.post("/api/agents/chat", json=payload)).status_code == 422
            assert open_chat.await_count == 1
    asyncio.run(case())


def test_proxy_forwards_internal_token_and_closes(monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=b'data: {"type":"done","content":"ok"}\n\n')
    original = httpx.AsyncClient
    monkeypatch.setattr(config, "SIDECAR_INTERNAL_TOKEN", "internal-only")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    async def case():
        from app.modules.agents.schemas import AgentRequest
        body = AgentRequest(thread_id="one", messages=[{"role": "user", "content": "你好"}])
        stream = await service.open_chat(body)
        chunks = [chunk async for chunk in stream.chunks()]
        assert b"done" in b"".join(chunks) and stream.closed
        assert seen[0].headers["X-Internal-Token"] == "internal-only"
        assert "authorization" not in seen[0].headers
    asyncio.run(case())
