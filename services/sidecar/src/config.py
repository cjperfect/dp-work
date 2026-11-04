"""由 Pydantic Settings 加载环境配置，启动时校验类型与范围。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from pydantic import AfterValidator, Field, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]


CleanStr = Annotated[str, StringConstraints(strip_whitespace=True)]
ServiceUrl = Annotated[str, AfterValidator(lambda value: value.rstrip("/"))]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("DP_SIDECAR_ENV_FILE") or SERVICE_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    LANGSMITH_API_KEY: str = Field(default="", repr=False)
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_TRACING: bool = False
    DP_DATA_DIR: str = ""
    VOLC_BASE_URL: CleanStr = (
        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
    )
    VOLC_API_KEY: CleanStr = Field(default="", repr=False)
    VOLC_RESOURCE_ID: str = "volc.seedasr.sauc.duration"
    VOLC_SPEAKER_INFO: bool = True
    PORT: int = Field(default=8001, ge=1024, le=65535)
    ARK_API_KEY: CleanStr = Field(default="", repr=False)
    ARK_MODEL: CleanStr = ""
    ARK_MODEL_LITE: CleanStr = ""
    ARK_MODEL_DEFAULT: CleanStr = ""
    ARK_MODEL_STRONG: CleanStr = ""
    ARK_BASE_URL: ServiceUrl = ""
    ARK_TIMEOUT_SECONDS: float = Field(default=180.0, gt=0)
    ARK_MAX_TOKENS: int = Field(default=8192, gt=0)
    MINUTES_MAX_INPUT_CHARS: int = Field(default=120000, gt=0)
    SIDECAR_INTERNAL_TOKEN: CleanStr = Field(default="", repr=False)
    PDF_PARSE_TIMEOUT: float = Field(default=90.0, gt=0)
    BAIDU_OCR_API_KEY: CleanStr = Field(default="", repr=False)
    BAIDU_OCR_SECRET_KEY: CleanStr = Field(default="", repr=False)
    BAIDU_OCR_TIMEOUT_SECONDS: float = Field(default=20.0, ge=1)
    BAIDU_OCR_MAX_PAGES: int = Field(default=20, ge=1, le=200)
    AGENT_MAX_STEPS: int = Field(default=12, gt=0)
    AGENT_REPEAT_LIMIT: int = Field(default=3, ge=1)
    AGENT_TOOL_ERROR_LIMIT: int = Field(default=5, ge=1)
    AGENT_SANDBOX_IMAGE: CleanStr = ""
    AGENT_RUN_TOKEN_LIMIT: int = Field(default=0, ge=0, repr=False)
    AGENT_RUN_COST_LIMIT: str = "0"
    AGENT_COST_CURRENCY: Annotated[str, AfterValidator(str.upper)] = "CNY"
    AGENT_MODEL_PRICES: str = "{}"
    MEMORY_AUTO_ENABLED: bool = True
    MEMORY_IDLE_HOURS: float = Field(default=6.0, ge=0.01)
    MEMORY_SCAN_SECONDS: float = Field(default=60.0, ge=10)
    MEMORY_MAX_AGE_DAYS: int = Field(default=30, ge=1, le=90)
    MEMORY_BATCH_SIZE: int = Field(default=4, ge=1, le=16)
    MEMORY_EXTRACT_MODEL: CleanStr = ""
    MEMORY_CONSOLIDATION_MODEL: CleanStr = ""
    EMBEDDING_API_KEY: CleanStr = Field(default="", repr=False)
    EMBEDDING_MODEL: CleanStr = "doubao-embedding-vision-251215"
    EMBEDDING_BASE_URL: ServiceUrl = "https://ark.cn-beijing.volces.com/api/v3"
    EMBEDDING_DIMENSIONS: int = Field(default=1024, gt=0)
    EMBEDDING_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    API_INTERNAL_URL: ServiceUrl = "http://127.0.0.1:8000"
    MEMORY_MIN_SIMILARITY: float = Field(default=0.25, ge=-1.0, le=1.0)
    MEMORY_RETRIEVAL_TIMEOUT_SECONDS: float = Field(default=10.0, ge=1)
    ASR_PRICE_PER_HOUR: CleanStr = ""
    REDIS_URL: CleanStr = Field(default="", repr=False)
    REDIS_PREFIX: str = "dp-work"
    REDIS_TIMEOUT_SECONDS: float = Field(default=0.3, ge=0.05)
    REDIS_MODEL_RPM: int = Field(default=120, ge=0)
    REDIS_MODEL_USER_RPM: int = Field(default=60, ge=0)
    REDIS_LIMIT_FAIL_OPEN: bool = False
    REDIS_CACHE_TTL_SECONDS: int = Field(default=300, ge=0)


settings = Settings()
# 保留模块级配置入口，避免改变业务调用及测试中的配置覆盖方式。
globals().update(settings.model_dump())

DATA_ROOT = (
    Path(settings.DP_DATA_DIR).parent
    if settings.DP_DATA_DIR
    else REPO_ROOT / ".dp-work"
)
TEMP_DIR = DATA_ROOT / "temp"
WORKSPACE_DIR = DATA_ROOT / "workspace"

# LangSmith SDK 从环境读取配置；只导出已验证设置，不覆盖显式进程环境。
for _name in ("LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT", "LANGSMITH_TRACING"):
    _value = getattr(settings, _name)
    if _value != "":
        os.environ.setdefault(
            _name, str(_value).lower() if isinstance(_value, bool) else _value
        )
