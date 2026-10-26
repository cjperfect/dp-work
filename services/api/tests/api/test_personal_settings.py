"""配置协议不接受任意内网地址或前端注入执行凭证。"""
import pytest
from pydantic import ValidationError
from app.modules.settings.schemas import ServiceConfig
from app.modules.agents.schemas import AgentRequest


def test_personal_endpoints_restrict_targets_and_keep_keys_out_of_repr():
    valid = {"provider": "ark", "enabled": True, "base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "model", "api_key": "secret-fixture"}
    assert "secret-fixture" not in repr(ServiceConfig(**valid))
    for url in ("http://127.0.0.1", "https://127.0.0.1", "https://ark.cn-beijing.volces.com.evil.test", "https://user:pass@ark.cn-beijing.volces.com", "https://ark.cn-beijing.volces.com?key=abc", "https://ark.cn-beijing.volces.com:8000"):
        with pytest.raises(ValidationError):
            ServiceConfig(**{**valid, "base_url": url})
    with pytest.raises(ValidationError):
        AgentRequest(thread_id="one", messages=[{"role": "user", "content": "hi"}], runtime={"api_key": "injected"})
