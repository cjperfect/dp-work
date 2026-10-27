"""个人配置隔离与加密存储。"""
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from src.core.security import create_access_token
from src.core.exceptions import ApiError
from src.infrastructure.database import session
from src.main import create_app
from src.modules.settings import service
from src.modules.settings.models import UserSettings
from src.modules.settings.schemas import ServiceConfig
from src.modules.users import service as users
from src.modules.users.models import User

DEFAULTS = {"model": {"provider": "ark", "base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "default", "configured": True},
            "asr": {"provider": "doubao", "base_url": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async", "configured": True}}


def test_settings_isolation_encryption_and_runtime(monkeypatch):
    sidecar = AsyncMock(return_value=DEFAULTS)
    monkeypatch.setattr(service, "sidecar", sidecar)
    async def case():
        await session.init_db()
        owners = []
        try:
            for _ in range(2):
                owners.append(await users.create_user("settings-" + uuid4().hex, "old", "product"))
            owner, other = owners
            async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
                assert (await client.get("/api/settings")).status_code == 401
                headers = {"Authorization": "Bearer " + create_access_token(owner.id, owner.role, owner.department)}
                payload = {"provider": "deepseek", "enabled": True, "base_url": "https://api.deepseek.com", "model": "test-model", "api_key": "private-fixture-key"}
                response = await client.put("/api/settings/model", json=payload, headers=headers)
                assert response.status_code == 200
                response = await client.get("/api/settings", headers=headers)
                assert "private-fixture-key" not in response.text and "model_key" not in response.text
                assert response.json()["data"]["model"]["has_api_key"]
                assert (await service.runtime(owner.id, "model"))["api_key"] == "private-fixture-key"
                assert await service.runtime(other.id, "model") is None
                async with session.read_session() as conn:
                    saved = await conn.get(UserSettings, owner.id)
                    assert saved.model_key != "private-fixture-key" and "private-fixture-key" not in saved.model_key
                    encrypted = saved.model_key
                with pytest.raises(ValueError):
                    service.unseal(encrypted, other.id, "model")
                # 不提交密钥时保留；测试连接使用当前表单但不保存。
                payload.pop("api_key")
                switched = {**payload, "provider": "openai", "base_url": "https://api.openai.com/v1"}
                assert (await client.post("/api/settings/model/test", json=switched, headers=headers)).status_code == 400
                assert (await client.put("/api/settings/model", json=switched, headers=headers)).status_code == 400
                assert (await service.runtime(owner.id, "model"))["provider"] == "deepseek"
                payload["model"] = "changed"
                sidecar.return_value = {"ok": True, "message": "连接成功"}
                assert (await client.post("/api/settings/model/test", json=payload, headers=headers)).status_code == 200
                assert sidecar.call_args.args[1]["config"]["api_key"] == "private-fixture-key"
                assert (await service.runtime(owner.id, "model"))["model"] == "test-model"
                await client.put("/api/settings/model", json=payload, headers=headers)
                assert (await service.runtime(owner.id, "model"))["model"] == "changed"
                # 启用状态不能清空密钥；事务回滚后原配置仍在。
                payload["clear_api_key"] = True
                assert (await client.put("/api/settings/model", json=payload, headers=headers)).status_code == 400
                assert (await service.runtime(owner.id, "model"))["api_key"] == "private-fixture-key"
                payload["enabled"] = False
                assert (await client.put("/api/settings/model", json=payload, headers=headers)).status_code == 200
                assert await service.runtime(owner.id, "model") is None
        finally:
            async with session.transaction() as conn:
                await conn.execute(delete(User).where(User.id.in_([owner.id for owner in owners])))
            await session.close_db()
    asyncio.run(case())
