"""个人模型覆盖与连接测试不依赖真实云服务。"""
import asyncio
from unittest.mock import AsyncMock
import httpx
import pytest
from pydantic import ValidationError
from src.providers import settings
from src.providers.settings import RuntimeConfig
from src.transport import internal
from src.agents.agent import AgentRequest
from src import config
from src.main import app
from fastapi.testclient import TestClient


def runtime(**changes):
    return RuntimeConfig(provider="deepseek", base_url="https://api.deepseek.com", model="personal-model", api_key="private-fixture", **changes)


def test_runtime_validation_and_model_conversion():
    value = runtime()
    assert value.llm().model == "personal-model"
    assert "private-fixture" not in repr(value)
    with pytest.raises(ValueError):
        value.asr()
    with pytest.raises(ValidationError):
        RuntimeConfig(provider="openai", base_url="https://127.0.0.1", model="test", api_key="key")


def test_personal_model_is_used_without_overwriting_global(monkeypatch):
    seen = []
    async def runner(body, resolved):
        seen.append(resolved)
        yield {"type": "done", "content": "fixture", "model": resolved.model}
    monkeypatch.setattr(config, "SIDECAR_INTERNAL_TOKEN", "fixture-token")
    monkeypatch.setattr(internal, "run_agent", runner)
    async def case():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            body = {"thread_id": "one", "messages": [{"role": "user", "content": "hi"}], "runtime": {"provider": "deepseek", "base_url": "https://api.deepseek.com", "model": "personal-model", "api_key": "private-fixture"}}
            assert (await client.post("/internal/agents/chat", json=body)).status_code == 401
            response = await client.post("/internal/agents/chat", json=body, headers={"X-Internal-Token": "fixture-token"})
            assert response.status_code == 200 and "personal-model" in response.text
            assert "private-fixture" not in response.text
            assert seen[0].api_key == "private-fixture"
    original = config.ARK_MODEL
    asyncio.run(case())
    assert config.ARK_MODEL == original


def test_connection_checks_real_response_and_hides_upstream_error(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(401, json={"error": "private-fixture"})
    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(settings.test_connection("model", runtime()))
    assert not result["ok"] and "401" in result["message"]
    assert "private-fixture" not in str(result)
    assert requests[0].headers["Authorization"] == "Bearer private-fixture"


def test_asr_tickets_are_one_time_and_bound_to_meeting(monkeypatch):
    monkeypatch.setattr(config, "SIDECAR_INTERNAL_TOKEN", "fixture-token")
    with TestClient(app) as client:
        assert client.post("/internal/asr/sessions", json={"owner_id": 1, "meeting_id": "one"}).status_code == 401
        response = client.post("/internal/asr/sessions", json={"owner_id": 1, "meeting_id": "one"}, headers={"X-Internal-Token": "fixture-token"})
        ticket = response.json()["ticket"]
        assert ticket in app.state.asr_tickets
        # 错误会议不能使用此票据，且票据立即销毁。
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "asr.start", "meetingId": "other", "requestId": "one", "ticket": ticket,
                "nextSeq": 0, "offsetMs": 0, "audio": {"format": "pcm", "sampleRate": 16000, "channels": 1, "bitsPerSample": 16}})
            assert ws.receive_json()["code"] == "INVALID_TICKET"
        assert ticket not in app.state.asr_tickets


def test_asr_ticket_uses_personal_credentials_without_exposing_them(monkeypatch, tmp_path):
    from src.transport import websocket
    from src.meetings import repository
    from tests.transport.test_asr_websocket import TestRecognizer as FakeRecognizer
    seen = []
    def recognizer(value):
        seen.append(value)
        return FakeRecognizer()
    monkeypatch.setattr(config, "SIDECAR_INTERNAL_TOKEN", "fixture-token")
    monkeypatch.setattr(websocket, "DoubaoRecognizer", recognizer)
    monkeypatch.setattr(repository, "TEMP_DIR", tmp_path)
    with TestClient(app) as client:
        response = client.post("/internal/asr/sessions", json={"owner_id": 1, "meeting_id": "one", "runtime": {
            "provider": "doubao", "base_url": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async", "api_key": "personal-asr-fixture", "resource_id": "personal-resource", "speaker_info": False}},
            headers={"X-Internal-Token": "fixture-token"})
        assert "personal-asr-fixture" not in response.text
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "asr.start", "meetingId": "one", "requestId": "start", "ticket": response.json()["ticket"],
                "nextSeq": 0, "offsetMs": 0, "audio": {"format": "pcm", "sampleRate": 16000, "channels": 1, "bitsPerSample": 16}})
            message = ws.receive_json()
            assert message["type"] == "asr.ready" and "personal-asr-fixture" not in str(message)
        assert seen[0].api_key == "personal-asr-fixture" and not seen[0].speaker_info
        assert seen[0].resource_id == "personal-resource"
