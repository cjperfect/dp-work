"""Sidecar 配置解析与 SDK 环境桥接之外的业务设置保持独立。"""

import pytest
from pydantic import ValidationError
from src.config import Settings


def test_config_types_paths_and_model_tiers(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "ARK_MODEL_LITE=light\nARK_MODEL_DEFAULT=default\nARK_BASE_URL=https://model.test/v3/\nMEMORY_AUTO_ENABLED=false\n"
    )
    monkeypatch.setenv("ARK_MODEL_LITE", "override")
    value = Settings(_env_file=env)
    assert value.ARK_MODEL_LITE == "override"
    assert value.ARK_MODEL_DEFAULT == "default"
    assert value.ARK_BASE_URL == "https://model.test/v3"
    assert value.MEMORY_AUTO_ENABLED is False
    assert "private-key" not in repr(
        Settings(_env_file=None, ARK_API_KEY="private-key")
    )


def test_config_rejects_invalid_ranges_and_types():
    for kwargs in (
        {"PORT": 80},
        {"MEMORY_BATCH_SIZE": 100},
        {"REDIS_MODEL_RPM": -1},
        {"ARK_TIMEOUT_SECONDS": 0},
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **kwargs)
