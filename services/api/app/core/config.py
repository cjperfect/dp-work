"""API 配置：环境变量读取，集中收口（对齐根 README 与 docker-compose 默认值）。

环境变量来源 = 本服务目录 services/api/.env（python-dotenv 加载，不覆盖进程内已设置的
变量，因此 docker exec / 显式 export 的方式仍然可用）。变量按子包单独管理。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 本服务目录：services/api/app/core/config.py → parents[2]
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
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3300,http://127.0.0.1:3300",
    ).split(",")
    if o.strip()
]

# RSA 私钥仅供服务端保存；多实例部署必须挂载同一份私钥。
CREDENTIAL_PRIVATE_KEY_FILE = os.environ.get(
    "CREDENTIAL_PRIVATE_KEY_FILE",
    str(Path(__file__).resolve().parents[4] / ".dp-work/keys/auth-transport.pem"),
)

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

# 是否运行知识库向量化任务；队列与进度保存在 PostgreSQL。
DOCUMENT_VECTOR_WORKER_ENABLED = os.environ.get("DOCUMENT_VECTOR_WORKER_ENABLED", "1") == "1"
