"""API 配置：环境变量读取，集中收口（对齐根 README 与 docker-compose 默认值）。

环境变量来源 = 本服务目录 services/api/.env（python-dotenv 加载，不覆盖进程内已设置的
变量，因此 docker exec / 显式 export 的方式仍然可用）。变量按子包单独管理。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 本服务目录：services/api/src/core/config.py → parents[2]
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# ---- 数据库 ----
# PostgreSQL 业务数据库；生产环境通过 DATABASE_URL 指定连接信息
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://chenjiang:chenjiang@127.0.0.1:5432/dp_work",
)

# ---- 认证 / JWT ----
JWT_SECRET = os.environ.get("JWT_SECRET", "dp-dev-insecure-secret-change-me")
JWT_ALG = os.environ.get("JWT_ALG", "HS256")
JWT_TTL_SECONDS = int(os.environ.get("JWT_TTL_SECONDS", "604800"))  # 一周

# ---- 初始管理员（只创建，不重置已有账号） ----
BOOTSTRAP_ADMIN_ENABLED = os.environ.get("BOOTSTRAP_ADMIN_ENABLED", "1") == "1"
BOOTSTRAP_ADMIN_USERNAME = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "chenjiang")
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "chenjiang")

# ---- CORS ----
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3300,http://127.0.0.1:3300,http://127.0.0.1:34731,http://localhost:34731",
    ).split(",")
    if o.strip()
]

# RSA 私钥仅供服务端保存；多实例部署必须挂载同一份私钥。
CREDENTIAL_PRIVATE_KEY_FILE = os.environ.get(
    "CREDENTIAL_PRIVATE_KEY_FILE",
    str(Path(__file__).resolve().parents[4] / ".dp-work/keys/auth-transport.pem"),
)

# ---- 执行服务：device 为用户本机反向连接，http 仅供集中式开发兼容 ----
SIDECAR_TRANSPORT = os.environ.get("SIDECAR_TRANSPORT", "http").strip()
if SIDECAR_TRANSPORT not in ("http", "device"):
    raise ValueError("SIDECAR_TRANSPORT 必须为 http 或 device")

# ---- 会议纪要生成执行服务 ----
SIDECAR_API_URL = os.environ.get("SIDECAR_API_URL", "http://127.0.0.1:8001").rstrip("/")
SIDECAR_INTERNAL_TOKEN = os.environ.get("SIDECAR_INTERNAL_TOKEN", "").strip()
MINUTES_TASK_TIMEOUT = float(os.environ.get("MINUTES_TASK_TIMEOUT", "210"))
MINUTES_WORKER_ENABLED = os.environ.get("MINUTES_WORKER_ENABLED", "1") == "1"

# ---- 文档解析任务 ----
DOCUMENT_PARSE_WORKER_ENABLED = os.environ.get("DOCUMENT_PARSE_WORKER_ENABLED", "1") == "1"
DOCUMENT_PARSE_TIMEOUT = float(os.environ.get("DOCUMENT_PARSE_TIMEOUT", "1200"))

# Agent 流式请求的最长等待秒数，应大于 Sidecar 模型调用总超时。
AGENT_REQUEST_TIMEOUT = float(os.environ.get("AGENT_REQUEST_TIMEOUT", "210"))

# 是否允许独立 MQ Worker 执行知识库向量化任务；进度保存在 PostgreSQL。
DOCUMENT_VECTOR_WORKER_ENABLED = os.environ.get("DOCUMENT_VECTOR_WORKER_ENABLED", "1") == "1"

# ---- Elasticsearch 关键词检索与混合召回 ----
ELASTICSEARCH_ENABLED = os.environ.get("ELASTICSEARCH_ENABLED", "1") == "1"
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://127.0.0.1:9200").rstrip("/")
ELASTICSEARCH_INDEX = os.environ.get("ELASTICSEARCH_INDEX", "dp-work-knowledge-v1")
ELASTICSEARCH_API_KEY = os.environ.get("ELASTICSEARCH_API_KEY", "").strip()
ELASTICSEARCH_USERNAME = os.environ.get("ELASTICSEARCH_USERNAME", "").strip()
ELASTICSEARCH_PASSWORD = os.environ.get("ELASTICSEARCH_PASSWORD", "")
ELASTICSEARCH_CA_FILE = os.environ.get("ELASTICSEARCH_CA_FILE", "").strip()
ELASTICSEARCH_TIMEOUT = float(os.environ.get("ELASTICSEARCH_TIMEOUT", "5"))
RAG_HYBRID_CANDIDATES = int(os.environ.get("RAG_HYBRID_CANDIDATES", "50"))
RAG_RRF_CONSTANT = int(os.environ.get("RAG_RRF_CONSTANT", "60"))

# ---- RabbitMQ / Celery ----
# AMQP 地址仅供 API 和独立 Worker 使用，生产环境设置专用账号及 TLS。
MQ_BROKER_URL = os.environ.get("MQ_BROKER_URL", "amqp://chenjiang:chenjiang@127.0.0.1:5672/dp-work")
# API 是否运行可靠投递器；关闭后仍会保留 PG 待投递消息。
MQ_DISPATCH_ENABLED = os.environ.get("MQ_DISPATCH_ENABLED", "1") == "1"
# 已投递但未完成的消息补投间隔，重复消息由业务租约与版本校验去重。
MQ_REDELIVERY_SECONDS = max(30, int(os.environ.get("MQ_REDELIVERY_SECONDS", "300")))
# 单任务进程硬超时，超时后由租约恢复；需覆盖大文档向量化时间。
MQ_TASK_TIME_LIMIT = int(os.environ.get("MQ_TASK_TIME_LIMIT", "3600"))
# 四类 Worker 的独立并发数，每个 Worker 只消费自己的队列。
MQ_MINUTES_CONCURRENCY = int(os.environ.get("MQ_MINUTES_CONCURRENCY", "2"))
MQ_PARSE_CONCURRENCY = int(os.environ.get("MQ_PARSE_CONCURRENCY", "2"))
MQ_VECTOR_CONCURRENCY = int(os.environ.get("MQ_VECTOR_CONCURRENCY", "2"))
MQ_SEARCH_CONCURRENCY = int(os.environ.get("MQ_SEARCH_CONCURRENCY", "1"))

# macOS 使用多组 solo 进程，避开 Celery 与 spawn 的兼容问题；Linux 使用 prefork。
MQ_WORKER_POOL = os.environ.get("MQ_WORKER_POOL", "").strip() or ("solo" if sys.platform == "darwin" else "prefork")
