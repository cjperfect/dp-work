"""托管 Sidecar 退出监测不会影响手动启动的服务。"""
import asyncio
import signal
import pytest
from fastapi.testclient import TestClient
from src.infrastructure import parent_watch
from src.main import app


def test_missing_parent_requests_self_shutdown(monkeypatch):
    signals = []
    monkeypatch.setattr(parent_watch, 'parent_alive', lambda _: False)
    monkeypatch.setattr(parent_watch.os, 'kill', lambda pid, sig: signals.append((pid, sig)))
    asyncio.run(parent_watch.watch_parent(12345, interval=.001))
    assert signals == [(parent_watch.os.getpid(), signal.SIGTERM)]


def test_live_parent_and_unmanaged_mode_do_not_stop_service(monkeypatch):
    monkeypatch.setattr(parent_watch, 'parent_alive', lambda _: True)
    monkeypatch.setattr(parent_watch.os, 'kill', lambda *_: pytest.fail('不应终止服务'))
    async def case():
        await parent_watch.watch_parent(0, interval=.001)
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(.02):
                await parent_watch.watch_parent(12345, interval=.001)
    asyncio.run(case())


def test_health_identifies_service_and_owned_instance(monkeypatch):
    monkeypatch.delenv('DP_SIDECAR_PARENT_PID', raising=False)
    monkeypatch.setenv('DP_SIDECAR_INSTANCE_ID', 'fixture-instance')
    with TestClient(app) as client:
        result = client.get('/health').json()
        assert result['service'] == 'dp-work-sidecar' and result['instance_id'] == 'fixture-instance'
        assert 'api_key' not in result and result['ok'] is True
