"""普通测试不连接开发机 Redis，专项测试显式启用独立命名空间。"""
import pytest
from src import config


@pytest.fixture(autouse=True)
def isolate_redis(monkeypatch):
    monkeypatch.setattr(config, 'REDIS_URL', '')
