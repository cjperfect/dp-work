"""启动初始化失败也应释放数据库资源。"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from src.lifespan import lifespan
from src.modules.users import bootstrap
from fastapi import FastAPI


def test_disabled_bootstrap_does_not_access_users(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(bootstrap.config, "BOOTSTRAP_ADMIN_ENABLED", False)
    monkeypatch.setattr(bootstrap.service, "create_user", create)
    asyncio.run(bootstrap.ensure_initial_admin())
    create.assert_not_awaited()


def test_bootstrap_failure_closes_pool(monkeypatch):
    import importlib

    module = importlib.import_module("src.lifespan")
    init, close = AsyncMock(), AsyncMock()
    monkeypatch.setattr(module.session, "init_db", init)
    monkeypatch.setattr(module.session, "close_db", close)
    monkeypatch.setattr(
        module,
        "ensure_initial_admin",
        AsyncMock(side_effect=RuntimeError("seed failed")),
    )

    async def case():
        with pytest.raises(RuntimeError, match="seed failed"):
            async with lifespan(FastAPI()):
                pytest.fail("初始化失败时不应启动服务")

    asyncio.run(case())
    init.assert_awaited_once()
    close.assert_awaited_once()
