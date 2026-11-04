"""由 Pydantic Settings 加载环境配置，启动时校验类型与范围。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Literal
from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    StringConstraints,
    field_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[2]


CleanStr = Annotated[str, StringConstraints(strip_whitespace=True)]
ServiceUrl = Annotated[str, AfterValidator(lambda value: value.rstrip("/"))]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SERVICE_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://chenjiang:chenjiang@127.0.0.1:5432/dp_work",
        repr=False,
    )
    JWT_SECRET: str = Field(default="dp-dev-insecure-secret-change-me", repr=False)
    JWT_ALG: str = "HS256"
    JWT_TTL_SECONDS: int = Field(default=604800, gt=0)
    BOOTSTRAP_ADMIN_ENABLED: bool = True
    BOOTSTRAP_ADMIN_USERNAME: str = "chenjiang"
    BOOTSTRAP_ADMIN_PASSWORD: str = Field(default="chenjiang", repr=False)
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3300",
        "http://127.0.0.1:3300",
        "http://127.0.0.1:34731",
        "http://localhost:34731",
    ]
    CREDENTIAL_PRIVATE_KEY_FILE: str = str(
        Path(__file__).resolve().parents[4] / ".dp-work/keys/auth-transport.pem"
    )
    SIDECAR_TRANSPORT: Annotated[
        Literal["http", "device"], BeforeValidator(str.strip)
    ] = "http"
    SIDECAR_API_URL: ServiceUrl = "http://127.0.0.1:8001"
    SIDECAR_INTERNAL_TOKEN: CleanStr = Field(default="", repr=False)
    MINUTES_TASK_TIMEOUT: float = Field(default=210.0, gt=0)
    MINUTES_WORKER_ENABLED: bool = True
    DOCUMENT_PARSE_WORKER_ENABLED: bool = True
    DOCUMENT_PARSE_TIMEOUT: float = Field(default=1200.0, gt=0)
    AGENT_REQUEST_TIMEOUT: float = Field(default=210.0, gt=0)
    DOCUMENT_VECTOR_WORKER_ENABLED: bool = True
    ELASTICSEARCH_ENABLED: bool = True
    ELASTICSEARCH_URL: ServiceUrl = "http://127.0.0.1:9200"
    ELASTICSEARCH_INDEX: str = "dp-work-knowledge-v1"
    ELASTICSEARCH_API_KEY: CleanStr = Field(default="", repr=False)
    ELASTICSEARCH_USERNAME: CleanStr = ""
    ELASTICSEARCH_PASSWORD: str = Field(default="", repr=False)
    ELASTICSEARCH_CA_FILE: CleanStr = ""
    ELASTICSEARCH_TIMEOUT: float = Field(default=5.0, gt=0)
    RAG_HYBRID_CANDIDATES: int = Field(default=50, gt=0)
    RAG_RRF_CONSTANT: int = Field(default=60, gt=0)
    MQ_BROKER_URL: str = Field(
        default="amqp://chenjiang:chenjiang@127.0.0.1:5672/dp-work", repr=False
    )
    MQ_DISPATCH_ENABLED: bool = True
    MQ_REDELIVERY_SECONDS: int = Field(default=300, ge=30)
    MQ_TASK_TIME_LIMIT: int = Field(default=3600, gt=0)
    MQ_MINUTES_CONCURRENCY: int = Field(default=2, gt=0)
    MQ_PARSE_CONCURRENCY: int = Field(default=2, gt=0)
    MQ_VECTOR_CONCURRENCY: int = Field(default=2, gt=0)
    MQ_SEARCH_CONCURRENCY: int = Field(default=1, gt=0)
    MQ_WORKER_POOL: str = "solo" if sys.platform == "darwin" else "prefork"
    REDIS_URL: CleanStr = Field(default="", repr=False)
    REDIS_PREFIX: str = "dp-work"
    REDIS_TIMEOUT_SECONDS: float = Field(default=0.3, ge=0.05)
    REDIS_IP_RPM: int = Field(default=600, ge=0)
    REDIS_USER_RPM: int = Field(default=300, ge=0)
    REDIS_LIMIT_FAIL_OPEN: bool = False
    REDIS_PUBSUB_ENABLED: bool = True

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def cors_origins(cls, value):
        if isinstance(value, str):
            import json

            value = (
                json.loads(value)
                if value.lstrip().startswith("[")
                else value.split(",")
            )
        return [item.strip() for item in value if item.strip()]

    @field_validator("MQ_WORKER_POOL")
    @classmethod
    def worker_pool(cls, value):
        return value or ("solo" if sys.platform == "darwin" else "prefork")


settings = Settings()
# 保留模块级配置入口，避免改变业务调用及测试中的配置覆盖方式。
globals().update(settings.model_dump())
