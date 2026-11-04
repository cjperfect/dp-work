"""配置优先级、兼容 CORS 格式以及无效配置的启动校验。"""

import pytest
from pydantic import ValidationError
from src.core.config import Settings


def test_environment_overrides_dotenv_and_cors_accepts_existing_format(
    monkeypatch, tmp_path
):
    env = tmp_path / ".env"
    env.write_text(
        "JWT_TTL_SECONDS=100\nCORS_ORIGINS=https://one.test, https://two.test\nIGNORED_EXTENSION=value\n"
    )
    monkeypatch.setenv("JWT_TTL_SECONDS", "200")
    value = Settings(_env_file=env)
    assert value.JWT_TTL_SECONDS == 200
    assert value.CORS_ORIGINS == ["https://one.test", "https://two.test"]
    assert Settings(
        _env_file=None, CORS_ORIGINS='["https://one.test"]'
    ).CORS_ORIGINS == ["https://one.test"]


def test_invalid_settings_are_rejected_without_echoing_input():
    for kwargs in (
        {"REDIS_IP_RPM": -1},
        {"SIDECAR_TRANSPORT": "invalid"},
        {"MINUTES_TASK_TIMEOUT": 0},
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **kwargs)
    with pytest.raises(ValidationError) as cause:
        Settings(_env_file=None, JWT_TTL_SECONDS="private-fixture")
    assert "private-fixture" not in str(cause.value)
    assert "private-key" not in repr(Settings(_env_file=None, JWT_SECRET="private-key"))
